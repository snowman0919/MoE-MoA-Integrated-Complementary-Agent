from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/evaluate-paired-noninferiority.py"
spec = importlib.util.spec_from_file_location("evaluate_paired_noninferiority", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("evaluate_paired_noninferiority", module)
spec.loader.exec_module(module)


def payload(count: int = 30) -> dict[str, object]:
    digest = "a" * 64
    clients = sorted(module.CLIENTS)
    categories = sorted(module.CATEGORIES)
    pairs = [
        {
            "pair_id": f"pair-{index:02d}",
            "task_id": f"task-{index:02d}",
            "protocol_epoch": "dynamic-moa-v3-20260808",
            "client": clients[index % len(clients)],
            "task_category": categories[index % len(categories)],
            "seed": index,
            "target_status": "completed",
            "reference_status": "completed",
            "target_success": 1,
            "reference_success": 0,
            "target_hidden_tests_passed": True,
            "reference_hidden_tests_passed": False,
            "target_false_completion": False,
            "reference_false_completion": False,
            "telemetry_complete": True,
            "quality_evidence_sha256": digest,
            "target_conditions_sha256": digest,
            "reference_conditions_sha256": digest,
        }
        for index in range(count)
    ]
    return {
        "schema_version": "paired-noninferiority-v1",
        "protocol_epoch": "dynamic-moa-v3-20260808",
        "comparator": "gpt-5.6-sol-high",
        "metric_contract": module.METRICS,
        "blind_assignment_sha256": digest,
        "score_freeze_sha256": digest,
        "identities_hidden_during_scoring": True,
        "reliability_gate_passed": True,
        "expected_pair_ids": [row["pair_id"] for row in pairs],
        "pairs": pairs,
    }


def test_frozen_paired_bootstrap_passes_only_complete_covered_matrix() -> None:
    first = module.evaluate(payload())
    second = module.evaluate(payload())

    assert first == second
    assert first["verdict"] == "PASS"
    assert first["confidence_interval_95"] == [1.0, 1.0]
    assert first["bootstrap_resamples"] == 10_000
    assert first["bootstrap_seed"] == 20_260_808


def test_missing_or_incomplete_pair_fails_closed_without_exclusion() -> None:
    incomplete = payload(29)
    incomplete["expected_pair_ids"] = [*incomplete["expected_pair_ids"], "pair-missing"]  # type: ignore[index]
    incomplete["pairs"][0]["telemetry_complete"] = False  # type: ignore[index]
    incomplete["pairs"][0]["target_false_completion"] = True  # type: ignore[index]

    result = module.evaluate(incomplete)

    assert result["verdict"] == "INCONCLUSIVE"
    assert result["completed_pairs"] == 29
    assert {
        "insufficient_pairs",
        "missing_or_unexpected_pair",
        "pair:pair-00:telemetry_incomplete",
        "pair:pair-00:target_success_without_quality_gate",
    }.issubset(result["violations"])
