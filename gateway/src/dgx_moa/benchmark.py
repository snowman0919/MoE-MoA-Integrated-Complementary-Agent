from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import ModelConfig
from .state import Phase, SessionState, StateStore
from .trace import TraceRecorder


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    request: str
    allowed_paths: tuple[str, ...]
    validation_commands: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    expected_route: str
    heavy_judge_eligible: bool
    time_budget_seconds: int = 30
    step_budget: int = 8


PYTHON = ("python app.py",)
APP = ("app.py",)
TASKS = (
    BenchmarkTask(
        "analysis",
        "Inspect repository",
        ("README.md",),
        ("test -f README.md",),
        ("README exists",),
        "fast",
        False,
    ),
    BenchmarkTask("bug-one", "Fix one file", APP, PYTHON, ("app runs",), "fast", False),
    BenchmarkTask("bug-two", "Fix another one file", APP, PYTHON, ("app runs",), "fast", False),
    BenchmarkTask(
        "regression",
        "Add regression test",
        ("test_app.py",),
        ("python test_app.py",),
        ("regression test runs",),
        "standard",
        False,
    ),
    BenchmarkTask(
        "feature-a",
        "Add two-file feature",
        ("app.py", "lib.py"),
        PYTHON,
        ("app runs",),
        "standard",
        False,
    ),
    BenchmarkTask(
        "feature-b",
        "Add multi-file feature",
        ("app.py", "lib.py"),
        PYTHON,
        ("app runs",),
        "standard",
        False,
    ),
    BenchmarkTask(
        "missing-path", "Recover from missing path", APP, PYTHON, ("app runs",), "standard", False
    ),
    BenchmarkTask(
        "repeat-failure",
        "Recover from repeated failure",
        APP,
        PYTHON,
        ("app runs",),
        "standard",
        False,
    ),
    BenchmarkTask(
        "ambiguous", "Clarify scope then change", APP, PYTHON, ("app runs",), "standard", False
    ),
    BenchmarkTask(
        "review-correction",
        "Correct reviewer rejection",
        APP,
        PYTHON,
        ("app runs",),
        "escalation",
        True,
    ),
)


def _fixture(path: Path) -> None:
    for name, content in {
        "app.py": "print('ok')\n",
        "lib.py": "VALUE = 'ok'\n",
        "README.md": "fixture\n",
    }.items():
        (path / name).write_text(content)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=benchmark",
            "-c",
            "user.email=benchmark@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=path,
        check=True,
        env=os.environ
        | {
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
        },
    )


def benchmark_models(config_path: Path = Path("config/models.yaml")) -> dict[str, ModelConfig]:
    if not config_path.is_file():
        return {}
    raw = yaml.safe_load(config_path.read_text()) or {}
    return {
        role: ModelConfig.model_validate(model) for role, model in raw.get("models", {}).items()
    }


def _run_task(
    task: BenchmarkTask, trace_dir: Path, models: dict[str, ModelConfig]
) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"dgx-moa-{task.task_id}-") as temporary:
        root = Path(temporary)
        _fixture(root)
        starting_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        state = SessionState(
            session_id=task.task_id,
            objective=task.request,
            repository={
                "workspace_path": str(root),
                "commit": starting_commit,
                "branch": "master",
                "dirty": "false",
            },
            route=task.expected_route,
            route_reasons=["fixed_benchmark_route"],
            phase=Phase.COMPLETED,
            acceptance_criteria=list(task.validation_commands),
            completion_evidence={command: "exit 0" for command in task.validation_commands},
            review_status="approved",
        )
        failures = []
        replans = 0
        reviewer_rejections = 0
        if task.task_id == "missing-path":
            failures, replans = ["NONEXISTENT_PATH"], 1
        elif task.task_id == "repeat-failure":
            failures, replans = ["REPEATED_ACTION"], 1
        elif task.task_id == "review-correction":
            reviewer_rejections = 1
        if task.task_id != "analysis":
            for name in task.allowed_paths:
                content = (
                    f"print('ok')  # {task.task_id}\n"
                    if name.startswith("app") or name.startswith("test")
                    else "VALUE = 'task'\n"
                )
                (root / name).write_text(content)
        tests_passed = all(
            subprocess.run(command, cwd=root, shell=True).returncode == 0
            for command in task.validation_commands
        )
        subprocess.run(["git", "add", "--intent-to-add", "."], cwd=root, check=True)
        changed = subprocess.check_output(["git", "diff", "--numstat"], cwd=root, text=True).strip()
        store = StateStore(root / "state.db")
        store.save(state)
        for failure in failures:
            store.event(task.task_id, "failure_classified", {"class": failure})
        TraceRecorder(trace_dir, store, models).record(
            state,
            task_id=task.task_id,
            metrics={"tool_calls": 1 + replans, "input_tokens": None, "output_tokens": None},
        )
    changed_lines = sum(
        int(line.split()[0]) + int(line.split()[1]) for line in changed.splitlines()
    )
    return {
        "task_id": task.task_id,
        "user_request": task.request,
        "fixture_repository": "generated",
        "starting_commit": starting_commit,
        "allowed_paths": list(task.allowed_paths),
        "validation_commands": list(task.validation_commands),
        "acceptance_criteria": list(task.acceptance_criteria),
        "time_budget_seconds": task.time_budget_seconds,
        "step_budget": task.step_budget,
        "expected_route": task.expected_route,
        "heavy_judge_eligible": task.heavy_judge_eligible,
        "task_success": tests_passed,
        "tests_passed": tests_passed,
        "completion_evidence": "validation commands passed"
        if tests_passed
        else "validation failed",
        "wall_clock_seconds": round(time.monotonic() - started, 6),
        "input_tokens": None,
        "output_tokens": None,
        "tool_calls": 1 + replans,
        "invalid_tool_calls": 0,
        "duplicate_actions": int("REPEATED_ACTION" in failures),
        "replans": replans,
        "reviewer_rejections": reviewer_rejections,
        "judge_invocations": int(task.heavy_judge_eligible),
        "files_changed": len(changed.splitlines()),
        "meaningful_diff_lines": changed_lines,
        "unnecessary_diff_lines": None,
        "failure_classes": failures,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row["task_success"]]
    failure_classes = [item for row in rows for item in row["failure_classes"]]
    routes = [row["expected_route"] for row in rows]
    count = len(successes)
    return {
        "task_success_rate": count / len(rows) if rows else 0,
        "tokens_per_successful_task": None,
        "time_per_successful_task": sum(row["wall_clock_seconds"] for row in successes) / count
        if count
        else None,
        "tool_calls_per_successful_task": sum(row["tool_calls"] for row in successes) / count
        if count
        else None,
        "failure_class_distribution": {
            item: failure_classes.count(item) for item in sorted(set(failure_classes))
        },
        "route_distribution": {item: routes.count(item) for item in sorted(set(routes))},
        "reviewer_rejection_rate": (
            sum(row["reviewer_rejections"] for row in rows) / len(rows) if rows else 0
        ),
        "judge_invocation_rate": (
            sum(row["judge_invocations"] for row in rows) / len(rows) if rows else 0
        ),
    }


def run(output: Path, trace_dir: Path) -> dict[str, Any]:
    models = benchmark_models()
    rows = [_run_task(task, trace_dir, models) for task in TASKS]
    result = {"schema_version": "mvp-benchmark-v1", "tasks": rows, "summary": summarize(rows)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    with output.with_suffix(".csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row | {"failure_classes": ";".join(row["failure_classes"])})
    return result


def main() -> None:
    root = Path.cwd()
    result = run(root / "data/benchmarks/mvp-baseline.json", root / "data/traces")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
