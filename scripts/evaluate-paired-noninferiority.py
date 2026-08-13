#!/usr/bin/env python3
"""Fail-closed paired non-inferiority analysis for frozen blind scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

CLIENTS = {"codex", "opencode", "hermes", "raw_openai_compatible"}
CATEGORIES = {
    "small_deterministic_engineering",
    "multi_file_implementation",
    "debugging_recovery",
    "architecture_sensitive_refactor",
    "novel_technology_integration",
    "research_implementation",
    "long_horizon_engineering_goal",
}
COMPARATORS = {"gpt-5.6-sol-high", "claude-opus-5-class"}
METRICS = {
    "quality": "task_success_0_1",
    "speed": "verified_completion_seconds",
    "cost": "usd",
    "reliability": "terminal_without_false_completion",
    "context_retention": "required_fact_retention_0_1",
}
MINIMUM_PAIRS = 30
MARGIN = -0.10
RESAMPLES = 10_000
SEED = 20_260_808
HEX64 = set("0123456789abcdef")


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def paired_bootstrap(differences: list[int]) -> tuple[float, float]:
    generator = random.Random(SEED)
    size = len(differences)
    samples = [
        sum(differences[generator.randrange(size)] for _ in range(size)) / size
        for _ in range(RESAMPLES)
    ]
    return percentile(samples, 0.025), percentile(samples, 0.975)


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    epoch = payload.get("protocol_epoch")
    if not isinstance(epoch, str) or not epoch:
        violations.append("invalid_protocol_epoch")
    if payload.get("schema_version") != "paired-noninferiority-v1":
        violations.append("invalid_schema_version")
    if payload.get("comparator") not in COMPARATORS:
        violations.append("invalid_comparator")
    if payload.get("metric_contract") != METRICS:
        violations.append("metric_contract_mismatch")
    if not valid_digest(payload.get("blind_assignment_sha256")):
        violations.append("invalid_blind_assignment_hash")
    if not valid_digest(payload.get("score_freeze_sha256")):
        violations.append("invalid_score_freeze_hash")
    if payload.get("identities_hidden_during_scoring") is not True:
        violations.append("scoring_not_blind")
    if payload.get("reliability_gate_passed") is not True:
        violations.append("reliability_gate_failed")

    expected = payload.get("expected_pair_ids")
    pairs = payload.get("pairs")
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        violations.append("invalid_expected_pairs")
        expected = []
    if not isinstance(pairs, list):
        violations.append("invalid_pairs")
        pairs = []
    pair_ids = [row.get("pair_id") for row in pairs if isinstance(row, dict)]
    if len(expected) != len(set(expected)) or len(pair_ids) != len(set(pair_ids)):
        violations.append("duplicate_pair_id")
    if set(pair_ids) != set(expected):
        violations.append("missing_or_unexpected_pair")
    if len(pairs) < MINIMUM_PAIRS:
        violations.append("insufficient_pairs")

    differences: list[int] = []
    clients: set[str] = set()
    categories: set[str] = set()
    for row in pairs:
        if not isinstance(row, dict):
            violations.append("invalid_pair")
            continue
        pair_id = row.get("pair_id", "unknown")
        prefix = f"pair:{pair_id}:"
        client = row.get("client")
        category = row.get("task_category")
        task_id = row.get("task_id")
        clients.add(client) if isinstance(client, str) else None
        categories.add(category) if isinstance(category, str) else None
        if row.get("protocol_epoch") != epoch:
            violations.append(prefix + "protocol_epoch_mismatch")
        if client not in CLIENTS:
            violations.append(prefix + "invalid_client")
        if category not in CATEGORIES:
            violations.append(prefix + "invalid_task_category")
        if not isinstance(task_id, str) or not task_id:
            violations.append(prefix + "invalid_task_id")
        if not isinstance(row.get("seed"), int) or isinstance(row.get("seed"), bool):
            violations.append(prefix + "invalid_seed")
        if row.get("telemetry_complete") is not True:
            violations.append(prefix + "telemetry_incomplete")
        if not valid_digest(row.get("quality_evidence_sha256")):
            violations.append(prefix + "invalid_quality_evidence_hash")
        target_conditions = row.get("target_conditions_sha256")
        reference_conditions = row.get("reference_conditions_sha256")
        if not valid_digest(target_conditions) or target_conditions != reference_conditions:
            violations.append(prefix + "conditions_mismatch")
        target = row.get("target_success")
        reference = row.get("reference_success")
        if target not in {0, 1} or isinstance(target, bool):
            violations.append(prefix + "invalid_target_success")
            continue
        if reference not in {0, 1} or isinstance(reference, bool):
            violations.append(prefix + "invalid_reference_success")
            continue
        if row.get("target_status") not in {"completed", "failed"}:
            violations.append(prefix + "invalid_target_status")
        if row.get("reference_status") not in {"completed", "failed"}:
            violations.append(prefix + "invalid_reference_status")
        if row.get("target_status") == "failed" and target != 0:
            violations.append(prefix + "failed_target_not_zero")
        if row.get("reference_status") == "failed" and reference != 0:
            violations.append(prefix + "failed_reference_not_zero")
        for side, success in (("target", target), ("reference", reference)):
            hidden_tests = row.get(f"{side}_hidden_tests_passed")
            false_completion = row.get(f"{side}_false_completion")
            if type(hidden_tests) is not bool or type(false_completion) is not bool:
                violations.append(prefix + f"invalid_{side}_quality_gate")
            elif success == 1 and (
                row.get(f"{side}_status") != "completed" or not hidden_tests or false_completion
            ):
                violations.append(prefix + f"{side}_success_without_quality_gate")
        differences.append(target - reference)

    if clients != CLIENTS:
        violations.append("client_strata_incomplete")
    if categories != CATEGORIES:
        violations.append("task_categories_incomplete")

    delta = sum(differences) / len(differences) if differences else None
    confidence_interval = paired_bootstrap(differences) if differences else None
    lower_bound = confidence_interval[0] if confidence_interval else None
    verdict = (
        "PASS"
        if not violations and lower_bound is not None and lower_bound > MARGIN
        else "INCONCLUSIVE"
    )
    return {
        "schema_version": "paired-noninferiority-result-v1",
        "protocol_epoch": epoch,
        "comparator": payload.get("comparator"),
        "verdict": verdict,
        "violations": sorted(set(violations)),
        "completed_pairs": len(differences),
        "minimum_pairs": MINIMUM_PAIRS,
        "target_success_rate": (
            sum(row["target_success"] for row in pairs if isinstance(row, dict)) / len(pairs)
            if pairs and len(differences) == len(pairs)
            else None
        ),
        "reference_success_rate": (
            sum(row["reference_success"] for row in pairs if isinstance(row, dict)) / len(pairs)
            if pairs and len(differences) == len(pairs)
            else None
        ),
        "paired_difference": delta,
        "confidence_interval_95": list(confidence_interval) if confidence_interval else None,
        "noninferiority_margin": MARGIN,
        "bootstrap_resamples": RESAMPLES,
        "bootstrap_seed": SEED,
        "input_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    result = evaluate(json.loads(arguments.input.read_text()))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "PASS" else 2)


if __name__ == "__main__":
    main()
