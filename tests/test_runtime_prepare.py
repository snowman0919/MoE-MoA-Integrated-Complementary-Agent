from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from dgx_moa.runtime_prepare import (
    MODELOPT_REVISION,
    apply_runtime,
    build_overlay,
    conversion_command,
    fingerprint,
    lifecycle_phase,
    parse_sglang_memory,
    reusable_smoke,
    runtime_sglang_command,
    update_environment,
    validate_hf_files,
    verify_snapshot,
    wait_lifecycle,
)

ROOT = Path(__file__).parents[1]


def write_runtime_overlay(path: Path) -> dict[str, object]:
    overlay = build_overlay(
        yaml.safe_load((ROOT / "config/models.yaml").read_text()),
        alias="qwen3.8-27b",
        source={"repo_id": "owner/model", "revision": "a" * 40},
        destination=path.parent / "nvfp4",
        draft_revision="b" * 40,
        draft_destination=path.parent / "draft",
        speculative_enabled=True,
    )
    path.write_text(yaml.safe_dump(overlay))
    return overlay["local_models"]["qwen3.8-27b"]


def test_checkpoint_contracts_and_fingerprint_are_deterministic(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="complete checkpoint"):
        validate_hf_files({".gitattributes"})
    validate_hf_files({"config.json", "tokenizer.json", "model.safetensors"})
    validate_hf_files(
        {"config.json", "model.safetensors"},
        require_tokenizer=False,
    )
    draft = tmp_path / "draft"
    draft.mkdir()
    (draft / "config.json").write_text("{}")
    (draft / "model.safetensors").write_bytes(b"weights")
    assert verify_snapshot(draft, draft=True)["status"] == "verified"
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})


def test_overlay_enables_pinned_local_dspark_without_mutating_base(tmp_path: Path) -> None:
    base = yaml.safe_load((ROOT / "config/models.yaml").read_text())
    overlay = build_overlay(
        base,
        alias="qwen3.8-27b",
        source={"repo_id": "owner/model", "revision": "a" * 40},
        destination=tmp_path / "nvfp4",
        draft_revision="b" * 40,
        draft_destination=tmp_path / "draft",
        speculative_enabled=True,
        torch_compile=True,
    )
    model = overlay["local_models"]["qwen3.8-27b"]
    assert model["repository"] == "owner/model"
    assert model["quantization"] == "modelopt_fp4"
    assert model["runtime_validated"] is True
    assert model["disable_flashinfer_autotune"] is True
    assert model["gpu_memory_utilization"] == 0.35
    assert model["max_total_tokens"] == 270_000
    assert model["max_mamba_cache_size"] == 5
    assert model["chunked_prefill_size"] == 4_096
    assert model["disable_prefill_cuda_graph"] is True
    assert model["disable_decode_cuda_graph"] is True
    assert model["enable_torch_compile"] is True
    assert model["torch_compile_max_bs"] == 4
    assert model["skip_server_warmup"] is True
    assert model["watchdog_timeout"] == 1_800
    assert model["speculative"] == {
        "enabled": True,
        "method": "dspark",
        "model": str(tmp_path / "draft"),
        "revision": "b" * 40,
        "num_speculative_tokens": 8,
        "draft_attention_backend": "flashinfer",
        "draft_quantization": "unquant",
        "num_continuous_decode_steps": 2,
    }
    assert base["local_models"]["qwen3.8-27b"]["runtime_validated"] is False

    from dgx_moa.config import ModelConfig

    command = runtime_sglang_command(
        tmp_path / "runtime/bin/python", ModelConfig.model_validate(model)
    )
    assert command[0] == str(tmp_path / "runtime/bin/python")
    assert "--disable-flashinfer-autotune" in command
    assert "--disable-prefill-cuda-graph" in command
    assert "--disable-decode-cuda-graph" in command
    assert "--enable-torch-compile" in command
    assert command[command.index("--torch-compile-max-bs") + 1] == "4"
    assert "--skip-server-warmup" in command
    assert command[command.index("--watchdog-timeout") + 1] == "1800.0"
    assert command[command.index("--max-total-tokens") + 1] == "270000"
    assert command[command.index("--max-mamba-cache-size") + 1] == "5"


def test_reusable_smoke_normalizes_new_inert_schema_defaults(tmp_path: Path) -> None:
    from dgx_moa.config import ModelConfig

    raw = yaml.safe_load((ROOT / "config/models.yaml").read_text())
    overlay = build_overlay(
        raw,
        alias="qwen3.8-27b",
        source={"repo_id": "owner/model", "revision": "a" * 40},
        destination=tmp_path / "nvfp4",
        draft_revision="b" * 40,
        draft_destination=tmp_path / "draft",
        speculative_enabled=False,
    )
    model = ModelConfig.model_validate(overlay["local_models"]["qwen3.8-27b"])
    profile = model.model_dump(mode="json")
    profile["speculative"].pop("draft_quantization")
    profile["speculative"].pop("num_continuous_decode_steps")
    evidence = tmp_path / "smoke.json"
    evidence.write_text(
        json.dumps(
            {
                "status": "verified",
                "profile": profile,
                "jit_compile_workers": 1,
                "context_stages": [{"target_tokens": 1_024}],
                "memory": {"minimum_system_available_bytes": 30 * 1024**3},
            }
        )
    )

    assert reusable_smoke(evidence, model, (1_024,), 20 * 1024**3) is not None


