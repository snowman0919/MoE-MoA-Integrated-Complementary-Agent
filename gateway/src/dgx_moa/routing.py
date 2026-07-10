from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def select_route(metadata: dict[str, Any]) -> tuple[str, list[str]]:
    """Return deterministic route and machine-readable reasons."""
    files = int(metadata.get("expected_files", metadata.get("files_changed", 0)) or 0)
    risks = {
        "authentication": bool(metadata.get("authentication")),
        "cryptography": bool(metadata.get("cryptography")),
        "database_schema": bool(metadata.get("database_schema")),
        "deployment_security": bool(metadata.get("deployment_security")),
        "public_api": bool(metadata.get("public_api")),
    }
    heavy = [name for name, enabled in risks.items() if enabled]
    if bool(metadata.get("heavy_review")):
        heavy.append("explicit_heavy_review")
    if heavy:
        return "escalation", heavy
    fast_blockers = []
    if not bool(metadata.get("target_clear")):
        fast_blockers.append("target_unclear")
    if files not in (1, 2):
        fast_blockers.append("expected_files_not_1_or_2")
    if not bool(metadata.get("validation_command")):
        fast_blockers.append("missing_validation_command")
    if bool(metadata.get("scope_uncertain")):
        fast_blockers.append("scope_requires_planning")
    if not fast_blockers:
        return "fast", ["clear_limited_validated_change"]
    return "standard", fast_blockers


def needs_planner(state: SessionState, nontrivial: bool = True) -> bool:
    return (
        state.route != "fast"
        and nontrivial
        and (
            state.phase in {Phase.INTAKE, Phase.REPLANNING}
            or any(count >= 2 for count in state.failure_families.values())
            or not state.plan
        )
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
