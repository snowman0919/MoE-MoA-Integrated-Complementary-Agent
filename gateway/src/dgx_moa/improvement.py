from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, cast

THRESHOLDS = {
    "target_failure_reduction": 0.30,
    "max_success_regression": 0.0,
    "max_token_increase": 0.10,
    "max_time_increase": 0.15,
}
DEFAULT_EVIDENCE_PRIORITY = {
    ("main", "production"): 100,
    ("candidate", "candidate_evaluation"): 60,
    ("dev", "validation"): 30,
    ("dev", "benchmark"): 10,
    ("dev", "diagnostic"): 0,
}


def _read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def statistics(
    result: dict[str, Any], priority: dict[tuple[str, str], int] | None = None
) -> dict[str, Any]:
    tasks = cast(list[dict[str, Any]], result.get("tasks", []))
    evidence_priority = priority or DEFAULT_EVIDENCE_PRIORITY
    excluded_statuses = {"resolved", "expected", "synthetic", "false_positive", "superseded"}
    failures = [
        item
        for task in tasks
        if task.get("resolution_status", "active") not in excluded_statuses
        for item in task.get("failure_classes", [])
    ]
    excluded_failures = [
        item
        for task in tasks
        if task.get("resolution_status") in excluded_statuses
        for item in task.get("failure_classes", [])
    ]
    known_tokens = [
        int(task["input_tokens"]) for task in tasks if isinstance(task.get("input_tokens"), int)
    ]
    failure_tasks = [
        task
        for task in tasks
        if task.get("failure_classes")
        and task.get("resolution_status", "active") not in excluded_statuses
    ]
    return {
        "failure_frequency": {item: failures.count(item) for item in sorted(set(failures))},
        "excluded_failure_frequency": {
            item: excluded_failures.count(item) for item in sorted(set(excluded_failures))
        },
        "failure_priority": {
            item: sum(
                evidence_priority.get(
                    (
                        str(task.get("runtime_channel", "dev")),
                        str(task.get("trace_origin", "benchmark")),
                    ),
                    0,
                )
                for task in tasks
                if item in task.get("failure_classes", [])
                and task.get("resolution_status", "active") not in excluded_statuses
            )
            for item in sorted(set(failures))
        },
        "failure_impact_tasks": sum(not task.get("task_success") for task in tasks),
        "token_waste": sum(known_tokens) if len(known_tokens) == len(tasks) else None,
        "time_waste_seconds": sum(float(task["wall_clock_seconds"]) for task in failure_tasks),
        "review_rejection_rate": (
            sum(int(task.get("reviewer_rejections", 0)) for task in tasks) / len(tasks)
            if tasks
            else 0
        ),
        "replan_rate": sum(int(task.get("replans", 0)) for task in tasks) / len(tasks)
        if tasks
        else 0,
        "route_inefficiency": None,
        "false_completion_rate": sum(
            bool(task.get("task_success")) and not bool(task.get("completion_evidence"))
            for task in tasks
        )
        / len(tasks)
        if tasks
        else 0,
        "profile_switch_failure_rate": None,
        "context_overflow_frequency": failures.count("CONTEXT_OVERFLOW"),
    }


def trace_tasks(directory: Path) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.rglob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line:
                trace = json.loads(line)
                if trace.get("schema_version") in {"agent-trace-v2", "agent-trace-v3"}:
                    latest[str(trace["session_id"])] = trace
    tasks = []
    for trace in latest.values():
        for failure in trace.get("failures", []):
            tasks.append(
                {
                    "task_success": trace.get("final_status") == "completed",
                    "wall_clock_seconds": 0,
                    "failure_classes": [failure.get("failure_class", "UNKNOWN")],
                    "resolution_status": failure.get("resolution_status", "unknown"),
                    "runtime_channel": trace.get("runtime_channel"),
                    "trace_origin": trace.get("trace_origin"),
                }
            )
    return tasks


