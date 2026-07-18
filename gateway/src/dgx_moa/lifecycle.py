from __future__ import annotations

import asyncio
import hashlib
import math
import re
import sqlite3
import subprocess
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from pathlib import Path
from statistics import quantiles
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from .config import MODEL_ROLES, SYSTEMD_UNIT_PATTERN, Limits

LifecycleState = Literal[
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unloading",
    "failed",
]
DriverStatus = Literal["active", "inactive", "failed"]
DriverOperation = Literal["status", "start", "stop", "cursor", "progress"]
DriverErrorKind = Literal["timeout", "command_failed", "malformed_output"]
ProgressQuality = Literal["measured_bytes", "measured_shards", "estimated", "unavailable"]
LeaseKind = Literal["active_request", "open_stream", "continuation"]
RequestLeaseKind = Literal["active_request", "open_stream"]
GuardKind = Literal["evaluation_guard", "profile_guard"]
ModelRole = Literal["executor", "planner", "reviewer", "reasoner", "judge"]
LifecycleMode = Literal["disabled", "observe", "fixed", "adaptive"]
IdleThresholdSource = Literal["disabled", "fixed", "sparse_fallback", "adaptive_p75"]
IdlePolicyReason = Literal[
    "mode_disabled",
    "mode_changed",
    "state_reset",
    "state_not_ready",
    "blocked",
    "minimum_residency",
    "activity_reset",
    "below_threshold",
    "first_idle_check",
    "idle_confirmed",
]

MAX_PROGRESS_LINES = 1_000
MAX_PROGRESS_LINE_CHARACTERS = 2_000
MAX_JOURNAL_CURSOR_CHARACTERS = 1_024
MAX_LOAD_RETRIES = 2
JOURNAL_CURSOR = re.compile(r"[A-Za-z0-9_.:;=+-]+")
BYTE_PROGRESS = re.compile(
    r"(?P<loaded>\d+(?:\.\d+)?)\s*/\s*(?P<total>\d+(?:\.\d+)?)\s*bytes?\b",
    re.IGNORECASE,
)
SHARD_PROGRESS = re.compile(
    r"checkpoint\s+shards?[^\r\n]*?(?P<loaded>\d+)\s*/\s*(?P<total>\d+)",
    re.IGNORECASE,
)
CONTINUATION_CORRELATION = re.compile(r"[0-9a-f]{64}")

LIFECYCLE_STATES: tuple[LifecycleState, ...] = (
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unloading",
    "failed",
)
TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    "cold": frozenset({"load_queued"}),
    "load_queued": frozenset({"cold", "process_starting", "failed"}),
    "process_starting": frozenset({"cold", "loading_weights", "failed"}),
    "loading_weights": frozenset({"cold", "initializing_engine", "failed"}),
    "initializing_engine": frozenset({"cold", "warming_up", "failed"}),
    "warming_up": frozenset({"cold", "ready", "failed"}),
    "ready": frozenset({"sleeping", "unloading", "failed"}),
    "sleeping": frozenset({"cold", "ready", "unloading", "failed"}),
    "unloading": frozenset({"cold", "failed"}),
    "failed": frozenset({"cold", "load_queued"}),
}


