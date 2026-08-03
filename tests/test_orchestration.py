from __future__ import annotations

from dgx_moa.orchestration import orchestration_requirements
from dgx_moa.schemas import AdditionalAgentRecommendation, ReasonerContribution
from dgx_moa.state import SessionState


def reasoner(*, confidence: str = "high", frontier: bool = False) -> ReasonerContribution:
    return ReasonerContribution(
        assumptions=[],
        constraints=[],
        conclusions=[],
        hypotheses=[],
        evidence_references=[],
        recommended_actions=[],
        confidence_category=confidence,
        additional_agents=(
            [AdditionalAgentRecommendation(role="frontier", needed=True, reason="risk")]
            if frontier
            else []
        ),
    )


def test_architecture_and_review_require_local_specialists_and_frontier() -> None:
    state = SessionState(
        session_id="architecture",
        objective="설계와 코드 리뷰를 수행해",
        request_class="small_clear_edit",
    )

    required, architecture, review = orchestration_requirements(state, reasoner(), {})

    assert required == ["planner", "reviewer", "frontier"]
    assert architecture is review is True


def test_high_risk_evidence_and_disagreement_require_review_and_judge() -> None:
    state = SessionState(
        session_id="risk",
        objective="Apply the security fix",
        request_class="high_risk_task",
    )

    required, _, _ = orchestration_requirements(
        state,
        reasoner(confidence="low", frontier=True),
        {"changed_paths": ["security.py"], "unresolved_disagreement": True},
    )

    assert required == ["planner", "reviewer", "frontier", "judge"]
