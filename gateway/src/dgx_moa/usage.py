from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean
from typing import Any, Literal, cast

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
ModelAlias = Literal[
    "dgx-moa",
    "dgx-moa-fast",
    "dgx-moa-agent",
    "dgx-moa-orchestrated",
    "dgx-moa-chat",
]
Role = Literal["executor", "planner", "reviewer", "reasoner", "judge"]
ModelState = Literal["warm", "cold", "loading"]
LifecycleKind = Literal["load", "unload"]
RequestStatus = Literal["completed", "failed", "cancelled", "timed_out"]
RetryableFailureClass = Literal[
    "backend_error",
    "model_loading",
    "planner_timeout",
    "reasoner_timeout",
    "executor_first_byte_timeout",
    "executor_total_timeout",
    "executor_timeout",
    "reviewer_timeout",
    "judge_timeout",
]
SQLITE_MAX_INTEGER = 2**63 - 1
MODEL_INVOCATION_RATE_COLUMNS = (
    "generated_at_epoch",
    "window",
    "role",
    "model",
    "total_requests",
    "requests_using_model",
    "invocation_count",
    "invocation_rate_percent",
    "success_count",
    "failure_count",
    "average_latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)

REQUEST_COLUMNS = (
    "request_id, session_id, api_token_id, client_class, model_alias, runtime_mode, request_class, "
    "roles_required, accepted_at, first_byte_at, completed_at, active_duration_seconds, "
    "status, streaming, model_state, load_triggered, retryable_failure_class, "
    "prompt_tokens, completion_tokens, total_tokens"
)
ROLE_REQUEST_COLUMNS = (
    "request_id, session_id_hash, role, client_mode, request_class, requested_at, "
    "load_triggered, cold_or_warm, ready_at, first_byte_at, completed_at, success, "
    "failure_class, active_duration_ms"
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
    api_token_id: str = Field(default="legacy", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
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


class RoleRequestUsageStart(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    request_id: str
    session_id_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: Role
    client_mode: RuntimeMode
    request_class: RequestClass
    requested_at: float = Field(ge=0, allow_inf_nan=False)
    load_triggered: bool
    cold_or_warm: Literal["cold", "warm"]
    ready_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class RoleRequestUsageFinalization(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ready_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    first_byte_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    completed_at: float = Field(ge=0, allow_inf_nan=False)
    success: bool
    failure_class: str | None = Field(default=None, max_length=64)
    active_duration_ms: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)


class RoleRequestUsageRecord(RoleRequestUsageStart):
    first_byte_at: float | None = None
    completed_at: float | None = None
    success: bool | None = None
    failure_class: str | None = None
    active_duration_ms: int | None = Field(default=None, ge=0, le=SQLITE_MAX_INTEGER)


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
        invocation_report_path: str | Path | None = None,
        model_catalog: Mapping[str, str] | None = None,
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
        self.invocation_report_path = (
            Path(invocation_report_path) if invocation_report_path is not None else None
        )
        self.model_catalog = dict(model_catalog or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_usage (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    api_token_id TEXT NOT NULL DEFAULT 'legacy',
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
                CREATE TABLE IF NOT EXISTS role_request_usage (
                    request_id TEXT NOT NULL,
                    session_id_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    client_mode TEXT NOT NULL,
                    request_class TEXT NOT NULL,
                    requested_at REAL NOT NULL,
                    load_triggered INTEGER NOT NULL,
                    cold_or_warm TEXT NOT NULL,
                    ready_at REAL,
                    first_byte_at REAL,
                    completed_at REAL,
                    success INTEGER,
                    failure_class TEXT,
                    active_duration_ms INTEGER,
                    PRIMARY KEY (request_id, role)
                );
                CREATE INDEX IF NOT EXISTS role_request_usage_role_time
                    ON role_request_usage(role, requested_at);
                CREATE TABLE IF NOT EXISTS model_invocation_usage (
                    invocation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    model TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    invoked_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER
                );
                CREATE INDEX IF NOT EXISTS model_invocation_usage_role_time
                    ON model_invocation_usage(role, invoked_at);
                """
            )
            columns = {row[1] for row in database.execute("PRAGMA table_info(request_usage)")}
            if "api_token_id" not in columns:
                database.execute(
                    "ALTER TABLE request_usage ADD COLUMN api_token_id "
                    "TEXT NOT NULL DEFAULT 'legacy'"
                )
        self.write_model_invocation_rates()

    def record_model_invocation(
        self,
        request_id: str,
        *,
        role: str,
        model: str,
        mode: str,
        status: str,
        latency_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        if role not in {*self.model_catalog, "frontier"}:
            raise ValueError("unknown invocation role")
        with self._connect() as database:
            database.execute(
                "INSERT INTO model_invocation_usage "
                "(invocation_id, request_id, role, model, mode, invoked_at, status, latency_ms, "
                "prompt_tokens, completion_tokens, total_tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    request_id,
                    role,
                    model,
                    mode,
                    time.time(),
                    status,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                ),
            )
        self.write_model_invocation_rates()

    def model_invocation_rates(self, *, now: float | None = None) -> list[dict[str, Any]]:
        current = time.time() if now is None else now
        rows: list[dict[str, Any]] = []
        with self._connect() as database:
            for window, since in (("all_time", 0.0), ("last_hour", current - 3_600)):
                total_requests = int(
                    database.execute(
                        "SELECT COUNT(*) FROM request_usage WHERE accepted_at >= ?", (since,)
                    ).fetchone()[0]
                )
                summaries = {
                    (str(row[0]), str(row[1])): row
                    for row in database.execute(
                        "SELECT role, model, COUNT(DISTINCT request_id), COUNT(*), "
                        "SUM(status = 'completed'), SUM(status != 'completed'), AVG(latency_ms), "
                        "COALESCE(SUM(prompt_tokens), 0), "
                        "COALESCE(SUM(completion_tokens), 0), "
                        "COALESCE(SUM(total_tokens), 0) "
                        "FROM model_invocation_usage WHERE invoked_at >= ? GROUP BY role, model",
                        (since,),
                    )
                }
                models = {*self.model_catalog.items(), *summaries}
                for role, model in sorted(models):
                    summary = summaries.get((role, model))
                    requests_using = int(summary[2]) if summary else 0
                    rows.append(
                        {
                            "generated_at_epoch": current,
                            "window": window,
                            "role": role,
                            "model": model,
                            "total_requests": total_requests,
                            "requests_using_model": requests_using,
                            "invocation_count": int(summary[3]) if summary else 0,
                            "invocation_rate_percent": round(
                                requests_using / total_requests * 100, 3
                            )
                            if total_requests
                            else 0.0,
                            "success_count": int(summary[4] or 0) if summary else 0,
                            "failure_count": int(summary[5] or 0) if summary else 0,
                            "average_latency_ms": round(float(summary[6]), 3)
                            if summary and summary[6] is not None
                            else "",
                            "prompt_tokens": int(summary[7]) if summary else 0,
                            "completion_tokens": int(summary[8]) if summary else 0,
                            "total_tokens": int(summary[9]) if summary else 0,
                        }
                    )
        return rows

    def write_model_invocation_rates(self) -> None:
        if self.invocation_report_path is None:
            return
        path = self.invocation_report_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        rows = self.model_invocation_rates()
        try:
            with temporary.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=MODEL_INVOCATION_RATE_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.row_factory = sqlite3.Row
        return connection

    def start(self, record: RequestUsageStart) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT OR IGNORE INTO request_usage "
                "(request_id, session_id, api_token_id, client_class, model_alias, runtime_mode, "
                "request_class, roles_required, accepted_at, streaming, model_state, "
                "load_triggered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.request_id,
                    record.session_id,
                    record.api_token_id,
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

    def start_roles(
        self,
        request_id: str,
        roles: Sequence[str],
        *,
        session_id: str,
        requested_at: float,
        client_mode: RuntimeMode,
        request_class: RequestClass,
        states: Mapping[str, str],
        load_triggered: Mapping[str, bool],
        ready_at: Mapping[str, float | None] | None = None,
    ) -> None:
        unique_roles = tuple(dict.fromkeys(roles))
        session_id_hash = hashlib.sha256(session_id.encode()).hexdigest()
        records = tuple(
            RoleRequestUsageStart(
                request_id=request_id,
                session_id_hash=session_id_hash,
                role=cast(Role, role),
                client_mode=client_mode,
                request_class=request_class,
                requested_at=requested_at,
                load_triggered=load_triggered[role],
                cold_or_warm="warm" if states[role] in {"ready", "warm"} else "cold",
                ready_at=(ready_at or {}).get(role),
            )
            for role in unique_roles
        )
        with self._connect() as database:
            database.executemany(
                "INSERT OR IGNORE INTO role_request_usage "
                "(request_id, session_id_hash, role, client_mode, request_class, requested_at, "
                "load_triggered, cold_or_warm, ready_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        record.request_id,
                        record.session_id_hash,
                        record.role,
                        record.client_mode,
                        record.request_class,
                        record.requested_at,
                        int(record.load_triggered),
                        record.cold_or_warm,
                        record.ready_at,
                    )
                    for record in records
                ),
            )

    def add_required_roles(self, request_id: str, roles: Sequence[str]) -> None:
        """Append dynamically selected roles to the content-free request summary."""
        with self._connect() as database:
            row = database.execute(
                "SELECT roles_required FROM request_usage WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            current = json.loads(row["roles_required"])
            combined = list(dict.fromkeys((*current, *roles)))
            database.execute(
                "UPDATE request_usage SET roles_required = ? WHERE request_id = ?",
                (json.dumps(combined, separators=(",", ":")), request_id),
            )

    def update_model_state(self, request_id: str, model_state: ModelState) -> None:
        """Reflect a dynamically selected cold/loading role in request accounting."""
        with self._connect() as database:
            database.execute(
                "UPDATE request_usage SET model_state = ? WHERE request_id = ?",
                (model_state, request_id),
            )

    def finalize_roles(
        self,
        request_id: str,
        *,
        completed_at: float,
        first_byte_at: float | None,
        success: bool,
        failure_class: str | None,
        ready_at: Mapping[str, float | None] | None = None,
        role_failures: Mapping[str, str] | None = None,
    ) -> None:
        def safe_failure_class(value: str | None) -> str | None:
            if value is None:
                return None
            return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:64] or "unknown"

        safe_failure = safe_failure_class(failure_class)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            rows = database.execute(
                "SELECT role, requested_at, ready_at, completed_at FROM role_request_usage "
                "WHERE request_id = ?",
                (request_id,),
            ).fetchall()
            if not rows:
                raise KeyError(request_id)
            for row in rows:
                if row["completed_at"] is not None:
                    continue
                requested_at = float(row["requested_at"])
                role_ready_at = (ready_at or {}).get(row["role"], row["ready_at"])
                role_failure = safe_failure_class((role_failures or {}).get(row["role"]))
                finalization = RoleRequestUsageFinalization(
                    ready_at=role_ready_at,
                    first_byte_at=first_byte_at,
                    completed_at=completed_at,
                    success=success and role_failure is None,
                    failure_class=role_failure or safe_failure,
                    active_duration_ms=round((completed_at - requested_at) * 1_000),
                )
                if finalization.completed_at < requested_at:
                    raise ValueError("completed_at cannot precede requested_at")
                if finalization.first_byte_at is not None and not (
                    requested_at <= finalization.first_byte_at <= finalization.completed_at
                ):
                    raise ValueError("first_byte_at must fall within the active request")
                database.execute(
                    "UPDATE role_request_usage SET ready_at = ?, first_byte_at = ?, "
                    "completed_at = ?, success = ?, failure_class = ?, active_duration_ms = ? "
                    "WHERE request_id = ? AND role = ? AND completed_at IS NULL",
                    (
                        finalization.ready_at,
                        finalization.first_byte_at,
                        finalization.completed_at,
                        int(finalization.success),
                        finalization.failure_class,
                        finalization.active_duration_ms,
                        request_id,
                        row["role"],
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

    def recent_role_requests(
        self,
        role: str,
        *,
        success: bool | None = None,
        limit: int | None = None,
    ) -> list[RoleRequestUsageRecord]:
        if role not in {"executor", "planner", "reviewer", "reasoner", "judge"}:
            raise ValueError("unknown role")
        bounded_limit = self.sample_window if limit is None else limit
        if (
            not isinstance(bounded_limit, int)
            or isinstance(bounded_limit, bool)
            or not 1 <= bounded_limit <= 10_000
        ):
            raise ValueError("role request limit must be between 1 and 10000")
        where = "WHERE role = ?"
        parameters: tuple[Any, ...] = (role, bounded_limit)
        if success is not None:
            where += " AND success = ?"
            parameters = (role, int(success), bounded_limit)
        with self._connect() as database:
            rows = database.execute(
                f"SELECT {ROLE_REQUEST_COLUMNS} FROM role_request_usage "
                f"{where} ORDER BY requested_at DESC, rowid DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [self._role_record(row) for row in reversed(rows)]

    def role_statistics(self, role: str, *, now: float | None = None) -> dict[str, Any]:
        records = self.recent_role_requests(role)
        current_time = time.time() if now is None else now
        successful = self.recent_role_requests(role, success=True)
        requested = [record.requested_at for record in successful]
        gaps = [
            later - earlier
            for earlier, later in zip(requested, requested[1:], strict=False)
            if later > earlier
        ]
        load_durations = [
            record.ready_at - record.requested_at
            for record in records
            if record.load_triggered
            and record.ready_at is not None
            and record.ready_at >= record.requested_at
        ]
        with self._connect() as database:
            summary = database.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN requested_at BETWEEN ? AND ? THEN 1 ELSE 0 END), "
                "SUM(load_triggered), SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), "
                "MAX(COALESCE(completed_at, requested_at)), "
                "AVG(CASE WHEN cold_or_warm = 'warm' AND first_byte_at >= requested_at "
                "THEN first_byte_at - requested_at END) "
                "FROM role_request_usage WHERE role = ?",
                (current_time - 3_600, current_time, role),
            ).fetchone()
            assert summary is not None
            hourly = {
                str(int(row[0])): int(row[1])
                for row in database.execute(
                    "SELECT strftime('%H', requested_at, 'unixepoch'), COUNT(*) "
                    "FROM role_request_usage WHERE role = ? GROUP BY 1 ORDER BY 1",
                    (role,),
                )
            }
            weekday_hour = {
                f"{int(row[0])}:{int(row[1])}": int(row[2])
                for row in database.execute(
                    "SELECT strftime('%w', requested_at, 'unixepoch'), "
                    "strftime('%H', requested_at, 'unixepoch'), COUNT(*) "
                    "FROM role_request_usage WHERE role = ? GROUP BY 1, 2 ORDER BY 1, 2",
                    (role,),
                )
            }
            sampled_load_durations = [
                float(row[0])
                for row in database.execute(
                    "SELECT duration_seconds FROM lifecycle_samples "
                    "WHERE role = ? AND kind = 'load' ORDER BY sample_id DESC LIMIT ?",
                    (role, self.sample_window),
                )
            ]
        if sampled_load_durations:
            load_durations = sampled_load_durations
        request_count = int(summary[0])
        cold_starts = int(summary[2] or 0)
        return {
            "role": role,
            "request_count": request_count,
            "requests_last_hour": int(summary[1] or 0),
            "requests_by_hour_utc": hourly,
            "requests_by_weekday_hour_utc": weekday_hour,
            "inter_arrival_gaps_seconds": gaps,
            "inter_arrival_ewma_seconds": _ewma(gaps, self.ewma_alpha),
            "inter_arrival_percentiles_seconds": _percentiles(gaps),
            "adaptive_policy_samples": {
                "usable": len(gaps),
                "minimum": self.adaptive_minimum_samples,
                "sufficient": len(gaps) >= self.adaptive_minimum_samples,
            },
            "cold_start_count": cold_starts,
            "cold_start_frequency": cold_starts / request_count if request_count else 0.0,
            "average_load_duration_seconds": (fmean(load_durations) if load_durations else None),
            "average_warm_latency_seconds": summary[5],
            "last_used_at": summary[4],
            "failure_count": int(summary[3] or 0),
        }

    def all_role_statistics(self, *, now: float | None = None) -> dict[str, dict[str, Any]]:
        return {
            role: self.role_statistics(role, now=now)
            for role in ("executor", "planner", "reviewer", "reasoner", "judge")
        }

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
        return (
            request_statistics(
                self.recent_requests(),
                now=time.time() if now is None else now,
                ewma_alpha=self.ewma_alpha,
                adaptive_minimum_samples=self.adaptive_minimum_samples,
            )
            | lifecycle_statistics(self.recent_lifecycle_samples())
            | {"api_token_usage": self.api_token_statistics()}
        )

    def api_token_statistics(self) -> dict[str, dict[str, int]]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT api_token_id, COUNT(*), "
                "COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(completion_tokens), 0), "
                "COALESCE(SUM(total_tokens), 0) FROM request_usage GROUP BY api_token_id "
                "ORDER BY api_token_id"
            ).fetchall()
        return {
            str(row[0]): {
                "requests": int(row[1]),
                "prompt_tokens": int(row[2]),
                "completion_tokens": int(row[3]),
                "total_tokens": int(row[4]),
            }
            for row in rows
        }

    @staticmethod
    def _record(row: sqlite3.Row) -> RequestUsageRecord:
        runtime_mode = cast(
            RuntimeMode, "fast" if row["runtime_mode"] == "chat" else row["runtime_mode"]
        )
        return RequestUsageRecord(
            request_id=row["request_id"],
            session_id=row["session_id"],
            api_token_id=row["api_token_id"],
            client_class=row["client_class"],
            model_alias=row["model_alias"],
            runtime_mode=runtime_mode,
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

    @staticmethod
    def _role_record(row: sqlite3.Row) -> RoleRequestUsageRecord:
        client_mode = cast(
            RuntimeMode, "fast" if row["client_mode"] == "chat" else row["client_mode"]
        )
        return RoleRequestUsageRecord(
            request_id=row["request_id"],
            session_id_hash=row["session_id_hash"],
            role=row["role"],
            client_mode=client_mode,
            request_class=row["request_class"],
            requested_at=row["requested_at"],
            load_triggered=bool(row["load_triggered"]),
            cold_or_warm=row["cold_or_warm"],
            ready_at=row["ready_at"],
            first_byte_at=row["first_byte_at"],
            completed_at=row["completed_at"],
            success=None if row["success"] is None else bool(row["success"]),
            failure_class=row["failure_class"],
            active_duration_ms=row["active_duration_ms"],
        )
