from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run-raw-openai-tool-loop.py"
spec = importlib.util.spec_from_file_location("run_raw_openai_tool_loop", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("run_raw_openai_tool_loop", module)
spec.loader.exec_module(module)


def test_raw_tools_are_workspace_bounded_and_execute_tests(tmp_path: Path) -> None:
    write = module.execute_tool(
        tmp_path,
        "write_file",
        {"path": "value.py", "content": "VALUE = 3\n"},
    )
    read = module.execute_tool(tmp_path, "read_file", {"path": "value.py"})
    terminal = module.execute_tool(
        tmp_path,
        "terminal",
        {"command": "python -c 'from value import VALUE; assert VALUE == 3'"},
    )

    assert write["exit_code"] == read["exit_code"] == terminal["exit_code"] == 0
    assert read["output"] == "VALUE = 3\n"
    with pytest.raises(ValueError, match="escapes workspace"):
        module.workspace_path(tmp_path, "../outside")
