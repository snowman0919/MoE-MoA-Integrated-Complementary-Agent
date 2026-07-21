from __future__ import annotations

from dgx_moa.loop_engineering import (
    LoopBudget,
    begin_iteration,
    completion_ready,
    consume_budget,
    consume_usage,
    failure_fingerprint,
    new_loop,
    progress_evidence_fingerprint,
    record_progress,
    register_failure,
    register_user_input,
    resolve_failures,
    set_criterion,
)


def test_iteration_requires_new_evidence_and_terminates_after_no_progress() -> None:
    loop = new_loop("request", "fix it", no_progress_iteration_limit=2)

    assert begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert not begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert loop.termination_reason is None
    assert not begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert loop.termination_reason == "NO_PROGRESS"


def test_new_evidence_allows_next_bounded_iteration() -> None:
    loop = new_loop("request", "fix it", budget=LoopBudget(iterations=2))

    assert begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert record_progress(loop, "evidence-1")
    assert begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert not begin_iteration(loop, now_epoch=loop.started_at_epoch)
    assert loop.termination_reason == "BUDGET_EXHAUSTED"


def test_required_acceptance_criterion_needs_supporting_evidence() -> None:
    loop = new_loop("request", "fix it")
    set_criterion(loop, "tests pass", "unknown")
    assert not completion_ready(loop)

    set_criterion(loop, "tests pass", "passed", evidence_ids=["test-result-1"])
    assert completion_ready(loop)


def test_call_budget_and_failure_fingerprint_are_deterministic() -> None:
    loop = new_loop("request", "fix it", budget=LoopBudget(frontier_calls=1))
    assert consume_budget(loop, "frontier_calls")
    assert not consume_budget(loop, "frontier_calls")
    assert loop.termination_reason == "BUDGET_EXHAUSTED"

    first = failure_fingerprint(
        failure_class="TEST_FAILURE",
        stderr="2026-07-22T01:02:03Z failed at /tmp/run-a/x.py line 17 0xabc",
    )
    second = failure_fingerprint(
        failure_class="TEST_FAILURE",
        stderr="2026-07-23T04:05:06Z failed at /tmp/run-b/x.py line 91 0xdef",
    )
    assert first == second
    assert first != failure_fingerprint(failure_class="TYPECHECK_FAILURE", stderr="failed")


def test_duplicate_failure_requires_new_strategy_then_terminates() -> None:
    loop = new_loop("request", "fix it")

    first = register_failure(loop, "TEST_FAILURE", strategy="retry", stderr="assertion failed")
    second = register_failure(loop, "TEST_FAILURE", strategy="retry", stderr="assertion failed")
    assert first is second
    assert second.strategy_change_required
    assert loop.termination_reason is None

    third = register_failure(
        loop, "TEST_FAILURE", strategy="inspect fixture", stderr="assertion failed"
    )
    assert third.attempted_strategies == ["retry", "inspect fixture"]
    assert loop.termination_reason == "DUPLICATE_FAILURE_LIMIT"


def test_token_and_external_cost_budgets_fail_closed() -> None:
    loop = new_loop("request", "fix it", budget=LoopBudget(tokens=10, external_cost_usd=0.5))

    assert consume_usage(loop, "tokens", 10)
    assert not consume_usage(loop, "external_cost_usd", 0.6)
    assert loop.remaining_budget.tokens == 0
    assert loop.remaining_budget.external_cost_usd == 0
    assert loop.termination_reason == "BUDGET_EXHAUSTED"


def test_user_feedback_is_content_free_and_deduplicated() -> None:
    loop = new_loop("request", "initial objective")

    assert register_user_input(loop, "initial objective") is None
    fingerprint = register_user_input(loop, "new constraint")
    assert fingerprint is not None and len(fingerprint) == 64
    assert register_user_input(loop, "new constraint") is None


def test_progress_fingerprint_ignores_timing_noise() -> None:
    loop = new_loop("request", "fix it")
    first = progress_evidence_fingerprint("test_result", {"status": "failed", "duration_ms": 1})
    second = progress_evidence_fingerprint("test_result", {"status": "failed", "duration_ms": 999})

    assert record_progress(loop, "evidence-1", evidence_fingerprint=first)
    assert not record_progress(loop, "evidence-2", evidence_fingerprint=second)


def test_successful_same_path_evidence_resolves_open_failure() -> None:
    loop = new_loop("request", "fix it")
    register_failure(
        loop,
        "MCP_SERVER_UNAVAILABLE",
        affected_path=["/workspace/objective.md"],
    )

    assert resolve_failures(loop, {"/workspace/objective.md"}) == 1
    assert loop.open_failures == []
