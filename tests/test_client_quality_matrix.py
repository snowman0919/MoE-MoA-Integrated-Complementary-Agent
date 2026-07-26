from __future__ import annotations

import json
import runpy
from argparse import Namespace
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/run-client-quality-matrix.py"
MODULE = runpy.run_path(str(SCRIPT))
SUCCESS = MODULE["successful_hermes_test_result"]


def test_installed_hermes_execute_code_is_valid_test_evidence() -> None:
    content = json.dumps(
        {
            "status": "success",
            "output": json.dumps(
                {
                    "unittest": {
                        "output": "Ran 4 tests\n\nOK\n",
                        "exit_code": 0,
                        "tests_run": 4,
                    }
                }
            ),
        }
    )

    assert SUCCESS("tool", "execute_code", content)
    assert not SUCCESS("tool", "execute_code", content.replace("success", "error"))


def test_prepared_quality_workspace_starts_clean(tmp_path: Path) -> None:
    args = Namespace(
        run_id="clean",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
    )

    result = MODULE["prepare_one"](args, "codex", MODULE["TASKS"][0])

    workspace = Path(result["workspace"])
    assert MODULE["git"](workspace, "status", "--porcelain").stdout == ""
