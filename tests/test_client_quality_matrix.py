from __future__ import annotations

import json
import runpy
import sqlite3
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


def test_baseline_runtime_mounts_same_search_tool() -> None:
    source = SCRIPT.read_text()

    assert '(OPENCODE_RIPGREP, "/tools/rg")' in source


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


def test_hermes_profile_targets_selected_gateway(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.yaml").write_text(
        "custom_providers:\n"
        "  - name: dgx-moa-agent\n"
        "    base_url: http://production:9000/v1\n"
        "    api_key: keep-me\n"
        "  - name: other\n"
        "    base_url: http://other/v1\n"
    )
    (source / ".env").write_text("KEEP=me\n")
    real_copy = MODULE["shutil"].copy2

    def copy_fixture(source_path: str, destination: Path) -> None:
        name = Path(source_path).name
        real_copy(source / name, destination)

    monkeypatch.setattr(MODULE["shutil"], "copy2", copy_fixture)
    target = tmp_path / "profile"

    MODULE["prepare_hermes_profile"](target, "http://127.0.0.1:19400/")

    config = (target / "config.yaml").read_text()
    assert "base_url: http://127.0.0.1:19400/v1" in config
    assert "api_key: keep-me" in config
    assert "base_url: http://other/v1" in config
    assert (target / ".env").read_text() == "KEEP=me\n"


def test_failed_hermes_usage_recovers_single_isolated_session(tmp_path: Path) -> None:
    args = Namespace(run_id="failed", output_root=tmp_path)
    task = MODULE["TASKS"][0]
    profile = tmp_path / "failed/profiles/hermes-rate-limiter"
    evidence = tmp_path / "evidence"
    profile.mkdir(parents=True)
    evidence.mkdir()
    (profile / "usage.json").write_text('{"session_id":null,"failed":true}\n')
    with sqlite3.connect(profile / "state.db") as connection:
        connection.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
            "tool_name TEXT, content TEXT, tool_calls TEXT)"
        )
        connection.execute(
            "INSERT INTO messages(session_id, role, tool_name, content, tool_calls) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "isolated-session",
                "tool",
                "terminal",
                json.dumps({"exit_code": 0, "output": "Ran 4 tests\nOK\n"}),
                "python -m unittest",
            ),
        )

    assert MODULE["hermes_test_evidence"](args, task, evidence)
    summary = json.loads((evidence / "hermes-tool-evidence.json").read_text())
    assert summary["unittest_tool_calls"] == 1
    assert summary["successful_unittest_results"] == 1


def test_hermes_usage_requires_explicit_completed_success(tmp_path: Path) -> None:
    usage = tmp_path / "usage.json"

    usage.write_text('{"completed":true,"failed":false}\n')
    assert MODULE["hermes_usage_succeeded"](usage)

    usage.write_text('{"completed":false,"failed":true}\n')
    assert not MODULE["hermes_usage_succeeded"](usage)

    usage.write_text('{"completed":true}\n')
    assert not MODULE["hermes_usage_succeeded"](usage)


def test_summary_keeps_incomplete_comparisons_inconclusive(tmp_path: Path) -> None:
    args = Namespace(
        run_id="incomplete",
        workspace_root=tmp_path / "workspaces",
        output_root=tmp_path / "evidence",
    )
    for task in MODULE["TASKS"]:
        _, evidence = MODULE["paths"](args, "hermes", task)
        evidence.mkdir(parents=True)
        (evidence / "score.json").write_text(json.dumps({"harness": "hermes", "status": "passed"}))

    result = MODULE["summary"](args)

    assert result["counts"]["hermes"] == {"passed": len(MODULE["TASKS"]), "total": 5}
    assert result["usability_not_below_baseline"]["hermes"] is None
    assert result["complete"] is False


def test_invocation_telemetry_is_content_free_and_fails_on_missing_cost(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, "
            "fallback_reason TEXT, latency_ms REAL, prompt_tokens INTEGER, "
            "completion_tokens INTEGER, total_tokens INTEGER, cached_tokens INTEGER, "
            "cost_usd REAL, invoked_at REAL)"
        )
        connection.execute(
            "CREATE TABLE events (session_id TEXT, event_type TEXT, payload TEXT, created_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "private-request",
                    "executor",
                    "local",
                    "local-model",
                    "completed",
                    None,
                    10,
                    5,
                    2,
                    7,
                    3,
                    None,
                    2,
                ),
                (
                    "private-request",
                    "executor",
                    "remote",
                    "remote-model",
                    "completed",
                    "local_busy",
                    20,
                    7,
                    3,
                    10,
                    0,
                    None,
                    3,
                ),
            ),
        )

    result = MODULE["invocation_telemetry"](database, 1, 4)

    assert result["complete"] is False
    assert result["reason"] == "remote_cost_missing"
    assert result["provider_pinned"] is False
    assert result["provider_switches"] == 1
    assert result["remote_cost_usd"] is None
    assert result["prompt_tokens"] == 12
    assert result["completion_tokens"] == 5
    assert result["total_tokens"] == 17
    assert result["cached_tokens"] == 3
    assert result["retryable_failures"] is None
    assert "private-request" not in json.dumps(result)


def test_invocation_telemetry_requires_and_collects_retry_cache_and_tokens(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, "
            "fallback_reason TEXT, latency_ms REAL, prompt_tokens INTEGER, "
            "completion_tokens INTEGER, total_tokens INTEGER, cached_tokens INTEGER, "
            "cost_usd REAL, invoked_at REAL)"
        )
        connection.execute(
            "CREATE TABLE request_usage (accepted_at TEXT, retryable_failure_class TEXT)"
        )
        connection.execute(
            "CREATE TABLE events (session_id TEXT, event_type TEXT, payload TEXT, created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "opaque",
                "reviewer",
                "remote",
                "review-model",
                "completed",
                "local_busy",
                20,
                7,
                3,
                10,
                2,
                0.0,
                2,
            ),
        )
        connection.execute("INSERT INTO request_usage VALUES ('1970-01-01T00:00:03+00:00', NULL)")

    result = MODULE["invocation_telemetry"](database, 1, 4)

    assert result["complete"] is True
    assert result["reason"] is None
    assert result["prompt_tokens"] == 7
    assert result["completion_tokens"] == 3
    assert result["total_tokens"] == 10
    assert result["cached_tokens"] == 2
    assert result["retryable_failures"] == 0


def test_cuda_memory_used_reads_runtime_without_torch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class Runtime:
        @staticmethod
        def cudaMemGetInfo(free, total):  # type: ignore[no-untyped-def]
            free._obj.value = 30  # noqa: SLF001
            total._obj.value = 100  # noqa: SLF001
            return 0

    monkeypatch.setattr(MODULE["ctypes"], "CDLL", lambda _name: Runtime())

    assert MODULE["cuda_memory_used"]() == 70
