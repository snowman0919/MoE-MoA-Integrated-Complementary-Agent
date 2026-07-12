from __future__ import annotations

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
