from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pytest
from dgx_moa import long_horizon_client as MODULE
from dgx_moa.controller import user_turn_intent


def test_phase_prompts_require_changes_only_during_core_implementation() -> None:
    workspace = Path("/tmp/exact-workspace")
    validation = "python -m unittest -v tests.test_job_journal"
    inputs = tuple(Path("/tmp/long-inputs") / name for name in (
        "OBJECTIVE.md",
        "ACCEPTANCE.md",
        "PLAN.md",
    ))
    assert [
        user_turn_intent(MODULE.client_prompt(index, workspace, validation, inputs))[0]
        for index in range(MODULE.CHECKPOINTS)
    ] == [False, True, False, False, False]
    assert all(
        f"{workspace}/state/long-review.json"
        not in MODULE.client_prompt(index, workspace, validation, inputs)
        for index in range(MODULE.CHECKPOINTS - 1)
    )
    final = MODULE.client_prompt(
        MODULE.CHECKPOINTS - 1, workspace, validation, inputs
    )
    assert f"{workspace}/state/long-review.json" in final
    assert str(workspace) in final
    assert validation in final
    assert "추측한 경로로 cd하지 말고" in final
    assert all(str(path) in final for path in inputs)
    assert "/inputs/OBJECTIVE.md" not in final
    implementation = MODULE.client_prompt(1, workspace, validation, inputs)
    assert "preliminary Reviewer" in implementation
    assert implementation.index("commit하라") < implementation.index(
        "preliminary Reviewer"
    )
    assert "최종 독립 검토는 이후 단계" in implementation


def test_avatarforge_prompts_require_a_commit_per_phase() -> None:
    workspace = Path("/tmp/avatarforge")
    inputs = tuple(
        Path("/tmp/avatarforge-inputs") / name
        for name in ("OBJECTIVE.md", "ACCEPTANCE.md", "PLAN.md")
    )
    prompts = [
        MODULE.client_prompt(
            index,
            workspace,
            "python -m unittest discover -s tests -v",
            inputs,
            "avatarforge",
        )
        for index in range(len(MODULE.AVATARFORGE_PHASES))
    ]

    assert all(user_turn_intent(prompt)[0] for prompt in prompts)
    assert all("새 clean commit이 필수" in prompt for prompt in prompts)
    assert "아무것도 설치하지 말고" in prompts[2]
    assert "Character IR" in prompts[3]
    assert f"{workspace}/state/long-review.json" in prompts[3]
    assert '"evidence_sha256":"64 lowercase hex"' in prompts[3]


def test_final_validation_rejects_zero_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = arguments(tmp_path, "codex")
    args.timeout = 1
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(
        MODULE.QUALITY,
        "run_process",
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess(
            [], 0, "Ran 0 tests in 0.000s\n\nOK", ""
        ),
    )
    monkeypatch.setattr(MODULE, "container_exists", lambda _name: False)

    exit_code, _output_sha256 = MODULE.run_validation(args, state)

    assert exit_code == 1


def test_final_event_uses_only_committed_sanitized_workspace_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = arguments(tmp_path, "codex")
    workspace = args.workspace
    MODULE.git(workspace, "init", "-q")
    MODULE.ensure_local_git_identity(workspace)
    (workspace / "implementation.py").write_text("VALUE = 1\n")
    MODULE.git(workspace, "add", "implementation.py")
    MODULE.git(workspace, "commit", "-qm", "baseline")
    baseline = MODULE.git(workspace, "rev-parse", "HEAD")
    review_path = workspace / "state" / "long-review.json"
    review_path.parent.mkdir()
    review_path.write_text(
        json.dumps(
            {
                "status": "approved",
                "unresolved_critical_findings": 0,
                "evidence_sha256": "a" * 64,
            }
        )
    )
    MODULE.git(workspace, "add", "state/long-review.json")
    MODULE.git(workspace, "commit", "-qm", "add review")
    checkpoint = {
        "commit": MODULE.git(workspace, "rev-parse", "HEAD"),
        "provider_provenance": [{"role": "reviewer"}],
        "terminal": True,
    }
    header = {
        "baseline_commit": baseline,
        **{field: "b" * 64 for field in MODULE.stable_hashes_fields()},
    }
    monkeypatch.setattr(MODULE, "run_validation", lambda *_args: (0, "c" * 64))

    result = MODULE.final_event(args, tmp_path / "private-state", header, checkpoint)

    assert result["task_outcome"] == "completed"
    review_path.write_text(
        json.dumps(
            {
                "status": "approved",
                "unresolved_critical_findings": 0,
                "evidence": "raw review output",
            }
        )
    )
    with pytest.raises(RuntimeError, match="invalid_review_evidence"):
        MODULE.final_event(args, tmp_path / "private-state", header, checkpoint)


