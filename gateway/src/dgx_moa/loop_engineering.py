from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LoopType = Literal[
    "implementation",
    "debugging",
    "review",
    "planning",
    "recovery",
    "validation",
    "skill_evaluation",
    "prompt_evaluation",
    "policy_evaluation",
    "routing_evaluation",
    "dataset_validation",
]
LOOP_TYPES = frozenset(
    {
        "implementation",
        "debugging",
        "review",
        "planning",
        "recovery",
        "validation",
        "skill_evaluation",
        "prompt_evaluation",
        "policy_evaluation",
        "routing_evaluation",
        "dataset_validation",
    }
)
CriterionState = Literal["unknown", "passed", "failed", "waived"]
ProgressState = Literal["progressing", "stalled", "terminated"]
TerminationReason = Literal[
    "SUCCESS",
    "PARTIAL_SUCCESS",
    "USER_DECISION_REQUIRED",
    "PERMISSION_REQUIRED",
    "POLICY_BLOCKED",
    "NO_PROGRESS",
    "DUPLICATE_FAILURE_LIMIT",
    "BUDGET_EXHAUSTED",
    "PROVIDER_UNAVAILABLE",
    "JUDGE_REJECTED",
    "UNRESOLVED_HIGH_RISK_DISAGREEMENT",
    "INTERNAL_FAILURE",
    "CLIENT_CANCELLED",
]
BudgetName = Literal[
    "iterations",
    "tool_calls",
    "reasoner_reentries",
    "planner_calls",
    "reviewer_calls",
    "frontier_calls",
    "judge_calls",
]
UsageBudgetName = Literal["tokens", "external_cost_usd"]
FailureClass = Literal[
    "TEST_FAILURE",
    "BUILD_FAILURE",
    "TYPECHECK_FAILURE",
    "LINT_FAILURE",
    "TOOL_EXECUTION_FAILURE",
    "UNSUPPORTED_TOOL",
    "MCP_SERVER_UNAVAILABLE",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_TIMEOUT",
    "AUTHENTICATION_FAILURE",
    "RATE_LIMITED",
    "INVALID_STRUCTURED_OUTPUT",
    "CONTEXT_INSUFFICIENT",
    "REPOSITORY_STATE_MISMATCH",
    "PLAN_INVALIDATED",
    "POLICY_BLOCKED",
    "PERMISSION_REQUIRED",
    "NO_PROGRESS",
    "DUPLICATE_FAILURE",
    "BUDGET_EXHAUSTED",
    "JUDGE_REJECTED",
    "JUDGE_UNAVAILABLE",
    "INTERNAL_RUNTIME_ERROR",
]
PROGRESS_EVIDENCE_KINDS = frozenset(
    {
        "tool_observed_fact",
        "tool_failure",
        "test_result",
        "build_result",
        "lint_result",
        "typecheck_result",
        "repository_observation",
        "file_change",
        "reviewer_finding",
        "judge_finding",
        "external_expert_finding",
        "user_feedback",
        "provider_failure",
        "policy_decision",
        "acceptance_evidence",
        "failure_resolved",
    }
)


class LoopBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    iterations: int = Field(default=4, ge=0)
    tool_calls: int = Field(default=30, ge=0)
    reasoner_reentries: int = Field(default=4, ge=0)
    planner_calls: int = Field(default=2, ge=0)
    reviewer_calls: int = Field(default=2, ge=0)
    frontier_calls: int = Field(default=2, ge=0)
    judge_calls: int = Field(default=2, ge=0)
    tokens: int = Field(default=250_000, ge=0)
    external_cost_usd: float = Field(default=10, ge=0, allow_inf_nan=False)
    wall_clock_seconds: float = Field(default=1_800, ge=0, allow_inf_nan=False)


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    criterion_id: str
    description: str = Field(min_length=1, max_length=2_000)
    required: bool = True
    state: CriterionState = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    waiver_reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def require_support(self) -> AcceptanceCriterion:
        if self.state == "passed" and not self.evidence_ids:
            raise ValueError("passed criterion requires evidence")
        if self.state == "waived" and not self.waiver_reason:
            raise ValueError("waived criterion requires a reason")
        return self


class LoopFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    failure_class: FailureClass
    occurrence_count: int = Field(default=1, ge=1)
    attempted_strategies: list[str] = Field(default_factory=list)
    strategy_change_required: bool = False
    affected_paths: list[str] = Field(default_factory=list)


