from __future__ import annotations

import pytest
from dgx_moa.config import SpeculativeConfig
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
        "executor": 3_400_000_000,
        "planner": 600_000_000,
        "reviewer": 2_300_000_000,
        "reasoner": 2_450_000_000,
        "judge": 4_000_000_000,
    }


def test_executor_defaults_to_qualified_128k_profile(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DGX_MOA_EXECUTOR_MOE_BACKEND", raising=False)
    monkeypatch.delenv("DGX_MOA_EXECUTOR_LINEAR_BACKEND", raising=False)
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    settings.models["executor"].context_length = 131072
    settings.models["executor"].base_url = "http://127.0.0.1:9001"
    arguments = command("executor")
    assert arguments[arguments.index("--port") + 1] == "9001"
    assert arguments[arguments.index("--max-model-len") + 1] == "131072"
    assert arguments[arguments.index("--kv-cache-memory-bytes") + 1] == "3400000000"
    assert "--linear-backend" not in arguments
    assert arguments[arguments.index("--moe-backend") + 1] == "flashinfer_b12x"
    assert arguments[arguments.index("--attention-backend") + 1] == "TRITON_MLA"
    assert arguments[arguments.index("--safetensors-load-strategy") + 1] == "lazy"
    assert arguments[arguments.index("--compilation-config") + 1] == (
        '{"cudagraph_mode":"FULL_DECODE_ONLY"}'
    )
    assert "--enforce-eager" not in arguments


def test_executor_marlin_rollback_is_explicit(settings, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DGX_MOA_EXECUTOR_LINEAR_BACKEND", "MARLIN")
    monkeypatch.setenv("DGX_MOA_EXECUTOR_MOE_BACKEND", "MARLIN")
    monkeypatch.setenv("DGX_MOA_EXECUTOR_COMPILATION_CONFIG", '{"cudagraph_mode":"NONE"}')
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    arguments = command("executor")
    assert arguments[arguments.index("--linear-backend") + 1] == "MARLIN"
    assert arguments[arguments.index("--moe-backend") + 1] == "MARLIN"
    assert arguments[arguments.index("--compilation-config") + 1] == ('{"cudagraph_mode":"NONE"}')


def test_explicit_context_environment_overrides_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", "16384")
    assert role_context_length("executor", 65536) == "16384"


def test_configured_context_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", raising=False)
    assert role_context_length("executor", 65536) == "65536"


def test_sglang_executor_command_is_loopback_single_sequence_and_dspark_disabled(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    model = settings.models["executor"]
    model.engine = "sglang"
    model.context_length = 262144
    model.quantization = "modelopt_fp4"
    model.attention_backend = "flashinfer"
    model.kv_cache_dtype = "fp8_e4m3"
    model.gpu_memory_utilization = 0.5
    model.cuda_graph_max_bs = 1
    model.reasoning_parser = "qwen3"
    model.tool_call_parser = "qwen3_coder"
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)

    arguments = command("executor")

    assert arguments[arguments.index("--host") + 1] == "127.0.0.1"
    assert arguments[arguments.index("--context-length") + 1] == "262144"
    assert arguments[arguments.index("--max-running-requests") + 1] == "1"
    assert arguments[arguments.index("--mem-fraction-static") + 1] == "0.5"
    assert "--speculative-algorithm" not in arguments


def test_sglang_dspark_command_requires_and_passes_pinned_measured_config(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    model = settings.models["executor"]
    model.engine = "sglang"
    model.speculative = SpeculativeConfig(
        enabled=True,
        method="dspark",
        model="vendor/qwen-dspark",
        revision="draft-sha",
        num_speculative_tokens=8,
        draft_attention_backend="flashinfer",
        draft_quantization="unquant",
        num_continuous_decode_steps=2,
    )
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)

    arguments = command("executor")

    assert arguments[arguments.index("--speculative-algorithm") + 1] == "DSPARK"
    assert arguments[arguments.index("--speculative-draft-model-revision") + 1] == "draft-sha"
    assert arguments[arguments.index("--speculative-draft-model-quantization") + 1] == "unquant"
    assert arguments[arguments.index("--speculative-dspark-block-size") + 1] == "7"
    assert arguments[arguments.index("--num-continuous-decode-steps") + 1] == "2"
