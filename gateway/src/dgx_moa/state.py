from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .loop_engineering import LoopState

RuntimeChannel = Literal["main", "dev", "candidate"]
TraceOrigin = Literal["production", "benchmark", "validation", "diagnostic", "candidate_evaluation"]
TrainingEligibility = Literal["eligible", "local_only", "requires_review", "excluded"]
FinalStatus = Literal["completed", "failed", "blocked", "cancelled", "degraded"]
SuspectedLayer = Literal[
    "controller",
    "prompt",
    "routing",
    "context",
    "executor",
    "planner",
    "reviewer",
    "provider",
    "harness",
    "infrastructure",
    "external",
    "unknown",
]
ResolutionStatus = Literal[
    "active", "resolved", "expected", "synthetic", "false_positive", "superseded", "unknown"
]
SUSPECTED_LAYERS = {
    "controller",
    "prompt",
    "routing",
    "context",
    "executor",
    "planner",
    "reviewer",
    "provider",
    "harness",
    "infrastructure",
    "external",
    "unknown",
}
RESOLUTION_STATUSES = {
    "active",
    "resolved",
    "expected",
    "synthetic",
    "false_positive",
    "superseded",
    "unknown",
}


def validate_failure_record(record: dict[str, Any]) -> None:
    if record.get("suspected_layer") not in SUSPECTED_LAYERS:
        raise ValueError("invalid suspected_layer")
    if record.get("resolution_status") not in RESOLUTION_STATUSES:
        raise ValueError("invalid resolution_status")


class Phase(StrEnum):
    INTAKE = "intake"
    PLANNING = "planning"
    EXECUTING = "executing"
    REPLANNING = "replanning"
    REVIEWING = "reviewing"
    AWAITING_HEAVY_JUDGE = "awaiting_heavy_judge"
    HEAVY_REVIEW = "heavy_review"
    CORRECTION = "correction"
    COMPLETED = "completed"
    BLOCKED = "blocked"


def now() -> str:
    return datetime.now(UTC).isoformat()


class SessionState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    session_id: str
    current_request_id: str = Field(default="", exclude=True)
    api_token_id: str = "legacy"
    runtime_mode: Literal["fast", "moa", "agent", "orchestrated"] = "agent"
    request_class: str = "native_agent_turn"
    roles_required: list[str] = Field(default_factory=lambda: ["executor"])
    review_fail_closed: bool = False
    review_deferred: bool = False
    finish_reasons: list[str] = Field(default_factory=list)
    truncated: bool = False
    timings_ms: dict[str, float] = Field(default_factory=dict)
    task_id: str = ""
    objective: str = ""
    repository: dict[str, str] = Field(default_factory=dict)
    route: str = "standard"
    route_reasons: list[str] = Field(default_factory=list)
    phase: Phase = Phase.INTAKE
    verified_facts: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    engineering_loop: LoopState | None = None
    skill_selections: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_selections: list[dict[str, Any]] = Field(default_factory=list)
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)
    policy_denied_tools: list[str] = Field(default_factory=list)
    policy_redact_fields: list[str] = Field(default_factory=list)
    completion_evidence: dict[str, str] = Field(default_factory=dict)
    approved_scope: list[str] = Field(default_factory=list)
    last_tool_call: dict[str, Any] | None = None
    pending_tool_call_ids: list[str] = Field(default_factory=list)
    last_decision_id: str | None = None
    failed_call_fingerprints: list[str] = Field(default_factory=list)
    failure_families: dict[str, int] = Field(default_factory=dict)
    no_progress_count: int = 0
    step_count: int = 0
    review_status: str = "pending"
    judge_status: str = "not_requested"
    pending_judge_evidence: str = ""
    judge_verdict: dict[str, Any] | None = None
    active_profile: str = "resident"
    heavy_switch_count: int = 0
    frontier_invocations: int = 0
    recursive_cycles: int = 0
    frontier_human_approval_required: bool = False
    runtime_channel: RuntimeChannel = "dev"
    trace_origin: TraceOrigin = "validation"
    training_eligibility: TrainingEligibility = "excluded"
    training_opt_out: bool = False
    user_training_opt_out: bool = False
    training_subject_hash: str | None = None
    repository_training_policy: Literal[
        "training_allowed", "internal_only", "training_denied", "unknown"
    ] = "unknown"
    final_status: FinalStatus | None = None
    control_state: Literal["running", "paused", "terminated"] = "running"
    control_approvals: list[str] = Field(default_factory=list)
    observability_status: Literal["ok", "degraded"] = "ok"
    observability_degraded: bool = False
    controller_commit: str = "unknown"
    gateway_version: str = "0.1.0"
    vllm_version: str = "unknown"
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    reasoner_contributions: list[dict[str, Any]] = Field(default_factory=list)
    orchestration_decisions: list[dict[str, Any]] = Field(default_factory=list)
    agent_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    agent_invocations: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_nodes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_edges: list[dict[str, str]] = Field(default_factory=list)
    derived_confidence: Literal["high", "medium", "low", "conflicted"] = "medium"
    tool_executions: list[dict[str, Any]] = Field(default_factory=list)
    evaluations: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    ending_repository: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._event_listeners: list[Callable[[str, str, dict[str, Any], str], None]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS events "
                "(session_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS trace_index "
                "(session_id TEXT NOT NULL, schema_version TEXT NOT NULL, path TEXT NOT NULL, "
                "runtime_channel TEXT NOT NULL, trace_origin TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def get(self, session_id: str) -> SessionState | None:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return SessionState.model_validate_json(row[0]) if row else None

    def find_tool_owner(self, tool_call_ids: set[str], api_token_id: str) -> SessionState | None:
        if not tool_call_ids:
            return None
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        for (payload,) in rows:
            state = SessionState.model_validate_json(payload)
            if state.api_token_id != api_token_id:
                continue
            pending = set(state.pending_tool_call_ids)
            if state.last_tool_call and isinstance(state.last_tool_call.get("id"), str):
                pending.add(state.last_tool_call["id"])
            if pending.intersection(tool_call_ids):
                return state
        return None

    def save(self, state: SessionState) -> None:
        state.updated_at = now()
        with self._connect() as database:
            database.execute(
                "INSERT INTO sessions(session_id, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at",
                (state.session_id, state.model_dump_json(), state.updated_at),
            )

    def event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        created_at = now()
        with self._connect() as database:
            database.execute(
                "INSERT INTO events(session_id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(payload, sort_keys=True), created_at),
            )
        for listener in self._event_listeners:
            try:
                listener(session_id, event_type, payload, created_at)
            except Exception:
                continue

    def subscribe_events(self, listener: Callable[[str, str, dict[str, Any], str], None]) -> None:
        self._event_listeners.append(listener)

    def events(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT event_type, payload, created_at FROM events WHERE session_id = ? "
                "ORDER BY rowid",
                (session_id,),
            ).fetchall()
        return [
            {"event_type": event_type, "payload": json.loads(payload), "created_at": created_at}
            for event_type, payload, created_at in rows
        ]

    def index_trace(
        self,
        session_id: str,
        path: str | Path,
        runtime_channel: RuntimeChannel,
        trace_origin: TraceOrigin,
        schema_version: str = "agent-trace-v3",
    ) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO trace_index(session_id, schema_version, path, runtime_channel, "
                "trace_origin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, schema_version, str(path), runtime_channel, trace_origin, now()),
            )
