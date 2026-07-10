from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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
    session_id: str
    objective: str = ""
    phase: Phase = Phase.INTAKE
    verified_facts: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    completion_evidence: dict[str, str] = Field(default_factory=dict)
    approved_scope: list[str] = Field(default_factory=list)
    last_tool_call: dict[str, Any] | None = None
    failed_call_fingerprints: list[str] = Field(default_factory=list)
    failure_families: dict[str, int] = Field(default_factory=dict)
    no_progress_count: int = 0
    step_count: int = 0
    review_status: str = "pending"
    judge_status: str = "not_requested"
    active_profile: str = "resident"
    heavy_switch_count: int = 0
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
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

    def save(self, state: SessionState) -> None:
        state.updated_at = now()
        with self._connect() as database:
            database.execute(
                "INSERT INTO sessions(session_id, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at",
                (state.session_id, state.model_dump_json(), state.updated_at),
            )
