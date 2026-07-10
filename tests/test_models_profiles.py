from __future__ import annotations

import json
import sqlite3

import pytest
import yaml
from dgx_moa.model_download import classify_failure, verify_model
from dgx_moa.model_registry import estimate
from dgx_moa.profiles import ProfileManager


def valid_model(path) -> None:  # type: ignore[no-untyped-def]
    path.mkdir()
    (path / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["TestForCausalLM"],
                "quantization_config": {"quant_method": "test"},
            }
        )
    )
    (path / "tokenizer.json").write_text("{}")
    (path / "chat_template.jinja").write_text("{{ messages }}")
    (path / "model.safetensors").write_bytes(b"weight")
    (path / ".revision").write_text("abc\n")


def test_model_integrity_and_partial_download(tmp_path) -> None:  # type: ignore[no-untyped-def]
    model = tmp_path / "model"
    valid_model(model)
    assert verify_model(model)["status"] == "verified"
    (model / "shard.incomplete").write_bytes(b"partial")
    result = verify_model(model)
    assert result["status"] == "invalid"
    assert "incomplete files remain" in result["errors"][0]
    assert classify_failure(OSError(28, "No space left on device")) == "capacity-blocked"
    assert classify_failure(RuntimeError("401 gated repo")) == "authentication-blocked"


def test_storage_estimate_blocks_unsafe(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "models.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "hf_home": str(tmp_path / "cache"),
                "models": {
                    "executor": {
                        "repository": "test/model",
                        "revision": "abc",
                        "destination": str(tmp_path / "model"),
                        "classification": "official",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "dgx_moa.model_registry.inspect_repository",
        lambda repository, revision: {"download_size": 100, "revision": "abc"},
    )
    monkeypatch.setattr("dgx_moa.model_registry.cached_bytes", lambda repository, home: 0)
    monkeypatch.setattr(
        "dgx_moa.model_registry.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 100})(),
    )
    result = estimate(config, minimum_free=80)
    assert not result["safe"]


def test_storage_estimate_accepts_required_final_headroom(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "models.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "hf_home": str(tmp_path / "cache"),
                "models": {
                    "judge": {
                        "repository": "test/model",
                        "revision": "abc",
                        "destination": str(tmp_path / "model"),
                        "classification": "vendor-provided",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "dgx_moa.model_registry.inspect_repository",
        lambda repository, revision: {"download_size": 100, "revision": "abc"},
    )
    monkeypatch.setattr("dgx_moa.model_registry.cached_bytes", lambda repository, home: 0)
    monkeypatch.setattr(
        "dgx_moa.model_registry.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 180})(),
    )
    result = estimate(config, minimum_free=80)
    assert result["safe"]
    assert result["remaining_bytes"] == 80


def test_profile_state_and_failed_switch(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    manager = ProfileManager(tmp_path / "run", tmp_path)
    assert manager.current()["active_profile"] == "stopped"
    assert manager.current()["status"] == "stopped"
    manager.record("resident")
    assert manager.current()["active_profile"] == "resident"
    assert manager.transition("judge")["status"] == "transitioning"
    assert manager.current()["to"] == "judge"
    manager.record("resident")
    manager.record("stopped")
    monkeypatch.setattr(
        "dgx_moa.profiles.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )
    with pytest.raises(RuntimeError, match="startup failed"):
        manager.switch("judge")
    assert manager.current()["active_profile"] == "stopped"


def test_profile_checkpoint(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as database:
        database.execute("create table state(value text)")
        database.execute("insert into state values ('ok')")
    ProfileManager.checkpoint(path)
    with sqlite3.connect(path) as database:
        assert database.execute("select value from state").fetchone() == ("ok",)
