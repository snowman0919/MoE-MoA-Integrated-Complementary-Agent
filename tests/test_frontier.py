from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from dgx_moa.frontier import (
    COLLABORATION_SCHEMAS,
    CodexOAuthCollaboration,
    CodexOAuthProvider,
    FrontierConfig,
    FrontierResult,
    FrontierTask,
    build_frontier_task,
    classify_frontier_failure,
    codex_command,
    codex_usage,
    evaluate_frontier_candidate,
    frontier_eligible,
    load_frontier_config,
    profile_lock,
    profile_status,
    record_frontier_run,
    select_frontier_profile,
    validate_isolated_worktree,
    validate_profile_name,
    validate_scope,
)
from dgx_moa.state import Phase, SessionState


def test_frontier_profile_and_selection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert validate_profile_name("primary") == "primary"
    with pytest.raises(ValueError):
        validate_profile_name("../secret")
    assert profile_status("primary", tmp_path)["authenticated"] == "no"
    assert str(tmp_path) not in profile_status("primary", tmp_path).values()
    assert (
        select_frontier_profile(explicit_profile="secondary", primary_profile="primary")
        == "secondary"
    )
    assert select_frontier_profile(explicit_profile=None, primary_profile="primary") == "primary"
    assert (
        select_frontier_profile(
            explicit_profile=None,
            primary_profile="primary",
            primary_auth_failed=True,
            allow_failover=False,
            failover_profile="secondary",
        )
        is None
    )


