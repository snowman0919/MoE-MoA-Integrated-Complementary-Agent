"""Run a sealed confirmation panel sequentially with score-file checkpoints."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

from . import confirmation_seal, quality_matrix


def run(args: argparse.Namespace) -> dict[str, int]:
    confirmation_seal.verify_seal(args)
    root = args.output_root / args.protocol_id
    seal = json.loads((root / "confirmation-seal.json").read_text())
    routes = json.loads((root / "confirmation-routing.json").read_text())["variant_routes"]
    counts = {"completed": 0, "passed": 0, "failed": 0}
    for attempt in sorted(seal["attempts"], key=lambda row: row["order"]):
        harness = routes[attempt["variant"]]["harness"]
        task = quality_matrix.TASK_BY_SLUG[attempt["task"]]
        evidence = args.output_root / attempt["attempt_id"] / harness / task.slug
        runner_args = Namespace(
            run_id=attempt["attempt_id"],
            workspace_root=args.workspace_root,
            output_root=args.output_root,
            gateway=args.gateway,
            state_db=args.state_db,
            timeout=args.timeout,
            runtime="docker",
        )
        score_path = evidence / "score.json"
        if not score_path.exists():
            if not (evidence / "run.json").exists():
                quality_matrix.run_one(runner_args, harness, task)
            score = quality_matrix.score_one(
                runner_args, harness, task, quality_matrix.HIDDEN_CHECKS
            )
        else:
            score = json.loads(score_path.read_text())
        status = "passed" if score.get("status") == "passed" else "failed"
        counts["completed"] += 1
        counts[status] += 1
        print(
            json.dumps(
                {
                    "attempt_id": attempt["attempt_id"],
                    "order": attempt["order"],
                    "status": status,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1_800)
    parser.add_argument("--panel", choices=("coding",), default="coding")
    return parser.parse_args()


def main() -> int:
    print(json.dumps(run(parse_args()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
