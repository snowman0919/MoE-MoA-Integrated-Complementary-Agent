from __future__ import annotations

import asyncio
import hashlib
import math
import re
import sqlite3
import subprocess
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, cast
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from .config import (
    MODEL_ROLES,
    SYSTEMD_UNIT_PATTERN,
    LifecyclePolicy,
    LifecycleRolePolicy,
    Limits,
)
from .usage import UsageStore

LifecycleState = Literal[
    "disabled",
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unload_queued",
    "unloading",
    "failed",
]
DriverStatus = Literal["active", "inactive", "failed"]
DriverOperation = Literal["status", "start", "stop", "cursor", "progress"]
DriverErrorKind = Literal["timeout", "command_failed", "malformed_output"]
ProgressQuality = Literal[
    "measured_bytes", "measured_shards", "measured_phase", "estimated", "unavailable"
]
LeaseKind = Literal["active_request", "open_stream", "continuation"]
RequestLeaseKind = Literal["active_request", "open_stream"]
GuardKind = Literal["evaluation_guard", "profile_guard"]
ModelRole = Literal["executor", "planner", "reviewer", "reasoner", "judge"]
LifecycleMode = Literal["disabled", "observe", "fixed", "adaptive"]
IdleThresholdSource = Literal["disabled", "fixed", "sparse_fallback", "adaptive_p75"]
IdlePolicyReason = Literal[
    "mode_disabled",
    "role_disabled",
    "idle_unload_disabled",
    "mode_changed",
    "state_reset",
    "state_not_ready",
    "blocked",
    "minimum_residency",
    "cooldown",
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
T = TypeVar("T")

LIFECYCLE_STATES: tuple[LifecycleState, ...] = (
    "disabled",
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unload_queued",
    "unloading",
    "failed",
)
TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    "disabled": frozenset({"cold"}),
    "cold": frozenset({"disabled", "load_queued"}),
    "load_queued": frozenset({"disabled", "cold", "process_starting", "failed"}),
    "process_starting": frozenset({"disabled", "cold", "loading_weights", "failed"}),
    "loading_weights": frozenset({"disabled", "cold", "initializing_engine", "failed"}),
    "initializing_engine": frozenset({"disabled", "cold", "warming_up", "failed"}),
    "warming_up": frozenset({"disabled", "cold", "ready", "failed"}),
    "ready": frozenset({"disabled", "sleeping", "unload_queued", "unloading", "failed"}),
    "sleeping": frozenset({"disabled", "cold", "ready", "unloading", "failed"}),
    "unload_queued": frozenset({"disabled", "ready", "unloading", "failed"}),
    "unloading": frozenset({"disabled", "cold", "failed"}),
    "failed": frozenset({"disabled", "cold", "load_queued"}),
}