def test_frontier_lock_and_eligibility(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = SessionState(session_id="frontier", phase=Phase.REPLANNING)
    assert frontier_eligible(state, {"validated_replan_failed": True}) == (
        True,
        "validated_replan_failed",
    )
    assert (
        frontier_eligible(state, {"frontier_requested": True, "frontier_invocations": 1})[0]
        is False
    )
    assert classify_frontier_failure("You've hit your usage limit") == "FRONTIER_USAGE_LIMIT"
    assert classify_frontier_failure("HTTP 429") == "FRONTIER_RATE_LIMIT"
    assert classify_frontier_failure("503 unavailable") == "FRONTIER_PROVIDER_UNAVAILABLE"
    usage_event = '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}'
    assert codex_usage(usage_event) == (
        7,
        3,
    )

    def take_second_lock() -> None:
        with profile_lock("primary", tmp_path):
            pass

    with profile_lock("primary", tmp_path), pytest.raises(RuntimeError, match="already active"):
        take_second_lock()


def test_frontier_task_scope_and_candidate_gate() -> None:
    state = SessionState(session_id="frontier", objective="fix", approved_scope=["gateway/src"])
    task = build_frontier_task(state, {"task_id": "one", "base_commit": "abc"})
    assert json.loads(task.model_dump_json())["schema_version"] == "frontier-task-v1"
    validate_scope(["gateway/src/dgx_moa/frontier.py"], task.allowed_paths)
    with pytest.raises(ValueError, match="FRONTIER_SCOPE_VIOLATION"):
        validate_scope([".env"], task.allowed_paths)
    result = FrontierResult(
        status="completed", summary="done", root_cause="x", recommended_next_action="review"
    )
    evaluation = evaluate_frontier_candidate(
        result,
        changed_paths=["gateway/src/dgx_moa/frontier.py"],
        task=task,
        focused_tests_passed=True,
        benchmark_passed=True,
        secret_scan_passed=True,
        local_review_passed=True,
    )
    assert evaluation == {
        "accepted_for_human_review": True,
        "automatic_merge": False,
        "automatic_deploy": False,
        "human_approval_required": True,
        "reason": "all deterministic gates passed",
    }


def test_frontier_config(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "frontier.yaml"
    config.write_text("model: gpt-5.6-sol\nreasoning_effort: high\n")
    assert load_frontier_config(config).model == "gpt-5.6-sol"
    command = codex_command("primary", config, tmp_path, "gpt-5.6-sol", "high", config)
    assert 'model_reasoning_effort="high"' in command
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert "--ask-for-approval" not in command
    assert CodexOAuthProvider("primary", tmp_path).environment()["CODEX_HOME"] == str(
        tmp_path / "primary"
    )
    assert "CODEX_HOME" not in CodexOAuthProvider("default").environment()


def test_codex_oauth_environment_excludes_gateway_secrets(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DGX_MOA_API_KEYS", '{"client":"secret"}')
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    environment = CodexOAuthProvider("primary", tmp_path).environment()

    assert environment["PATH"] == "/usr/bin"
    assert environment["CODEX_HOME"] == str(tmp_path / "primary")
    assert "DGX_MOA_API_KEYS" not in environment
    assert "OPENAI_API_KEY" not in environment


@pytest.mark.parametrize(
    ("mode", "output"),
    [
        (
            "architecture",
            {
                "recommended_architecture": "bounded",
                "design_decisions": [],
                "tradeoffs": [],
                "failure_modes": [],
                "implementation_sequence": [],
                "review_questions": [],
            },
        ),
        (
            "code_review",
            {
                "verdict": "approve",
                "critical": [],
                "important": [],
                "suggestions": [],
                "missing_tests": [],
                "confidence": 0.9,
            },
        ),
        (
            "disagreement",
            {
                "preferred_position": "evidence",
                "evidence": [],
                "rejected_assumptions": [],
                "required_follow_up": [],
                "confidence": 0.8,
            },
        ),
    ],
)
def test_codex_oauth_collaboration_modes_are_read_only_and_redacted(
    tmp_path, monkeypatch: pytest.MonkeyPatch, mode: str, output: dict[str, object]
) -> None:  # type: ignore[no-untyped-def]
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        observed["command"] = command
        observed["task"] = command[-1]
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(json.dumps(output))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed","usage":{"input_tokens":11,"output_tokens":5}}',
            stderr="",
        )

    monkeypatch.setattr("dgx_moa.frontier.subprocess.run", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            model="gpt-5.6-sol",
            primary_profile="default",
            collaboration_retries=0,
            input_cost_per_million=1.0,
            output_cost_per_million=2.0,
        ),
        tmp_path / "run",
        tmp_path,
    )
    result = runner._run(  # type: ignore[arg-type]
        mode,
        {"objective": "review", "api_key": "sk-secret-value"},
        "correlation",
    )

    command = observed["command"]
    assert isinstance(command, list)
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "sk-secret-value" not in str(observed["task"])
    assert COLLABORATION_SCHEMAS[mode].model_validate(result.output)
    assert result.total_tokens == 16
    assert result.cost_usd == 0.000021


def test_codex_oauth_timeout_opens_circuit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    def timeout(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["env"]["CODEX_HOME"]).name)
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("dgx_moa.frontier.subprocess.run", timeout)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
            circuit_failure_limit=1,
            circuit_cooldown_seconds=300,
        ),
        tmp_path / "run",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="FRONTIER_TIMEOUT"):
        runner._run("architecture", {"objective": "x"}, "one")
    with pytest.raises(RuntimeError, match="FRONTIER_CIRCUIT_OPEN"):
        runner._run("architecture", {"objective": "x"}, "two")
    assert profiles == ["primary"]