def arguments(tmp_path: Path, harness: str) -> argparse.Namespace:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    inputs = []
    for name in ("objective.md", "acceptance.md", "plan.md"):
        path = tmp_path / name
        path.write_text(name)
        inputs.append(path)
    provider_manifest = tmp_path / "provider.json"
    provider_manifest.write_text(
        json.dumps(
            {
                "executor": {"model": "executor-fixed", "revision": "a" * 40},
                "specialist": {"model": "specialist-fixed", "revision": "b" * 40},
            }
        )
    )
    return argparse.Namespace(
        harness=harness,
        workspace=workspace,
        objective=inputs[0],
        acceptance=inputs[1],
        plan=inputs[2],
        gateway="http://127.0.0.1:19300",
        api_key_env="TEST_LONG_API_KEY",
        provider_manifest=provider_manifest,
        provider_manifest_sha256=MODULE.sha256_file(provider_manifest),
        validation_command="python -m unittest -v tests.test_job_journal",
    )


def test_missing_local_git_identity_is_added_without_overwriting_existing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    MODULE.git(workspace, "init", "-q")
    MODULE.git(workspace, "config", "--local", "user.name", "Existing User")

    MODULE.ensure_local_git_identity(workspace)

    assert MODULE.git(workspace, "config", "--local", "--get", "user.name") == "Existing User"
    assert (
        MODULE.git(workspace, "config", "--local", "--get", "user.email")
        == "evaluation@localhost"
    )


def test_evidence_is_durable_and_rejects_private_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    MODULE.append_event(evidence, {"type": "header", "value": 1}, create=True)
    MODULE.append_event(evidence, {"type": "checkpoint", "value": 2})

    assert evidence.stat().st_mode & 0o777 == 0o600
    assert [row["type"] for row in MODULE.load_events(evidence)] == [
        "header",
        "checkpoint",
    ]
    with pytest.raises(ValueError, match="private evidence"):
        MODULE.append_event(evidence, {"type": "bad", "raw_prompt": "secret"})
    with pytest.raises(ValueError, match="private evidence"):
        MODULE.append_event(evidence, {"type": "bad", "nested": {"session_id": "raw"}})


def test_provider_manifest_hash_rejects_private_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(json.dumps({"executor": {"model": "fixed", "revision": "abc"}}))

    assert MODULE.provider_manifest_hash(manifest) == MODULE.sha256_file(manifest)

    manifest.write_text(json.dumps({"executor": {"api_key": "private"}}))
    with pytest.raises(ValueError, match="private evidence"):
        MODULE.provider_manifest_hash(manifest)


def test_gateway_progress_state_hashes_context_without_payloads(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    private = "private-objective"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE sessions (session_id TEXT, payload TEXT, updated_at REAL)"
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            (
                "private-session",
                json.dumps(
                    {
                        "objective": private,
                        "acceptance_criteria": ["works"],
                        "plan": ["inspect", "implement"],
                        "phase": "executing",
                        "step_count": 2,
                        "completed_steps": ["inspect"],
                        "tool_executions": [{"tool": "test"}],
                        "review_status": "approved",
                        "final_status": None,
                    }
                ),
                1,
            ),
        )

    result = MODULE.gateway_progress_state(database, "private-session", 1)

    assert result["phase_index"] == 1
    assert result["phase"] == MODULE.PHASES[1]
    assert result["premature_completion"] is False
    assert private not in json.dumps(result)
    assert all(
        len(result[field]) == 64
        for field in ("next_action_sha256", "context_summary_sha256", "evidence_sha256")
    )


