from __future__ import annotations

from dataclasses import dataclass

from .state import Phase, SessionState


@dataclass(frozen=True)
class ChangeRisk:
    files_changed: int = 0
    meaningful_lines: int = 0
    public_api: bool = False
    authentication: bool = False
    cryptography: bool = False
    database_schema: bool = False
    deployment_security: bool = False
    explicit: bool = False


def needs_planner(state: SessionState, nontrivial: bool = True) -> bool:
    return nontrivial and (
        state.phase in {Phase.INTAKE, Phase.REPLANNING}
        or any(count >= 2 for count in state.failure_families.values())
        or not state.plan
    )


def needs_reviewer(state: SessionState, executor_stopped: bool, meaningful_diff: bool) -> bool:
    return executor_stopped and meaningful_diff and state.review_status != "approved"


def heavy_eligible(state: SessionState, risk: ChangeRisk) -> bool:
    return state.heavy_switch_count == 0 and (
        risk.explicit
        or risk.public_api
        or risk.authentication
        or risk.cryptography
        or risk.database_schema
        or risk.deployment_security
        or risk.files_changed > 8
        or risk.meaningful_lines > 500
        or state.review_status == "rejected_after_correction"
        or state.judge_status == "planner_reviewer_disagreement"
        or any(count >= 3 for count in state.failure_families.values())
    )