class LoopState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    loop_id: str
    request_id: str
    loop_type: LoopType
    iteration: int = Field(default=0, ge=0)
    completed_iteration: int = Field(default=0, ge=0)
    objective: str
    accepted_plan: list[dict[str, object]] = Field(default_factory=list)
    completed_actions: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    observed_evidence_ids: list[str] = Field(default_factory=list)
    progress_evidence_fingerprints: list[str] = Field(default_factory=list)
    open_failures: list[LoopFailure] = Field(default_factory=list)
    accepted_findings: list[str] = Field(default_factory=list)
    rejected_findings: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    retrieved_knowledge: list[str] = Field(default_factory=list)
    active_agents: list[str] = Field(default_factory=list)
    remaining_budget: LoopBudget = Field(default_factory=LoopBudget)
    progress_state: ProgressState = "progressing"
    termination_reason: TerminationReason | None = None
    started_at_epoch: float = Field(default_factory=time.time, ge=0, allow_inf_nan=False)
    last_iteration_evidence_count: int = Field(default=0, ge=0)
    no_progress_iterations: int = Field(default=0, ge=0)
    no_progress_iteration_limit: int = Field(default=2, ge=1)
    input_fingerprints: list[str] = Field(default_factory=list)


def new_loop(
    request_id: str,
    objective: str,
    *,
    loop_type: LoopType = "implementation",
    budget: LoopBudget | None = None,
    no_progress_iteration_limit: int = 2,
) -> LoopState:
    loop = LoopState(
        loop_id=f"loop_{uuid.uuid4().hex}",
        request_id=request_id,
        loop_type=loop_type,
        objective=objective,
        remaining_budget=budget or LoopBudget(),
        no_progress_iteration_limit=no_progress_iteration_limit,
    )
    register_user_input(loop, objective)
    return loop


def record_progress(
    loop: LoopState, evidence_id: str, *, evidence_fingerprint: str | None = None
) -> bool:
    if evidence_id in loop.observed_evidence_ids or (
        evidence_fingerprint is not None
        and evidence_fingerprint in loop.progress_evidence_fingerprints
    ):
        return False
    loop.observed_evidence_ids.append(evidence_id)
    if evidence_fingerprint is not None:
        loop.progress_evidence_fingerprints.append(evidence_fingerprint)
    loop.progress_state = "progressing"
    loop.no_progress_iterations = 0
    return True


def register_user_input(loop: LoopState, content: str) -> str | None:
    fingerprint = hashlib.sha256(content.encode()).hexdigest()
    if fingerprint in loop.input_fingerprints:
        return None
    loop.input_fingerprints.append(fingerprint)
    return fingerprint


def progress_evidence_fingerprint(kind: str, payload: object) -> str:
    stable = _drop_unstable_evidence_fields(payload)
    serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{kind}:{serialized}".encode()).hexdigest()


def _drop_unstable_evidence_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _drop_unstable_evidence_fields(item)
            for key, item in value.items()
            if key
            not in {
                "created_at",
                "ended_at",
                "started_at",
                "timestamp",
                "duration_ms",
                "latency_ms",
                "request_id",
                "tool_call_id",
            }
        }
    if isinstance(value, list):
        return [_drop_unstable_evidence_fields(item) for item in value]
    return value


def record_no_progress(loop: LoopState) -> None:
    loop.no_progress_iterations += 1
    loop.progress_state = "stalled"
    if loop.no_progress_iterations >= loop.no_progress_iteration_limit:
        terminate(loop, "NO_PROGRESS")


def begin_iteration(loop: LoopState, *, now_epoch: float | None = None) -> bool:
    if loop.termination_reason is not None:
        return False
    current = time.time() if now_epoch is None else now_epoch
    elapsed = max(0.0, current - loop.started_at_epoch)
    loop.remaining_budget.wall_clock_seconds = max(
        0.0, loop.remaining_budget.wall_clock_seconds - elapsed
    )
    loop.started_at_epoch = current
    if loop.remaining_budget.wall_clock_seconds == 0 or loop.remaining_budget.iterations == 0:
        terminate(loop, "BUDGET_EXHAUSTED")
        return False
    if loop.iteration and len(loop.observed_evidence_ids) == loop.last_iteration_evidence_count:
        record_no_progress(loop)
        return False
    loop.iteration += 1
    loop.remaining_budget.iterations -= 1
    loop.last_iteration_evidence_count = len(loop.observed_evidence_ids)
    loop.progress_state = "progressing"
    return True


def consume_budget(loop: LoopState, name: BudgetName) -> bool:
    if loop.termination_reason is not None:
        return False
    remaining = getattr(loop.remaining_budget, name)
    if remaining == 0:
        terminate(loop, "BUDGET_EXHAUSTED")
        return False
    setattr(loop.remaining_budget, name, remaining - 1)
    return True