def test_codex_model_catalog_enables_native_patch_tool() -> None:
    model = MODULE.codex_model_catalog()["models"][0]

    assert model["slug"] == "dgx-moa-orchestrated"
    assert model["apply_patch_tool_type"] == "freeform"
    assert model["context_window"] == 65_536
    assert "apply_patch" in model["base_instructions"]


@pytest.mark.parametrize(
    ("harness", "binary", "resume_flag"),
    (
        ("codex", "/tools/codex", "resume"),
        ("opencode", "/tools/opencode", "--session"),
        ("hermes", "/home/kotori9/.hermes/hermes-agent/venv/bin/python", "--resume"),
    ),
)
def test_client_commands_resume_the_same_private_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    harness: str,
    binary: str,
    resume_flag: str,
) -> None:
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    args = arguments(tmp_path, harness)
    state = tmp_path / f"state-{harness}"

    command, environment, _ = MODULE.client_command(
        args, state, "private-session", 4, "private-gateway-session"
    )

    inner = command[command.index(binary) :]
    assert resume_flag in inner
    assert "private-session" in inner
    assert environment["TEST_LONG_API_KEY"] == "private-test-value"
    assert str(args.objective) in " ".join(command)
    assert "private-test-value" not in " ".join(command)
    prompt = inner[inner.index("-z") + 1] if harness == "hermes" else inner[-1]
    for path in (args.objective, args.acceptance, args.plan):
        assert f"{path}:{path}:ro" in command
        assert str(path) in prompt
    assert "/inputs/OBJECTIVE.md" not in prompt
    if harness == "codex":
        catalog = json.loads((state / "model-catalog.json").read_text())
        assert catalog["models"][0]["apply_patch_tool_type"] == "freeform"
        assert 'model_catalog_json="/state/model-catalog.json"' in inner
        headers = next(value for value in inner if "http_headers=" in value)
        assert '"X-Session-ID" = "private-gateway-session"' in headers
        assert '"X-Runtime-Channel" = "candidate"' in headers
        assert '"X-Trace-Origin" = "candidate_evaluation"' in headers
        assert '"X-Workspace-ID" = "long-horizon"' in headers
    elif harness == "opencode":
        assert inner[inner.index("--title") + 1] == "DGX MoA long horizon"
        assert "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER=1" in command
        raw_config = next(
            value.removeprefix("OPENCODE_CONFIG_CONTENT=")
            for value in command
            if value.startswith("OPENCODE_CONFIG_CONTENT=")
        )
        permissions = json.loads(raw_config)["permission"]["external_directory"]
        assert permissions["*"] == "deny"
        assert {path for path, action in permissions.items() if action == "allow"} == {
            f"{args.workspace}/**",
            f"{args.objective.parent}/**",
            f"{args.acceptance.parent}/**",
            f"{args.plan.parent}/**",
        }


