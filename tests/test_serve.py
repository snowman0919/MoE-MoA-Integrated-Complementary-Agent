from __future__ import annotations

import pytest
from dgx_moa.serve import command, role_bool_environment


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
