from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.config import ModelConfig, Settings, load_settings, parse_bool
from pydantic import ValidationError


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on", True, 1])
def test_true_boolean_forms(value) -> None:  # type: ignore[no-untyped-def]
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", False, 0])
def test_false_boolean_forms(value) -> None:  # type: ignore[no-untyped-def]
    assert parse_bool(value) is False


def test_invalid_boolean_rejected(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "sometimes")
    monkeypatch.setenv("DGX_MOA_API_KEY", "valid-test-token")
    with pytest.raises(ValidationError, match="must be one of"):
        load_settings(config)


def test_auth_enabled_requires_real_key() -> None:
    with pytest.raises(ValidationError, match="DGX_MOA_API_KEY"):
        Settings(auth_enabled=True, api_key=None)
    with pytest.raises(ValidationError, match="non-placeholder"):
        Settings(auth_enabled=True, api_key="replace-with-a-long-random-token")


def test_auth_disabled_allows_missing_key() -> None:
    settings = Settings(auth_enabled=False, api_key=None)
    assert settings.api_key is None


def test_bind_environment_overrides(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.delenv("DGX_MOA_API_KEY", raising=False)
    monkeypatch.setenv("DGX_MOA_BIND_HOST", "100.64.1.2")
    monkeypatch.setenv("DGX_MOA_BIND_PORT", "9100")
    settings = load_settings(config)
    assert settings.bind_host == "100.64.1.2"
    assert settings.bind_port == 9100


def test_model_context_requires_64k(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 65536"):
        ModelConfig(
            repository="test/model",
            revision="abc",
            classification="test",
            base_url="http://127.0.0.1:8104",
            served_name="test",
            destination=tmp_path / "model",
            context_length=65_535,
        )