def test_client_metrics_and_provider_pinning_are_aggregated_without_payloads(
    tmp_path: Path,
) -> None:
    repeated_read = {
        "type": "tool_use",
        "sessionID": "private-session",
        "part": {"tool": "read", "state": {"input": {"filePath": "/private/file"}}},
    }
    finish = {
        "type": "step_finish",
        "sessionID": "private-session",
        "part": {
            "reason": "stop",
            "tokens": {"input": 100, "cache": {"read": 75}},
        },
    }
    metrics = MODULE.client_metrics(
        "opencode",
        "\n".join(json.dumps(row) for row in (repeated_read, repeated_read, finish)),
        "",
        None,
    )

    assert metrics["session"] == "private-session"
    assert metrics["terminal"] is True
    assert metrics["tool_calls"] == 2
    assert metrics["context_tokens"] == 100
    assert metrics["cached_tokens"] == 75
    assert metrics["unjustified_repeated_reads"] == 1
    assert "/private/file" not in json.dumps(metrics)

    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, latency_ms REAL, "
            "prompt_tokens INTEGER, total_tokens INTEGER, cost_usd REAL, invoked_at REAL)"
        )
        connection.executemany(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "request-a",
                    "executor",
                    "local",
                    "executor-fixed",
                    "completed",
                    10,
                    120,
                    130,
                    0,
                    2,
                ),
                ("request-b", "reviewer", "local", "specialist-fixed", "success", 20, 80, 90, 0, 3),
            ),
        )

    provider = MODULE.provider_metrics(database, 1, 4)

    assert provider["provider_pinned"] is True
    assert provider["provider_errors"] == 0
    assert provider["context_tokens"] == 120
    assert provider["variable_cost_usd"] == 0
    assert provider["provider_provenance"] == [
        {"role": "executor", "provider": "local", "model": "executor-fixed"},
        {"role": "reviewer", "provider": "local", "model": "specialist-fixed"},
    ]


def test_avatarforge_opencode_bounds_agent_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = arguments(tmp_path, "opencode")
    args.profile = "avatarforge"
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")

    bounded = json.loads(MODULE.opencode_config(args, "private-session"))
    command, _, _ = MODULE.client_command(
        args, tmp_path / "state", None, 0, "private-session"
    )
    args.profile = "journal"
    unbounded = json.loads(MODULE.opencode_config(args, "private-session"))

    agent = MODULE.AVATARFORGE_OPENCODE_AGENT
    assert bounded["default_agent"] == agent
    assert bounded["agent"][agent]["steps"] == MODULE.AVATARFORGE_OPENCODE_STEPS
    assert command[command.index("--agent") + 1] == agent
    assert (
        f"{MODULE.AVATARFORGE_PYTHON_ROOT}:{MODULE.AVATARFORGE_PYTHON_TARGET}:ro"
        in command
    )
    assert (
        f"{MODULE.AVATARFORGE_UV_PYTHON_ROOT}:"
        f"{MODULE.AVATARFORGE_UV_PYTHON_TARGET}:ro"
        in command
    )
    assert (
        f"PYTHONPATH={MODULE.AVATARFORGE_PYTHON_TARGET}/lib/python3.13/site-packages:"
        f"{args.workspace}/gateway/src"
        in command
    )
    assert any(
        value.startswith(f"PATH={MODULE.AVATARFORGE_PYTHON_BIN}:")
        for value in command
    )
    assert "host 검증 명령이 입력 문서의 이전 검증 명령보다 우선" in command[-1]
    assert "agent" not in unbounded


def test_avatarforge_codex_uses_complete_python_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = arguments(tmp_path, "codex")
    args.profile = "avatarforge"
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")

    command, _, _ = MODULE.client_command(
        args, tmp_path / "state", None, 0, "private-session"
    )

    assert (
        f"{MODULE.AVATARFORGE_PYTHON_ROOT}:{MODULE.AVATARFORGE_PYTHON_TARGET}:ro"
        in command
    )
    assert (
        f"{MODULE.AVATARFORGE_UV_PYTHON_ROOT}:"
        f"{MODULE.AVATARFORGE_UV_PYTHON_TARGET}:ro"
        in command
    )
    assert any(
        value.startswith(f"PATH={MODULE.AVATARFORGE_PYTHON_BIN}:")
        for value in command
    )
    assert (
        f"PYTHONPATH={MODULE.AVATARFORGE_PYTHON_TARGET}/lib/python3.13/site-packages:"
        f"{args.workspace}/gateway/src"
        in command
    )


