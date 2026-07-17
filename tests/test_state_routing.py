from __future__ import annotations

import pytest

from dgx_moa.routing import (
    classify_request,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
)
from dgx_moa.routing import ChangeRisk, heavy_eligible, needs_planner, needs_reviewer, select_route
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
        ("dgx-moa-chat", "chat"),
        ("dgx-moa-agent", "agent"),
        ("dgx-moa-orchestrated", "orchestrated"),
    ],
)
def test_public_model_aliases(model: str, mode: str) -> None:
    assert resolve_runtime_mode(model, "dgx-moa-agent") == mode


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        resolve_runtime_mode("missing", "dgx-moa-agent")


def test_request_classes_and_roles() -> None:
    assert classify_request(
        "chat", [{"role": "user", "content": "Hello"}], None, {}
    ) == "plain_chat"
    assert classify_request(
        "chat", [{"role": "user", "content": "What changed?"}], None, {}
    ) == "read_only_question"
    assert classify_request(
        "agent", [{"role": "tool", "content": "ok"}], None, {}
    ) == "native_agent_turn"
    assert classify_request(
        "orchestrated", [], None, {"target_clear": True, "expected_files": 1}
    ) == "small_clear_edit"
    assert classify_request(
        "orchestrated", [], None, {"expected_files": 4}
    ) == "multi_file_task"
    assert classify_request(
        "orchestrated", [], None, {"recovery_task": True}
    ) == "recovery_task"
    assert classify_request(
        "orchestrated", [], None, {"authentication": True}
    ) == "high_risk_task"
    assert classify_request("orchestrated", [], None, {}) == "explicit_orchestrated"
    assert required_roles("chat", "plain_chat") == ("executor",)
    assert required_roles("agent", "high_risk_task") == ("executor",)
    assert required_roles("orchestrated", "multi_file_task") == ("planner", "executor")
    assert required_roles("orchestrated", "high_risk_task") == (
        "planner", "executor", "reviewer"
    )
    assert review_fails_closed("high_risk_task") is True
    assert review_fails_closed("explicit_orchestrated") is False
