#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from dgx_moa.config import load_settings
from dgx_moa.state import Phase, StateStore, now
from dgx_moa.trace import TraceRecorder


def git(workspace: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(workspace), *args], text=True, capture_output=True, check=False
    ).stdout.strip()


def ending_repository(workspace: Path) -> dict[str, str]:
    return {
        "workspace_path": str(workspace.resolve()),
        "workspace_identifier": workspace.name,
        "current_branch": git(workspace, "branch", "--show-current") or "detached",
        "current_commit": git(workspace, "rev-parse", "HEAD") or "unknown",
        "dirty_status": "dirty" if git(workspace, "status", "--porcelain") else "clean",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument(
        "--status",
        choices=("completed", "failed", "blocked", "cancelled", "degraded"),
        required=True,
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/models.yaml"))
    args = parser.parse_args()
    store = StateStore(args.state_db)
    state = store.get(args.session_id)
    if state is None:
        raise SystemExit("session not found")
    state.final_status = args.status
    state.phase = Phase.COMPLETED if args.status == "completed" else Phase.BLOCKED
    state.ending_repository = ending_repository(args.workspace)
    state.completion_evidence.update(
        dict(item.split("=", 1) for item in args.evidence if "=" in item)
    )
    state.evaluations.extend(
        {
            "evaluation_id": hashlib.sha256(
                f"{state.session_id}:{key}:{value}".encode()
            ).hexdigest()[:24],
            "target_type": "task",
            "target_id": state.task_id or state.session_id,
            "evaluator_type": "deterministic",
            "evaluator_model": None,
            "result": "passed" if "exit 0" in value else "failed",
            "evidence_references": [value],
            "requirement_ids": [key],
            "created_at": now(),
        }
        for key, value in state.completion_evidence.items()
    )
    state.training_eligibility = "excluded"
    store.event(args.session_id, "session_ended", {"status": args.status})
    store.save(state)
    settings = load_settings(args.config)
    path = TraceRecorder(args.trace_dir, store, settings.models).record(state)
    print(json.dumps({"session_id": args.session_id, "status": args.status, "trace": str(path)}))


if __name__ == "__main__":
    main()
