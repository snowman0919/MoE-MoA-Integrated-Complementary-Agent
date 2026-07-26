from __future__ import annotations

import json
import runpy
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/seal-frontier-confirmation.py"
MODULE = runpy.run_path(str(SCRIPT))


def test_attempt_plan_is_complete_deterministic_and_opaque() -> None:
    first, routes = MODULE["attempt_plan"]("confirm")
    second, second_routes = MODULE["attempt_plan"]("confirm")

    assert first == second
    assert routes == second_routes
    assert len(first) == 200
    assert len({row["attempt_id"] for row in first}) == 200
    assert set(routes.values()) == set(MODULE["RUNNER"]["HARNESSES"])
    assert all(row["variant"] not in MODULE["RUNNER"]["HARNESSES"] for row in first)
    assert {(row["repeat"], row["task"], row["variant"]) for row in first} == {
        (repeat, task.slug, label)
        for repeat in range(1, 11)
        for task in MODULE["RUNNER"]["TASKS"]
        for label in MODULE["OPAQUE_LABELS"]
    }


def test_breadth_attempt_plan_has_160_separate_attempts() -> None:
    configuration = MODULE["configure_panel"]("breadth")
    try:
        attempts, _routes = MODULE["attempt_plan"]("breadth")
        assert len(attempts) == 160
        assert {row["task"] for row in attempts} == {
            "scientific-meta-analysis",
            "scientific-decay-fit",
            "general-ranked-choice",
            "general-timezone-schedule",
        }
        assert configuration["bootstrap_seed"] == 56_052_027
    finally:
        MODULE["configure_panel"]("coding")


def test_exclusive_json_refuses_overwrite_and_protects_routing(tmp_path: Path) -> None:
    path = tmp_path / "routing.json"
    MODULE["exclusive_json"](path, {"secret": "mapping"}, mode=0o600)

    assert json.loads(path.read_text()) == {"secret": "mapping"}
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        MODULE["exclusive_json"](path, {"secret": "replacement"}, mode=0o600)


def test_created_seal_records_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    globals_ = MODULE["create_seal"].__globals__
    monkeypatch.setitem(globals_, "configure_panel", lambda _panel: None)
    monkeypatch.setitem(globals_, "repository_revision", lambda: "revision")
    monkeypatch.setitem(globals_, "attempt_plan", lambda _protocol: ([], {}))
    monkeypatch.setitem(globals_, "client_metadata", lambda: {})
    monkeypatch.setitem(globals_, "provider_fingerprints", lambda: {})
    monkeypatch.setitem(globals_, "container_image_digest", lambda: "image-digest")
    monkeypatch.setitem(globals_, "RUNNER", {"TASKS": (), "DOCKER_IMAGE": "test-image"})
    args = Namespace(
        panel="breadth",
        protocol_id="panel-metadata",
        output_root=tmp_path,
        workspace_root=tmp_path / "work",
        gateway="http://127.0.0.1:9000",
    )

    seal = MODULE["create_seal"](args)
    routing = json.loads((tmp_path / "panel-metadata/confirmation-routing.json").read_text())

    assert seal["panel"] == "breadth"
    assert routing["panel"] == "breadth"
