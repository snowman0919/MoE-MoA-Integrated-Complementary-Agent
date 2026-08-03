from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.serve import KV_CACHE, command, role_bool_environment, role_context_length


def test_role_boolean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGX_MOA_EXECUTOR_ENFORCE_EAGER", "yes")
    assert role_bool_environment("executor", "ENFORCE_EAGER") is True


def test_invalid_role_boolean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGX_MOA_EXECUTOR_ENFORCE_EAGER", "sometimes")
    with pytest.raises(ValueError, match="must be one of"):
        role_bool_environment("executor", "ENFORCE_EAGER")


def test_role_kv_cache_environment(settings, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DGX_MOA_JUDGE_KV_CACHE_MEMORY_BYTES", "750000000")
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    arguments = command("judge")
    assert arguments[arguments.index("--kv-cache-memory-bytes") + 1] == "750000000"


def test_reasoner_uses_loopback_64k_context(settings, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    arguments = command("reasoner")
    assert arguments[arguments.index("--port") + 1] == "8104"
    assert arguments[arguments.index("--max-model-len") + 1] == "65536"


def test_reviewer_uses_calibrated_kv_reservation() -> None:
    assert KV_CACHE == {
        "executor": 1_700_000_000,
        "planner": 600_000_000,
        "reviewer": 2_300_000_000,
        "reasoner": 2_450_000_000,
        "judge": 4_000_000_000,
    }


def test_explicit_context_environment_overrides_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", "16384")
    assert role_context_length("executor", 65536) == "16384"


def test_configured_context_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", raising=False)
    assert role_context_length("executor", 65536) == "65536"


def test_executor_defaults_to_exact_vllm_restore_path(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    monkeypatch.delenv("DGX_MOA_EXECUTOR_BACKEND", raising=False)
    arguments = command("executor")

    assert arguments[1] == "serve"
    assert arguments[arguments.index("--max-model-len") + 1] == "65536"
    assert arguments[arguments.index("--max-num-seqs") + 1] == "1"
    assert arguments[arguments.index("--kv-cache-memory-bytes") + 1] == "1700000000"
    assert arguments[arguments.index("--gpu-memory-utilization") + 1] == "0.5"
    assert arguments[arguments.index("--moe-backend") + 1] == "MARLIN"


def test_executor_sglang_candidate_keeps_loopback_context_and_radix_cache(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    executor = settings.models["executor"].model_copy(
        update={"quantization": "compressed-tensors", "tool_call_parser": "qwen3_coder"}
    )
    controlled = settings.model_copy(update={"models": {**settings.models, "executor": executor}})
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: controlled)
    monkeypatch.setenv("DGX_MOA_EXECUTOR_BACKEND", "sglang")
    arguments = command("executor")

    assert arguments[:3] == [
        str(Path("~/.pyenv/shims/sglang").expanduser()),
        "serve",
        "--model-path",
    ]
    assert arguments[arguments.index("--host") + 1] == "127.0.0.1"
    assert arguments[arguments.index("--context-length") + 1] == "65536"
    assert arguments[arguments.index("--mem-fraction-static") + 1] == "0.6"
    assert arguments[arguments.index("--max-running-requests") + 1] == "1"
    assert arguments[arguments.index("--max-total-tokens") + 1] == "65536"
    assert arguments[arguments.index("--max-mamba-cache-size") + 1] == "16"
    assert arguments[arguments.index("--quantization") + 1] == "compressed-tensors"
    assert arguments[arguments.index("--tool-call-parser") + 1] == "qwen3_coder"
    assert "--disable-radix-cache" not in arguments


def test_executor_rejects_unknown_backend(settings, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    monkeypatch.setenv("DGX_MOA_EXECUTOR_BACKEND", "unknown")

    with pytest.raises(ValueError, match="unsupported executor backend"):
        command("executor")