def test_provider_pinning_is_scoped_to_each_call(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, latency_ms REAL, "
            "prompt_tokens INTEGER, total_tokens INTEGER, cost_usd REAL, invoked_at REAL)"
        )
        connection.executemany(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "request-a",
                    "reviewer",
                    "local",
                    "specialist-fixed",
                    "completed",
                    10,
                    10,
                    12,
                    0,
                    2,
                ),
                ("request-b", "reviewer", "remote", "reviewer-go", "completed", 20, 10, 12, 0, 3),
            ),
        )

    assert MODULE.provider_metrics(database, 1, 4)["provider_pinned"] is True

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "request-b",
                "reviewer",
                "local",
                "specialist-fixed",
                "completed",
                10,
                10,
                12,
                0,
                3.5,
            ),
        )

    assert MODULE.provider_metrics(database, 1, 4)["provider_pinned"] is False


def test_provider_cost_handles_fixed_plans_and_fails_closed_for_paid_routes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, latency_ms REAL, "
            "prompt_tokens INTEGER, total_tokens INTEGER, invoked_at REAL)"
        )
        connection.execute(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("fixed", "executor", "frontier", "gpt-fixed", "completed", 10, 10, 12, 2),
        )

    assert MODULE.provider_metrics(database, 1, 4)["variable_cost_usd"] == 0

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "paid",
                "executor",
                "openrouter:paid-model",
                "paid-model",
                "completed",
                10,
                10,
                12,
                3,
            ),
        )

    assert MODULE.provider_metrics(database, 1, 4)["variable_cost_usd"] is None


def test_provider_metrics_exclude_concurrent_other_sessions(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "request_id TEXT, role TEXT, provider TEXT, model TEXT, status TEXT, latency_ms REAL, "
            "prompt_tokens INTEGER, total_tokens INTEGER, cost_usd REAL, invoked_at REAL)"
        )
        connection.execute(
            "CREATE TABLE role_request_usage (request_id TEXT, session_id_hash TEXT, role TEXT)"
        )
        connection.executemany(
            "INSERT INTO role_request_usage VALUES (?, ?, ?)",
            (
                ("target-request", MODULE.sha256_text("private-target"), "executor"),
                ("target-request", MODULE.sha256_text("private-target"), "reviewer"),
                ("other-request", MODULE.sha256_text("private-other"), "executor"),
            ),
        )
        connection.executemany(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "target-request",
                    "executor",
                    "local",
                    "executor-fixed",
                    "completed",
                    10,
                    10,
                    12,
                    0,
                    2,
                ),
                (
                    "other-request",
                    "executor",
                    "openrouter:paid-model",
                    "paid-model",
                    "completed",
                    10,
                    10,
                    12,
                    None,
                    2.5,
                ),
            ),
        )

    metrics = MODULE.provider_metrics(database, 1, 4, "private-target")

    assert metrics["provider_provenance"] == [
        {"role": "executor", "provider": "local", "model": "executor-fixed"}
    ]
    assert metrics["variable_cost_usd"] == 0


def test_hermes_metrics_use_tool_rows_not_model_api_count(tmp_path: Path) -> None:
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "session_id": "private-hermes",
                "input_tokens": 90,
                "cache_read_tokens": 40,
                "api_calls": 99,
                "completed": True,
                "failed": False,
            }
        )
    )
    with sqlite3.connect(tmp_path / "state.db") as connection:
        connection.execute(
            "CREATE TABLE messages (id INTEGER, session_id TEXT, tool_name TEXT, tool_calls TEXT)"
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?)",
            (
                1,
                "private-hermes",
                None,
                json.dumps(
                    [
                        {
                            "function": {
                                "name": "read_file",
                                "arguments": {"path": "/private/file"},
                            }
                        }
                    ]
                ),
            ),
        )

    metrics = MODULE.client_metrics("hermes", "done", "", usage, tmp_path)

    assert metrics["tool_calls"] == 1
    assert metrics["context_tokens"] == 90
    assert metrics["cached_tokens"] == 40
    assert "/private/file" not in json.dumps(metrics)


