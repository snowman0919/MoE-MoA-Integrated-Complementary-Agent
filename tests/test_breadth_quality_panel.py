from __future__ import annotations

import runpy
from argparse import Namespace
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/run-breadth-quality-panel.py"
PROTOCOL = Path(__file__).parents[1] / "docs/QUALITY_EVALUATION.md"
MODULE = runpy.run_path(str(SCRIPT))


def test_breadth_panel_is_frozen_and_separate_from_coding_panel() -> None:
    tasks = MODULE["TASKS"]
    slugs = {task.slug for task in tasks}

    assert len(tasks) == 4
    assert sum(slug.startswith("scientific-") for slug in slugs) == 2
    assert sum(slug.startswith("general-") for slug in slugs) == 2
    assert not slugs & {task.slug for task in MODULE["CODING_TASKS"]}
    assert set(MODULE["HIDDEN_CHECKS"]) == slugs
    assert MODULE["BASE"]["main"].__globals__["TASKS"] == tasks


def test_breadth_starters_fail_without_touching_base_runner(tmp_path: Path) -> None:
    args = Namespace(
        run_id="breadth-starters",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
        gateway="http://127.0.0.1:19300",
    )

    for task in MODULE["TASKS"]:
        manifest = MODULE["BASE"]["prepare_one"](args, "baseline", task)
        assert manifest["starter_test_exit"] != 0
        assert Path(manifest["workspace"], task.source_name).is_file()


def test_breadth_protocol_freezes_sample_and_category_verdicts() -> None:
    protocol = PROTOCOL.read_text()

    assert "160 total" in protocol
    assert "ten matched repeats per variant" in protocol
    assert "`56052027`" in protocol
    assert "Scientific and General must each independently pass" in protocol
