from __future__ import annotations

import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run-client-quality-matrix.py"
GLOBALS = runpy.run_path(str(SCRIPT))
SUCCESS = GLOBALS["successful_hermes_test_result"]


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


def test_codex_command_uses_explicit_model_catalog(tmp_path: Path) -> None:
    command = GLOBALS["codex_moa_command"](
        Namespace(gateway="http://127.0.0.1:9000"),
        tmp_path,
        GLOBALS["TASKS"][0],
    )

    assert 'model_catalog_json="/state/model-catalog.json"' in command


def test_codex_catalog_is_pinned_from_authenticated_gateway(tmp_path: Path) -> None:
    class Response:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        @staticmethod
        def read() -> bytes:
            return json.dumps(
                {
                    "models": [
                        {
                            "slug": "dgx-moa-orchestrated",
                            "tool_mode": "direct",
                            "context_window": 65536,
                        }
                    ]
                }
            ).encode()

    path = tmp_path / "model-catalog.json"
    with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
        GLOBALS["write_codex_model_catalog"](
            "http://127.0.0.1:9000",
            "test-secret",
            path,
        )

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:9000/v1/models"
    assert request.get_header("Authorization") == "Bearer test-secret"
    assert json.loads(path.read_text())["models"][0]["tool_mode"] == "direct"
    assert "test-secret" not in path.read_text()


def test_docker_command_has_stable_unique_name(tmp_path: Path) -> None:
    command = GLOBALS["docker_command"](
        tmp_path / "workspace",
        tmp_path / "state",
        ["true"],
    )

    name = command[command.index("--name") + 1]
    assert name.startswith("moa-qm-")
    assert len(name) == len("moa-qm-") + 20


def test_timed_out_docker_run_removes_exact_container(tmp_path: Path) -> None:
    command = ["docker", "run", "--rm", "--name", "moa-qm-test", "image"]
    timeout = subprocess.TimeoutExpired(command, 1, output="partial", stderr="")
    cleanup = subprocess.CompletedProcess(
        ["docker", "rm", "-f", "moa-qm-test"], 0, "", ""
    )

    with mock.patch("subprocess.run", side_effect=(timeout, cleanup)) as run:
        result = GLOBALS["run_process"](
            command,
            cwd=tmp_path,
            environment={},
            timeout=1,
        )

    assert result.returncode == 124
    assert run.call_args_list[1].args[0] == ["docker", "rm", "-f", "moa-qm-test"]


def matrix_args(tmp_path: Path, *, gateway: str = "http://gateway.invalid:9000") -> Namespace:
    return Namespace(
        run_id="preregistered",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
        gateway=gateway,
        timeout=30,
        runtime="docker",
    )


def test_fixture_manifest_pins_gateway_runner_and_prompt(tmp_path: Path) -> None:
    args = matrix_args(tmp_path)
    task = GLOBALS["TASKS"][0]

    manifest = GLOBALS["prepare_one"](args, "codex", task)

    assert manifest["gateway"] == args.gateway
    assert manifest["harness_sha256"] == GLOBALS["sha256"](SCRIPT)
    assert manifest["prompt_sha256"] == GLOBALS["text_sha256"](GLOBALS["prompt"](task))

    changed = matrix_args(tmp_path, gateway="http://other.invalid:9000")
    with pytest.raises(RuntimeError, match="fixture manifest mismatch: gateway"):
        GLOBALS["run_one"](changed, "codex", task)


def test_partial_summary_does_not_claim_noninferiority(tmp_path: Path) -> None:
    args = matrix_args(tmp_path)
    task = GLOBALS["TASKS"][0]
    _, evidence = GLOBALS["paths"](args, "baseline", task)
    evidence.mkdir(parents=True)
    (evidence / "score.json").write_text(
        json.dumps({"harness": "baseline", "task": task.slug, "status": "passed"})
    )

    result = GLOBALS["summary"](args)

    assert result["matrix_complete"] is False
    assert result["complete"] is False
    assert result["usability_not_below_baseline"] == {
        "opencode": None,
        "codex": None,
        "hermes": None,
    }
