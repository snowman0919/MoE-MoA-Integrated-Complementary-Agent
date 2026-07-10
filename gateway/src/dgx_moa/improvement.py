from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

THRESHOLDS = {
    "target_failure_reduction": 0.30,
    "max_success_regression": 0.0,
    "max_token_increase": 0.10,
    "max_time_increase": 0.15,
}


def _read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def statistics(result: dict[str, Any]) -> dict[str, Any]:
    tasks = cast(list[dict[str, Any]], result.get("tasks", []))
    failures = [item for task in tasks for item in task.get("failure_classes", [])]
    known_tokens = [
        int(task["input_tokens"]) for task in tasks if isinstance(task.get("input_tokens"), int)
    ]
    failure_tasks = [task for task in tasks if task.get("failure_classes")]
    return {
        "failure_frequency": {item: failures.count(item) for item in sorted(set(failures))},
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


def mine(benchmark: Path, output: Path) -> dict[str, Any]:
    result = _read(benchmark)
    evidence = statistics(result)
    failures = evidence["failure_frequency"]
    failure_class, affected = max(
        failures.items(), key=lambda item: (item[1], item[0]), default=("NONE", 0)
    )
    proposal = {
        "schema_version": "improvement-proposal-v1",
        "proposal_id": "IMP-2026-0001",
        "title": f"Block {failure_class.lower()} earlier",
        "problem": f"{failure_class} appears in {affected} benchmark task(s).",
        "evidence": {
            "affected_tasks": affected,
            "failure_class": failure_class,
            "wasted_input_tokens": evidence["token_waste"],
            "wasted_seconds": evidence["time_waste_seconds"],
        },
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
        "priority": {"affected_tasks": affected, "risk": "low", "benchmark_coverage": affected},
    }
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
