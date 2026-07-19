from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .routing import RequestClass, RuntimeMode

SafeClientClass = Literal[
    "curl", "openai-python", "httpx", "opencode", "hermes-agent", "openai-compatible"
]
CLIENT_MARKERS: tuple[tuple[str, SafeClientClass], ...] = (
    ("opencode", "opencode"),
    ("hermes-agent", "hermes-agent"),
    ("openai/python", "openai-python"),
    ("python-httpx", "httpx"),
    ("curl/", "curl"),
)
ModelAlias = Literal["dgx-moa-chat", "dgx-moa-agent", "dgx-moa-orchestrated"]
Role = Literal["executor", "planner", "reviewer", "reasoner", "judge"]
ModelState = Literal["warm", "cold", "loading"]
LifecycleKind = Literal["load", "unload"]
RequestStatus = Literal["completed", "failed", "cancelled", "timed_out"]
RetryableFailureClass = Literal[
    "backend_error",
    "model_loading",
    "planner_timeout",
    "executor_first_byte_timeout",
    "executor_total_timeout",
    "executor_timeout",
    "reviewer_timeout",
    "judge_timeout",
]
SQLITE_MAX_INTEGER = 2**63 - 1

REQUEST_COLUMNS = (
    "request_id, session_id, client_class, model_alias, runtime_mode, request_class, "
    "roles_required, accepted_at, first_byte_at, completed_at, active_duration_seconds, "
    "status, streaming, model_state, load_triggered, retryable_failure_class, "
    "prompt_tokens, completion_tokens, total_tokens"
)


def classify_client(user_agent: str | None) -> SafeClientClass:
    normalized = (user_agent or "").lower()
    for marker, client_class in CLIENT_MARKERS:
        if marker in normalized:
            return client_class
    return "openai-compatible"


class RequestUsageStart(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    request_id: str
    session_id: str
    client_class: SafeClientClass
    model_alias: ModelAlias
    runtime_mode: RuntimeMode
    request_class: RequestClass
    roles_required: tuple[Role, ...]
    accepted_at: float = Field(ge=0)
    streaming: bool
    model_state: ModelState
    load_triggered: bool = False


class RequestUsageFinalization(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    first_byte_at: float | None = Field(default=None, ge=0)
    completed_at: float = Field(ge=0)
    active_duration_seconds: float | None = Field(default=None, ge=0)
    status: RequestStatus
    retryable_failure_class: RetryableFailureClass | None = None
    prompt_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)
    completion_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)
    total_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)


class RequestUsageRecord(RequestUsageStart):
    first_byte_at: float | None = None
    completed_at: float | None = None
    active_duration_seconds: float | None = None
    status: RequestStatus | None = None
    retryable_failure_class: RetryableFailureClass | None = None
    prompt_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)
    completion_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)
    total_tokens: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)


class LifecycleSample(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    role: Role
    kind: LifecycleKind
    duration_seconds: float = Field(ge=0)
    memory_before_bytes: int | None = Field(default=None, ge=0)
    memory_after_bytes: int | None = Field(default=None, ge=0)


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _percentiles(values: Sequence[float]) -> dict[str, float | None]:
    return {
        "p50": _percentile(values, 0.50),
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
    }


def _duration_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": fmean(values) if values else None,
        **_percentiles(values),
    }


def _ewma(values: Sequence[float], alpha: float) -> float | None:
    if not values:
        return None
    average = values[0]
    for value in values[1:]:
        average = alpha * value + (1 - alpha) * average
    return average


def request_statistics(
    records: Sequence[RequestUsageRecord],
    *,
    now: float,
    ewma_alpha: float,
    adaptive_minimum_samples: int,
) -> dict[str, Any]:
    accepted = sorted(record.accepted_at for record in records)
    gaps = [later - earlier for earlier, later in zip(accepted, accepted[1:], strict=False)]
    roles = Counter(role for record in records for role in record.roles_required)
    warm_latencies = [
        record.active_duration_seconds
        for record in records
        if record.model_state == "warm" and record.active_duration_seconds is not None
    ]
    return {
        "request_count": len(records),
        "requests_last_hour": sum(now - 3_600 <= value <= now for value in accepted),
        "requests_last_day": sum(now - 86_400 <= value <= now for value in accepted),
        "inter_arrival_gaps_seconds": gaps,
        "inter_arrival_ewma_seconds": _ewma(gaps, ewma_alpha),
        "inter_arrival_percentiles_seconds": _percentiles(gaps),
        "adaptive_policy_samples": {
            "usable": len(gaps),
            "minimum": adaptive_minimum_samples,
            "sufficient": len(gaps) >= adaptive_minimum_samples,
        },
        "role_frequency": dict(sorted(roles.items())),
        "warm_latency_seconds": _duration_summary(warm_latencies),
        "cold_starts": sum(record.load_triggered for record in records),
    }


def lifecycle_statistics(samples: Sequence[LifecycleSample]) -> dict[str, Any]:
    return {
        f"{kind}_duration_seconds": _duration_summary(
            [sample.duration_seconds for sample in samples if sample.kind == kind]
        )
        for kind in ("load", "unload")
    }


