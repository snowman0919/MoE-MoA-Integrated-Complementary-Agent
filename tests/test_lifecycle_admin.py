from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


def test_atomic_disable_is_idempotent_and_preserves_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dgx_moa.lifecycle_admin import atomic_disable_lifecycle

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "auth_enabled": False,
                    "lifecycle_mode": "adaptive",
                    "lifecycle_unit_map": {"planner": "dgx-moa-dev-planner.service"},
                    "state_db": str(tmp_path / "state.db"),
                    "unrelated": "preserved",
                },
                "models": {},
            }
        )
    )
    evidence = tmp_path / "evidence.db"
    evidence.write_bytes(b"sqlite-evidence")
    monkeypatch.delenv("DGX_MOA_LIFECYCLE_MODE", raising=False)
    monkeypatch.delenv("DGX_MOA_LIFECYCLE_UNIT_MAP", raising=False)

    atomic_disable_lifecycle(config)
    atomic_disable_lifecycle(config)

    loaded = yaml.safe_load(config.read_text())
    assert loaded["gateway"]["lifecycle_mode"] == "disabled"
    assert loaded["gateway"]["lifecycle_unit_map"] == {}
    assert loaded["gateway"]["unrelated"] == "preserved"
    assert evidence.read_bytes() == b"sqlite-evidence"
    assert config.stat().st_mode & 0o777 == 0o600


def test_invalid_atomic_disable_leaves_original_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dgx_moa.lifecycle_admin import atomic_disable_lifecycle

    config = tmp_path / "invalid.yaml"
    original = b"gateway: []\nmodels: {}\n"
    config.write_bytes(original)
    replacements: list[tuple[object, object]] = []
    real_replace = os.replace

    def record_replace(source: object, target: object) -> None:
        replacements.append((source, target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", record_replace)

    with pytest.raises(ValueError):
        atomic_disable_lifecycle(config)

    assert config.read_bytes() == original
    assert replacements == []


def test_environment_override_prevents_atomic_rollback_without_replacing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dgx_moa.lifecycle_admin import atomic_disable_lifecycle

    config = tmp_path / "config.yaml"
    original = b"gateway:\n  auth_enabled: false\n  lifecycle_mode: adaptive\nmodels: {}\n"
    config.write_bytes(original)
    monkeypatch.setenv("DGX_MOA_LIFECYCLE_MODE", "adaptive")

    with pytest.raises(ValueError, match="environment overrides"):
        atomic_disable_lifecycle(config)

    assert config.read_bytes() == original
    assert list(tmp_path.glob(".config.yaml.*.tmp")) == []


def test_rollback_resets_circuit_without_deleting_failure_history(tmp_path: Path) -> None:
    from dgx_moa.lifecycle import LifecycleStore
    from dgx_moa.lifecycle_admin import rollback

    state_db = tmp_path / "state.db"
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "auth_enabled": False,
                    "state_db": str(state_db),
                    "lifecycle_mode": "adaptive",
                    "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
                },
                "models": {},
            }
        )
    )
    store = LifecycleStore(state_db, ("executor",), clock=lambda: 100.0)
    for index in range(3):
        store.record_failure(
            "executor",
            "injected_start",
            f"injected_{index}",
            0,
            failure_limit=3,
            failure_window_seconds=900,
        )
    assert store.automation_status().automation_disabled is True

    rollback(config)

    assert store.automation_status().automation_disabled is False
    assert store.automation_status().failure_count == 0
    assert len(store.recent_failure_events()) == 3


def test_rollback_wrapper_has_fixed_order_and_no_dynamic_service_input() -> None:
    script = Path("scripts/rollback-lifecycle.sh").read_text()

    ordered = (
        '.venv/bin/python -m dgx_moa.lifecycle_admin rollback --config "$config"',
        "systemctl --user restart dgx-moa-gateway.service",
        "scripts/switch-profile.sh resident",
        "scripts/healthcheck.sh",
        'curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY:?}"',
    )
    positions = [script.index(command) for command in ordered]
    assert positions == sorted(positions)
    assert "eval " not in script
    assert 'systemctl --user restart "$' not in script
    assert "rm -" not in script
