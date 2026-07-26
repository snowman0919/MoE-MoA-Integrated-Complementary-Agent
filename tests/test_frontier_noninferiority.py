from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze-frontier-noninferiority.py"
MODULE = runpy.run_path(str(SCRIPT))


def write_panel(path: Path, *, failed: tuple[str, str, str] | None = None) -> None:
    rows = []
    for repeat in ("r1", "r2"):
        for task in MODULE["TASKS"]:
            for variant in MODULE["VARIANTS"]:
                passed = (repeat, task, variant) != failed
                rows.append(
                    {
                        "repeat": repeat,
                        "task": task,
                        "variant": variant,
                        "passed": passed,
                        "telemetry_complete": True,
                        "quality_score": 90 if passed else None,
                        "duration_seconds": 10 if variant == "baseline" else 11,
                        "variable_cost_usd": 0,
                    }
                )
    path.write_text("\n".join(map(json.dumps, rows)) + "\n")


def test_analyzer_requires_complete_panel_and_preserves_failures(tmp_path: Path) -> None:
    attempts = tmp_path / "attempts.jsonl"
    write_panel(attempts)

    result = MODULE["analyze"](attempts, repeats=2, bootstrap_samples=200)

    assert result["comparisons"]["codex"]["overall"] == "FRONTIER-NONINFERIOR"
    assert result["comparisons"]["codex"]["quality_pairs"] == 10
    assert result["comparisons"]["codex"]["speed_geomean_ratio"] == pytest.approx(1.1)

    write_panel(attempts, failed=("r1", "rate-limiter", "codex"))
    failed = MODULE["analyze"](attempts, repeats=2, bootstrap_samples=200)
    assert failed["comparisons"]["codex"]["overall"] == "INFERIOR"
    assert failed["variants"]["codex"]["passes"] == 9
    json.dumps(failed, allow_nan=False)

    rows = [json.loads(line) for line in attempts.read_text().splitlines()]
    rows[0]["passed"] = False
    rows[0]["quality_score"] = None
    rows[0]["variable_cost_usd"] = None
    attempts.write_text("\n".join(map(json.dumps, rows)) + "\n")
    missing_cost = MODULE["analyze"](attempts, repeats=2, bootstrap_samples=200)
    variant = rows[0]["variant"]
    assert missing_cost["variants"][variant]["cost_complete"] is False
    assert missing_cost["variants"][variant]["variable_cost_usd"] is None

    attempts.write_text(attempts.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="repeats|incomplete"):
        MODULE["analyze"](attempts, repeats=2, bootstrap_samples=200)