class LifecycleRecord(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    role: str
    generation: int = Field(default=0, ge=0)
    state: LifecycleState
    transition_id: str
    transitioned_at: float
    updated_at: float
    ready_since: float | None = None
    last_used_at: float | None = None
    load_started_at: float | None = Field(default=None, ge=0)
    ready_at: float | None = Field(default=None, ge=0)
    last_requested_at: float | None = Field(default=None, ge=0)
    last_completed_at: float | None = Field(default=None, ge=0)
    failure_class: str | None = None
    failure_detail: str | None = None
    retry_count: int = Field(default=0, ge=0)
    active_request_count: int = Field(default=0, ge=0)
    open_stream_count: int = Field(default=0, ge=0)
    continuation_lease_count: int = Field(default=0, ge=0)
    evaluation_guard: bool = False
    profile_guard: bool = False
    progress_value: float | None = Field(default=None, ge=0, le=100)
    weight_load_percent: float | None = Field(default=None, ge=0, le=100)
    overall_load_percent: float | None = Field(default=None, ge=0, le=100)
    progress_quality: ProgressQuality | None = None
    eta_seconds: float | None = Field(default=None, ge=0)
    last_load_duration_seconds: float | None = Field(default=None, ge=0)
    last_unload_duration_seconds: float | None = Field(default=None, ge=0)
    memory_before_bytes: int | None = Field(default=None, ge=0)
    memory_after_bytes: int | None = Field(default=None, ge=0)
    service_unit: str | None = None
    last_error_class: str | None = None
    last_error_message_redacted: str | None = None


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


class PersistedIdlePolicyDecision(IdlePolicyDecision):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    decided_at: float = Field(ge=0)


class LifecycleFailureEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    event_id: int = Field(ge=1)
    role: ModelRole
    operation_stage: str
    failure_class: str
    generation: int = Field(ge=0)
    occurred_at: float = Field(ge=0)


class LifecycleAutomationStatus(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    automation_disabled: bool = False
    disabled_at: float | None = Field(default=None, ge=0)
    failure_count: int = Field(default=0, ge=0)
    window_started_at: float | None = Field(default=None, ge=0)
    last_failure_at: float | None = Field(default=None, ge=0)
    last_reset_at: float = Field(default=0, ge=0)


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
            raw_timestamp = getattr(record, "requested_at", getattr(record, "accepted_at", None))
            if raw_timestamp is None:
                continue
            accepted_at = float(raw_timestamp)
        except (AttributeError, TypeError, ValueError):
            continue
        record_role = getattr(record, "role", None)
        record_roles = getattr(record, "roles_required", ())
        successful = getattr(record, "success", True) is not False
        if (
            successful
            and (record_role == role or role in record_roles)
            and math.isfinite(accepted_at)
            and accepted_at >= 0
        ):
            timestamps.append(accepted_at)
    timestamps = sorted(timestamps)[-sample_window:]
    return [
        gap
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
        if math.isfinite(gap := later - earlier) and gap > 0
    ]


def _configured_quantile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def calculate_idle_policy(
    role: ModelRole,
    mode: LifecycleMode,
    records: Sequence[RoleUsageRecord],
    record: LifecycleRecord,
    *,
    now: float,
    limits: Limits | None = None,
    policy: LifecycleRolePolicy | None = None,
    lifecycle: LifecyclePolicy | None = None,
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
    if (policy is None) != (lifecycle is None):
        raise ValueError("role and lifecycle policy must be provided together")
    if limits is None and lifecycle is None:
        raise ValueError("idle policy configuration is required")
    if lifecycle is not None:
        minimum_samples = lifecycle.minimum_samples
        sample_window = lifecycle.recent_sample_window
        multiplier = lifecycle.multiplier
        percentile = lifecycle.percentile
        cooldown = lifecycle.load_unload_cooldown_seconds
    else:
        assert limits is not None
        minimum_samples = limits.adaptive_minimum_samples
        sample_window = limits.usage_sample_window
        multiplier = 1.5
        percentile = 0.75
        cooldown = 0.0
    if (
        not isinstance(minimum_samples, int)
        or isinstance(minimum_samples, bool)
        or minimum_samples < 1
    ):
        raise ValueError("adaptive minimum samples must be positive")

    if policy is not None:
        minimum = policy.minimum_timeout_seconds
        fallback = policy.fallback_timeout_seconds
        maximum = policy.maximum_timeout_seconds
        minimum_residency = policy.minimum_ready_residency_seconds
    else:
        assert limits is not None
        minimum, fallback, maximum, minimum_residency = _idle_bounds(role, limits)
    gaps = _role_usage_gaps(records, role, sample_window)
    adaptive = mode in {"observe", "adaptive"} and len(gaps) >= minimum_samples
    if adaptive:
        selected = _configured_quantile(gaps, percentile)
        threshold = min(maximum, max(minimum, multiplier * selected))
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
    elif policy is not None and not policy.enabled:
        reason = "role_disabled"
    elif policy is not None and not policy.idle_unload_enabled:
        reason = "idle_unload_disabled"
    elif previous_mode is not None and previous_mode != mode:
        reason = "mode_changed"
    elif record.state != "ready" or ready_since is None or activity_at is None:
        reason = "state_not_ready"
    elif has_blockers:
        reason = "blocked"
    elif residency_seconds < minimum_residency:
        reason = "minimum_residency"
    elif now - record.transitioned_at < cooldown:
        reason = "cooldown"
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
    try:
        loaded = float(match.group("loaded"))
        total = float(match.group("total"))
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(loaded) or not math.isfinite(total) or total <= 0 or loaded > total:
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
                else "measured_phase"
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


class LifecycleNotReadyError(LifecycleError):
    def __init__(self, record: LifecycleRecord):
        self.record = record
        super().__init__(record.state)


def continuation_correlation(session_id: str) -> str:
    return hashlib.sha256(b"dgx-moa-continuation\0" + session_id.encode()).hexdigest()


def read_latest_decisions(path: str | Path) -> dict[str, PersistedIdlePolicyDecision]:
    database_path = Path(path)
    if not database_path.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as database:
            database.row_factory = sqlite3.Row
            table = database.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'model_lifecycle_decisions'"
            ).fetchone()
            if table is None:
                return {}
            rows = database.execute(
                f"SELECT {', '.join(DECISION_COLUMNS)} FROM model_lifecycle_decisions ORDER BY role"
            ).fetchall()
    except sqlite3.Error:
        return {}
    decisions: dict[str, PersistedIdlePolicyDecision] = {}
    for row in rows:
        if row["role"] not in MODEL_ROLES:
            continue
        try:
            decisions[row["role"]] = LifecycleStore._decision(row)
        except ValueError:
            continue
    return decisions


def read_automation_status(path: str | Path) -> LifecycleAutomationStatus:
    database_path = Path(path)
    if not database_path.exists():
        return LifecycleAutomationStatus()
    try:
        with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as database:
            database.row_factory = sqlite3.Row
            row = database.execute(
                f"SELECT {', '.join(AUTOMATION_COLUMNS)} FROM lifecycle_automation "
                "WHERE singleton = 1"
            ).fetchone()
    except sqlite3.Error:
        return LifecycleAutomationStatus()
    return LifecycleStore._automation(row) if row is not None else LifecycleAutomationStatus()


class LifecycleDriver(Protocol):
    def status(self, role: str) -> DriverStatus: ...

    def start(self, role: str) -> None: ...

    def stop(self, role: str) -> None: ...

    def capture_progress_cursor(self, role: str) -> str: ...

    def progress(self, role: str, cursor: str) -> tuple[str, ...]: ...


COLUMNS = tuple(LifecycleRecord.model_fields)
LEASE_COLUMNS = tuple(LifecycleLease.model_fields)
DECISION_COLUMNS = tuple(PersistedIdlePolicyDecision.model_fields)
FAILURE_EVENT_COLUMNS = tuple(LifecycleFailureEvent.model_fields)
AUTOMATION_COLUMNS = tuple(LifecycleAutomationStatus.model_fields)
MUTABLE_FIELDS = frozenset(COLUMNS) - {
    "role",
    "generation",
    "state",
    "transition_id",
    "transitioned_at",
    "updated_at",
    "service_unit",
}
BOOLEAN_FIELDS = {"evaluation_guard", "profile_guard"}
FAILURE_CLASS_PATTERN = re.compile(r"[^a-z0-9]+")
LIFECYCLE_COLUMN_MIGRATIONS = {
    "generation": "INTEGER NOT NULL DEFAULT 0",
    "load_started_at": "REAL",
    "ready_at": "REAL",
    "last_requested_at": "REAL",
    "last_completed_at": "REAL",
    "weight_load_percent": "REAL",
    "overall_load_percent": "REAL",
    "service_unit": "TEXT",
    "last_error_class": "TEXT",
    "last_error_message_redacted": "TEXT",
}


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
        unit_map: Mapping[str, str] | None = None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._roles = tuple(dict.fromkeys(roles))
        self._role_set = set(self._roles)
        self._clock = clock
        self._unit_map = dict(unit_map or {})
        unknown = self._role_set - MODEL_ROLES
        if unknown:
            raise UnknownRoleError(sorted(unknown)[0])
        unknown_units = set(self._unit_map) - self._role_set
        if unknown_units:
            raise UnknownRoleError(sorted(unknown_units)[0])
        if any(not SYSTEMD_UNIT_PATTERN.fullmatch(unit) for unit in self._unit_map.values()):
            raise ValueError("invalid systemd unit")
        if len(set(self._unit_map.values())) != len(self._unit_map):
            raise ValueError("duplicate lifecycle unit")
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS model_lifecycle ("
                "role TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0, "
                "state TEXT NOT NULL, transition_id TEXT NOT NULL, "
                "transitioned_at REAL NOT NULL, updated_at REAL NOT NULL, ready_since REAL, "
                "last_used_at REAL, load_started_at REAL, ready_at REAL, "
                "last_requested_at REAL, last_completed_at REAL, "
                "failure_class TEXT, failure_detail TEXT, "
                "retry_count INTEGER NOT NULL, active_request_count INTEGER NOT NULL, "
                "open_stream_count INTEGER NOT NULL, continuation_lease_count INTEGER NOT NULL, "
                "evaluation_guard INTEGER NOT NULL, profile_guard INTEGER NOT NULL, "
                "progress_value REAL, weight_load_percent REAL, overall_load_percent REAL, "
                "progress_quality TEXT, eta_seconds REAL, "
                "last_load_duration_seconds REAL, last_unload_duration_seconds REAL, "
                "memory_before_bytes INTEGER, memory_after_bytes INTEGER, service_unit TEXT, "
                "last_error_class TEXT, last_error_message_redacted TEXT)"
            )
            existing_columns = {
                row[1] for row in database.execute("PRAGMA table_info(model_lifecycle)")
            }
            for name, definition in LIFECYCLE_COLUMN_MIGRATIONS.items():
                if name not in existing_columns:
                    database.execute(f"ALTER TABLE model_lifecycle ADD COLUMN {name} {definition}")
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
            database.execute(
                "CREATE TABLE IF NOT EXISTS model_lifecycle_decisions ("
                "role TEXT PRIMARY KEY, mode TEXT NOT NULL, threshold_seconds REAL NOT NULL, "
                "threshold_source TEXT NOT NULL, sample_count INTEGER NOT NULL, "
                "idle_seconds REAL NOT NULL, residency_seconds REAL NOT NULL, "
                "next_consecutive_check_count INTEGER NOT NULL, would_unload INTEGER NOT NULL, "
                "action_allowed INTEGER NOT NULL, reason TEXT NOT NULL, decided_at REAL NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_samples ("
                "sample_id INTEGER PRIMARY KEY, role TEXT NOT NULL, kind TEXT NOT NULL, "
                "duration_seconds REAL NOT NULL, memory_before_bytes INTEGER, "
                "memory_after_bytes INTEGER)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_failure_events ("
                "event_id INTEGER PRIMARY KEY, role TEXT NOT NULL, "
                "operation_stage TEXT NOT NULL, failure_class TEXT NOT NULL, "
                "generation INTEGER NOT NULL, occurred_at REAL NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_automation ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "automation_disabled INTEGER NOT NULL, disabled_at REAL, "
                "failure_count INTEGER NOT NULL, window_started_at REAL, "
                "last_failure_at REAL, last_reset_at REAL NOT NULL, "
                "last_reset_event_id INTEGER NOT NULL DEFAULT 0)"
            )
            automation_columns = {
                row[1] for row in database.execute("PRAGMA table_info(lifecycle_automation)")
            }
            if "last_reset_event_id" not in automation_columns:
                database.execute(
                    "ALTER TABLE lifecycle_automation ADD COLUMN "
                    "last_reset_event_id INTEGER NOT NULL DEFAULT 0"
                )
            database.execute(
                "INSERT OR IGNORE INTO lifecycle_automation "
                "(singleton, automation_disabled, failure_count, last_reset_at) "
                "VALUES (1, 0, 0, 0)"
            )
            for role in self._roles:
                now = self._clock()
                record = LifecycleRecord(
                    role=role,
                    state="disabled" if unit_map is not None else "cold",
                    transition_id=str(uuid4()),
                    transitioned_at=now,
                    updated_at=now,
                    service_unit=self._unit_map.get(role),
                )
                database.execute(
                    f"INSERT OR IGNORE INTO model_lifecycle ({', '.join(COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in COLUMNS)})",
                    self._values(record),
                )
                if role in self._unit_map:
                    database.execute(
                        "UPDATE model_lifecycle SET service_unit = ? WHERE role = ?",
                        (self._unit_map[role], role),
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

    @staticmethod
    def _decision(row: sqlite3.Row) -> PersistedIdlePolicyDecision:
        values = dict(row)
        values["would_unload"] = bool(values["would_unload"])
        values["action_allowed"] = bool(values["action_allowed"])
        return PersistedIdlePolicyDecision.model_validate(values)

    def persist_decision(self, decision: IdlePolicyDecision) -> PersistedIdlePolicyDecision:
        self._require_role(decision.role)
        persisted = PersistedIdlePolicyDecision(
            **decision.model_dump(),
            decided_at=self._lease_now(),
        )
        values = persisted.model_dump()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                f"INSERT INTO model_lifecycle_decisions ({', '.join(DECISION_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in DECISION_COLUMNS)}) "
                "ON CONFLICT(role) DO UPDATE SET "
                + ", ".join(
                    f"{column} = excluded.{column}"
                    for column in DECISION_COLUMNS
                    if column != "role"
                ),
                tuple(
                    int(values[column])
                    if column in {"would_unload", "action_allowed"}
                    else values[column]
                    for column in DECISION_COLUMNS
                ),
            )
            row = database.execute(
                f"SELECT {', '.join(DECISION_COLUMNS)} FROM model_lifecycle_decisions "
                "WHERE role = ?",
                (decision.role,),
            ).fetchone()
        assert row is not None
        return self._decision(row)

    def latest_decision(self, role: str) -> PersistedIdlePolicyDecision | None:
        self._require_role(role)
        with self._connect() as database:
            row = database.execute(
                f"SELECT {', '.join(DECISION_COLUMNS)} FROM model_lifecycle_decisions "
                "WHERE role = ?",
                (role,),
            ).fetchone()
        return self._decision(row) if row is not None else None

    def latest_decisions(self) -> dict[str, PersistedIdlePolicyDecision]:
        with self._connect() as database:
            rows = database.execute(
                f"SELECT {', '.join(DECISION_COLUMNS)} FROM model_lifecycle_decisions ORDER BY role"
            ).fetchall()
        return {row["role"]: self._decision(row) for row in rows}

    @staticmethod
    def _automation(row: sqlite3.Row) -> LifecycleAutomationStatus:
        values = {column: row[column] for column in AUTOMATION_COLUMNS}
        values["automation_disabled"] = bool(values["automation_disabled"])
        return LifecycleAutomationStatus.model_validate(values)

    def automation_status(self) -> LifecycleAutomationStatus:
        with self._connect() as database:
            row = database.execute(
                f"SELECT {', '.join(AUTOMATION_COLUMNS)} FROM lifecycle_automation "
                "WHERE singleton = 1"
            ).fetchone()
        assert row is not None
        return self._automation(row)

    def record_failure(
        self,
        role: str,
        operation_stage: str,
        failure_class: str,
        generation: int,
        *,
        failure_limit: int,
        failure_window_seconds: float,
    ) -> LifecycleAutomationStatus:
        self._require_role(role)
        if (
            failure_limit < 1
            or not math.isfinite(failure_window_seconds)
            or failure_window_seconds <= 0
        ):
            raise ValueError("invalid lifecycle failure policy")
        if generation < 0:
            raise ValueError("invalid lifecycle generation")
        now = self._lease_now()
        safe_stage = _sanitize_failure_class(operation_stage)
        safe_class = _sanitize_failure_class(failure_class)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                f"SELECT {', '.join(AUTOMATION_COLUMNS)} FROM lifecycle_automation "
                "WHERE singleton = 1"
            ).fetchone()
            assert row is not None
            current = self._automation(row)
            if current.automation_disabled:
                return current
            reset_event_id = int(
                database.execute(
                    "SELECT last_reset_event_id FROM lifecycle_automation WHERE singleton = 1"
                ).fetchone()[0]
            )
            database.execute(
                "INSERT INTO lifecycle_failure_events "
                "(role, operation_stage, failure_class, generation, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (role, safe_stage, safe_class, generation, now),
            )
            window_start = max(now - failure_window_seconds, current.last_reset_at)
            aggregate = database.execute(
                "SELECT COUNT(*), MIN(occurred_at), MAX(occurred_at) "
                "FROM lifecycle_failure_events WHERE occurred_at >= ? AND event_id > ?",
                (window_start, reset_event_id),
            ).fetchone()
            assert aggregate is not None
            count = int(aggregate[0])
            disabled = count >= failure_limit
            database.execute(
                "UPDATE lifecycle_automation SET automation_disabled = ?, disabled_at = ?, "
                "failure_count = ?, window_started_at = ?, last_failure_at = ? "
                "WHERE singleton = 1",
                (
                    int(disabled),
                    now if disabled else None,
                    count,
                    aggregate[1],
                    aggregate[2],
                ),
            )
            updated = database.execute(
                f"SELECT {', '.join(AUTOMATION_COLUMNS)} FROM lifecycle_automation "
                "WHERE singleton = 1"
            ).fetchone()
        assert updated is not None
        return self._automation(updated)

    def recent_failure_events(self, limit: int = 100) -> tuple[LifecycleFailureEvent, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("failure event limit must be between 1 and 1000")
        with self._connect() as database:
            rows = database.execute(
                f"SELECT {', '.join(FAILURE_EVENT_COLUMNS)} FROM lifecycle_failure_events "
                "ORDER BY event_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(LifecycleFailureEvent.model_validate(dict(row)) for row in reversed(rows))

    def reset_automation(self) -> LifecycleAutomationStatus:
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "UPDATE lifecycle_automation SET automation_disabled = 0, disabled_at = NULL, "
                "failure_count = 0, window_started_at = NULL, last_failure_at = NULL, "
                "last_reset_at = ?, last_reset_event_id = "
                "COALESCE((SELECT MAX(event_id) FROM lifecycle_failure_events), 0) "
                "WHERE singleton = 1",
                (now,),
            )
            row = database.execute(
                f"SELECT {', '.join(AUTOMATION_COLUMNS)} FROM lifecycle_automation "
                "WHERE singleton = 1"
            ).fetchone()
        assert row is not None
        return self._automation(row)

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
        require_ready: bool = False,
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
            first_request_roles = {
                role
                for role in requested_roles
                if kind in {"active_request", "open_stream"}
                and database.execute(
                    "SELECT COUNT(*) FROM model_lifecycle_leases "
                    "WHERE role = ? AND kind IN ('active_request', 'open_stream')",
                    (role,),
                ).fetchone()[0]
                == 0
            }
            if require_ready:
                for role in requested_roles:
                    record = self._read(database, role)
                    if record.state != "ready":
                        raise LifecycleNotReadyError(record)
            for lease in leases:
                database.execute(
                    f"INSERT OR IGNORE INTO model_lifecycle_leases "
                    f"({', '.join(LEASE_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in LEASE_COLUMNS)})",
                    self._lease_values(lease),
                )
            self._sync_lease_counts(database, requested_roles, now)
            for role in first_request_roles:
                database.execute(
                    "UPDATE model_lifecycle SET last_requested_at = ?, updated_at = ? "
                    "WHERE role = ?",
                    (now, now, role),
                )
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

    def claim_guards(
        self,
        roles: Iterable[str],
        guard: GuardKind,
    ) -> dict[str, str]:
        requested_roles = tuple(dict.fromkeys(roles))
        for role in requested_roles:
            self._require_role(role)
        if guard not in BOOLEAN_FIELDS:
            raise ValueError("invalid lifecycle guard")
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            records = {role: self._read(database, role) for role in requested_roles}
            if any(getattr(record, guard) for record in records.values()):
                raise LifecycleError(f"{guard} is already active")
            for record in records.values():
                self._write(database, self._updated_record(record, {guard: True}, now))
            return {role: record.transition_id for role, record in records.items()}

    def release_guards(
        self,
        ownership: Mapping[str, str],
        guard: GuardKind,
    ) -> None:
        for role in ownership:
            self._require_role(role)
        if guard not in BOOLEAN_FIELDS:
            raise ValueError("invalid lifecycle guard")
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            for role, transition_id in ownership.items():
                record = self._read(database, role)
                if record.transition_id != transition_id or not getattr(record, guard):
                    continue
                self._write(database, self._updated_record(record, {guard: False}, now))

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

    def admit_unload(
        self,
        role: str,
        *,
        expected_transition_id: str,
        memory_before_bytes: int,
        expected_ready_since: float | None = None,
        expected_last_used_at: float | None = None,
    ) -> LifecycleRecord | None:
        self._require_role(role)
        if (
            not isinstance(memory_before_bytes, int)
            or isinstance(memory_before_bytes, bool)
            or not 0 <= memory_before_bytes <= 2**63 - 1
        ):
            raise ValueError("memory sample must be a nonnegative integer")
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            _, expired_roles = self._prune_expired_continuations(database, now)
            self._sync_lease_counts(database, (*expired_roles, role), now)
            current = self._read(database, role)
            if (
                current.state not in {"ready", "unload_queued"}
                or current.transition_id != expected_transition_id
                or (
                    expected_ready_since is not None and current.ready_since != expected_ready_since
                )
                or current.last_used_at != expected_last_used_at
                or current.active_request_count
                or current.open_stream_count
                or current.continuation_lease_count
                or current.evaluation_guard
                or current.profile_guard
            ):
                return None
            values = self._updated_record(
                current,
                {"memory_before_bytes": memory_before_bytes},
                now,
            ).model_dump()
            values.update(
                state="unloading",
                transition_id=str(uuid4()),
                transitioned_at=now,
                updated_at=now,
                failure_class=None,
                failure_detail=None,
            )
            admitted = LifecycleRecord.model_validate(values)
            self._write(database, admitted)
            return admitted

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
            owned = tuple(
                database.execute(
                    f"SELECT DISTINCT role, kind FROM model_lifecycle_leases "
                    f"WHERE lease_id IN ({placeholders})",
                    requested,
                )
            )
            roles = tuple(dict.fromkeys(row[0] for row in owned))
            database.execute(
                f"DELETE FROM model_lifecycle_leases WHERE lease_id IN ({placeholders})",
                requested,
            )
            self._sync_lease_counts(database, roles, now)
            request_roles = dict.fromkeys(
                row[0] for row in owned if row[1] in {"active_request", "open_stream"}
            )
            for role in request_roles:
                remaining = database.execute(
                    "SELECT active_request_count, open_stream_count "
                    "FROM model_lifecycle WHERE role = ?",
                    (role,),
                ).fetchone()
                assert remaining is not None
                if remaining[0] == 0 and remaining[1] == 0:
                    database.execute(
                        "UPDATE model_lifecycle SET last_used_at = ?, last_completed_at = ?, "
                        "updated_at = ? WHERE role = ?",
                        (now, now, now, role),
                    )

    def _updated_record(
        self, current: LifecycleRecord, changes: Mapping[str, Any], now: float
    ) -> LifecycleRecord:
        unknown = set(changes) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"immutable lifecycle fields: {sorted(unknown)}")
        values = current.model_dump()
        values.update(changes)
        if "progress_value" in changes and "weight_load_percent" not in changes:
            values["weight_load_percent"] = changes["progress_value"]
        if "progress_value" in changes or "weight_load_percent" in changes:
            weight_progress = values["weight_load_percent"]
            if weight_progress is not None and current.weight_load_percent is not None:
                weight_progress = max(current.weight_load_percent, float(weight_progress))
            values["progress_value"] = weight_progress
            values["weight_load_percent"] = weight_progress
        if (
            "overall_load_percent" in changes
            and changes["overall_load_percent"] is not None
            and current.overall_load_percent is not None
        ):
            values["overall_load_percent"] = max(
                current.overall_load_percent,
                float(changes["overall_load_percent"]),
            )
        if values.get("failure_class") is not None:
            values["failure_class"] = _sanitize_failure_class(str(values["failure_class"]))
        if values.get("failure_detail") is not None:
            values["failure_detail"] = _sanitize_failure_detail(str(values["failure_detail"]))
        if "failure_class" in changes and "last_error_class" not in changes:
            values["last_error_class"] = values["failure_class"]
        if "failure_detail" in changes and "last_error_message_redacted" not in changes:
            values["last_error_message_redacted"] = values["failure_detail"]
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
            if state == "load_queued" and current.state in {"cold", "failed"}:
                values.update(
                    generation=current.generation + 1,
                    load_started_at=None,
                    ready_at=None,
                    progress_value=None,
                    weight_load_percent=None,
                    overall_load_percent=0.0,
                    progress_quality="unavailable",
                    eta_seconds=None,
                )
            elif state == "process_starting":
                values.update(load_started_at=now, overall_load_percent=5.0)
            elif state == "initializing_engine":
                values["overall_load_percent"] = 70.0
            elif state == "warming_up":
                values["overall_load_percent"] = 90.0
            if state == "ready":
                values.update(
                    ready_since=current.ready_since if current.state == "unload_queued" else now,
                    ready_at=current.ready_at if current.state == "unload_queued" else now,
                    weight_load_percent=100.0,
                    overall_load_percent=100.0,
                )
            elif state in {"cold", "disabled"}:
                values.update(
                    ready_since=None,
                    ready_at=None,
                    load_started_at=None,
                    failure_class=None,
                    failure_detail=None,
                    progress_value=None,
                    weight_load_percent=None,
                    overall_load_percent=None,
                    progress_quality=None,
                    eta_seconds=None,
                )
            elif state != "failed":
                values["failure_class"] = None
                values["failure_detail"] = None
            transitioned = LifecycleRecord.model_validate(values)
            self._write(database, transitioned)
            if state == "ready" and transitioned.last_load_duration_seconds is not None:
                database.execute(
                    "INSERT INTO lifecycle_samples "
                    "(role, kind, duration_seconds, memory_before_bytes, memory_after_bytes) "
                    "VALUES (?, 'load', ?, ?, ?)",
                    (
                        role,
                        transitioned.last_load_duration_seconds,
                        transitioned.memory_before_bytes,
                        transitioned.memory_after_bytes,
                    ),
                )
            return transitioned

    def queue_unload(
        self,
        role: str,
        *,
        expected_transition_id: str,
    ) -> LifecycleRecord:
        return self.transition(
            role,
            "unload_queued",
            expected_transition_id=expected_transition_id,
        )

    def cancel_queued_unload(
        self,
        role: str,
        *,
        expected_transition_id: str,
    ) -> LifecycleRecord:
        return self.transition(
            role,
            "ready",
            expected_transition_id=expected_transition_id,
        )

    def disable_all(self) -> dict[str, LifecycleRecord]:
        disabled: dict[str, LifecycleRecord] = {}
        for role in self._roles:
            current = self.get(role)
            if current.state == "disabled":
                disabled[role] = current
                continue
            disabled[role] = self.transition(
                role,
                "disabled",
                expected_transition_id=current.transition_id,
            )
        return disabled

    def complete_unload(
        self,
        role: str,
        *,
        expected_transition_id: str,
        duration_seconds: float,
        memory_before_bytes: int | None,
        memory_after_bytes: int | None,
    ) -> LifecycleRecord:
        self._require_role(role)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            if current.transition_id != expected_transition_id:
                raise StaleTransitionError(role)
            if current.state != "unloading":
                raise InvalidTransitionError(f"{current.state} -> cold")
            now = self._clock()
            updated = self._updated_record(
                current,
                {
                    "last_unload_duration_seconds": duration_seconds,
                    "memory_before_bytes": memory_before_bytes,
                    "memory_after_bytes": memory_after_bytes,
                },
                now,
            )
            values = updated.model_dump()
            values.update(
                state="cold",
                transition_id=str(uuid4()),
                transitioned_at=now,
                updated_at=now,
                ready_since=None,
                ready_at=None,
                load_started_at=None,
                failure_class=None,
                failure_detail=None,
                progress_value=None,
                weight_load_percent=None,
                overall_load_percent=None,
                progress_quality=None,
                eta_seconds=None,
            )
            cold = LifecycleRecord.model_validate(values)
            self._write(database, cold)
            database.execute(
                "INSERT INTO lifecycle_samples "
                "(role, kind, duration_seconds, memory_before_bytes, memory_after_bytes) "
                "VALUES (?, 'unload', ?, ?, ?)",
                (
                    role,
                    cold.last_unload_duration_seconds,
                    cold.memory_before_bytes,
                    cold.memory_after_bytes,
                ),
            )
            return cold

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
                ready_at=None,
                load_started_at=(
                    now
                    if state == "process_starting"
                    else current.load_started_at
                    if state == "failed"
                    else None
                ),
                progress_value=None,
                weight_load_percent=None,
                overall_load_percent=5.0 if state == "process_starting" else None,
                progress_quality=None,
                eta_seconds=None,
                failure_class="service_failed" if state == "failed" else None,
                failure_detail=None,
                last_error_class=(
                    "service_failed" if state == "failed" else current.last_error_class
                ),
                last_error_message_redacted=current.last_error_message_redacted,
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

    def recover_state(
        self,
        role: str,
        state: Literal["cold", "ready", "failed"],
        *,
        failure_class: str | None = None,
    ) -> LifecycleRecord:
        self._require_role(role)
        now = self._lease_now()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            current = self._read(database, role)
            values = current.model_dump()
            values.update(
                state=state,
                transition_id=(current.transition_id if current.state == state else str(uuid4())),
                transitioned_at=(current.transitioned_at if current.state == state else now),
                updated_at=now,
                ready_since=(
                    current.ready_since
                    if state == "ready" and current.state == "ready"
                    else now
                    if state == "ready"
                    else None
                ),
                ready_at=(
                    current.ready_at
                    if state == "ready" and current.state == "ready"
                    else now
                    if state == "ready"
                    else None
                ),
                load_started_at=current.load_started_at if state == "failed" else None,
                failure_class=(failure_class or "service_failed") if state == "failed" else None,
                failure_detail=None,
                last_error_class=(
                    failure_class or "service_failed"
                    if state == "failed"
                    else current.last_error_class
                ),
                last_error_message_redacted=current.last_error_message_redacted,
                progress_value=None,
                weight_load_percent=100.0 if state == "ready" else None,
                overall_load_percent=100.0 if state == "ready" else None,
                progress_quality=None,
                eta_seconds=None,
            )
            if state in {"cold", "ready"}:
                values["retry_count"] = 0
            recovered = LifecycleRecord.model_validate(values)
            self._write(database, recovered)
            return recovered


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
        memory_probe: Callable[[], int] | None = None,
        lifecycle_policy: LifecyclePolicy | None = None,
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
        self.memory_probe = memory_probe or self._memory_unavailable
        self.lifecycle_policy = lifecycle_policy or LifecyclePolicy()
        self._mutation_disabled = False
        self._locks = {role: asyncio.Lock() for role in store._roles}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._load_driver_tasks: set[asyncio.Task[Any]] = set()
        self._scheduler_task: asyncio.Task[None] | None = None
        self._stop_tasks: dict[str, asyncio.Task[None]] = {}
        self._idle_state: dict[str, tuple[LifecycleMode, float | None, int]] = {}

    def _automation_disabled(self) -> bool:
        return self._mutation_disabled or self.store.automation_status().automation_disabled

    def _record_failure(self, role: str, operation_stage: str, failure_class: str) -> None:
        record = self.store.get(role)
        try:
            self.store.record_failure(
                role,
                operation_stage,
                failure_class,
                record.generation,
                failure_limit=self.lifecycle_policy.failure_limit,
                failure_window_seconds=self.lifecycle_policy.failure_window_seconds,
            )
        except Exception:
            self._mutation_disabled = True

    @staticmethod
    def _memory_unavailable() -> int:
        raise LifecycleError("memory probe unavailable")

    @staticmethod
    def _activity_at(record: LifecycleRecord) -> float | None:
        if record.state != "ready" or record.ready_since is None:
            return None
        return max(record.ready_since, record.last_used_at or record.ready_since)

    @staticmethod
    def _ordered_roles(roles: Iterable[str]) -> tuple[str, ...]:
        unique = tuple(dict.fromkeys(roles))
        return tuple(sorted(role for role in unique if role != "executor")) + (
            ("executor",) if "executor" in unique else ()
        )

    def start_scheduler(
        self,
        mode: LifecycleMode,
        roles: Iterable[str],
        policy_config: Limits | LifecyclePolicy,
        usage: UsageStore,
    ) -> asyncio.Task[None] | None:
        if mode == "disabled":
            return None
        if mode not in {"observe", "fixed", "adaptive"}:
            raise ValueError("invalid lifecycle scheduler mode")
        managed_roles = self._ordered_roles(roles)
        if any(role not in self._locks for role in managed_roles):
            raise UnknownRoleError(next(role for role in managed_roles if role not in self._locks))
        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(
                self._run_scheduler(mode, managed_roles, policy_config, usage)
            )
        return self._scheduler_task

    async def _run_scheduler(
        self,
        mode: LifecycleMode,
        roles: tuple[str, ...],
        policy_config: Limits | LifecyclePolicy,
        usage: UsageStore,
    ) -> None:
        while True:
            await self.sleeper(self.poll_seconds)
            await self.run_scheduler_check(mode, roles, policy_config, usage)
            await asyncio.sleep(0)

    async def run_scheduler_check(
        self,
        mode: LifecycleMode,
        roles: Iterable[str],
        policy_config: Limits | LifecyclePolicy,
        usage: UsageStore,
    ) -> None:
        legacy_records = usage.recent_requests() if isinstance(policy_config, Limits) else None
        now = float(self.clock())
        if not math.isfinite(now) or now < 0:
            raise ValueError("scheduler clock must be finite and nonnegative")
        for role in self._ordered_roles(roles):
            try:
                if isinstance(policy_config, LifecyclePolicy):
                    records: Sequence[RoleUsageRecord] = cast(
                        Sequence[RoleUsageRecord],
                        usage.recent_role_requests(
                            role,
                            success=True,
                            limit=policy_config.recent_sample_window,
                        ),
                    )
                    policy_arguments: dict[str, Any] = {
                        "policy": policy_config.roles[role],
                        "lifecycle": policy_config,
                    }
                else:
                    records = cast(Sequence[RoleUsageRecord], legacy_records)
                    policy_arguments = {"limits": policy_config}
                record = self.store.get(role)
                previous_mode, previous_activity, previous_count = self._idle_state.get(
                    role, (None, None, 0)
                )
                blockers = bool(self.store.unload_blockers(role))
                decision = calculate_idle_policy(
                    cast(ModelRole, role),
                    mode,
                    records,
                    record,
                    now=now,
                    **policy_arguments,
                    has_blockers=blockers,
                    previous_mode=previous_mode,
                    previous_last_activity_at=previous_activity,
                    previous_consecutive_check_count=previous_count,
                )
                self.store.persist_decision(decision)
                activity = self._activity_at(record)
                self._idle_state[role] = (
                    mode,
                    activity,
                    decision.next_consecutive_check_count,
                )
                if decision.would_unload and decision.action_allowed:
                    try:
                        await self._unload_role(role, record)
                    except asyncio.CancelledError:
                        self._idle_state[role] = (mode, None, 0)
                        try:
                            current = self.store.get(role)
                            reset_decision = calculate_idle_policy(
                                cast(ModelRole, role),
                                mode,
                                records,
                                current,
                                now=now,
                                **policy_arguments,
                                has_blockers=bool(self.store.unload_blockers(role)),
                                previous_mode=mode,
                                previous_last_activity_at=None,
                                previous_consecutive_check_count=(
                                    decision.next_consecutive_check_count
                                ),
                            )
                            self.store.persist_decision(reset_decision)
                        except Exception:
                            pass
                        raise
                    else:
                        current = self.store.get(role)
                        safe_decision = calculate_idle_policy(
                            cast(ModelRole, role),
                            mode,
                            records,
                            current,
                            now=now,
                            **policy_arguments,
                            has_blockers=bool(self.store.unload_blockers(role)),
                            previous_mode=mode,
                            previous_last_activity_at=activity,
                            previous_consecutive_check_count=decision.next_consecutive_check_count,
                        )
                        self.store.persist_decision(safe_decision)
                        self._idle_state[role] = (
                            mode,
                            self._activity_at(current),
                            safe_decision.next_consecutive_check_count,
                        )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._idle_state[role] = (mode, None, 0)
                self._record_failure(role, "adaptive_decision", type(error).__name__)

    def _memory_sample(self) -> int:
        value = self.memory_probe()
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2**63 - 1:
            raise ValueError("memory sample must be a nonnegative integer")
        return value

    async def _unload_role(
        self,
        role: str,
        policy_record: LifecycleRecord,
    ) -> bool:
        async with self._locks[role]:
            if self._automation_disabled():
                return False
            try:
                queued = self.store.queue_unload(
                    role,
                    expected_transition_id=policy_record.transition_id,
                )
            except (InvalidTransitionError, StaleTransitionError):
                return False
            try:
                memory_before = await asyncio.to_thread(self._memory_sample)
            except Exception as error:
                self._fail_unload(role, "memory_before_failed", type(error).__name__)
                return False
            admitted = self.store.admit_unload(
                role,
                expected_transition_id=queued.transition_id,
                expected_ready_since=policy_record.ready_since,
                expected_last_used_at=policy_record.last_used_at,
                memory_before_bytes=memory_before,
            )
            if admitted is None:
                current = self.store.get(role)
                if current.state == "unload_queued":
                    self.store.cancel_queued_unload(
                        role,
                        expected_transition_id=current.transition_id,
                    )
                return False
            task = asyncio.create_task(self._complete_unload(role, admitted))
            self._stop_tasks[role] = task
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
            finally:
                self._stop_tasks.pop(role, None)
            return self.store.get(role).state == "cold"

    async def _complete_unload(
        self,
        role: str,
        admitted: LifecycleRecord,
    ) -> None:
        started = float(self.clock())
        try:
            if self._automation_disabled():
                self.store.recover_state(role, "ready")
                return
            await asyncio.to_thread(self.driver.stop, role)
            driver_status = await asyncio.to_thread(self.driver.status, role)
            if driver_status != "inactive":
                raise LifecycleLoadError(
                    f"service_{driver_status}", "service did not become inactive"
                )
            try:
                memory_after = await asyncio.to_thread(self._memory_sample)
            except Exception as error:
                raise LifecycleLoadError("memory_after_failed", type(error).__name__) from None
            duration = max(0.0, float(self.clock()) - started)
            self.store.complete_unload(
                role,
                expected_transition_id=admitted.transition_id,
                duration_seconds=duration,
                memory_before_bytes=admitted.memory_before_bytes,
                memory_after_bytes=memory_after,
            )
        except LifecycleLoadError as error:
            self._fail_unload(role, error.failure_class, error.failure_detail)
        except LifecycleDriverError as error:
            self._fail_unload(role, f"{error.operation}_{error.kind}", "lifecycle driver failed")
        except Exception as error:
            self._fail_unload(role, "unload_failed", type(error).__name__)

    def _fail_unload(self, role: str, failure_class: str, failure_detail: str) -> None:
        record = self.store.get(role)
        if record.state == "failed":
            return
        if "failed" not in TRANSITIONS[record.state]:
            return
        self.store.transition(
            role,
            "failed",
            expected_transition_id=record.transition_id,
            failure_class=failure_class,
            failure_detail=failure_detail,
        )
        self._record_failure(role, f"unload_{failure_class}", failure_class)

    async def acquire_request_leases(
        self,
        request_id: str,
        roles: Iterable[str],
        *,
        kind: RequestLeaseKind,
        require_ready: bool,
    ) -> tuple[LifecycleLease, ...]:
        requested_roles = tuple(dict.fromkeys(roles))
        try:
            locks = tuple(self._locks[role] for role in sorted(requested_roles))
        except KeyError as error:
            raise UnknownRoleError(str(error.args[0])) from error
        async with AsyncExitStack() as stack:
            for lock in locks:
                await stack.enter_async_context(lock)
            return self.store.acquire_request_leases(
                request_id,
                requested_roles,
                kind=kind,
                require_ready=require_ready,
            )

    async def reconcile_managed(
        self,
        roles: Iterable[str],
    ) -> dict[str, LifecycleRecord]:
        recovered: dict[str, LifecycleRecord] = {}
        for role in self._ordered_roles(roles):
            try:
                lock = self._locks[role]
            except KeyError as error:
                raise UnknownRoleError(role) from error
            async with lock:
                try:
                    driver_status = await asyncio.to_thread(self.driver.status, role)
                except Exception:
                    recovered[role] = self.store.recover_state(
                        role,
                        "failed",
                        failure_class="recovery_status_failed",
                    )
                    continue
                if driver_status == "inactive":
                    recovered[role] = self.store.recover_state(role, "cold")
                    continue
                if driver_status == "failed":
                    recovered[role] = self.store.recover_state(
                        role,
                        "failed",
                        failure_class="service_failed",
                    )
                    continue
                try:
                    async with asyncio.timeout(self.timeout_seconds):
                        healthy = await self.health_probe(role)
                except Exception:
                    healthy = False
                recovered[role] = self.store.recover_state(
                    role,
                    "ready" if healthy else "failed",
                    failure_class=None if healthy else "recovery_unhealthy",
                )
        return recovered

    async def release_request_leases(self, lease_ids: Iterable[str]) -> None:
        self.store.release_leases(lease_ids)

    async def claim_guards(
        self,
        roles: Iterable[str],
        guard: GuardKind,
    ) -> dict[str, str]:
        requested_roles = self._ordered_roles(roles)
        try:
            locks = tuple(self._locks[role] for role in sorted(requested_roles))
        except KeyError as error:
            raise UnknownRoleError(str(error.args[0])) from error
        ownership: dict[str, str] = {}
        async with AsyncExitStack() as stack:
            for lock in locks:
                await stack.enter_async_context(lock)
            ownership = self.store.claim_guards(requested_roles, guard)
        return ownership

    async def release_guards(
        self,
        ownership: Mapping[str, str],
        guard: GuardKind,
    ) -> None:
        requested_roles = self._ordered_roles(ownership)
        locks = tuple(self._locks[role] for role in sorted(requested_roles))
        async with AsyncExitStack() as stack:
            for lock in locks:
                await stack.enter_async_context(lock)
            self.store.release_guards(ownership, guard)

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
            if record.state == "unload_queued":
                record = self.store.cancel_queued_unload(
                    role, expected_transition_id=record.transition_id
                )
            if record.state == "ready" or task is not None:
                return LoadCheck(record=record)
            if self._automation_disabled():
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
            self._fail(role, "load_cancelled", "model load cancelled during shutdown")
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
        cursor = await self._owned_load_driver_call(self.driver.capture_progress_cursor, role)
        if self._automation_disabled():
            self.store.recover_state(role, "cold")
            return
        await self._owned_load_driver_call(self.driver.start, role)
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
            try:
                progress = parse_load_progress(
                    lines,
                    previous_percent=record.progress_value,
                    previous_quality=record.progress_quality,
                )
            except Exception:
                progress = LoadProgress(
                    state="loading_weights",
                    weight_load_percent=record.progress_value,
                    progress_quality=record.progress_quality or "unavailable",
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
                    overall_load_percent=(
                        5.0 + 0.60 * progress.weight_load_percent
                        if progress.weight_load_percent is not None
                        else record.overall_load_percent
                    ),
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
                    and record.progress_quality
                    in {"measured_bytes", "measured_shards", "measured_phase"}
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

    async def _owned_load_driver_call(self, operation: Callable[[str], T], role: str) -> T:
        task = asyncio.create_task(asyncio.to_thread(operation, role))
        self._load_driver_tasks.add(task)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            self._load_driver_tasks.discard(task)

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
        self._record_failure(role, f"load_{failure_class}", failure_class)

    async def close(self) -> None:
        scheduler = self._scheduler_task
        if scheduler is not None:
            scheduler.cancel()
            await asyncio.gather(scheduler, return_exceptions=True)
            self._scheduler_task = None
        stop_tasks = tuple(self._stop_tasks.values())
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        self._stop_tasks.clear()
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        load_driver_tasks = tuple(self._load_driver_tasks)
        if load_driver_tasks:
            await asyncio.gather(*load_driver_tasks, return_exceptions=True)
        self._load_driver_tasks.clear()


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
        if output.splitlines() == ["-- No entries --"]:
            output = self._run(
                "cursor",
                ["journalctl", "--user", "--no-pager", "-n", "0", "--show-cursor"],
            )
        lines = output.splitlines()
        prefix = "-- cursor: "
        cursor_lines = [line for line in lines if line.startswith(prefix)]
        other_lines = [line for line in lines if not line.startswith(prefix)]
        if len(cursor_lines) != 1 or any(line != "-- No entries --" for line in other_lines):
            raise LifecycleDriverError("cursor", "malformed_output")
        cursor = cursor_lines[0][len(prefix) :]
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
