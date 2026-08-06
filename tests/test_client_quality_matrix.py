from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/run-client-quality-matrix.py"
spec = importlib.util.spec_from_file_location("run_client_quality_matrix", str(SCRIPT))
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("run_client_quality_matrix", module)
spec.loader.exec_module(module)
SUCCESS = module.successful_hermes_test_result


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