class LifecycleRecord(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    role: str
    state: LifecycleState
    transition_id: str
    transitioned_at: float
    updated_at: float
    ready_since: float | None = None
    last_used_at: float | None = None
    failure_class: str | None = None
    failure_detail: str | None = None
    retry_count: int = Field(default=0, ge=0)
    active_request_count: int = Field(default=0, ge=0)
    open_stream_count: int = Field(default=0, ge=0)
    continuation_lease_count: int = Field(default=0, ge=0)
    evaluation_guard: bool = False
    profile_guard: bool = False
    progress_value: float | None = Field(default=None, ge=0, le=100)
    progress_quality: ProgressQuality | None = None
    eta_seconds: float | None = Field(default=None, ge=0)
    last_load_duration_seconds: float | None = Field(default=None, ge=0)
    last_unload_duration_seconds: float | None = Field(default=None, ge=0)
    memory_before_bytes: int | None = Field(default=None, ge=0)
    memory_after_bytes: int | None = Field(default=None, ge=0)


class LifecycleLease(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    lease_id: str
    role: str
    kind: LeaseKind
    owner_correlation: str
    created_at: float = Field(ge=0)
    expires_at: float | None = Field(default=None, ge=0)


class LoadProgress(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    state: Literal["loading_weights", "initializing_engine", "warming_up"]
    weight_load_percent: float | None = Field(default=None, ge=0, le=100)
    progress_quality: ProgressQuality


class LoadCheck(BaseModel):
    record: LifecycleRecord
    load_triggered: bool = False


class RoleUsageRecord(Protocol):
    accepted_at: float
    roles_required: tuple[str, ...]


class IdlePolicyDecision(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    role: ModelRole
    mode: LifecycleMode
    threshold_seconds: float = Field(gt=0)
    threshold_source: IdleThresholdSource
    sample_count: int = Field(ge=0)
    idle_seconds: float = Field(ge=0)
    residency_seconds: float = Field(ge=0)
    next_consecutive_check_count: int = Field(ge=0, le=2)
    would_unload: bool
    action_allowed: bool
    reason: IdlePolicyReason


def _idle_bounds(role: str, limits: Limits) -> tuple[float, float, float, float]:
    prefix = "executor" if role == "executor" else "optional"
    minimum = float(getattr(limits, f"{prefix}_idle_minimum_seconds"))
    fallback = float(getattr(limits, f"{prefix}_idle_fallback_seconds"))
    maximum = float(getattr(limits, f"{prefix}_idle_maximum_seconds"))
    residency = float(getattr(limits, f"{prefix}_minimum_ready_residency_seconds"))
    if (
        any(
            not math.isfinite(value) or value <= 0
            for value in (minimum, fallback, maximum, residency)
        )
        or not minimum <= fallback <= maximum
    ):
        raise ValueError("invalid idle policy limits")
    return minimum, fallback, maximum, residency


def _role_usage_gaps(
    records: Sequence[RoleUsageRecord], role: str, sample_window: int
) -> list[float]:
    if not isinstance(sample_window, int) or isinstance(sample_window, bool) or sample_window < 1:
        raise ValueError("usage sample window must be positive")
    timestamps: list[float] = []
    for record in records:
        try:
            accepted_at = float(record.accepted_at)
        except (AttributeError, TypeError, ValueError):
            continue
        if role in record.roles_required and math.isfinite(accepted_at) and accepted_at >= 0:
            timestamps.append(accepted_at)
    timestamps = sorted(timestamps)[-sample_window:]
    return [
        gap
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
        if math.isfinite(gap := later - earlier) and gap > 0
    ]


def calculate_idle_policy(
    role: ModelRole,
    mode: LifecycleMode,
    records: Sequence[RoleUsageRecord],
    record: LifecycleRecord,
    *,
    now: float,
    limits: Limits,
    has_blockers: bool = False,
    previous_mode: LifecycleMode | None = None,
    previous_last_activity_at: float | None = None,
    previous_consecutive_check_count: int = 0,
) -> IdlePolicyDecision:
    if role not in MODEL_ROLES or record.role != role:
        raise ValueError("invalid idle policy role")
    modes = {"disabled", "observe", "fixed", "adaptive"}
    if mode not in modes or (previous_mode is not None and previous_mode not in modes):
        raise ValueError("invalid idle policy mode")
    if type(has_blockers) is not bool:
        raise ValueError("has_blockers must be boolean")
    if (
        not isinstance(previous_consecutive_check_count, int)
        or isinstance(previous_consecutive_check_count, bool)
        or not 0 <= previous_consecutive_check_count <= 2
    ):
        raise ValueError("invalid idle policy check count")
    now = float(now)
    if not math.isfinite(now) or now < 0:
        raise ValueError("idle policy time must be finite and nonnegative")
    if previous_last_activity_at is not None and (
        not math.isfinite(previous_last_activity_at) or previous_last_activity_at < 0
    ):
        raise ValueError("previous activity time must be finite and nonnegative")
    if (
        not isinstance(limits.adaptive_minimum_samples, int)
        or isinstance(limits.adaptive_minimum_samples, bool)
        or limits.adaptive_minimum_samples < 1
    ):
        raise ValueError("adaptive minimum samples must be positive")

    minimum, fallback, maximum, minimum_residency = _idle_bounds(role, limits)
    gaps = _role_usage_gaps(records, role, limits.usage_sample_window)
    adaptive = mode in {"observe", "adaptive"} and len(gaps) >= limits.adaptive_minimum_samples
    if adaptive:
        p75 = gaps[0] if len(gaps) == 1 else quantiles(gaps, n=4, method="inclusive")[2]
        threshold = min(maximum, max(minimum, 1.5 * p75))
        source: IdleThresholdSource = "adaptive_p75"
    else:
        threshold = fallback
        source = (
            "disabled" if mode == "disabled" else "fixed" if mode == "fixed" else "sparse_fallback"
        )

    ready_since = record.ready_since
    activity_at: float | None = None
    if record.state == "ready" and ready_since is not None:
        ready_since = float(ready_since)
        if not math.isfinite(ready_since) or ready_since < 0:
            raise ValueError("ready time must be finite and nonnegative")
        if record.last_used_at is not None:
            last_used_at = float(record.last_used_at)
            if not math.isfinite(last_used_at) or last_used_at < 0:
                raise ValueError("last activity time must be finite and nonnegative")
            activity_at = max(ready_since, last_used_at)
        else:
            # A ready role never used in this residency safely idles from ready_since.
            activity_at = ready_since
    idle_seconds = max(0.0, now - activity_at) if activity_at is not None else 0.0
    residency_seconds = max(0.0, now - ready_since) if ready_since is not None else 0.0

    reason: IdlePolicyReason
    next_count = 0
    would_unload = False
    if mode == "disabled":
        reason = "mode_disabled"
    elif previous_mode is not None and previous_mode != mode:
        reason = "mode_changed"
    elif record.state != "ready" or ready_since is None or activity_at is None:
        reason = "state_not_ready"
    elif has_blockers:
        reason = "blocked"
    elif residency_seconds < minimum_residency:
        reason = "minimum_residency"
    elif previous_last_activity_at is not None and previous_last_activity_at != activity_at:
        reason = "activity_reset"
    elif idle_seconds <= threshold:
        reason = "below_threshold"
    elif previous_consecutive_check_count and (
        previous_mode is None or previous_last_activity_at is None
    ):
        reason = "state_reset"
    elif previous_consecutive_check_count == 0:
        next_count = 1
        reason = "first_idle_check"
    else:
        next_count = 2
        would_unload = True
        reason = "idle_confirmed"

    return IdlePolicyDecision(
        role=role,
        mode=mode,
        threshold_seconds=threshold,
        threshold_source=source,
        sample_count=len(gaps),
        idle_seconds=idle_seconds,
        residency_seconds=residency_seconds,
        next_consecutive_check_count=next_count,
        would_unload=would_unload,
        action_allowed=would_unload and mode in {"fixed", "adaptive"},
        reason=reason,
    )


def _reported_percent(match: re.Match[str]) -> float | None:
    loaded = float(match.group("loaded"))
    total = float(match.group("total"))
    if total <= 0 or loaded > total:
        return None
    return loaded / total * 100


def parse_load_progress(
    lines: Sequence[str],
    *,
    previous_percent: float | None = None,
    previous_quality: ProgressQuality | None = None,
) -> LoadProgress:
    bytes_percent: float | None = None
    shards_percent: float | None = None
    stage: Literal["loading_weights", "initializing_engine", "warming_up"] = "loading_weights"
    for raw_line in lines[-MAX_PROGRESS_LINES:]:
        line = raw_line[:MAX_PROGRESS_LINE_CHARACTERS]
        normalized = line.lower()
        if "warm" in normalized and "up" in normalized:
            stage = "warming_up"
        elif stage == "loading_weights" and "engine" in normalized and "initializ" in normalized:
            stage = "initializing_engine"
        if match := BYTE_PROGRESS.search(line):
            candidate = _reported_percent(match)
            if candidate is not None:
                bytes_percent = candidate
        if match := SHARD_PROGRESS.search(line):
            candidate = _reported_percent(match)
            if candidate is not None:
                shards_percent = candidate

    measured = bytes_percent if bytes_percent is not None else shards_percent
    quality: ProgressQuality = (
        "measured_bytes"
        if bytes_percent is not None
        else "measured_shards"
        if shards_percent is not None
        else "unavailable"
    )
    if previous_percent is not None and (measured is None or previous_percent > measured):
        measured = previous_percent
        quality = previous_quality or (quality if quality != "unavailable" else "estimated")
    if stage != "loading_weights":
        return LoadProgress(
            state=stage,
            weight_load_percent=100.0,
            progress_quality=(
                quality
                if measured == 100.0 and quality in {"measured_bytes", "measured_shards"}
                else "estimated"
            ),
        )
    return LoadProgress(
        state="loading_weights",
        weight_load_percent=measured,
        progress_quality=quality,
    )


class LifecycleError(RuntimeError):
    pass


class UnknownRoleError(LifecycleError):
    pass


class InvalidTransitionError(LifecycleError):
    pass


class StaleTransitionError(LifecycleError):
    pass


class LifecycleDriverError(LifecycleError):
    def __init__(self, operation: DriverOperation, kind: DriverErrorKind):
        self.operation = operation
        self.kind = kind
        super().__init__(f"lifecycle {operation} {kind}")


class LifecycleLoadError(LifecycleError):
    def __init__(self, failure_class: str, failure_detail: str):
        self.failure_class = failure_class
        self.failure_detail = failure_detail
        super().__init__(failure_class)


def continuation_correlation(session_id: str) -> str:
    return hashlib.sha256(b"dgx-moa-continuation\0" + session_id.encode()).hexdigest()


class LifecycleDriver(Protocol):
    def status(self, role: str) -> DriverStatus: ...

    def start(self, role: str) -> None: ...

    def stop(self, role: str) -> None: ...

    def capture_progress_cursor(self, role: str) -> str: ...

    def progress(self, role: str, cursor: str) -> tuple[str, ...]: ...


COLUMNS = tuple(LifecycleRecord.model_fields)
LEASE_COLUMNS = tuple(LifecycleLease.model_fields)
MUTABLE_FIELDS = frozenset(COLUMNS) - {
    "role",
    "state",
    "transition_id",
    "transitioned_at",
    "updated_at",
}
BOOLEAN_FIELDS = {"evaluation_guard", "profile_guard"}
FAILURE_CLASS_PATTERN = re.compile(r"[^a-z0-9]+")


def _sanitize_failure_class(value: str) -> str:
    return FAILURE_CLASS_PATTERN.sub("_", value.lower()).strip("_")[:64] or "unknown"


def _sanitize_failure_detail(value: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()[:256]


class LifecycleStore:
    def __init__(
        self,
        path: str | Path,
        roles: Iterable[str],
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._roles = tuple(dict.fromkeys(roles))
        self._role_set = set(self._roles)
        self._clock = clock
        unknown = self._role_set - MODEL_ROLES
        if unknown:
            raise UnknownRoleError(sorted(unknown)[0])
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS model_lifecycle ("
                "role TEXT PRIMARY KEY, state TEXT NOT NULL, transition_id TEXT NOT NULL, "
                "transitioned_at REAL NOT NULL, updated_at REAL NOT NULL, ready_since REAL, "
                "last_used_at REAL, failure_class TEXT, failure_detail TEXT, "
                "retry_count INTEGER NOT NULL, active_request_count INTEGER NOT NULL, "
                "open_stream_count INTEGER NOT NULL, continuation_lease_count INTEGER NOT NULL, "
                "evaluation_guard INTEGER NOT NULL, profile_guard INTEGER NOT NULL, "
                "progress_value REAL, progress_quality TEXT, eta_seconds REAL, "
                "last_load_duration_seconds REAL, last_unload_duration_seconds REAL, "
                "memory_before_bytes INTEGER, memory_after_bytes INTEGER)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS model_lifecycle_leases ("
                "lease_id TEXT PRIMARY KEY, role TEXT NOT NULL, kind TEXT NOT NULL "
                "CHECK(kind IN ('active_request', 'open_stream', 'continuation')), "
                "owner_correlation TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL, "
                "FOREIGN KEY(role) REFERENCES model_lifecycle(role))"
            )
            database.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS model_lifecycle_lease_owner "
                "ON model_lifecycle_leases(role, kind, owner_correlation)"
            )
            for role in self._roles:
                now = self._clock()
                record = LifecycleRecord(
                    role=role,
                    state="cold",
                    transition_id=str(uuid4()),
                    transitioned_at=now,
                    updated_at=now,
                )
                database.execute(
                    f"INSERT OR IGNORE INTO model_lifecycle ({', '.join(COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in COLUMNS)})",
                    self._values(record),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.row_factory = sqlite3.Row
        return connection

    def _require_role(self, role: str) -> None:
        if role not in self._role_set:
            raise UnknownRoleError(role)

    def _lease_now(self) -> float:
        now = self._clock()
        if not math.isfinite(now) or now < 0:
            raise ValueError("lifecycle lease clock must be finite and nonnegative")
        return now

    @staticmethod
    def _record(row: sqlite3.Row) -> LifecycleRecord:
        values = dict(row)
        for field in BOOLEAN_FIELDS:
            values[field] = bool(values[field])
        return LifecycleRecord.model_validate(values)

    @staticmethod
    def _values(record: LifecycleRecord) -> tuple[Any, ...]:
        values = record.model_dump()
        return tuple(
            int(values[column]) if column in BOOLEAN_FIELDS else values[column]
            for column in COLUMNS
        )

    @staticmethod
    def _lease_values(lease: LifecycleLease) -> tuple[Any, ...]:
        values = lease.model_dump()
        return tuple(values[column] for column in LEASE_COLUMNS)

    @staticmethod
    def _lease(row: sqlite3.Row) -> LifecycleLease:
        return LifecycleLease.model_validate(dict(row))

    def _read(self, database: sqlite3.Connection, role: str) -> LifecycleRecord:
        row = database.execute(
            f"SELECT {', '.join(COLUMNS)} FROM model_lifecycle WHERE role = ?", (role,)
        ).fetchone()
        if row is None:
            raise UnknownRoleError(role)
        return self._record(row)

    @staticmethod
    def _write(database: sqlite3.Connection, record: LifecycleRecord) -> None:
        assignments = ", ".join(f"{column} = ?" for column in COLUMNS if column != "role")
        values = LifecycleStore._values(record)
        database.execute(
            f"UPDATE model_lifecycle SET {assignments} WHERE role = ?",
            values[1:] + (record.role,),
        )

    def get(self, role: str) -> LifecycleRecord:
        self._require_role(role)
        with self._connect() as database:
            return self._read(database, role)

    def _sync_lease_counts(
        self,
        database: sqlite3.Connection,
        roles: Iterable[str],
        now: float,
    ) -> None:
        for role in roles:
            counts = database.execute(
                "SELECT "
                "COUNT(*) FILTER (WHERE kind = 'active_request'), "
                "COUNT(*) FILTER (WHERE kind = 'open_stream'), "
                "COUNT(*) FILTER (WHERE kind = 'continuation' "
                "AND expires_at > ?) "
                "FROM model_lifecycle_leases WHERE role = ?",
                (now, role),
            ).fetchone()
            assert counts is not None
            database.execute(
                "UPDATE model_lifecycle SET active_request_count = ?, open_stream_count = ?, "
                "continuation_lease_count = ?, updated_at = ? WHERE role = ?",
                (*counts, now, role),
            )

    def acquire_request_leases(
        self,
        request_id: str,
        roles: Iterable[str],
        *,
        kind: RequestLeaseKind,
    ) -> tuple[LifecycleLease, ...]:
        namespace = UUID(request_id)
        requested_roles = tuple(dict.fromkeys(roles))
        for role in requested_roles:
            self._require_role(role)
        now = self._lease_now()
        leases = tuple(
            LifecycleLease(
                lease_id=str(uuid5(namespace, f"{kind}:{role}")),
                role=role,
                kind=kind,
                owner_correlation=request_id,
                created_at=now,
            )
            for role in requested_roles
        )
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            for lease in leases:
                database.execute(
                    f"INSERT OR IGNORE INTO model_lifecycle_leases "
                    f"({', '.join(LEASE_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in LEASE_COLUMNS)})",
                    self._lease_values(lease),
                )
            self._sync_lease_counts(database, requested_roles, now)
            return tuple(
                self._lease(
                    database.execute(
                        f"SELECT {', '.join(LEASE_COLUMNS)} FROM model_lifecycle_leases "
                        "WHERE lease_id = ?",
                        (lease.lease_id,),
                    ).fetchone()
                )
                for lease in leases
            )

    def _prune_expired_continuations(
        self,
        database: sqlite3.Connection,
        now: float,
    ) -> tuple[int, tuple[str, ...]]:
        roles = tuple(
            row[0]
            for row in database.execute(
                "SELECT DISTINCT role FROM model_lifecycle_leases "
                "WHERE kind = 'continuation' AND expires_at <= ?",
                (now,),
            )
        )
        removed = database.execute(
            "DELETE FROM model_lifecycle_leases WHERE kind = 'continuation' AND expires_at <= ?",
            (now,),
        ).rowcount
        return removed, roles

    def refresh_continuation(
        self,
        request_id: str,
        role: str,
        owner_correlation: str,
        *,
        expires_at: float,
    ) -> LifecycleLease:
        self._require_role(role)
        namespace = UUID(request_id)
        if CONTINUATION_CORRELATION.fullmatch(owner_correlation) is None:
            raise ValueError("invalid continuation correlation")
        now = self._lease_now()
        if not math.isfinite(expires_at) or expires_at <= now:
            raise ValueError("continuation expiry must be finite and in the future")
        lease = LifecycleLease(
            lease_id=str(uuid5(namespace, f"continuation:{role}")),
            role=role,
            kind="continuation",
            owner_correlation=owner_correlation,
            created_at=now,
            expires_at=expires_at,
        )
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            _, expired_roles = self._prune_expired_continuations(database, now)
            database.execute(
                f"INSERT INTO model_lifecycle_leases ({', '.join(LEASE_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in LEASE_COLUMNS)}) "
                "ON CONFLICT(role, kind, owner_correlation) DO UPDATE SET "
                "lease_id = excluded.lease_id, created_at = excluded.created_at, "
                "expires_at = excluded.expires_at",
                self._lease_values(lease),
            )
            self._sync_lease_counts(database, (*expired_roles, role), now)
            row = database.execute(
                f"SELECT {', '.join(LEASE_COLUMNS)} FROM model_lifecycle_leases "
                "WHERE role = ? AND kind = 'continuation' AND owner_correlation = ?",
                (role, owner_correlation),
            ).fetchone()
            assert row is not None
            return self._lease(row)

    def prune_expired_continuations(self) -> int:
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            removed, roles = self._prune_expired_continuations(database, now)
            self._sync_lease_counts(database, roles, now)
            return removed

    def release_continuation(self, role: str, owner_correlation: str) -> bool:
        self._require_role(role)
        if CONTINUATION_CORRELATION.fullmatch(owner_correlation) is None:
            raise ValueError("invalid continuation correlation")
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            _, expired_roles = self._prune_expired_continuations(database, now)
            removed = database.execute(
                "DELETE FROM model_lifecycle_leases WHERE role = ? "
                "AND kind = 'continuation' AND owner_correlation = ? AND expires_at > ?",
                (role, owner_correlation, now),
            ).rowcount
            self._sync_lease_counts(database, (*expired_roles, role), now)
            return bool(removed)

    def set_guard(
        self,
        role: str,
        guard: GuardKind,
        enabled: bool,
        *,
        expected_transition_id: str,
    ) -> LifecycleRecord:
        self._require_role(role)
        if guard not in BOOLEAN_FIELDS:
            raise ValueError("invalid lifecycle guard")
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            if current.transition_id != expected_transition_id:
                raise StaleTransitionError(role)
            if getattr(current, guard) is enabled:
                return current
            updated = self._updated_record(current, {guard: enabled}, now)
            self._write(database, updated)
            return updated

    def unload_blockers(self, role: str) -> frozenset[str]:
        self._require_role(role)
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            _, expired_roles = self._prune_expired_continuations(database, now)
            self._sync_lease_counts(database, (*expired_roles, role), now)
            record = self._read(database, role)
            blockers = {
                kind
                for kind, count in (
                    ("active_request", record.active_request_count),
                    ("open_stream", record.open_stream_count),
                    ("continuation", record.continuation_lease_count),
                )
                if count
            }
            blockers.update(guard for guard in BOOLEAN_FIELDS if getattr(record, guard))
            return frozenset(blockers)

    def recover_leases(self) -> dict[str, LifecycleRecord]:
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "DELETE FROM model_lifecycle_leases WHERE kind IN ('active_request', 'open_stream')"
            )
            self._prune_expired_continuations(database, now)
            self._sync_lease_counts(database, self._roles, now)
            return {role: self._read(database, role) for role in self._roles}

    def release_leases(self, lease_ids: Iterable[str]) -> None:
        requested = tuple(dict.fromkeys(lease_ids))
        if not requested:
            return
        if any(str(UUID(lease_id)) != lease_id for lease_id in requested):
            raise ValueError("invalid lifecycle lease ID")
        placeholders = ", ".join("?" for _ in requested)
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            roles = tuple(
                row[0]
                for row in database.execute(
                    f"SELECT DISTINCT role FROM model_lifecycle_leases "
                    f"WHERE lease_id IN ({placeholders})",
                    requested,
                )
            )
            database.execute(
                f"DELETE FROM model_lifecycle_leases WHERE lease_id IN ({placeholders})",
                requested,
            )
            self._sync_lease_counts(database, roles, now)

    def _updated_record(
        self, current: LifecycleRecord, changes: Mapping[str, Any], now: float
    ) -> LifecycleRecord:
        unknown = set(changes) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"immutable lifecycle fields: {sorted(unknown)}")
        values = current.model_dump()
        values.update(changes)
        if values.get("failure_class") is not None:
            values["failure_class"] = _sanitize_failure_class(str(values["failure_class"]))
        if values.get("failure_detail") is not None:
            values["failure_detail"] = _sanitize_failure_detail(str(values["failure_detail"]))
        values["updated_at"] = now
        return LifecycleRecord.model_validate(values)

    def update(self, role: str, transition_id: str, **changes: Any) -> LifecycleRecord:
        self._require_role(role)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            if current.transition_id != transition_id:
                raise StaleTransitionError(role)
            updated = self._updated_record(current, changes, self._clock())
            self._write(database, updated)
            return updated

    def transition(
        self,
        role: str,
        state: LifecycleState,
        *,
        expected_transition_id: str,
        **changes: Any,
    ) -> LifecycleRecord:
        self._require_role(role)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            if current.transition_id != expected_transition_id:
                raise StaleTransitionError(role)
            if state not in TRANSITIONS[current.state]:
                raise InvalidTransitionError(f"{current.state} -> {state}")
            now = self._clock()
            updated = self._updated_record(current, changes, now)
            values = updated.model_dump()
            values.update(
                state=state,
                transition_id=str(uuid4()),
                transitioned_at=now,
                updated_at=now,
            )
            if state == "ready":
                values["ready_since"] = now
            elif state == "cold":
                values.update(
                    ready_since=None,
                    failure_class=None,
                    failure_detail=None,
                    progress_value=None,
                    progress_quality=None,
                    eta_seconds=None,
                )
            elif state != "failed":
                values["failure_class"] = None
                values["failure_detail"] = None
            transitioned = LifecycleRecord.model_validate(values)
            self._write(database, transitioned)
            return transitioned

    def _reconcile_transition(self, role: str, state: LifecycleState) -> LifecycleRecord:
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            if current.state == state:
                return current
            now = self._clock()
            values = current.model_dump()
            values.update(
                state=state,
                transition_id=str(uuid4()),
                transitioned_at=now,
                updated_at=now,
                ready_since=None,
                progress_value=None,
                progress_quality=None,
                eta_seconds=None,
                failure_class="service_failed" if state == "failed" else None,
                failure_detail=None,
            )
            reconciled = LifecycleRecord.model_validate(values)
            self._write(database, reconciled)
            return reconciled

    def reconcile(self, driver: LifecycleDriver) -> dict[str, LifecycleRecord]:
        target: dict[DriverStatus, LifecycleState] = {
            "active": "process_starting",
            "inactive": "cold",
            "failed": "failed",
        }
        return {
            role: self._reconcile_transition(role, target[driver.status(role)])
            for role in self._roles
        }


class LifecycleCoordinator:
    def __init__(
        self,
        store: LifecycleStore,
        driver: LifecycleDriver,
        *,
        health_probe: Callable[[str], Awaitable[bool]],
        timeout_seconds: float,
        poll_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.store = store
        self.driver = driver
        self.health_probe = health_probe
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.clock = clock
        self.sleeper = sleeper
        self._locks = {role: asyncio.Lock() for role in store._roles}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def ensure_ready(self, role: str) -> LoadCheck:
        try:
            lock = self._locks[role]
        except KeyError as error:
            raise UnknownRoleError(role) from error
        async with lock:
            record = self.store.get(role)
            task = self._tasks.get(role)
            if task is not None and task.done():
                self._tasks.pop(role)
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                record = self.store.get(role)
                task = None
            if record.state == "ready" or task is not None:
                return LoadCheck(record=record)
            if record.state not in {"cold", "failed"} or record.retry_count >= MAX_LOAD_RETRIES:
                return LoadCheck(record=record)
            queued = self.store.transition(
                role,
                "load_queued",
                expected_transition_id=record.transition_id,
                progress_value=None,
                progress_quality="unavailable",
                eta_seconds=None,
            )
            self._tasks[role] = asyncio.create_task(self._load(role, queued.transition_id))
            return LoadCheck(record=queued, load_triggered=True)

    async def _load(self, role: str, transition_id: str) -> None:
        started = self.clock()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self._run_load(role, transition_id, started)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self._fail(role, "load_timeout", "model load timed out")
        except LifecycleLoadError as error:
            self._fail(role, error.failure_class, error.failure_detail)
        except LifecycleDriverError as error:
            self._fail(role, f"{error.operation}_{error.kind}", "lifecycle driver failed")
        except Exception as error:
            self._fail(role, "load_failed", type(error).__name__)

    async def _run_load(self, role: str, transition_id: str, started: float) -> None:
        record = self.store.transition(
            role,
            "process_starting",
            expected_transition_id=transition_id,
        )
        cursor = await asyncio.to_thread(self.driver.capture_progress_cursor, role)
        await asyncio.to_thread(self.driver.start, role)
        while True:
            driver_status = await asyncio.to_thread(self.driver.status, role)
            if driver_status != "active":
                raise LifecycleLoadError(
                    f"service_{driver_status}", "service did not become active"
                )
            if record.state == "process_starting":
                record = self.store.transition(
                    role,
                    "loading_weights",
                    expected_transition_id=record.transition_id,
                    progress_quality="unavailable",
                )
            lines = await asyncio.to_thread(self.driver.progress, role, cursor)
            progress = parse_load_progress(
                lines,
                previous_percent=record.progress_value,
                previous_quality=record.progress_quality,
            )
            if progress.state == "initializing_engine" and record.state == "loading_weights":
                record = self.store.transition(
                    role,
                    "initializing_engine",
                    expected_transition_id=record.transition_id,
                    progress_value=100.0,
                    progress_quality=progress.progress_quality,
                )
            elif progress.state == "warming_up":
                if record.state == "loading_weights":
                    record = self.store.transition(
                        role,
                        "initializing_engine",
                        expected_transition_id=record.transition_id,
                        progress_value=100.0,
                        progress_quality=progress.progress_quality,
                    )
                if record.state == "initializing_engine":
                    record = self.store.transition(
                        role,
                        "warming_up",
                        expected_transition_id=record.transition_id,
                        progress_value=100.0,
                        progress_quality=progress.progress_quality,
                    )
            else:
                eta = None
                if (
                    record.last_load_duration_seconds is not None
                    and progress.weight_load_percent is not None
                ):
                    eta = min(
                        self.timeout_seconds,
                        max(
                            0.0,
                            record.last_load_duration_seconds
                            * (100 - progress.weight_load_percent)
                            / 100,
                        ),
                    )
                record = self.store.update(
                    role,
                    record.transition_id,
                    progress_value=progress.weight_load_percent,
                    progress_quality=progress.progress_quality,
                    eta_seconds=eta,
                )
            try:
                healthy = await self.health_probe(role)
            except Exception as error:
                raise LifecycleLoadError("health_probe_failed", type(error).__name__) from None
            if healthy:
                ready_quality: ProgressQuality = (
                    record.progress_quality
                    if record.progress_value == 100.0
                    and record.progress_quality in {"measured_bytes", "measured_shards"}
                    else "estimated"
                )
                if record.state == "loading_weights":
                    record = self.store.transition(
                        role,
                        "initializing_engine",
                        expected_transition_id=record.transition_id,
                        progress_value=100.0,
                        progress_quality=ready_quality,
                    )
                if record.state == "initializing_engine":
                    record = self.store.transition(
                        role,
                        "warming_up",
                        expected_transition_id=record.transition_id,
                        progress_value=100.0,
                        progress_quality=ready_quality,
                    )
                self.store.transition(
                    role,
                    "ready",
                    expected_transition_id=record.transition_id,
                    progress_value=100.0,
                    progress_quality=ready_quality,
                    eta_seconds=0.0 if record.last_load_duration_seconds is not None else None,
                    last_load_duration_seconds=max(0.0, self.clock() - started),
                )
                return
            try:
                await self.sleeper(self.poll_seconds)
            except TimeoutError:
                raise LifecycleLoadError("health_timeout", "model health timed out") from None

    def _fail(self, role: str, failure_class: str, failure_detail: str) -> None:
        record = self.store.get(role)
        if record.state == "failed":
            return
        self.store.transition(
            role,
            "failed",
            expected_transition_id=record.transition_id,
            failure_class=failure_class,
            failure_detail=failure_detail,
            retry_count=record.retry_count + 1,
            eta_seconds=None,
        )

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


class FakeLifecycleDriver:
    def __init__(
        self,
        statuses: Mapping[str, DriverStatus],
        *,
        progress: Mapping[str, tuple[str, ...]] | None = None,
        cursors: Mapping[str, str] | None = None,
    ):
        self._statuses = dict(statuses)
        self._progress = dict(progress or {})
        self._cursors = {role: (cursors or {}).get(role, f"s=fake_{role}") for role in statuses}
        self.calls: list[tuple[DriverOperation, str]] = []
        self.progress_cursors: list[tuple[str, str]] = []

    def _require_role(self, role: str) -> None:
        if role not in self._statuses:
            raise UnknownRoleError(role)

    def status(self, role: str) -> DriverStatus:
        self._require_role(role)
        self.calls.append(("status", role))
        return self._statuses[role]

    def start(self, role: str) -> None:
        self._require_role(role)
        self.calls.append(("start", role))
        self._statuses[role] = "active"

    def stop(self, role: str) -> None:
        self._require_role(role)
        self.calls.append(("stop", role))
        self._statuses[role] = "inactive"

    def capture_progress_cursor(self, role: str) -> str:
        self._require_role(role)
        self.calls.append(("cursor", role))
        return self._cursors[role]

    def progress(self, role: str, cursor: str) -> tuple[str, ...]:
        self._require_role(role)
        self.calls.append(("progress", role))
        self.progress_cursors.append((role, cursor))
        return self._progress.get(role, ())


class SystemdLifecycleDriver:
    def __init__(
        self,
        unit_map: Mapping[str, str],
        *,
        timeout_seconds: float = 10.0,
        journal_lines: int = 200,
    ):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= journal_lines <= 1_000:
            raise ValueError("journal_lines must be between 1 and 1000")
        unknown = set(unit_map) - MODEL_ROLES
        if unknown:
            raise UnknownRoleError(sorted(unknown)[0])
        if any(not SYSTEMD_UNIT_PATTERN.fullmatch(unit) for unit in unit_map.values()):
            raise ValueError("invalid systemd unit")
        if len(set(unit_map.values())) != len(unit_map):
            raise ValueError("duplicate lifecycle unit")
        self._units = dict(unit_map)
        self._timeout_seconds = timeout_seconds
        self._journal_lines = journal_lines

    def _unit(self, role: str) -> str:
        try:
            return self._units[role]
        except KeyError as error:
            raise UnknownRoleError(role) from error

    def _run(self, operation: DriverOperation, args: Sequence[str]) -> str:
        completed: subprocess.CompletedProcess[str] | None
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed = None
        if completed is None:
            raise LifecycleDriverError(operation, "timeout") from None
        if completed.returncode != 0:
            raise LifecycleDriverError(operation, "command_failed")
        return completed.stdout

    def status(self, role: str) -> DriverStatus:
        output = self._run(
            "status",
            [
                "systemctl",
                "--user",
                "show",
                self._unit(role),
                "--property=ActiveState",
                "--property=SubState",
                "--value",
            ],
        )
        lines = output.splitlines()
        states: dict[str, DriverStatus] = {
            "active": "active",
            "inactive": "inactive",
            "failed": "failed",
        }
        if len(lines) != 2 or not lines[1] or lines[0] not in states:
            raise LifecycleDriverError("status", "malformed_output")
        return states[lines[0]]

    def start(self, role: str) -> None:
        args = ["systemctl", "--user", "start", self._unit(role)]
        self._run("start", args)

    def stop(self, role: str) -> None:
        args = ["systemctl", "--user", "stop", self._unit(role)]
        self._run("stop", args)

    @staticmethod
    def _valid_cursor(cursor: str) -> bool:
        return (
            0 < len(cursor) <= MAX_JOURNAL_CURSOR_CHARACTERS
            and JOURNAL_CURSOR.fullmatch(cursor) is not None
        )

    def capture_progress_cursor(self, role: str) -> str:
        output = self._run(
            "cursor",
            [
                "journalctl",
                "--user",
                "-u",
                self._unit(role),
                "--no-pager",
                "-n",
                "0",
                "--show-cursor",
            ],
        )
        lines = output.splitlines()
        prefix = "-- cursor: "
        if len(lines) != 1 or not lines[0].startswith(prefix):
            raise LifecycleDriverError("cursor", "malformed_output")
        cursor = lines[0][len(prefix) :]
        if not self._valid_cursor(cursor):
            raise LifecycleDriverError("cursor", "malformed_output")
        return cursor

    def progress(self, role: str, cursor: str) -> tuple[str, ...]:
        if not self._valid_cursor(cursor):
            raise LifecycleDriverError("progress", "malformed_output")
        output = self._run(
            "progress",
            [
                "journalctl",
                "--user",
                "-u",
                self._unit(role),
                "--no-pager",
                "-n",
                str(self._journal_lines),
                "--after-cursor",
                cursor,
                "--output=cat",
            ],
        )
        return tuple(output.splitlines()[-self._journal_lines :])
