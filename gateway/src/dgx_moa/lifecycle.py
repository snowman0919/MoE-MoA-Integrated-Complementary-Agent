from __future__ import annotations

import re
import sqlite3
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import MODEL_ROLES, SYSTEMD_UNIT_PATTERN

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
DriverOperation = Literal["status", "start", "stop", "progress"]
DriverErrorKind = Literal["timeout", "command_failed", "malformed_output"]
ProgressQuality = Literal["measured_bytes", "measured_shards", "estimated"]

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


class LifecycleDriver(Protocol):
    def status(self, role: str) -> DriverStatus: ...

    def start(self, role: str) -> None: ...

    def stop(self, role: str) -> None: ...

    def progress(self, role: str) -> tuple[str, ...]: ...


COLUMNS = tuple(LifecycleRecord.model_fields)
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


class FakeLifecycleDriver:
    def __init__(
        self,
        statuses: Mapping[str, DriverStatus],
        *,
        progress: Mapping[str, tuple[str, ...]] | None = None,
    ):
        self._statuses = dict(statuses)
        self._progress = dict(progress or {})
        self.calls: list[tuple[DriverOperation, str]] = []

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

    def progress(self, role: str) -> tuple[str, ...]:
        self._require_role(role)
        self.calls.append(("progress", role))
        return self._progress.get(role, ())


class SystemdLifecycleDriver:
    def __init__(
        self,
        unit_map: Mapping[str, str],
        *,
        timeout_seconds: float = 10.0,
        journal_lines: int = 200,
    ):
        if timeout_seconds <= 0:
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
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise LifecycleDriverError(operation, "timeout") from error
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
        self._run("start", ["systemctl", "--user", "start", self._unit(role)])

    def stop(self, role: str) -> None:
        self._run("stop", ["systemctl", "--user", "stop", self._unit(role)])

    def progress(self, role: str) -> tuple[str, ...]:
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
                "--output=cat",
            ],
        )
        return tuple(output.splitlines()[-self._journal_lines :])
