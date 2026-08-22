from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


def evaluator():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts/evaluate-frontier-dominance-v2.py"
    spec = importlib.util.spec_from_file_location("frontier_dominance_v2", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontier_dominance_v2_passes_only_complete_real_evidence(tmp_path: Path) -> None:
    module = evaluator()
    evidence = tmp_path / "raw.json"
    evidence.write_text('{"hidden":"passed"}\n')
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    pairs = []
    for epoch in ("epoch-a", "epoch-b"):
        for index, client in enumerate(("raw_openai_compatible", "codex", "opencode", "hermes")):
            result = {
                "success": True,
                "false_completion": False,
                "verified_completion_seconds": 8.0,
                "tokens": 100,
                "cost_usd": 1.0,
                "evidence_path": evidence.name,
                "evidence_sha256": digest,
            }
            pairs.append(
                {
                    "epoch_id": epoch,
                    "epoch_manifest_sha256": "a" * 64 if epoch == "epoch-a" else "b" * 64,
                    "pair_id": f"{epoch}-{client}",
                    "comparator": "pinned-frontier",
                    "client": client,
                    "task_source": "repository",
                    "task_type": "implementation",
                    "language": "python",
                    "context_length_bucket": "short",
                    "paired_execution": True,
                    "isolated_workspace": True,
                    "hidden_validation": "external",
                    "validator_exposed": False,
                    "mock_provider_used": False,
                    "generated_patch_used": False,
                    "unintended_fallback_used": False,
                    "target": result,
                    "comparator_result": result
                    | {
                        "success": epoch == "epoch-a" and index == 0,
                        "verified_completion_seconds": 9.0,
                    },
                    "current_system": result | {"verified_completion_seconds": 10.0},
                }
            )
    payload = {
        "schema_version": "frontier-dominance-v2",
        "comparators": [{"id": "pinned-frontier", "revision_sha256": "c" * 64}],
        "pairs": pairs,
    }

    assert module.evaluate(payload, evidence_root=tmp_path)["verdict"] == "PASS"
    pairs[0]["target"]["false_completion"] = True
    result = module.evaluate(payload, evidence_root=tmp_path)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "pair:epoch-a-raw_openai_compatible:target_false_completion" in result["violations"]
