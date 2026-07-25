#!/usr/bin/env python3
"""Analyze the frozen frontier-agent non-inferiority panel."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

TASKS = (
    "rate-limiter",
    "atomic-store",
    "dag-runner",
    "webhook-verifier",
    "log-report",
)
VARIANTS = ("baseline", "codex", "opencode", "hermes")
SEED = 56052026
QUALITY_MARGIN = -5.0
SPEED_MARGIN = 1.5


def percentile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("invalid percentile")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"invalid {name}")
    return number


def load_rows(path: Path, repeats: int) -> dict[tuple[str, str, str], dict[str, Any]]:
    if isinstance(repeats, bool) or repeats < 1:
        raise ValueError("repeats must be positive")
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {line_number}: invalid JSON") from error
        if not isinstance(row, dict):
            raise ValueError(f"line {line_number}: object required")
        repeat, task, variant = (row.get(name) for name in ("repeat", "task", "variant"))
        if not isinstance(repeat, str) or not repeat:
            raise ValueError(f"line {line_number}: invalid repeat")
        if task not in TASKS or variant not in VARIANTS:
            raise ValueError(f"line {line_number}: unknown task or variant")
        key = (repeat, task, variant)
        if key in rows:
            raise ValueError(f"line {line_number}: duplicate attempt")
        if type(row.get("passed")) is not bool or type(row.get("telemetry_complete")) is not bool:
            raise ValueError(f"line {line_number}: boolean status required")
        row["duration_seconds"] = finite_number(
            row.get("duration_seconds"), "duration_seconds", minimum=0.000001
        )
        row["variable_cost_usd"] = finite_number(
            row.get("variable_cost_usd"), "variable_cost_usd", minimum=0
        )
        score = row.get("quality_score")
        if score is not None:
            row["quality_score"] = finite_number(score, "quality_score", minimum=0)
            if row["quality_score"] > 100:
                raise ValueError(f"line {line_number}: invalid quality_score")
        elif row["passed"]:
            raise ValueError(f"line {line_number}: passing attempt requires quality_score")
        rows[key] = row

    repeat_ids = sorted({key[0] for key in rows})
    if len(repeat_ids) != repeats:
        raise ValueError(f"expected {repeats} repeats")
    expected = {
        (repeat, task, variant)
        for repeat in repeat_ids
        for task in TASKS
        for variant in VARIANTS
    }
    if set(rows) != expected:
        raise ValueError("incomplete or incomparable panel")
    return rows


def stratified_bootstrap(
    values: dict[str, list[float]], *, samples: int, seed: int
) -> tuple[float, float]:
    if samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    if set(values) != set(TASKS) or any(not items for items in values.values()):
        raise ValueError("every task stratum requires observations")
    generator = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [
            generator.choice(values[task])
            for task in TASKS
            for _ in range(len(values[task]))
        ]
        estimates.append(statistics.fmean(draw))
    return percentile(estimates, 0.05), percentile(estimates, 0.95)


def verdict_quality(lower: float, upper: float) -> str:
    if lower > 0:
        return "superior"
    if lower > QUALITY_MARGIN:
        return "noninferior"
    if upper < QUALITY_MARGIN:
        return "inferior"
    return "inconclusive"


def verdict_speed(lower: float, upper: float) -> str:
    if upper < 1:
        return "superior"
    if upper < SPEED_MARGIN:
        return "noninferior"
    if lower > SPEED_MARGIN:
        return "inferior"
    return "inconclusive"


def analyze(
    path: Path, *, repeats: int = 10, bootstrap_samples: int = 10_000
) -> dict[str, Any]:
    rows = load_rows(path, repeats)
    repeat_ids = sorted({key[0] for key in rows})
    result: dict[str, Any] = {
        "protocol": "frontier-agent-noninferiority-v1",
        "bootstrap_seed": SEED,
        "bootstrap_samples": bootstrap_samples,
        "repeats": repeats,
        "attempts_per_variant": repeats * len(TASKS),
        "variants": {},
        "comparisons": {},
    }
    for variant in VARIANTS:
        attempts = [
            rows[(repeat, task, variant)] for repeat in repeat_ids for task in TASKS
        ]
        result["variants"][variant] = {
            "passes": sum(row["passed"] for row in attempts),
            "telemetry_complete": all(row["telemetry_complete"] for row in attempts),
            "variable_cost_usd": sum(row["variable_cost_usd"] for row in attempts),
            "median_seconds": statistics.median(
                row["duration_seconds"] for row in attempts
            ),
        }

    for variant in VARIANTS[1:]:
        quality: dict[str, list[float]] = defaultdict(list)
        speed: dict[str, list[float]] = defaultdict(list)
        for repeat in repeat_ids:
            for task in TASKS:
                baseline = rows[(repeat, task, "baseline")]
                candidate = rows[(repeat, task, variant)]
                if (
                    baseline["quality_score"] is not None
                    and candidate["quality_score"] is not None
                ):
                    quality[task].append(
                        candidate["quality_score"] - baseline["quality_score"]
                    )
                speed[task].append(
                    math.log(candidate["duration_seconds"] / baseline["duration_seconds"])
                )

        expected_pairs = repeats * len(TASKS)
        quality_pairs = sum(map(len, quality.values()))
        quality_bounds: tuple[float | None, float | None] = (
            stratified_bootstrap(quality, samples=bootstrap_samples, seed=SEED)
            if quality_pairs == expected_pairs
            else (None, None)
        )
        speed_log_bounds = stratified_bootstrap(
            speed, samples=bootstrap_samples, seed=SEED + 1
        )
        speed_bounds = tuple(math.exp(value) for value in speed_log_bounds)
        quality_result = (
            verdict_quality(quality_bounds[0], quality_bounds[1])
            if quality_pairs == expected_pairs
            else "inconclusive"
        )
        speed_result = verdict_speed(*speed_bounds)
        metrics = result["variants"][variant]
        hard_gate = (
            metrics["passes"] == expected_pairs and metrics["telemetry_complete"]
        )
        cost_gate = metrics["variable_cost_usd"] == 0
        overall = (
            "FRONTIER-SUPERIOR"
            if hard_gate
            and cost_gate
            and quality_result == "superior"
            and speed_result == "superior"
            else "FRONTIER-NONINFERIOR"
            if hard_gate
            and cost_gate
            and quality_result in {"noninferior", "superior"}
            and speed_result in {"noninferior", "superior"}
            else "INFERIOR"
            if not hard_gate
            or not cost_gate
            or quality_result == "inferior"
            or speed_result == "inferior"
            else "INCONCLUSIVE"
        )
        result["comparisons"][variant] = {
            "quality_pairs": quality_pairs,
            "quality_mean_delta": (
                statistics.fmean(value for items in quality.values() for value in items)
                if quality_pairs
                else None
            ),
            "quality_one_sided_95": list(quality_bounds),
            "quality_verdict": quality_result,
            "speed_geomean_ratio": math.exp(
                statistics.fmean(value for items in speed.values() for value in items)
            ),
            "speed_one_sided_95": list(speed_bounds),
            "speed_verdict": speed_result,
            "hard_reliability_gate": hard_gate,
            "zero_variable_cost_gate": cost_gate,
            "overall": overall,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempts", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = analyze(
        args.attempts,
        repeats=args.repeats,
        bootstrap_samples=args.bootstrap_samples,
    )
    rendered = json.dumps(result, indent=2, allow_nan=False, sort_keys=True) + "\n"
    if args.write:
        args.write.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
