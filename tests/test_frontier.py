from __future__ import annotations

import json
import subprocess

import pytest
from dgx_moa.frontier import (
    CodexOAuthProvider,
    FrontierResult,
    FrontierTask,
    build_frontier_task,
    classify_frontier_failure,
    codex_command,
    evaluate_frontier_candidate,
    frontier_eligible,
    load_frontier_config,
    profile_lock,
    profile_status,
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
