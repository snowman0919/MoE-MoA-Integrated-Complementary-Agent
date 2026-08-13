from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run-client-quality-matrix.py"
VALIDATION_SCRIPT = Path(__file__).parents[1] / "scripts/validate-live-client-matrix.py"
spec = importlib.util.spec_from_file_location("run_client_quality_matrix", str(SCRIPT))
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("run_client_quality_matrix", module)
spec.loader.exec_module(module)
SUCCESS = module.successful_hermes_test_result
GLOBALS = module.__dict__


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


def test_current_hermes_unit_tests_key_is_valid_test_evidence() -> None:
    content = json.dumps(
        {
            "status": "success",
            "output": json.dumps(
                {
                    "unit_tests": {
                        "output": "Ran 4 tests\n\nOK\n",
                        "exit_code": 0,
                    }
                }
            ),
        }
    )

    assert SUCCESS("tool", "execute_code", content)


def test_codex_command_uses_explicit_model_catalog(tmp_path: Path) -> None:
    command = GLOBALS["codex_moa_command"](
        Namespace(gateway="http://127.0.0.1:9000"),
        tmp_path,
        GLOBALS["TASKS"][0],
    )

    assert 'model_catalog_json="/state/model-catalog.json"' in command
    assert "model_context_window=131072" in command


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
                            "context_window": 131072,
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


def test_matrix_protocol_pins_current_context_channel_and_baseline_effort() -> None:
    source = SCRIPT.read_text()
    assert "0.146.0-aarch64-unknown-linux-musl" in source
    assert '"X-Runtime-Channel": "dev"' in source
    assert '"model_context_window=131072"' in source
    assert "gpt-5.6-sol" in source
    assert 'model_reasoning_effort="high"' in source


def test_baseline_reasoning_effort_has_bounded_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DGX_MOA_BASELINE_REASONING_EFFORT", raising=False)
    assert GLOBALS["baseline_reasoning_effort"]() == "high"
    monkeypatch.setenv("DGX_MOA_BASELINE_REASONING_EFFORT", "xhigh")
    assert GLOBALS["baseline_reasoning_effort"]() == "xhigh"
    monkeypatch.setenv("DGX_MOA_BASELINE_REASONING_EFFORT", "max")
    with pytest.raises(RuntimeError, match="invalid baseline reasoning effort"):
        GLOBALS["baseline_reasoning_effort"]()


def test_frontier_validation_gateway_enables_operator_admin_path() -> None:
    source = VALIDATION_SCRIPT.read_text()
    assert '"api_keys": {"operator": secret}' in source
    assert '"admin_api_enabled": True' in source
    assert '"kind": "evaluation"' in source
    assert '"expires_in_minutes": 5' in source
    assert "rejected_after_revoke=rejected.status_code == 401" in source


def test_docker_command_has_stable_unique_name(tmp_path: Path) -> None:
    command = GLOBALS["docker_command"](
        tmp_path / "workspace",
        tmp_path / "state",
        ["true"],
    )

    name = command[command.index("--name") + 1]
    assert name.startswith("moa-qm-")
    assert len(name) == len("moa-qm-") + 20
    state_mount = next(value for value in command if value.endswith(":/state:rw"))
    assert state_mount.startswith("/")


def test_hermes_profile_is_pinned_to_isolated_gateway(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "custom_providers:\n"
        "  - name: dgx-moa-agent\n"
        "    base_url: http://production.invalid:9000/v1\n"
        "    api_key: old-key\n"
        "    model: dgx-moa-agent\n"
    )

    GLOBALS["pin_hermes_gateway"](path, "http://127.0.0.1:19300", "canary-key")

    updated = path.read_text()
    assert "base_url: http://127.0.0.1:19300/v1" in updated
    assert "api_key: canary-key" in updated
    assert "old-key" not in updated


def test_timed_out_docker_run_removes_exact_container(tmp_path: Path) -> None:
    command = ["docker", "run", "--rm", "--name", "moa-qm-test", "image"]
    timeout = subprocess.TimeoutExpired(command, 1, output="partial", stderr="")
    cleanup = subprocess.CompletedProcess(["docker", "rm", "-f", "moa-qm-test"], 0, "", "")

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
        harness=None,
        task=None,
    )


def test_fixture_manifest_pins_gateway_runner_and_prompt(tmp_path: Path) -> None:
    args = matrix_args(tmp_path)
    task = GLOBALS["TASKS"][0]

    manifest = GLOBALS["prepare_one"](args, "codex", task)

    assert manifest["gateway"] == args.gateway
    assert manifest["harness_sha256"] == GLOBALS["sha256"](SCRIPT)
    assert manifest["prompt_sha256"] == GLOBALS["text_sha256"](GLOBALS["prompt"](task))
    assert manifest["runtime_fingerprint"] == GLOBALS["runtime_fingerprint"]("codex")

    changed = matrix_args(tmp_path, gateway="http://other.invalid:9000")
    with pytest.raises(RuntimeError, match="fixture manifest mismatch: gateway"):
        GLOBALS["run_one"](changed, "codex", task)

    manifest_path = args.output_root / args.run_id / "codex" / task.slug / "manifest.json"
    stored = json.loads(manifest_path.read_text())
    stored["runtime_fingerprint"]["version"] = "changed"
    manifest_path.write_text(json.dumps(stored))
    with pytest.raises(RuntimeError, match="fixture manifest mismatch: runtime_fingerprint"):
        GLOBALS["run_one"](args, "codex", task)


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


def test_schedule_is_complete_deterministic_and_manifest_bound(tmp_path: Path) -> None:
    args = matrix_args(tmp_path)
    for harness in GLOBALS["HARNESSES"]:
        for task in GLOBALS["TASKS"]:
            GLOBALS["prepare_one"](args, harness, task)

    first = GLOBALS["schedule"](args)
    second = GLOBALS["schedule"](args)

    assert first == second
    assert len(first["entries"]) == len(GLOBALS["HARNESSES"]) * len(GLOBALS["TASKS"])
    assert len({row["order"] for row in first["entries"]}) == len(first["entries"])
    for row in first["entries"]:
        task = GLOBALS["TASK_BY_SLUG"][row["task"]]
        _, evidence = GLOBALS["paths"](args, row["harness"], task)
        assert row["manifest_sha256"] == GLOBALS["sha256"](evidence / "manifest.json")
    assert (args.output_root / args.run_id / "schedule.json").stat().st_mode & 0o222 == 0
