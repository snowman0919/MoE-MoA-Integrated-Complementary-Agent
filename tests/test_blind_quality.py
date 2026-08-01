from __future__ import annotations

import json

import pytest
from dgx_moa import blind_quality as MODULE


def valid_score() -> dict[str, object]:
    return {
        "contract_completeness": 28,
        "correctness_edge_cases": 22,
        "security_data_integrity": 18,
        "maintainability_diff_discipline": 13,
        "validation_evidence_discipline": 9,
        "total": 90,
        "findings": ["One bounded edge case remains."],
    }


def test_score_validation_requires_component_sum_and_bounds() -> None:
    result = MODULE.validate_score(valid_score())
    assert result["total"] == 90

    wrong_total = valid_score() | {"total": 89}
    with pytest.raises(ValueError, match="component sum"):
        MODULE.validate_score(wrong_total)

    out_of_range = valid_score() | {"security_data_integrity": 21, "total": 93}
    with pytest.raises(ValueError, match="out of range"):
        MODULE.validate_score(out_of_range)


def test_openrouter_schema_removes_only_numeric_constraints() -> None:
    schema = MODULE.openrouter_schema(MODULE.score_schema())
    encoded = str(schema)

    assert "minimum" not in encoded
    assert "maximum" not in encoded
    assert schema["additionalProperties"] is False
    assert schema["properties"]["findings"]["type"] == "array"


def test_blind_artifact_secret_scan_rejects_credential_like_values() -> None:
    MODULE.assert_sanitized({"candidate_source": "value = 'ordinary'"})
    with pytest.raises(ValueError, match="credential"):
        MODULE.assert_sanitized({"candidate_source": "api_key = 'visible-secret'"})


def test_artifact_payload_has_only_blinded_evidence() -> None:
    task = MODULE.SEAL_TOOL.configure_panel("coding").tasks[0]
    package = MODULE.artifact_payload(
        {
            "attempt_id": "confirm-a001",
            "repeat": 1,
            "variant": "variant-a",
        },
        task,
        "starter",
        "candidate",
        {"hidden": True, "public": True},
    )

    assert set(package) == {
        "schema_version",
        "attempt_id",
        "repeat",
        "task",
        "variant",
        "contract",
        "starter_source",
        "candidate_source",
        "functional_checks",
    }
    assert not {"provider", "model", "route", "latency", "cost", "tokens"} & set(package)


def test_hard_gate_rejects_missing_cache_or_gpu_memory() -> None:
    score = {
        "status": "passed",
        "telemetry": {
            "complete": True,
            "provider_pinned": True,
            "provider_switches": 0,
            "provider_errors": 0,
            "remote_cost_complete": True,
            "remote_cost_usd": 0.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cached_tokens": 0,
            "retryable_failures": 0,
        },
        "resources": {
            phase: {
                "gpu_memory_used_bytes": 1,
                "gpu_memory_source": "cudaMemGetInfo",
                "host_memory_used_bytes": 2,
                "swap_used_bytes": 0,
            }
            for phase in ("before", "after")
        },
    }

    assert MODULE.hard_gate_pass("opencode", score)
    score["telemetry"]["cached_tokens"] = None
    assert not MODULE.hard_gate_pass("opencode", score)
    score["telemetry"]["cached_tokens"] = 0
    score["resources"]["after"]["gpu_memory_used_bytes"] = None
    assert not MODULE.hard_gate_pass("opencode", score)
    assert MODULE.hard_gate_pass("baseline", {"status": "passed"})


def test_secondary_selection_is_stratified_and_adds_large_difference_pairs() -> None:
    seal_module = MODULE.SEAL_TOOL
    attempts, routes = seal_module.attempt_plan("confirm")
    seal = {"attempts": attempts}
    routing = {"variant_routes": {label: {"harness": harness} for label, harness in routes.items()}}
    primary = {
        row["attempt_id"]: {
            "score": {
                "total": (
                    70
                    if routes[row["variant"]] == "baseline"
                    else 90
                    if row["repeat"] == 1 and row["task"] == "rate-limiter"
                    else 72
                )
            }
        }
        for row in attempts
    }

    selected = MODULE.initial_secondary_ids(seal, routing, primary)

    assert len(selected) >= 40
    baseline_label = next(label for label, harness in routes.items() if harness == "baseline")
    baseline_id = next(
        row["attempt_id"]
        for row in attempts
        if row["repeat"] == 1 and row["task"] == "rate-limiter" and row["variant"] == baseline_label
    )
    assert baseline_id in selected


def test_judge_prompt_does_not_add_provider_or_route_metadata() -> None:
    package = {
        "variant": "variant-a",
        "contract": "Return one.",
        "candidate_source": "def one(): return 1",
    }
    prompt = MODULE.judge_prompt(package)

    assert "variant-a" in prompt
    assert "opencode" not in prompt.lower()
    assert "hermes" not in prompt.lower()
    assert "gpt-5.6-sol" not in prompt.lower()
    assert "hidden reasoning" in prompt


def test_secondary_score_pins_bedrock_and_parses_accounting(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {}
    response = {
        "provider": "Amazon Bedrock",
        "choices": [{"message": {"content": json.dumps(valid_score())}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.01},
    }

    class FakeResponse:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return json.dumps(response).encode()

    def urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured.update(json.loads(request.data))
        assert timeout == 30
        return FakeResponse()

    monkeypatch.setattr(MODULE.urllib.request, "urlopen", urlopen)
    score, accounting = MODULE.secondary_score(
        {"variant": "variant-a"}, key="synthetic", timeout=30
    )

    assert captured["provider"] == {
        "only": ["amazon-bedrock"],
        "allow_fallbacks": False,
    }
    assert captured["reasoning"] == {"effort": "high", "exclude": True}
    assert score["total"] == 90
    assert accounting == {
        "provider": "Amazon Bedrock",
        "input_tokens": 10,
        "output_tokens": 20,
        "cost_usd": 0.01,
    }
