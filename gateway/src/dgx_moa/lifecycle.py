from __future__ import annotations

import asyncio
import math
import re
import sqlite3
import subprocess
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

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
DriverOperation = Literal["status", "start", "stop", "cursor", "progress"]
DriverErrorKind = Literal["timeout", "command_failed", "malformed_output"]
ProgressQuality = Literal["measured_bytes", "measured_shards", "estimated", "unavailable"]

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


class LoadProgress(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    state: Literal["loading_weights", "initializing_engine", "warming_up"]
    weight_load_percent: float | None = Field(default=None, ge=0, le=100)
    progress_quality: ProgressQuality


class LoadCheck(BaseModel):
    record: LifecycleRecord
    load_triggered: bool = False


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

    if stage != "loading_weights":
        return LoadProgress(
            state=stage,
            weight_load_percent=100.0,
            progress_quality="estimated",
        )
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


class LifecycleDriver(Protocol):
    def status(self, role: str) -> DriverStatus: ...

    def start(self, role: str) -> None: ...

    def stop(self, role: str) -> None: ...

    def capture_progress_cursor(self, role: str) -> str: ...

    def progress(self, role: str, cursor: str) -> tuple[str, ...]: ...


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
                return LoadCheck(record=self.store.get(role))
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