@pytest.mark.parametrize("primary_failure", ["not logged in", "usage limit", "rate limit"])
def test_codex_oauth_falls_back_to_secondary_profile(
    tmp_path, monkeypatch: pytest.MonkeyPatch, primary_failure: str
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profile = Path(kwargs["env"]["CODEX_HOME"]).name
        profiles.append(profile)
        if profile == "primary":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=primary_failure)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "recommended_architecture": "secondary",
                    "design_decisions": [],
                    "tradeoffs": [],
                    "failure_modes": [],
                    "implementation_sequence": [],
                    "review_questions": [],
                }
            )
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}',
            stderr="",
        )

    monkeypatch.setattr("dgx_moa.frontier.subprocess.run", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    result = runner._run("architecture", {"objective": "x"}, "fallback")

    assert profiles == ["primary", "secondary"]
    assert result.profile == "secondary"
    assert result.total_tokens == 10


@pytest.mark.parametrize(
    ("primary_failure", "failure_class"),
    [
        ("connection refused", "FRONTIER_PROVIDER_UNAVAILABLE"),
        ("malformed response", "FRONTIER_PROTOCOL_ERROR"),
    ],
)
def test_codex_oauth_does_not_fail_over_unapproved_failures(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    primary_failure: str,
    failure_class: str,
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["env"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=primary_failure)

    monkeypatch.setattr("dgx_moa.frontier.subprocess.run", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match=failure_class):
        runner._run("architecture", {"objective": "x"}, "no-fallback")

    assert profiles == ["primary"]


def test_codex_oauth_does_not_fail_over_validation_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["env"]["CODEX_HOME"]).name)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text("{}")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.subprocess.run", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(ValueError):
        runner._run("architecture", {"objective": "x"}, "invalid-result")

    assert profiles == ["primary"]


def test_frontier_output_schema_uses_strict_property_types() -> None:
    schema = json.loads((Path(__file__).parents[1] / "schemas/frontier-result-v1.json").read_text())
    assert schema["properties"]["schema_version"] == {
        "type": "string",
        "const": "frontier-result-v1",
    }
    assert schema["properties"]["status"]["type"] == "string"
    assert schema["properties"]["changes"]["items"]["required"] == ["path", "purpose"]
    assert schema["properties"]["validation"]["items"]["required"] == [
        "command",
        "exit_code",
        "summary",
    ]


def test_frontier_rejects_production_worktree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    task = FrontierTask(
        task_id="one",
        objective="x",
        repository_identity={"workspace_path": str(tmp_path)},
        base_commit="abc",
        allowed_paths=["gateway"],
        acceptance_criteria=[],
    )
    with pytest.raises(ValueError, match="must not be production"):
        validate_isolated_worktree(task, tmp_path)


def test_frontier_rejects_immutable_evaluator_change() -> None:
    task = FrontierTask(
        task_id="one",
        objective="x",
        base_commit="abc",
        allowed_paths=["data/benchmarks"],
        acceptance_criteria=[],
    )
    result = FrontierResult(
        status="completed", summary="done", root_cause="x", recommended_next_action="review"
    )
    with pytest.raises(ValueError, match="immutable baseline"):
        evaluate_frontier_candidate(
            result,
            changed_paths=["data/benchmarks/mvp-baseline.json"],
            task=task,
            focused_tests_passed=True,
            benchmark_passed=True,
            secret_scan_passed=True,
            local_review_passed=True,
        )


def test_frontier_run_record_excludes_credentials(tmp_path) -> None:  # type: ignore[no-untyped-def]
    task = FrontierTask(
        task_id="record",
        objective="x",
        repository_identity={"workspace_path": "/repo"},
        base_commit="abc",
        allowed_paths=[],
        acceptance_criteria=[],
    )
    path = record_frontier_run(
        tmp_path,
        task,
        profile="secondary",
        model="gpt-5.6-sol",
        reasoning_effort="high",
        result=FrontierResult(
            status="blocked", summary="x", root_cause="x", recommended_next_action="local"
        ),
        failure_class="FRONTIER_VALIDATION_FAILURE",
    )
    assert "auth" not in path.read_text().lower()


def test_frontier_accepts_registered_isolated_worktree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    production = tmp_path / "production"
    worktree = tmp_path / "frontier"
    production.mkdir()
    subprocess.run(["git", "init", "-q", str(production)], check=True)
    (production / "README.md").write_text("fixture\n")
    subprocess.run(["git", "-C", str(production), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(production),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(production), "worktree", "add", "-qb", "frontier/test", str(worktree)],
        check=True,
    )
    task = FrontierTask(
        task_id="one",
        objective="x",
        repository_identity={"workspace_path": str(production)},
        base_commit="abc",
        allowed_paths=["gateway"],
        acceptance_criteria=[],
    )
    validate_isolated_worktree(task, worktree)