class UsageStore:
    def __init__(
        self,
        path: str | Path,
        *,
        sample_window: int = 512,
        ewma_alpha: float = 0.25,
        adaptive_minimum_samples: int = 20,
    ) -> None:
        if sample_window < 1:
            raise ValueError("sample_window must be positive")
        if not 0 < ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be greater than zero and at most one")
        if adaptive_minimum_samples < 1:
            raise ValueError("adaptive_minimum_samples must be positive")
        self.path = Path(path)
        self.sample_window = sample_window
        self.ewma_alpha = ewma_alpha
        self.adaptive_minimum_samples = adaptive_minimum_samples
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_usage (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    client_class TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    runtime_mode TEXT NOT NULL,
                    request_class TEXT NOT NULL,
                    roles_required TEXT NOT NULL,
                    accepted_at REAL NOT NULL,
                    first_byte_at REAL,
                    completed_at REAL,
                    active_duration_seconds REAL,
                    status TEXT,
                    streaming INTEGER NOT NULL,
                    model_state TEXT NOT NULL,
                    load_triggered INTEGER NOT NULL,
                    retryable_failure_class TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER
                );
                CREATE TABLE IF NOT EXISTS lifecycle_samples (
                    sample_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    memory_before_bytes INTEGER,
                    memory_after_bytes INTEGER
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.row_factory = sqlite3.Row
        return connection

    def start(self, record: RequestUsageStart) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT OR IGNORE INTO request_usage "
                "(request_id, session_id, client_class, model_alias, runtime_mode, "
                "request_class, roles_required, accepted_at, streaming, model_state, "
                "load_triggered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.request_id,
                    record.session_id,
                    record.client_class,
                    record.model_alias,
                    record.runtime_mode,
                    record.request_class,
                    json.dumps(record.roles_required, separators=(",", ":")),
                    record.accepted_at,
                    int(record.streaming),
                    record.model_state,
                    int(record.load_triggered),
                ),
            )

    def finalize(self, request_id: str, finalization: RequestUsageFinalization) -> None:
        with self._connect() as database:
            row = database.execute(
                "SELECT accepted_at, completed_at FROM request_usage WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            if row["completed_at"] is not None:
                return
            accepted_at = float(row["accepted_at"])
            if finalization.completed_at < accepted_at:
                raise ValueError("completed_at cannot precede accepted_at")
            if finalization.first_byte_at is not None and not (
                accepted_at <= finalization.first_byte_at <= finalization.completed_at
            ):
                raise ValueError("first_byte_at must fall within the active request")
            active_duration = (
                finalization.active_duration_seconds
                if finalization.active_duration_seconds is not None
                else finalization.completed_at - accepted_at
            )
            database.execute(
                "UPDATE request_usage SET first_byte_at = ?, completed_at = ?, "
                "active_duration_seconds = ?, status = ?, retryable_failure_class = ?, "
                "prompt_tokens = ?, completion_tokens = ?, total_tokens = ? "
                "WHERE request_id = ? AND completed_at IS NULL",
                (
                    finalization.first_byte_at,
                    finalization.completed_at,
                    active_duration,
                    finalization.status,
                    finalization.retryable_failure_class,
                    finalization.prompt_tokens,
                    finalization.completion_tokens,
                    finalization.total_tokens,
                    request_id,
                ),
            )

    def get(self, request_id: str) -> RequestUsageRecord | None:
        with self._connect() as database:
            row = database.execute(
                f"SELECT {REQUEST_COLUMNS} FROM request_usage WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def recent_requests(self) -> list[RequestUsageRecord]:
        with self._connect() as database:
            rows = database.execute(
                f"SELECT {REQUEST_COLUMNS} FROM request_usage "
                "ORDER BY accepted_at DESC, rowid DESC LIMIT ?",
                (self.sample_window,),
            ).fetchall()
        return [self._record(row) for row in reversed(rows)]

    def active_request_count(self) -> int:
        with self._connect() as database:
            row = database.execute(
                "SELECT COUNT(*) FROM request_usage WHERE completed_at IS NULL"
            ).fetchone()
        return int(row[0])

    def record_lifecycle_sample(self, sample: LifecycleSample) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO lifecycle_samples "
                "(role, kind, duration_seconds, memory_before_bytes, memory_after_bytes) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    sample.role,
                    sample.kind,
                    sample.duration_seconds,
                    sample.memory_before_bytes,
                    sample.memory_after_bytes,
                ),
            )

    def recent_lifecycle_samples(self) -> list[LifecycleSample]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT role, kind, duration_seconds, memory_before_bytes, memory_after_bytes "
                "FROM lifecycle_samples ORDER BY sample_id DESC LIMIT ?",
                (self.sample_window,),
            ).fetchall()
        return [
            LifecycleSample(
                role=row["role"],
                kind=row["kind"],
                duration_seconds=row["duration_seconds"],
                memory_before_bytes=row["memory_before_bytes"],
                memory_after_bytes=row["memory_after_bytes"],
            )
            for row in reversed(rows)
        ]

    def report(self, *, now: float | None = None) -> dict[str, Any]:
        return request_statistics(
            self.recent_requests(),
            now=time.time() if now is None else now,
            ewma_alpha=self.ewma_alpha,
            adaptive_minimum_samples=self.adaptive_minimum_samples,
        ) | lifecycle_statistics(self.recent_lifecycle_samples())

    @staticmethod
    def _record(row: sqlite3.Row) -> RequestUsageRecord:
        return RequestUsageRecord(
            request_id=row["request_id"],
            session_id=row["session_id"],
            client_class=row["client_class"],
            model_alias=row["model_alias"],
            runtime_mode=row["runtime_mode"],
            request_class=row["request_class"],
            roles_required=tuple(json.loads(row["roles_required"])),
            accepted_at=row["accepted_at"],
            first_byte_at=row["first_byte_at"],
            completed_at=row["completed_at"],
            active_duration_seconds=row["active_duration_seconds"],
            status=row["status"],
            streaming=bool(row["streaming"]),
            model_state=row["model_state"],
            load_triggered=bool(row["load_triggered"]),
            retryable_failure_class=row["retryable_failure_class"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
        )
