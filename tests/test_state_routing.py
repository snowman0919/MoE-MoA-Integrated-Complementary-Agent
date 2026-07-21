from __future__ import annotations

import pytest
from dgx_moa.routing import (
    ChangeRisk,
    classify_request,
    heavy_eligible,
    needs_planner,
    needs_reviewer,
    optional_roles,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
    select_route,
)
from dgx_moa.state import Phase, SessionState, StateStore
from dgx_moa.validation import completion_ready, missing_evidence


def test_session_persistence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "state.db"
    first = StateStore(path)
    state = SessionState(session_id="persist", objective="ship")
    first.save(state)
    loaded = StateStore(path).get("persist")
    assert loaded and loaded.objective == "ship"


def test_deterministic_routing_and_completion() -> None:
    state = SessionState(session_id="x", acceptance_criteria=["tests", "security"])
    assert needs_planner(state)
    state.plan = [{"step": "work"}]
    state.phase = Phase.EXECUTING
    assert not needs_planner(state)
    assert needs_reviewer(state, executor_stopped=True, meaningful_diff=True)
    assert heavy_eligible(state, ChangeRisk(authentication=True))
    state.review_status = "approved"
    state.completion_evidence["tests"] = "pytest exit 0"
    assert missing_evidence(state) == ["security"]
    state.completion_evidence["security"] = "reviewed"
    assert completion_ready(state)
    state.heavy_switch_count = 1
    assert not heavy_eligible(state, ChangeRisk(explicit=True))


def test_route_selection_has_machine_reasons() -> None:
    assert select_route(
        {"target_clear": True, "expected_files": 1, "validation_command": "pytest"}
    ) == ("fast", ["clear_limited_validated_change"])
    route, reasons = select_route({"authentication": True})
    assert route == "escalation" and reasons == ["authentication"]


@pytest.mark.parametrize(
    ("model", "mode"),
    [
        ("dgx-moa", "moa"),
        ("dgx-moa-fast", "fast"),
        ("dgx-moa-chat", "fast"),
        ("dgx-moa-agent", "agent"),
        ("dgx-moa-orchestrated", "orchestrated"),
    ],
)
def test_public_model_aliases(model: str, mode: str) -> None:
    assert resolve_runtime_mode(model, "dgx-moa-agent") == mode


@pytest.mark.parametrize(
    ("model", "mode"),
    [
        ("dgx-moa", "moa"),
        ("dgx-moa-fast", "fast"),
        ("dgx-moa-chat", "fast"),
        ("dgx-moa-orchestrated", "orchestrated"),
    ],
)
def test_configured_name_cannot_override_public_model_alias(model: str, mode: str) -> None:
    assert resolve_runtime_mode(model, model) == mode


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        resolve_runtime_mode("missing", "dgx-moa-agent")


def test_request_classes_and_roles() -> None:
    assert (
        classify_request("fast", [{"role": "user", "content": "Hello"}], None, {}) == "plain_chat"
    )
    assert (
        classify_request("moa", [{"role": "user", "content": "What changed?"}], None, {})
        == "read_only_question"
    )
    assert (
        classify_request("agent", [{"role": "tool", "content": "ok"}], None, {})
        == "native_agent_turn"
    )
    assert (
        classify_request("orchestrated", [], None, {"target_clear": True, "expected_files": 1})
        == "small_clear_edit"
    )
    assert classify_request("orchestrated", [], None, {"expected_files": 4}) == "multi_file_task"
    assert classify_request("orchestrated", [], None, {"recovery_task": True}) == "recovery_task"
    assert classify_request("orchestrated", [], None, {"authentication": True}) == "high_risk_task"
    assert classify_request("orchestrated", [], None, {}) == "explicit_orchestrated"
    assert required_roles("fast", "plain_chat") == ("executor",)
    assert required_roles("moa", "plain_chat") == ("reasoner", "executor")
    assert required_roles("agent", "high_risk_task") == ("reasoner", "executor")
    assert required_roles("orchestrated", "multi_file_task") == (
        "reasoner",
        "executor",
    )
    assert required_roles("orchestrated", "high_risk_task") == (
        "reasoner",
        "executor",
    )
    assert required_roles("orchestrated", "explicit_orchestrated", reasoner_mode="required") == (
        "reasoner",
        "executor",
    )
    assert optional_roles("orchestrated", reasoner_mode="optional") == ()
    assert optional_roles("agent", reasoner_mode=None) == ()
    assert review_fails_closed("high_risk_task") is True
    assert review_fails_closed("explicit_orchestrated") is False
