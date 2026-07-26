#!/usr/bin/env python3
"""Analyze Scientific and General breadth evidence independently."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from dgx_moa import frontier_noninferiority as BASE

CATEGORIES = {
    "scientific": ("scientific-meta-analysis", "scientific-decay-fit"),
    "general": ("general-ranked-choice", "general-timezone-schedule"),
}
SEED = 56_052_027


def analyze(
    path: Path,
    *,
    repeats: int = 10,
    bootstrap_samples: int = 10_000,
) -> dict[str, Any]:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    categories = {}
    for category, tasks in CATEGORIES.items():
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl") as handle:
            for row in lines:
                if row.get("task") in tasks:
                    handle.write(json.dumps(row) + "\n")
            handle.flush()
            categories[category] = BASE.analyze(
                Path(handle.name),
                repeats=repeats,
                bootstrap_samples=bootstrap_samples,
                tasks=tasks,
                seed=SEED,
            )
    return {
        "protocol": "frontier-breadth-noninferiority-v1",
        "bootstrap_seed": SEED,
        "repeats": repeats,
        "categories": categories,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempts", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    args = parser.parse_args()
    result = analyze(
        args.attempts,
        repeats=args.repeats,
        bootstrap_samples=args.bootstrap_samples,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