def test_sglang_memory_parser_separates_target_draft_kv_and_recurrent_state(
    tmp_path: Path,
) -> None:
    log = tmp_path / "sglang.log"
    log.write_text(
        "Load weight end. elapsed=1 s, mem usage=19.16 GB.\n"
        "Load weight end. elapsed=1 s, mem usage=3.05 GB.\n"
        "Mamba Cache is allocated. max_mamba_cache_size: 5, conv_state size: 0.02GB, "
        "ssm_state size: 0.84GB intermediate_ssm_state_cache size: 2.25GB "
        "intermediate_conv_window_cache size: 0.02GB\n"
        "KV Cache is allocated. dtype: fp8, #tokens: 270000, K size: 4.12 GB, "
        "V size: 4.12 GB\n"
        "KV Cache is allocated. dtype: fp8, #tokens: 270000, K size: 1.29 GB, "
        "V size: 1.29 GB\n"
    )

    assert parse_sglang_memory(log) == {
        "weight_memory_gb": 19.16,
        "target_weight_memory_gb": 19.16,
        "draft_weight_memory_gb": 3.05,
        "total_weight_memory_gb": 22.21,
        "mamba_slots": 5,
        "mamba_conv_gb": 0.02,
        "mamba_ssm_gb": 0.84,
        "mamba_intermediate_ssm_gb": 2.25,
        "mamba_intermediate_conv_gb": 0.02,
        "mamba_total_gb": 3.13,
        "kv_token_capacity": 270000,
        "kv_k_gb": 4.12,
        "kv_v_gb": 4.12,
        "target_kv_token_capacity": 270000,
        "target_kv_k_gb": 4.12,
        "target_kv_v_gb": 4.12,
        "draft_kv_token_capacity": 270000,
        "draft_kv_k_gb": 1.29,
        "draft_kv_v_gb": 1.29,
        "kv_total_gb": 10.82,
    }


def test_conversion_command_is_pinned_nvfp4_recipe(tmp_path: Path) -> None:
    command = conversion_command(
        tmp_path / "venv/bin/python",
        tmp_path / "modelopt",
        tmp_path / "source",
        tmp_path / "target",
        calibration_dataset="cnn_dailymail",
        calibration_size=128,
    )
    assert "general/ptq/nvfp4_default-kv_fp8_cast" in command
    assert command[command.index("--dataset") + 1] == "cnn_dailymail"
    assert command[command.index("--calib_size") + 1] == "128"
    assert command[-1] == "--trust_remote_code"
    assert len(MODELOPT_REVISION) == 40


def test_environment_update_is_idempotent_and_preserves_secrets() -> None:
    original = "API_SECRET=keep-me\nDGX_MOA_CONFIG=/old\n"
    values = {"DGX_MOA_CONFIG": "/new", "SGLANG_PYTHON": "/runtime/python"}
    updated = update_environment(original, values)
    assert update_environment(updated, values) == updated
    assert "API_SECRET=keep-me" in updated
    assert updated.count("DGX_MOA_CONFIG=") == 1


def test_apply_gate_reads_public_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dgx_moa.runtime_prepare.request_json",
        lambda *_args, **_kwargs: {"data": [{"role": "executor", "runtime_state": "READY"}]},
    )

    assert lifecycle_phase("http://127.0.0.1:9000", "token", "executor") == "READY"
    wait_lifecycle("http://127.0.0.1:9000", "token", "executor", "READY", 0.1)


def test_apply_restores_environment_when_ready_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text("KEEP=value\n")
    write_runtime_overlay(tmp_path / "runtime.yaml")
    calls: list[str] = []
    monkeypatch.setenv("DGX_MOA_ADMIN_API_KEY", "not-persisted")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setattr(
        "dgx_moa.runtime_prepare.request_json",
        lambda url, **_kwargs: calls.append(url) or {},
    )
    checks = iter((None, RuntimeError("load failed"), None))

    def wait(*_args: object, **_kwargs: object) -> None:
        result = next(checks)
        if isinstance(result, Exception):
            raise result

    monkeypatch.setattr("dgx_moa.runtime_prepare.wait_lifecycle", wait)
    with pytest.raises(RuntimeError, match="load failed"):
        apply_runtime(
            env_file,
            tmp_path / "runtime.yaml",
            tmp_path / "venv/bin/python",
            admin_url="http://127.0.0.1:9000",
            role="executor",
            timeout=1,
        )
    assert env_file.read_text() == "KEEP=value\n"
    assert len(calls) == 3
    assert "not-persisted" not in env_file.read_text()


def test_apply_is_noop_when_same_runtime_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env.local"
    overlay = tmp_path / "runtime.yaml"
    runtime_python = tmp_path / "venv/bin/python"
    model = write_runtime_overlay(overlay)
    desired = update_environment(
        "KEEP=value\n",
        {
            "DGX_MOA_CONFIG": str(overlay),
            "SGLANG_PYTHON": str(runtime_python),
            "DGX_MOA_EXECUTOR_MAX_MODEL_LEN": str(model["context_length"]),
            "DGX_MOA_EXECUTOR_GPU_MEMORY_UTILIZATION": str(model["gpu_memory_utilization"]),
            "DGX_MOA_MAX_NUM_SEQS": str(model["max_num_seqs"]),
            "MAX_JOBS": "1",
            "FLASHINFER_MM_FP4_CUTE_DSL_COMPILE_WORKERS": "1",
        },
    )
    env_file.write_text(desired)
    monkeypatch.setenv("DGX_MOA_ADMIN_API_KEY", "not-persisted")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setattr("dgx_moa.runtime_prepare.lifecycle_phase", lambda *_args: "READY")
    monkeypatch.setattr(
        "dgx_moa.runtime_prepare.request_json",
        lambda *_args, **_kwargs: pytest.fail("idempotent apply made an API request"),
    )

    apply_runtime(
        env_file,
        overlay,
        runtime_python,
        admin_url="http://127.0.0.1:9000",
        role="executor",
        timeout=1,
    )

    assert env_file.read_text() == desired
