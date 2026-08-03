from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run-client-quality-matrix.py"
MODULE = runpy.run_path(str(SCRIPT))
SUCCESS = MODULE["successful_hermes_test_result"]
ISOLATED_HERMES_CONFIG = MODULE["isolated_hermes_config"]


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


def test_fixture_pins_gateway(tmp_path: Path) -> None:
    args = SimpleNamespace(
        run_id="gateway-pin",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
        gateway="http://127.0.0.1:19000",
        runtime="docker",
        timeout=1,
    )
    task = MODULE["TASKS"][0]
    MODULE["prepare_one"](args, "opencode", task)
    args.gateway = "http://127.0.0.1:9000"

    with pytest.raises(RuntimeError, match="gateway differs"):
        MODULE["run_one"](args, "opencode", task)


def test_hermes_profile_replaces_production_endpoint_and_embedded_key(tmp_path: Path) -> None:
    source = """\
model:
  provider: custom:dgx-moa-agent
custom_providers:
  - name: dgx-moa-agent
    base_url: http://100.64.0.1:9000/v1
    api_key: production-secret
    model: dgx-moa-agent
    extra_headers:
      X-Workspace-ID: production
fallback_model:
  provider: none
"""

    result = ISOLATED_HERMES_CONFIG(
        source,
        gateway="http://127.0.0.1:19000",
        workspace=tmp_path,
        run_id="isolated",
        task=MODULE["TASKS"][0],
    )

    assert "http://127.0.0.1:19000/v1" in result
    assert "key_env: DGX_MOA_API_KEY" in result
    assert "production-secret" not in result
    assert "100.64.0.1:9000" not in result
    assert f"X-Workspace-Path: {tmp_path}" in result
    assert "fallback_model:" in result


def test_summary_requires_complete_comparable_samples(tmp_path: Path) -> None:
    args = SimpleNamespace(
        run_id="summary",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
    )
    task = MODULE["TASKS"][0]
    evidence = args.output_root / args.run_id / "codex" / task.slug
    evidence.mkdir(parents=True)
    (evidence / "score.json").write_text(
        json.dumps({"harness": "codex", "task": task.slug, "status": "passed"})
    )

    result = MODULE["summary"](args)

    assert result["matrix_complete"] is False
    assert result["usability_not_below_baseline"]["codex"] is False
    assert result["complete"] is False


def test_summary_allows_imperfect_reference_but_requires_all_moa_tasks(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        run_id="complete-summary",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
    )
    for harness in MODULE["HARNESSES"]:
        for index, task in enumerate(MODULE["TASKS"]):
            evidence = args.output_root / args.run_id / harness / task.slug
            evidence.mkdir(parents=True)
            status = "failed" if harness == "baseline" and index == 0 else "passed"
            (evidence / "score.json").write_text(
                json.dumps({"harness": harness, "task": task.slug, "status": status})
            )

    result = MODULE["summary"](args)

    assert result["matrix_complete"] is True
    assert all(result["usability_not_below_baseline"].values())
    assert result["complete"] is True


def test_docker_timeout_removes_named_container(tmp_path: Path, monkeypatch) -> None:
    command = MODULE["docker_command"](
        tmp_path / "workspace",
        tmp_path / "state",
        ["python", "-V"],
    )
    container = command[command.index("--name") + 1]
    calls: list[list[str]] = []

    def run(arguments, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(arguments)
        if arguments[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(arguments, 0, "", "")
        raise subprocess.TimeoutExpired(arguments, 1, output="partial", stderr="")

    monkeypatch.setattr(MODULE["subprocess"], "run", run)
    result = MODULE["run_process"](
        command,
        cwd=tmp_path,
        environment={},
        timeout=1,
    )

    assert result.returncode == 124
    assert calls[-1] == ["docker", "rm", "-f", container]
