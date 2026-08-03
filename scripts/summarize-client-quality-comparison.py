#!/usr/bin/env python3
"""Aggregate preregistered quality-matrix repeats without replacing failures."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

HARNESSES = ("baseline", "opencode", "codex", "hermes")


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total must be positive")
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def load_run(root: Path, run_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for score_path in sorted((root / run_id).glob("*/*/score.json")):
        score = json.loads(score_path.read_text())
        key = (score["harness"], score["task"])
        if key in rows:
            raise ValueError(f"duplicate score: {run_id}/{key}")
        manifest_path = score_path.with_name("manifest.json")
        if not manifest_path.exists():
            raise ValueError(f"missing manifest: {manifest_path}")
        score["_manifest"] = json.loads(manifest_path.read_text())
        rows[key] = score
    return rows


def summarize(root: Path, run_ids: list[str], margin: float) -> dict[str, Any]:
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("run IDs must be unique")
    runs = {run_id: load_run(root, run_id) for run_id in run_ids}
    if not runs or not all(runs.values()):
        raise ValueError("every run must contain scores")

    expected = set(next(iter(runs.values())))
    tasks = sorted(task for harness, task in expected if harness == "baseline")
    if expected != {(harness, task) for harness in HARNESSES for task in tasks}:
        raise ValueError("first run is not a complete four-harness matrix")
    for run_id, rows in runs.items():
        if set(rows) != expected:
            raise ValueError(f"incomplete or incomparable matrix: {run_id}")

    fixture_hashes: dict[str, set[str]] = {task: set() for task in tasks}
    prompt_hashes: dict[str, set[str]] = {task: set() for task in tasks}
    harness_hashes: set[str] = set()
    for rows in runs.values():
        for (_, task), row in rows.items():
            manifest = row["_manifest"]
            fixture_hashes[task].add(manifest["tests_sha256"])
            prompt_hashes[task].add(manifest["prompt_sha256"])
            harness_hashes.add(manifest.get("harness_sha256", ""))
    if any(len(values) != 1 for values in fixture_hashes.values()):
        raise ValueError("fixture hashes differ across harnesses or repeats")
    if any(len(values) != 1 for values in prompt_hashes.values()):
        raise ValueError("prompt hashes differ across harnesses or repeats")
    if "" in harness_hashes or len(harness_hashes) != 1:
        raise ValueError("harness hash differs across repeats")

    metrics: dict[str, dict[str, Any]] = {}
    for harness in HARNESSES:
        rows = [runs[run_id][(harness, task)] for run_id in run_ids for task in tasks]
        successes = sum(row["status"] == "passed" for row in rows)
        durations = [float(row["duration_seconds"]) for row in rows]
        interval = wilson(successes, len(rows))
        metrics[harness] = {
            "attempts": len(rows),
            "passes": successes,
            "pass_rate": successes / len(rows),
            "pass_rate_wilson_95": list(interval),
            "median_seconds": statistics.median(durations),
            "p90_seconds": percentile(durations, 0.9),
        }

    baseline = metrics["baseline"]
    comparisons: dict[str, dict[str, Any]] = {}
    for harness in HARNESSES[1:]:
        candidate = metrics[harness]
        lower = candidate["pass_rate_wilson_95"][0] - baseline["pass_rate_wilson_95"][1]
        upper = candidate["pass_rate_wilson_95"][1] - baseline["pass_rate_wilson_95"][0]
        verdict = (
            "noninferior" if lower >= -margin else "inferior" if upper < -margin else "inconclusive"
        )
        comparisons[harness] = {
            "pass_rate_delta": candidate["pass_rate"] - baseline["pass_rate"],
            "delta_conservative_95": [lower, upper],
            "margin": margin,
            "quality_verdict": verdict,
            "median_latency_ratio": candidate["median_seconds"] / baseline["median_seconds"],
        }

    return {
        "run_ids": run_ids,
        "repeats": len(run_ids),
        "tasks": tasks,
        "harness_sha256": next(iter(harness_hashes)),
        "metrics": metrics,
        "comparisons": comparisons,
        "complete": all(
            comparison["quality_verdict"] != "inconclusive" for comparison in comparisons.values()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--margin", type=float, default=0.05)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    if not 0 <= args.margin < 1:
        parser.error("--margin must be in [0, 1)")
    result = summarize(args.output_root, args.run_id, args.margin)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
