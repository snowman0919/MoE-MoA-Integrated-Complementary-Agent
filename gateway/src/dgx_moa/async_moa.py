from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

Effort = Literal["fast", "low", "medium", "high", "xhigh"]
Role = Literal["reasoner", "planner", "reviewer", "frontier"]


class EvidenceClass(StrEnum):
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    EXECUTOR_HYPOTHESIS = "EXECUTOR_HYPOTHESIS"
    AGENT_RECOMMENDATION = "AGENT_RECOMMENDATION"
    DECISION = "DECISION"


class Staleness(StrEnum):
    CURRENT = "CURRENT"
    PARTIALLY_STALE = "PARTIALLY_STALE"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    uri: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class DelegationSnapshot:
    task_state_version: int
    repository_head: str
    working_tree_hash: str
    decision_version: int
    artifact_refs: tuple[ArtifactRef, ...] = ()

    @property
    def evidence_hash(self) -> str:
        value = {
            "task_state_version": self.task_state_version,
            "repository_head": self.repository_head,
            "working_tree_hash": self.working_tree_hash,
            "decision_version": self.decision_version,
            "artifact_refs": [
                (item.artifact_id, item.kind, item.uri, item.content_hash)
                for item in self.artifact_refs
            ],
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def classify(self, current: DelegationSnapshot) -> Staleness:
        if self == current:
            return Staleness.CURRENT
        if (
            self.repository_head == current.repository_head
            and self.working_tree_hash == current.working_tree_hash
        ):
            return Staleness.PARTIALLY_STALE
        return Staleness.STALE


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    classification: EvidenceClass
    statement: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentFinding:
    claims: tuple[EvidenceClaim, ...]
    materially_corrective: bool = False
    invalidates: tuple[str, ...] = ()
    recommended_direction: str = ""
    requested_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffortBudget:
    max_concurrent_delegates: int
    delegation_budget: int
    max_depth: int
    role_budgets: dict[Role, int]
    activation_thresholds: dict[Role, int]
    semantic_cooldown_seconds: float


DEFAULT_EFFORT_BUDGETS: dict[Effort, EffortBudget] = {
    "fast": EffortBudget(
        0,
        0,
        0,
        {role: 0 for role in ("reasoner", "planner", "reviewer", "frontier")},
        {role: 101 for role in ("reasoner", "planner", "reviewer", "frontier")},
        0,
    ),
    "low": EffortBudget(
        1,
        1,
        1,
        {"reasoner": 1, "planner": 1, "reviewer": 1, "frontier": 0},
        {"reasoner": 80, "planner": 90, "reviewer": 90, "frontier": 101},
        120,
    ),
    "medium": EffortBudget(
        3,
        4,
        1,
        {"reasoner": 2, "planner": 1, "reviewer": 1, "frontier": 1},
        {"reasoner": 50, "planner": 70, "reviewer": 70, "frontier": 90},
        60,
    ),
    "high": EffortBudget(
        3,
        6,
        2,
        {"reasoner": 3, "planner": 2, "reviewer": 2, "frontier": 1},
        {"reasoner": 25, "planner": 45, "reviewer": 45, "frontier": 65},
        30,
    ),
    "xhigh": EffortBudget(
        4,
        10,
        2,
        {"reasoner": 4, "planner": 3, "reviewer": 3, "frontier": 2},
        {"reasoner": 10, "planner": 25, "reviewer": 25, "frontier": 45},
        10,
    ),
}


@dataclass(frozen=True, slots=True)
class DelegateResult:
    handle_id: str
    role: Role
    launched_from: DelegationSnapshot
    staleness: Staleness
    finding: AgentFinding | None
    failure_class: str | None = None
    failure_message: str | None = None


@dataclass(slots=True)
class DelegateHandle:
    handle_id: str
    role: Role
    launched_from: DelegationSnapshot
    fingerprint: str
    depth: int
    relevant: bool
    task: asyncio.Task[AgentFinding]


@dataclass(slots=True)
class Reconciliation:
    results: list[DelegateResult] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    reloop_required: bool = False
    notification: str | None = None
    requested_actions: list[str] = field(default_factory=list)


class AsyncMoARuntime:
    """Bounded task/future runtime; auxiliary workers return evidence, never authority."""

    def __init__(
        self,
        effort: Effort,
        *,
        budgets: dict[Effort, EffortBudget] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.effort = effort
        self.budget = (budgets or DEFAULT_EFFORT_BUDGETS)[effort]
        self._clock = clock
        self._semaphore = asyncio.Semaphore(max(1, self.budget.max_concurrent_delegates))
        self._handles: dict[str, DelegateHandle] = {}
        self._role_counts: Counter[Role] = Counter()
        self._recent: dict[str, float] = {}
        self._launched = 0
        self.useful_work_events: list[str] = []

    @property
    def pending(self) -> tuple[DelegateHandle, ...]:
        return tuple(handle for handle in self._handles.values() if not handle.task.done())

    def should_activate(self, role: Role, signal_strength: int) -> bool:
        return (
            self.effort != "fast"
            and signal_strength >= self.budget.activation_thresholds[role]
            and self._launched < self.budget.delegation_budget
            and self._role_counts[role] < self.budget.role_budgets[role]
        )

    def spawn(
        self,
        role: Role,
        snapshot: DelegationSnapshot,
        worker: Callable[[DelegationSnapshot], Awaitable[AgentFinding]],
        *,
        signal_strength: int,
        semantic_key: str,
        depth: int = 1,
        relevant: bool = True,
    ) -> DelegateHandle | None:
        if not self.should_activate(role, signal_strength):
            return None
        if depth > self.budget.max_depth or (role == "frontier" and depth != 1):
            return None
        fingerprint = hashlib.sha256(
            f"{role}\0{semantic_key}\0{snapshot.evidence_hash}".encode()
        ).hexdigest()
        last = self._recent.get(fingerprint)
        if last is not None and self._clock() - last < self.budget.semantic_cooldown_seconds:
            return None

        async def bounded_worker() -> AgentFinding:
            async with self._semaphore:
                return await worker(snapshot)

        self._launched += 1
        self._role_counts[role] += 1
        self._recent[fingerprint] = self._clock()
        handle_id = f"delegate_{self._launched:04d}_{fingerprint[:12]}"
        handle = DelegateHandle(
            handle_id,
            role,
            snapshot,
            fingerprint,
            depth,
            relevant,
            asyncio.create_task(bounded_worker(), name=handle_id),
        )
        self._handles[handle_id] = handle
        return handle

    def record_useful_work(self, event: str) -> None:
        self.useful_work_events.append(event)

    def cancel_obsolete(self, current: DelegationSnapshot) -> tuple[str, ...]:
        cancelled = []
        for handle in self.pending:
            if handle.launched_from.classify(current) is Staleness.STALE:
                handle.task.cancel()
                cancelled.append(handle.handle_id)
        return tuple(cancelled)

    async def finalize(self, current: DelegationSnapshot) -> Reconciliation:
        relevant = [handle for handle in self._handles.values() if handle.relevant]
        if relevant:
            await asyncio.gather(*(handle.task for handle in relevant), return_exceptions=True)
        reconciliation = Reconciliation()
        for handle in relevant:
            finding: AgentFinding | None = None
            failure: str | None = None
            failure_message: str | None = None
            if handle.task.cancelled():
                failure = "CancelledError"
            else:
                error = handle.task.exception()
                if error is None:
                    finding = handle.task.result()
                else:
                    failure = type(error).__name__
                    failure_message = str(error)[:256]
            staleness = handle.launched_from.classify(current)
            result = DelegateResult(
                handle.handle_id,
                handle.role,
                handle.launched_from,
                staleness,
                finding,
                failure,
                failure_message,
            )
            reconciliation.results.append(result)
            if finding is None:
                continue
            reconciliation.requested_actions.extend(finding.requested_actions)
            if finding.materially_corrective and staleness is not Staleness.STALE:
                reconciliation.reloop_required = True
                reconciliation.decisions.append(
                    {
                        "type": "direction_invalidated",
                        "old_assumptions": list(finding.invalidates),
                        "new_evidence": [
                            claim.statement
                            for claim in finding.claims
                            if claim.classification
                            in {EvidenceClass.FACT, EvidenceClass.OBSERVATION}
                        ],
                        "reason": "material auxiliary evidence",
                        "new_direction": finding.recommended_direction,
                        "affected_work": list(finding.requested_actions),
                        "source_role": handle.role,
                        "snapshot_id": handle.launched_from.evidence_hash,
                    }
                )
        if reconciliation.reloop_required:
            reconciliation.notification = (
                "새로 도착한 독립 검토 결과에서 현재 구현 방향을 수정해야 할 근거가 "
                "확인됐습니다. 영향을 받은 가정을 폐기하고 재루프해 검증하겠습니다."
            )
        reconciliation.requested_actions = list(dict.fromkeys(reconciliation.requested_actions))
        return reconciliation


def reasoner_signal(events: Iterable[str]) -> int:
    """Semantic triggers beat periodic/random activation."""
    weights = {
        "unexpected_test_result": 100,
        "new_failure": 100,
        "conflicting_evidence": 100,
        "strategy_changed": 90,
        "delegate_result_arrived": 80,
        "major_tool_output": 70,
        "new_subsystem": 60,
        "multiple_hypotheses": 60,
        "goal_alignment_check": 50,
    }
    return max((weights.get(event, 0) for event in events), default=0)
