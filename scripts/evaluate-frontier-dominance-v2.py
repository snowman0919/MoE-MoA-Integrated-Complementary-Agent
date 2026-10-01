#!/usr/bin/env python3
"""Fail-closed evaluator for real paired Frontier-dominance-v2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

CLIENTS = {"raw_openai_compatible", "codex", "opencode", "hermes"}
RESAMPLES = 10_000
SEED = 20_260_820


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def lower_bound(differences: list[float], seed: str) -> float | None:
    if not differences:
        return None
    generator = random.Random(f"{SEED}:{seed}")
    size = len(differences)
    samples = [
        sum(differences[generator.randrange(size)] for _ in range(size)) / size
        for _ in range(RESAMPLES)
    ]
    return percentile(samples, 0.05)


def digest_ok(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def finite_number(value: object, *, minimum: float = 0.0) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= minimum
    )


def evidence_ok(result: dict[str, Any], root: Path) -> bool:
    path_value = result.get("evidence_path")
    expected = result.get("evidence_sha256")
    if not isinstance(path_value, str) or not digest_ok(expected):
        return False
    path = Path(path_value)
    path = path if path.is_absolute() else root / path
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def successful_cost(rows: list[dict[str, Any]], side: str, field: str) -> float | None:
    values = [
        float(row[side][field])
        for row in rows
        if row[side].get("success") is True and finite_number(row[side].get(field))
    ]
    return sum(values) / len(values) if values else None


def evaluate(payload: dict[str, Any], *, evidence_root: Path = Path(".")) -> dict[str, Any]:
    violations: list[str] = []
    rows = payload.get("pairs")
    comparators = payload.get("comparators")
    if payload.get("schema_version") != "frontier-dominance-v2":
        violations.append("invalid_schema_version")
    if (
        not isinstance(comparators, list)
        or not comparators
        or not all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and digest_ok(item.get("revision_sha256"))
            for item in comparators
        )
    ):
        violations.append("comparators_not_pinned")
        comparators = []
    comparator_ids = {item["id"] for item in comparators}
    if len(comparator_ids) != len(comparators):
        violations.append("duplicate_comparator")
    if not isinstance(rows, list) or not rows:
        violations.append("missing_pairs")
        rows = []

    seen_pairs: set[tuple[str, str, str]] = set()
    epochs: set[str] = set()
    clients: set[str] = set()
    by_comparator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            violations.append("invalid_pair")
            continue
        prefix = f"pair:{row.get('pair_id', 'unknown')}:"
        epoch = row.get("epoch_id")
        pair_id = row.get("pair_id")
        comparator = row.get("comparator")
        client = row.get("client")
        identity = (str(epoch), str(pair_id), str(comparator))
        if identity in seen_pairs:
            violations.append(prefix + "duplicate")
        seen_pairs.add(identity)
        if (
            not isinstance(epoch, str)
            or not epoch
            or not digest_ok(row.get("epoch_manifest_sha256"))
        ):
            violations.append(prefix + "invalid_epoch")
        else:
            epochs.add(epoch)
        if client not in CLIENTS:
            violations.append(prefix + "invalid_client")
        else:
            clients.add(client)
        if comparator not in comparator_ids:
            violations.append(prefix + "unknown_comparator")
            continue
        if (
            row.get("task_source") != "repository"
            or row.get("paired_execution") is not True
            or row.get("isolated_workspace") is not True
            or row.get("hidden_validation") != "external"
            or row.get("validator_exposed") is not False
        ):
            violations.append(prefix + "not_real_hidden_paired_execution")
        for key in ("task_type", "language", "context_length_bucket"):
            if not isinstance(row.get(key), str) or not row[key]:
                violations.append(prefix + f"invalid_{key}")
        for forbidden in (
            "mock_provider_used",
            "generated_patch_used",
            "unintended_fallback_used",
        ):
            if row.get(forbidden) is not False:
                violations.append(prefix + forbidden)
        for side in ("target", "comparator_result", "current_system"):
            result = row.get(side)
            if not isinstance(result, dict):
                violations.append(prefix + f"invalid_{side}")
                continue
            if (
                type(result.get("success")) is not bool
                or type(result.get("false_completion")) is not bool
            ):
                violations.append(prefix + f"invalid_{side}_outcome")
            if not all(
                finite_number(result.get(field))
                for field in ("verified_completion_seconds", "tokens", "cost_usd")
            ):
                violations.append(prefix + f"invalid_{side}_metrics")
            if not evidence_ok(result, evidence_root):
                violations.append(prefix + f"invalid_{side}_evidence")
        target = row.get("target", {})
        if isinstance(target, dict) and target.get("false_completion") is not False:
            violations.append(prefix + "target_false_completion")
        by_comparator[str(comparator)].append(row)

    if len(epochs) < 2:
        violations.append("independent_epochs_incomplete")
    if clients != CLIENTS:
        violations.append("client_matrix_incomplete")
    gates: dict[str, Any] = {}
    for comparator in sorted(comparator_ids):
        group = by_comparator.get(comparator, [])
        differences = [
            int(row["target"]["success"]) - int(row["comparator_result"]["success"])
            for row in group
            if isinstance(row.get("target"), dict)
            and isinstance(row.get("comparator_result"), dict)
            and type(row["target"].get("success")) is bool
            and type(row["comparator_result"].get("success")) is bool
        ]
        success_lcb = lower_bound(differences, comparator)
        if success_lcb is None or success_lcb <= 0.03:
            violations.append(f"comparator:{comparator}:success_lcb")
        strata: dict[str, float | None] = {}
        for dimension in ("task_type", "language", "context_length_bucket"):
            values = sorted({str(row.get(dimension)) for row in group if row.get(dimension)})
            for value in values:
                key = f"{dimension}:{value}"
                stratum = [
                    int(row["target"]["success"]) - int(row["comparator_result"]["success"])
                    for row in group
                    if row.get(dimension) == value
                    and type(row.get("target", {}).get("success")) is bool
                    and type(row.get("comparator_result", {}).get("success")) is bool
                ]
                strata[key] = lower_bound(stratum, f"{comparator}:{key}")
                if strata[key] is None or strata[key] <= -0.05:
                    violations.append(f"comparator:{comparator}:stratum:{key}")
        valid_latencies = [
            row
            for row in group
            if all(
                isinstance(row.get(side), dict)
                and finite_number(row[side].get("verified_completion_seconds"), minimum=1e-12)
                for side in ("target", "comparator_result", "current_system")
            )
        ]
        latency: dict[str, float] = {}
        if valid_latencies:
            for side in ("target", "comparator_result", "current_system"):
                values = [
                    float(row[side]["verified_completion_seconds"]) for row in valid_latencies
                ]
                latency[f"{side}_p50"] = percentile(values, 0.50)
                latency[f"{side}_p95"] = percentile(values, 0.95)
            if latency["target_p50"] > 0.80 * latency["current_system_p50"]:
                violations.append(f"comparator:{comparator}:current_p50_latency")
            if latency["target_p95"] > 0.90 * latency["current_system_p95"]:
                violations.append(f"comparator:{comparator}:current_p95_latency")
            if latency["target_p50"] > latency["comparator_result_p50"]:
                violations.append(f"comparator:{comparator}:comparator_p50_latency")
            if latency["target_p95"] > 1.10 * latency["comparator_result_p95"]:
                violations.append(f"comparator:{comparator}:comparator_p95_latency")
        else:
            violations.append(f"comparator:{comparator}:latency_missing")
        efficiency: dict[str, float | None] = {}
        for field in ("tokens", "cost_usd"):
            target_value = successful_cost(group, "target", field)
            comparator_value = successful_cost(group, "comparator_result", field)
            efficiency[f"target_{field}"] = target_value
            efficiency[f"comparator_{field}"] = comparator_value
            if (
                target_value is None
                or comparator_value is None
                or target_value > 1.20 * comparator_value
            ):
                violations.append(f"comparator:{comparator}:{field}")
        gates[comparator] = {
            "pairs": len(group),
            "success_lcb_one_sided_95": success_lcb,
            "strata_lcb_one_sided_95": strata,
            "latency_seconds": latency,
            "successful_task_efficiency": efficiency,
        }

    return {
        "schema_version": "frontier-dominance-result-v2",
        "verdict": "PASS" if not violations else "INCONCLUSIVE",
        "violations": sorted(set(violations)),
        "epochs": sorted(epochs),
        "clients": sorted(clients),
        "comparators": gates,
        "bootstrap_resamples": RESAMPLES,
        "input_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    result = evaluate(json.loads(arguments.input.read_text()), evidence_root=arguments.input.parent)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "PASS" else 2)


if __name__ == "__main__":
    main()