def test_checkpoint_interrupt_removes_only_its_named_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = arguments(tmp_path, "codex")
    args.state_db = tmp_path / "unused.db"
    args.timeout = 1
    state = tmp_path / "state"
    state.mkdir()
    control = {
        "started_at_epoch": 1,
        "baseline": {},
        "gateway_session": "private-gateway",
        "client_session": None,
    }
    existence = iter((False, True))
    removed: list[str] = []
    globals_ = MODULE.run_checkpoint.__globals__
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    monkeypatch.setattr(
        MODULE.QUALITY,
        "run_process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(MODULE.RUNTIME, "runtime_snapshot", lambda: {})
    monkeypatch.setitem(
        globals_,
        "client_command",
        lambda *_args, **_kwargs: (["docker", "run", "--rm", "image", "command"], {}, None),
    )
    monkeypatch.setitem(globals_, "wait_until", lambda _target: None)
    monkeypatch.setitem(globals_, "container_exists", lambda _name: next(existence))
    monkeypatch.setitem(globals_, "remove_client_container", removed.append)

    with pytest.raises(KeyboardInterrupt):
        MODULE.run_checkpoint(args, state, control, 0)

    assert removed == [MODULE.client_container_name(args, state, 0)]


def test_avatarforge_timeout_is_one_active_work_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = argparse.Namespace(profile="avatarforge", timeout=36_000)
    monkeypatch.setattr(MODULE.time, "time", lambda: 2_800.0)
    assert MODULE.client_timeout(args, {"started_at_epoch": 1_000}) == 34_200
    monkeypatch.setattr(MODULE.time, "time", lambda: 37_001.0)
    with pytest.raises(RuntimeError, match="client_goal_timeout"):
        MODULE.client_timeout(args, {"started_at_epoch": 1_000})
    args.profile = "journal"
    assert MODULE.client_timeout(args, {"started_at_epoch": 1_000}) == 36_000


@pytest.mark.parametrize(
    ("harness", "expected"),
    (
        ("opencode", "client-session"),
        ("codex", "configured-session"),
        ("hermes", "configured-session"),
    ),
)
def test_observed_gateway_session_uses_opencode_client_identity(
    harness: str, expected: str
) -> None:
    assert (
        MODULE.observed_gateway_session(harness, "configured-session", "client-session")
        == expected
    )


def test_secure_client_state_restricts_shell_snapshots(tmp_path: Path) -> None:
    snapshots = tmp_path / "shell_snapshots"
    snapshots.mkdir(mode=0o755)
    snapshot = snapshots / "session.sh"
    snapshot.write_text("export PRIVATE=value\n")
    snapshot.chmod(0o644)

    MODULE.secure_client_state(tmp_path)

    assert snapshots.stat().st_mode & 0o777 == 0o700
    assert snapshot.stat().st_mode & 0o777 == 0o600


def test_client_container_starts_with_private_umask(tmp_path: Path) -> None:
    command = MODULE.QUALITY.docker_command(
        tmp_path / "workspace",
        tmp_path / "state",
        ["python", "-c", "pass"],
    )

    assert command[-6:] == [
        "-c",
        'umask 077; exec "$@"',
        "sh",
        "python",
        "-c",
        "pass",
    ]
    assert command[command.index("--entrypoint") + 1] == "/bin/sh"


@pytest.mark.parametrize(
    ("returncode", "session", "terminal", "failure"),
    (
        (124, None, False, "client_checkpoint_timeout"),
        (1, "private-session", False, "client_nonzero_exit"),
        (0, "private-session", False, "client_terminal_missing"),
        (0, None, True, "client_session_missing"),
    ),
)
def test_checkpoint_failures_are_distinguished(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    session: str | None,
    terminal: bool,
    failure: str,
) -> None:
    args = arguments(tmp_path, "codex")
    args.state_db = tmp_path / "unused.db"
    args.timeout = 1
    state = tmp_path / "state"
    state.mkdir()
    control = {
        "started_at_epoch": 1,
        "baseline": {},
        "gateway_session": "private-gateway",
        "client_session": None,
    }
    globals_ = MODULE.run_checkpoint.__globals__
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    monkeypatch.setattr(
        MODULE.QUALITY,
        "run_process",
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess(
            [], returncode, "", "failure"
        ),
    )
    monkeypatch.setattr(MODULE.RUNTIME, "runtime_snapshot", lambda: {})
    monkeypatch.setitem(
        globals_,
        "client_command",
        lambda *_args, **_kwargs: (["docker", "run", "--rm", "image", "command"], {}, None),
    )
    monkeypatch.setitem(globals_, "wait_until", lambda _target: None)
    monkeypatch.setitem(globals_, "container_exists", lambda _name: False)
    monkeypatch.setitem(
        globals_,
        "client_metrics",
        lambda *_args: {
            "session": session,
            "terminal": terminal,
            "context_tokens": 0,
            "cached_tokens": 0,
            "tool_calls": 0,
            "retries": 0,
            "unjustified_repeated_reads": 0,
            "output_sha256": "0" * 64,
        },
    )

    with pytest.raises(RuntimeError, match=failure):
        MODULE.run_checkpoint(args, state, control, 0)


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        ("Error response from daemon", "container_runtime"),
        ("Gateway is draining", "gateway_draining"),
        ("stream disconnected before completion", "stream_disconnected"),
        ("unrecognized client failure", "unclassified"),
    ),
)
def test_client_exit_classification_never_returns_payload(
    output: str, expected: str
) -> None:
    assert MODULE.classify_client_exit(output, "") == expected


