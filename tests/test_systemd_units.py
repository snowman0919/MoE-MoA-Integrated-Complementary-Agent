from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
SYSTEMD = ROOT / "systemd"


def test_required_systemd_units_exist() -> None:
    required = {
        "dgx-moa-gateway.service",
        "dgx-moa-executor.service",
        "dgx-moa-planner.service",
        "dgx-moa-reviewer.service",
        "dgx-moa-judge.service",
        "dgx-moa-resident.target",
        "dgx-moa-judge.target",
        "dgx-moa.target",
    }
    assert required == {path.name for path in SYSTEMD.iterdir()}


def test_targets_and_services_are_mutually_exclusive() -> None:
    resident = (SYSTEMD / "dgx-moa-resident.target").read_text()
    judge_target = (SYSTEMD / "dgx-moa-judge.target").read_text()
    judge = (SYSTEMD / "dgx-moa-judge.service").read_text()
    assert "Conflicts=dgx-moa-judge.target" in resident
    assert "Conflicts=dgx-moa-resident.target" in judge_target
    for role in ("executor", "planner", "reviewer"):
        service = (SYSTEMD / f"dgx-moa-{role}.service").read_text()
        assert "Conflicts=dgx-moa-judge.service dgx-moa-judge.target" in service
        assert f"dgx-moa-{role}.service" in judge
    assert "After=dgx-moa-executor.service" in (SYSTEMD / "dgx-moa-reviewer.service").read_text()
    assert "After=dgx-moa-reviewer.service" in (SYSTEMD / "dgx-moa-planner.service").read_text()


def test_unit_environment_and_hardening() -> None:
    for path in SYSTEMD.glob("*.service"):
        unit = path.read_text()
        assert "EnvironmentFile=/home/kotori9/dgx-moa-agent/.env" in unit
        assert "EnvironmentFile=-/home/kotori9/dgx-moa-agent/.env.local" in unit
        assert "NoNewPrivileges=true" in unit
        assert "PrivateTmp=true" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectHome=read-only" in unit
        assert "LockPersonality=true" in unit
        assert "RestrictSUIDSGID=true" in unit
        assert "Restart=on-failure" in unit
        assert "StartLimitIntervalSec=600" in unit
        assert "StartLimitBurst=3" in unit


def test_profile_switch_uses_systemd_and_lock() -> None:
    script = (ROOT / "scripts/switch-profile.sh").read_text()
    assert "flock -n" in script
    assert "systemctl --user start" in script
    assert "systemctl --user stop" in script
    assert "scripts/stop-model.sh" not in script
    assert "pkill" not in script
    assert "rollback" in script
