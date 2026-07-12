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
        "dgx-moa-reasoner.service",
        "dgx-moa-judge.service",
        "dgx-moa-resident.target",
        "dgx-moa-judge.target",
        "dgx-moa.target",
        "dgx-moa-codex-frontier@.service",
    }
    assert required == {path.name for path in SYSTEMD.iterdir()}


def test_targets_and_services_are_mutually_exclusive() -> None:
    resident = (SYSTEMD / "dgx-moa-resident.target").read_text()
    judge_target = (SYSTEMD / "dgx-moa-judge.target").read_text()
    judge = (SYSTEMD / "dgx-moa-judge.service").read_text()
    assert "Conflicts=dgx-moa-judge.target" in resident
    assert "Conflicts=dgx-moa-resident.target" in judge_target
    for role in ("executor", "planner", "reviewer", "reasoner"):
        service = (SYSTEMD / f"dgx-moa-{role}.service").read_text()
        assert "Conflicts=dgx-moa-judge.service dgx-moa-judge.target" in service
        assert f"dgx-moa-{role}.service" in judge
    assert "After=dgx-moa-executor.service" in (SYSTEMD / "dgx-moa-reviewer.service").read_text()
    assert "After=dgx-moa-reviewer.service" in (SYSTEMD / "dgx-moa-planner.service").read_text()
    assert "After=dgx-moa-planner.service" in (SYSTEMD / "dgx-moa-reasoner.service").read_text()


def test_unit_environment_and_hardening() -> None:
    for path in SYSTEMD.glob("dgx-moa-*.service"):
        unit = path.read_text()
        if "codex-frontier" not in path.name:
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


def test_frontier_unit_has_no_repository_credentials() -> None:
    unit = (SYSTEMD / "dgx-moa-codex-frontier@.service").read_text()
    assert "EnvironmentFile=" not in unit
    assert "CODEX_HOME" not in unit
    assert "ExecStart=" in unit and "%i" in unit
