from __future__ import annotations

import json
import runpy
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/analyze-breadth-noninferiority.py"
MODULE = runpy.run_path(str(SCRIPT))


def test_breadth_analyzer_keeps_categories_independent(tmp_path: Path) -> None:
    attempts = tmp_path / "attempts.jsonl"
    rows = []
    for repeat in ("r1", "r2"):
        for tasks in MODULE["CATEGORIES"].values():
            for task in tasks:
                for variant in MODULE["BASE"]["VARIANTS"]:
                    rows.append(
                        {
                            "repeat": repeat,
                            "task": task,
                            "variant": variant,
                            "passed": True,
                            "telemetry_complete": True,
                            "quality_score": 90 if variant == "baseline" else 91,
                            "duration_seconds": 10 if variant == "baseline" else 11,
                            "variable_cost_usd": 0,
                        }
                    )
    attempts.write_text("\n".join(map(json.dumps, rows)) + "\n")

    result = MODULE["analyze"](attempts, repeats=2, bootstrap_samples=200)

    assert set(result["categories"]) == {"scientific", "general"}
    for category in result["categories"].values():
        assert category["comparisons"]["codex"]["overall"] == "FRONTIER-NONINFERIOR"
        assert category["comparisons"]["codex"]["quality_pairs"] == 4
