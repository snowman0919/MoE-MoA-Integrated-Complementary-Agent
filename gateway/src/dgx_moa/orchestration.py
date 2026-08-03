from __future__ import annotations

from typing import Any

from .evidence import active_failures, effective_objective
from .schemas import ReasonerContribution
from .state import SessionState


def orchestration_requirements(
    state: SessionState,
    reasoner: ReasonerContribution,
    metadata: dict[str, Any],
) -> tuple[list[str], bool, bool]:
    required = [role for role in state.roles_required if role in {"planner", "reviewer", "judge"}]
    objective = effective_objective(state).lower()
    implementation_evidence = any(
        metadata.get(key)
        for key in (
            "diff_summary",
            "relevant_diff",
            "changed_paths",
            "validation_results",
            "completion_evidence",
        )
    )
    architecture = bool(metadata.get("architecture") or metadata.get("design")) or any(
        marker in objective
        for marker in (
            "architecture",
            "architect",
            "design",
            "migration",
            "아키텍처",
            "설계",
            "마이그레이션",
        )
    )
    code_review = (
        bool(metadata.get("code_review"))
        or bool(metadata.get("executor_complete") and implementation_evidence)
        or any(
            marker in objective
            for marker in ("code review", "review this", "diff review", "코드 리뷰", "검토")
        )
    )
    frontier = (
        architecture
        or code_review
        or state.request_class == "high_risk_task"
        or any(item.needed and item.role == "frontier" for item in reasoner.additional_agents)
        or len(active_failures(state)) >= 2
    )
    if reasoner.confidence_category == "low":
        required.append("planner")
    if architecture:
        required.append("planner")
    if code_review:
        required.append("reviewer")
    if state.request_class in {"multi_file_task", "recovery_task"}:
        required.append("planner")
    if state.request_class == "high_risk_task" and implementation_evidence:
        required.append("reviewer")
    if frontier:
        required.append("frontier")
    if metadata.get("unresolved_disagreement"):
        required.append("frontier")
        if state.request_class == "high_risk_task" or metadata.get("heavy_review"):
            required.append("judge")
    return list(dict.fromkeys(required)), architecture, code_review
