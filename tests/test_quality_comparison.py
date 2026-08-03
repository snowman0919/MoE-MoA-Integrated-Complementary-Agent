from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/summarize-client-quality-comparison.py"
MODULE = runpy.run_path(str(SCRIPT))


def write_matrix(root: Path, run_id: str, *, omit: tuple[str, str] | None = None) -> None:
    for harness in MODULE["HARNESSES"]:
        for task in ("one", "two"):
            if (harness, task) == omit:
                continue
            evidence = root / run_id / harness / task
            evidence.mkdir(parents=True)
            passed = harness != "baseline" or task == "one"
            (evidence / "manifest.json").write_text(
                json.dumps(
                    {
                        "tests_sha256": f"fixture-{task}",
                        "prompt_sha256": f"prompt-{task}",
                        "harness_sha256": "pinned-harness",
                    }
                )
            )
            (evidence / "score.json").write_text(
                json.dumps(
                    {
                        "harness": harness,
                        "task": task,
                        "status": "passed" if passed else "failed",
                        "duration_seconds": 1 if harness == "baseline" else 2,
                    }
                )
            )


def test_summary_preserves_all_repeats_and_rejects_incomplete_matrix(tmp_path: Path) -> None:
    write_matrix(tmp_path, "r1")
    write_matrix(tmp_path, "r2")

    result = MODULE["summarize"](tmp_path, ["r1", "r2"], 0.05)

    assert result["metrics"]["baseline"]["passes"] == 2
    assert result["metrics"]["opencode"]["passes"] == 4
    assert result["comparisons"]["opencode"]["median_latency_ratio"] == 2

    write_matrix(tmp_path, "r3", omit=("hermes", "two"))
    with pytest.raises(ValueError, match="incomplete"):
        MODULE["summarize"](tmp_path, ["r1", "r3"], 0.05)
