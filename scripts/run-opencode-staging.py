#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    task_id: str
    category: str
    prompt: str
    validation: str


TASKS = (
    Task(
        "read-1",
        "read",
        "Use repository tools to read README.md. Reply READ_DONE.",
        "test -f README.md",
    ),
    Task(
        "read-2",
        "read",
        "Inspect app.py with tools and report its current output. Reply ANALYSIS_DONE.",
        "python app.py",
    ),
    Task(
        "read-3",
        "read",
        "Inspect README.md and app.py with tools. Reply REPOSITORY_DONE.",
        "python app.py",
    ),
    Task(
        "edit-1",
        "small_edit",
        "Create RESULT.txt containing exactly EDIT_ONE, then reply EDIT_DONE.",
        'test "$(cat RESULT.txt)" = EDIT_ONE',
    ),
    Task(
        "edit-2",
        "small_edit",
        "Change app.py to print EDIT_TWO, run it, then reply EDIT_DONE.",
        'test "$(python app.py)" = EDIT_TWO',
    ),
    Task(
        "edit-3",
        "small_edit",
        "Create value.py containing VALUE = 3, then reply EDIT_DONE.",
        "python -c 'import value; assert value.VALUE == 3'",
    ),
    Task(
        "multi-1",
        "multi_file",
        "Change lib.py VALUE to MULTI_ONE and app.py to print it. "
        "Run app.py, then reply MULTI_DONE.",
        'test "$(python app.py)" = MULTI_ONE',
    ),
    Task(
        "multi-2",
        "multi_file",
        "Add double(x) to lib.py and test it from test_app.py. "
        "Run test_app.py, then reply MULTI_DONE.",
        "python test_app.py",
    ),
    Task(
        "recovery-1",
        "failure_recovery",
        "Try reading MISSING.txt. Recover by creating it with RECOVERED, verify it, "
        "then reply RECOVERY_DONE.",
        'test "$(cat MISSING.txt)" = RECOVERED',
    ),
    Task(
        "long-1",
        "bounded_engineering",
        "Implement add(a, b) in lib.py, use it from app.py to print 5, "
        "add test_app.py assertions, run both programs, then reply LONG_DONE.",
        'test "$(python app.py)" = 5 && python test_app.py',
    ),
)


def git(workspace: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(workspace), *args], text=True, capture_output=True, check=True
    ).stdout.strip()


def create_fixture(workspace: Path) -> None:
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("staging fixture\n")
    (workspace / "app.py").write_text("print('BASE')\n")
    (workspace / "lib.py").write_text("VALUE = 'BASE'\n")
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    subprocess.run(["git", "-C", str(workspace), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=staging",
            "-c",
            "user.email=staging@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )


def project_config(base_url: str, session: str, task: Task, workspace: Path) -> dict:
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "dgx-moa": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "DGX MoA",
                "options": {
                    "baseURL": base_url.rstrip("/") + "/v1",
                    "apiKey": "{env:DGX_MOA_API_KEY}",
                    "headers": {
                        "X-Session-ID": session,
                        "X-Runtime-Channel": "dev",
                        "X-Trace-Origin": "validation",
                        "X-Task-ID": task.task_id,
                        "X-Workspace-Path": str(workspace.resolve()),
                        "X-Workspace-ID": session,
                        "X-Repository-Branch": git(workspace, "branch", "--show-current"),
                        "X-Repository-Commit": git(workspace, "rev-parse", "HEAD"),
                        "X-Dirty-State": "clean",
                    },
                },
                "models": {"dgx-moa-agent": {"name": "DGX MoA Agent"}},
            }
        },
        "model": "dgx-moa/dgx-moa-agent",
        "permission": {"*": "allow"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://100.125.239.72:9000")
    parser.add_argument("--opencode", type=Path, default=Path.home() / ".opencode/bin/opencode")
    parser.add_argument("--output-root", type=Path, default=Path("data/staging/opencode"))
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/models.yaml"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--limit", type=int, choices=range(1, len(TASKS) + 1), default=len(TASKS))
    args = parser.parse_args()
    if not os.getenv("DGX_MOA_API_KEY"):
        raise SystemExit("DGX_MOA_API_KEY is required")
    run_id = time.strftime("%Y%m%d-%H%M%S")
    root = args.output_root / run_id
    rows = []
    selected = TASKS[: args.limit]
    for index, task in enumerate(selected, 1):
        session = f"staging-{run_id}-{index:02d}"
        workspace = root / session / "repo"
        create_fixture(workspace)
        exclude = workspace / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\nopencode.json\n")
        (workspace / "opencode.json").write_text(
            json.dumps(project_config(args.base_url, session, task, workspace), indent=2) + "\n"
        )
        started = time.monotonic()
        command = [
            str(args.opencode),
            "run",
            "--format",
            "json",
            "--auto",
            "--dir",
            str(workspace),
            "--model",
            "dgx-moa/dgx-moa-agent",
            task.prompt,
        ]
        try:
            run = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            run = subprocess.CompletedProcess(
                command,
                124,
                error.stdout or "",
                (error.stderr or "") + f"\ntimeout={args.timeout}\n",
            )
        (workspace.parent / "opencode.stdout.jsonl").write_text(run.stdout)
        (workspace.parent / "opencode.stderr.log").write_text(run.stderr)
        validation = subprocess.run(
            task.validation, cwd=workspace, shell=True, text=True, capture_output=True, check=False
        )
        stopped = '"reason":"stop"' in run.stdout
        status = (
            "completed"
            if run.returncode == 0 and validation.returncode == 0 and stopped
            else "failed"
        )
        finalize = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "scripts/finalize-validation-session.py",
                session,
                "--status",
                status,
                "--workspace",
                str(workspace),
                "--evidence",
                f"validation={task.validation}:exit {validation.returncode}",
                "--state-db",
                str(args.state_db),
                "--trace-dir",
                str(args.trace_dir),
                "--config",
                str(args.config),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if finalize.returncode != 0:
            status = "failed"
        rows.append(
            {
                "session_id": session,
                "task_id": task.task_id,
                "category": task.category,
                "status": status,
                "opencode_exit": run.returncode,
                "validation_exit": validation.returncode,
                "finalize_exit": finalize.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        print(json.dumps(rows[-1], sort_keys=True), flush=True)
    summary = {
        "schema_version": "opencode-staging-v1",
        "run_id": run_id,
        "sessions": rows,
        "distribution": {
            category: sum(row["category"] == category for row in rows)
            for category in sorted({task.category for task in selected})
        },
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(root / "summary.json")


if __name__ == "__main__":
    main()
