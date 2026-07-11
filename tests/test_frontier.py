from __future__ import annotations

import json

import pytest
from dgx_moa.frontier import (
    FrontierResult,
    build_frontier_task,
    evaluate_frontier_candidate,
    frontier_eligible,
    profile_lock,
    profile_status,
    select_frontier_profile,
    validate_profile_name,
    validate_scope,
)
from dgx_moa.state import Phase, SessionState


def test_frontier_profile_and_selection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert validate_profile_name("primary") == "primary"
    with pytest.raises(ValueError):
        validate_profile_name("../secret")
    assert profile_status("primary", tmp_path)["authenticated"] == "no"
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
