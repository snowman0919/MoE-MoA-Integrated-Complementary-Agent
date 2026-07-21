from __future__ import annotations

from .loop_engineering import completion_ready as loop_completion_ready
from .state import SessionState


def completion_ready(state: SessionState) -> bool:
    if state.engineering_loop is not None:
        return state.review_status == "approved" and loop_completion_ready(state.engineering_loop)
    return (
        state.review_status == "approved"
        and bool(state.acceptance_criteria)
        and all(criterion in state.completion_evidence for criterion in state.acceptance_criteria)
    )


def missing_evidence(state: SessionState) -> list[str]:
    return [
        criterion
        for criterion in state.acceptance_criteria
        if criterion not in state.completion_evidence
    ]