def proposal_fingerprint(failure_class: str, affected: int, evidence: dict[str, Any]) -> str:
    payload = json.dumps(
        {"failure_class": failure_class, "affected": affected, "evidence": evidence},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def cooldown_active(previous: dict[str, Any], fingerprint: str) -> bool:
    return bool(previous) and previous.get("proposal_fingerprint") == fingerprint


def mine(benchmark: Path, output: Path) -> dict[str, Any]:
    result = {"tasks": trace_tasks(benchmark)} if benchmark.is_dir() else _read(benchmark)
    evidence = statistics(result)
    failures = evidence["failure_frequency"]
    failure_class, affected = max(
        failures.items(),
        key=lambda item: (evidence["failure_priority"].get(item[0], 0), item[1], item[0]),
        default=("NONE", 0),
    )
    evidence_summary = {
        "affected_tasks": affected,
        "failure_class": failure_class,
        "wasted_input_tokens": evidence["token_waste"],
        "wasted_seconds": evidence["time_waste_seconds"],
    }
    fingerprint = proposal_fingerprint(failure_class, affected, evidence_summary)
    previous = _read(output) if output.is_file() else {}
    proposal = {
        "schema_version": "improvement-proposal-v1",
        "proposal_id": "IMP-2026-0001",
        "title": f"Block {failure_class.lower()} earlier",
        "problem": f"{failure_class} appears in {affected} benchmark task(s).",
        "evidence": evidence_summary,
        "statistics": evidence,
        "suspected_layer": "controller",
        "proposed_change": (
            "Block normalized equivalent failed tool calls before another executor turn."
        ),
        "acceptance_criteria": [
            f"{failure_class} frequency decreases by at least 30 percent",
            "task success rate does not decrease",
        ],
        "risk": "low",
        "requires_human_approval": True,
        "proposal_fingerprint": fingerprint,
        "cooldown_active": affected > 0 and cooldown_active(previous, fingerprint),
        "status": "no_actionable_failure" if affected == 0 else "proposed",
        "priority": {"affected_tasks": affected, "risk": "low", "benchmark_coverage": affected},
    }
    if affected == 0:
        proposal.update(
            {
                "title": "No actionable failure",
                "problem": "All observed failures are resolved, expected, or synthetic.",
                "suspected_layer": "unknown",
                "proposed_change": None,
                "acceptance_criteria": [],
                "requires_human_approval": False,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    return proposal


def compare(baseline_path: Path, candidate_path: Path, output: Path) -> dict[str, Any]:
    baseline, candidate = _read(baseline_path)["summary"], _read(candidate_path)["summary"]
    target = "REPEATED_ACTION"
    before = baseline["failure_class_distribution"].get(target, 0)
    after = candidate["failure_class_distribution"].get(target, 0)
    reduction = (before - after) / before if before else 0.0
    success_ok = candidate["task_success_rate"] >= baseline["task_success_rate"]
    baseline_time = baseline.get("time_per_successful_task")
    candidate_time = candidate.get("time_per_successful_task")
    time_ok = isinstance(baseline_time, (int, float)) and isinstance(candidate_time, (int, float))
    if time_ok:
        time_ok = candidate_time <= baseline_time * (1 + THRESHOLDS["max_time_increase"])
    verdict = (
        "recommended"
        if reduction >= THRESHOLDS["target_failure_reduction"] and success_ok and time_ok
        else "not_recommended"
    )
    result = {
        "schema_version": "improvement-comparison-v1",
        "verdict": verdict,
        "target_failure_class": target,
        "target_failure_reduction": reduction,
        "success_ok": success_ok,
        "time_ok": time_ok,
        "automatic_merge": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    mine_parser = commands.add_parser("mine")
    mine_parser.add_argument("benchmark", type=Path)
    mine_parser.add_argument("output", type=Path)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    compare_parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "mine":
        print(json.dumps(mine(arguments.benchmark, arguments.output), indent=2))
    else:
        print(
            json.dumps(compare(arguments.baseline, arguments.candidate, arguments.output), indent=2)
        )


if __name__ == "__main__":
    main()
