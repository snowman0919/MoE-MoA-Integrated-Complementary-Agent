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


def test_codex_quality_command_uses_native_patch_catalog(tmp_path: Path) -> None:
    args = Namespace(gateway="http://127.0.0.1:19300")
    command = MODULE["codex_moa_command"](args, tmp_path, MODULE["TASKS"][0])
    model = MODULE["codex_model_catalog"]()["models"][0]

    assert 'model_catalog_json="/state/model-catalog.json"' in command
    assert model["apply_patch_tool_type"] == "freeform"
    assert "apply_patch" in model["base_instructions"]


def test_opencode_fixture_bounds_output_tokens(tmp_path: Path) -> None:
    args = Namespace(
        run_id="bounded",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
        gateway="http://127.0.0.1:19300",
    )

    result = MODULE["prepare_one"](args, "opencode", MODULE["TASKS"][0])
    config = json.loads((Path(result["workspace"]) / "opencode.json").read_text())
    model = config["provider"]["dgx-moa"]["models"]["dgx-moa-agent"]

    assert model["limit"] == {"context": 65_536, "output": 4_096}


def test_opencode_runtime_cache_is_mounted_read_only(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    node_modules = tmp_path / "node_modules"
    package_json = tmp_path / "package.json"
    package_lock = tmp_path / "package-lock.json"
    ripgrep = tmp_path / "rg"
    node_modules.mkdir()
    package_json.write_text("{}")
    package_lock.write_text("{}")
    ripgrep.touch()
    monkeypatch.setitem(
        MODULE["opencode_runtime_mounts"].__globals__, "OPENCODE_NODE_MODULES", node_modules
    )
    monkeypatch.setitem(
        MODULE["opencode_runtime_mounts"].__globals__, "OPENCODE_PACKAGE_JSON", package_json
    )
    monkeypatch.setitem(
        MODULE["opencode_runtime_mounts"].__globals__, "OPENCODE_PACKAGE_LOCK", package_lock
    )
    monkeypatch.setitem(MODULE["opencode_runtime_mounts"].__globals__, "OPENCODE_RIPGREP", ripgrep)

    mounts = MODULE["opencode_runtime_mounts"](tmp_path / "state")

    assert mounts == (
        (node_modules, "/state/.config/opencode/node_modules"),
        (ripgrep, "/state/.cache/opencode/bin/rg"),
    )
    assert (tmp_path / "state/.config/opencode/package.json").read_text() == "{}"
    assert (tmp_path / "state/.config/opencode/package-lock.json").read_text() == "{}"