@pytest.mark.parametrize(("profile", "index"), (("journal", 1), ("avatarforge", 0)))
def test_checkpoint_requires_committed_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    index: int,
) -> None:
    args = arguments(tmp_path, "codex")
    args.profile = profile
    args.state_db = tmp_path / "unused.db"
    args.timeout = 1
    state = tmp_path / "state"
    state.mkdir()
    baseline = "a" * 40
    control = {
        "started_at_epoch": MODULE.time.time(),
        "baseline": {"commit": baseline},
        "gateway_session": "private-gateway",
        "client_session": None,
    }
    globals_ = MODULE.run_checkpoint.__globals__
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    monkeypatch.setattr(
        MODULE.QUALITY,
        "run_process",
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess([], 0, "", ""),
    )
    monkeypatch.setattr(MODULE.RUNTIME, "runtime_snapshot", lambda: {})
    monkeypatch.setitem(
        globals_,
        "client_command",
        lambda *_args, **_kwargs: (["docker", "run", "--rm", "image", "command"], {}, None),
    )
    monkeypatch.setitem(globals_, "wait_until", lambda _target: None)
    monkeypatch.setitem(globals_, "container_exists", lambda _name: False)
    monkeypatch.setitem(
        globals_,
        "client_metrics",
        lambda *_args: {
            "session": "private-session",
            "terminal": True,
            "context_tokens": 0,
            "cached_tokens": 0,
            "tool_calls": 1,
            "retries": 0,
            "unjustified_repeated_reads": 0,
            "output_sha256": "0" * 64,
        },
    )
    monkeypatch.setitem(
        globals_,
        "gateway_progress_state",
        lambda *_args: {
            "phase_index": index,
            "phase": (
                MODULE.AVATARFORGE_PHASES
                if profile == "avatarforge"
                else MODULE.PHASES
            )[index],
            "next_action_sha256": "0" * 64,
            "context_summary_sha256": "0" * 64,
            "evidence_sha256": "0" * 64,
            "premature_completion": False,
        },
    )
    monkeypatch.setitem(
        globals_,
        "git_snapshot",
        lambda _workspace: {"dirty_state": "clean", "commit": baseline},
    )
    monkeypatch.setitem(globals_, "git", lambda *_args: "")

    with pytest.raises(RuntimeError, match="implementation_checkpoint_unchanged"):
        MODULE.run_checkpoint(args, state, control, index)
