from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from dgx_moa import confirmation_seal as MODULE


def test_attempt_plan_is_complete_deterministic_and_opaque() -> None:
    config = MODULE.configure_panel("coding")
    first, routes = MODULE.attempt_plan("confirm")
    second, second_routes = MODULE.attempt_plan("confirm")

    assert first == second
    assert routes == second_routes
    assert len(first) == 200
    assert len({row["attempt_id"] for row in first}) == 200
    assert set(routes.values()) == set(config.runner.HARNESSES)
    assert all(row["variant"] not in config.runner.HARNESSES for row in first)
    assert {(row["repeat"], row["task"], row["variant"]) for row in first} == {
        (repeat, task.slug, label)
        for repeat in range(1, 11)
        for task in config.tasks
        for label in MODULE.OPAQUE_LABELS
    }


def test_breadth_attempt_plan_has_160_separate_attempts() -> None:
    configuration = MODULE.configure_panel("breadth")
    attempts, _routes = MODULE.attempt_plan("breadth", configuration)

    assert len(attempts) == 160
    assert {row["task"] for row in attempts} == {
        "scientific-meta-analysis",
        "scientific-decay-fit",
        "general-ranked-choice",
        "general-timezone-schedule",
    }
    assert configuration.bootstrap_seed == 56_052_027
    assert len(MODULE.attempt_plan("coding")[0]) == 200
    with pytest.raises(TypeError):
        configuration.task_by_slug["replacement"] = configuration.tasks[0]  # type: ignore[index]


def test_exclusive_json_refuses_overwrite_and_protects_routing(tmp_path: Path) -> None:
    path = tmp_path / "routing.json"
    MODULE.exclusive_json(path, {"secret": "mapping"}, mode=0o600)

    assert json.loads(path.read_text()) == {"secret": "mapping"}
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        MODULE.exclusive_json(path, {"secret": "replacement"}, mode=0o600)


def test_created_seal_records_panel(tmp_path: Path) -> None:
    runner = SimpleNamespace(DOCKER_IMAGE="test-image", prompt=lambda _task: "")
    config = MODULE.PanelConfig(
        "breadth",
        56_052_027,
        runner,
        (),
        {},
        Path(MODULE.__file__),
        Path(MODULE.__file__),
    )
    backend = MODULE.SealBackend(
        configure_panel=lambda _panel: config,
        repository_revision=lambda: "revision",
        attempt_plan=lambda _protocol, _config: ([], {}),
        client_metadata=lambda _config: {},
        provider_fingerprints=lambda _config: {},
        container_image_digest=lambda _config: "image-digest",
    )
    args = Namespace(
        panel="breadth",
        protocol_id="panel-metadata",
        output_root=tmp_path,
        workspace_root=tmp_path / "work",
        gateway="http://127.0.0.1:9000",
    )

    seal = MODULE.create_seal(args, backend=backend)
    routing = json.loads((tmp_path / "panel-metadata/confirmation-routing.json").read_text())

    assert seal["panel"] == "breadth"
    assert routing["panel"] == "breadth"