def consume_usage(loop: LoopState, name: UsageBudgetName, amount: int | float) -> bool:
    if amount < 0:
        raise ValueError("usage amount must be nonnegative")
    if loop.termination_reason is not None:
        return False
    remaining = getattr(loop.remaining_budget, name)
    if amount > remaining:
        setattr(loop.remaining_budget, name, 0)
        terminate(loop, "BUDGET_EXHAUSTED")
        return False
    setattr(loop.remaining_budget, name, remaining - amount)
    return True


def set_criterion(
    loop: LoopState,
    description: str,
    state: CriterionState,
    *,
    evidence_ids: list[str] | None = None,
    waiver_reason: str | None = None,
    required: bool = True,
) -> AcceptanceCriterion:
    existing = next(
        (item for item in loop.acceptance_criteria if item.description == description), None
    )
    criterion = AcceptanceCriterion(
        criterion_id=existing.criterion_id if existing else f"ac_{uuid.uuid4().hex}",
        description=description,
        required=required,
        state=state,
        evidence_ids=evidence_ids or [],
        waiver_reason=waiver_reason,
    )
    if existing:
        loop.acceptance_criteria[loop.acceptance_criteria.index(existing)] = criterion
    else:
        loop.acceptance_criteria.append(criterion)
    return criterion


def completion_ready(loop: LoopState) -> bool:
    required = [item for item in loop.acceptance_criteria if item.required]
    return bool(required) and all(item.state in {"passed", "waived"} for item in required)


def terminate(loop: LoopState, reason: TerminationReason) -> None:
    loop.termination_reason = reason
    loop.progress_state = "terminated"


def register_failure(
    loop: LoopState,
    failure_class: FailureClass,
    *,
    strategy: str = "",
    **fingerprint_fields: object,
) -> LoopFailure:
    fingerprint = failure_fingerprint(failure_class=failure_class, **fingerprint_fields)
    existing = next((item for item in loop.open_failures if item.fingerprint == fingerprint), None)
    if existing is None:
        raw_paths = fingerprint_fields.get("affected_path", [])
        affected_paths = (
            [str(path) for path in raw_paths]
            if isinstance(raw_paths, list | tuple | set)
            else [str(raw_paths)]
            if raw_paths
            else []
        )
        failure = LoopFailure(
            fingerprint=fingerprint,
            failure_class=failure_class,
            attempted_strategies=[strategy] if strategy else [],
            affected_paths=affected_paths,
        )
        loop.open_failures.append(failure)
        return failure
    existing.occurrence_count += 1
    existing.strategy_change_required = existing.occurrence_count >= 2
    if strategy and strategy not in existing.attempted_strategies:
        existing.attempted_strategies.append(strategy)
        existing.strategy_change_required = False
    if existing.occurrence_count >= 3:
        terminate(loop, "DUPLICATE_FAILURE_LIMIT")
    return existing


def resolve_failures(loop: LoopState, paths: set[str]) -> int:
    resolved = [
        failure for failure in loop.open_failures if paths.intersection(failure.affected_paths)
    ]
    loop.open_failures = [failure for failure in loop.open_failures if failure not in resolved]
    return len(resolved)


def normalized_failure_class(value: str) -> FailureClass:
    mapped: dict[str, FailureClass] = {
        "TEST_FAILURE": "TEST_FAILURE",
        "UNSUPPORTED_TOOL": "UNSUPPORTED_TOOL",
        "MCP_SERVER_UNAVAILABLE": "MCP_SERVER_UNAVAILABLE",
        "NONEXISTENT_PATH": "TOOL_EXECUTION_FAILURE",
        "SYNTAX_ERROR": "BUILD_FAILURE",
        "TYPE_ERROR": "TYPECHECK_FAILURE",
        "CONTEXT_OVERFLOW": "CONTEXT_INSUFFICIENT",
        "TIMEOUT": "TOOL_EXECUTION_FAILURE",
        "MODEL_BACKEND_ERROR": "PROVIDER_UNAVAILABLE",
    }
    return mapped.get(value, "TOOL_EXECUTION_FAILURE")


def failure_fingerprint(**fields: object) -> str:
    normalized = {
        key: _normalize_failure_value(str(value))
        for key, value in fields.items()
        if value not in (None, "")
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _normalize_failure_value(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}t\S+", "<timestamp>", normalized)
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<request-id>", normalized)
    normalized = re.sub(r"/(?:tmp|var/tmp)/[^\s:]+", "/<tmp>", normalized)
    normalized = re.sub(r"0x[0-9a-f]+", "<address>", normalized)
    normalized = re.sub(r"\bline \d+\b", "line <n>", normalized)
    return " ".join(normalized.split())
