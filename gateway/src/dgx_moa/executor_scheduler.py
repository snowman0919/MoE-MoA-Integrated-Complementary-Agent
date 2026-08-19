"""API-key-fair admission for the single local Executor."""

from __future__ import annotations

import asyncio
import re
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

ExecutorSelection = Literal["local_primary", "remote_overflow"]
LeaseState = Literal["acquired", "queued", "overflow"]
Risk = Literal["low", "medium", "high", "critical"]


class ExecutorSchedulingError(RuntimeError):
    pass


class ExecutorQueueFull(ExecutorSchedulingError):
    pass


class ExecutorQueueTimeout(ExecutorSchedulingError):
    pass


@dataclass(frozen=True)
class ExecutorAdmission:
    request_id: str
    api_key_id: str
    selected_executor: ExecutorSelection
    lease_owner_api_key_id: str | None
    acquired_at: str | None
    lease_state: LeaseState
    queue_position: int
    round_robin_epoch: int
    reason: str


@dataclass(frozen=True)
class _Queued:
    request_id: str
    api_key_id: str
    future: asyncio.Future[ExecutorAdmission]
    sequence: int


class ExecutorScheduler:
    """Pin each turn to one local or remote Executor at admission."""

    def __init__(
        self,
        *,
        same_key_max_local_queue: int = 3,
        max_total_local_queue: int = 256,
        queue_timeout_seconds: float = 14_400,
    ) -> None:
        if same_key_max_local_queue < 1 or max_total_local_queue < 1:
            raise ValueError("Executor queue limits must be positive")
        if queue_timeout_seconds <= 0:
            raise ValueError("Executor queue timeout must be positive")
        self.same_key_max_local_queue = same_key_max_local_queue
        self.max_total_local_queue = max_total_local_queue
        self.queue_timeout_seconds = queue_timeout_seconds
        self._lock = threading.Lock()
        self._owner: ExecutorAdmission | None = None
        self._queues: dict[str, deque[_Queued]] = {}
        self._round_robin: deque[str] = deque()
        self._pins: dict[str, ExecutorAdmission] = {}
        self._sequence = 0
        self._epoch = 0
        self._local_enabled = True

    def set_local_enabled(self, enabled: bool) -> None:
        """Gate new local pins without disturbing requests already pinned locally."""
        with self._lock:
            self._local_enabled = enabled

    @staticmethod
    def _validate(api_key_id: str, request_id: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", api_key_id):
            raise ValueError("invalid API key ID")
        if not request_id or len(request_id) > 256:
            raise ValueError("invalid request ID")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _queue_position(self, request_id: str) -> int:
        waiting = sorted(
            (entry for queue in self._queues.values() for entry in queue),
            key=lambda entry: entry.sequence,
        )
        return next(
            (index for index, entry in enumerate(waiting, 1) if entry.request_id == request_id),
            0,
        )

    def _current_pin(self, request_id: str) -> ExecutorAdmission | None:
        pin = self._pins.get(request_id)
        if pin is None or pin.lease_state != "queued":
            return pin
        return replace(
            pin,
            lease_owner_api_key_id=(self._owner.api_key_id if self._owner else None),
            queue_position=self._queue_position(request_id),
            round_robin_epoch=self._epoch,
        )

    def pinned(self, request_id: str) -> ExecutorAdmission | None:
        with self._lock:
            return self._current_pin(request_id)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "owner_api_key_id": self._owner.api_key_id if self._owner else None,
                "owner_request_id": self._owner.request_id if self._owner else None,
                "acquired_at": self._owner.acquired_at if self._owner else None,
                "lease_state": self._owner.lease_state if self._owner else "idle",
                "queued": sum(len(queue) for queue in self._queues.values()),
                "round_robin_epoch": self._epoch,
            }

    async def acquire(
        self,
        api_key_id: str,
        request_id: str,
        *,
        risk: Risk = "low",
        flash_available: bool,
        local_available: bool = True,
        on_queued: Callable[[ExecutorAdmission], None] | None = None,
    ) -> ExecutorAdmission:
        self._validate(api_key_id, request_id)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ExecutorAdmission] | None = None
        with self._lock:
            existing = self._current_pin(request_id)
            if existing is not None:
                if existing.api_key_id != api_key_id:
                    raise ExecutorSchedulingError("request ID already belongs to another API key")
                if existing.lease_state == "queued":
                    raise ExecutorSchedulingError("request is already queued")
                return existing
            local_available = local_available and self._local_enabled
            high_risk = risk in {"high", "critical"}
            if not local_available:
                if not flash_available:
                    raise ExecutorQueueFull("local Executor is unavailable")
                admission = ExecutorAdmission(
                    request_id,
                    api_key_id,
                    "remote_overflow",
                    self._owner.api_key_id if self._owner else None,
                    self._now(),
                    "overflow",
                    0,
                    self._epoch,
                    "local_unavailable",
                )
                self._pins[request_id] = admission
                return admission
            if self._owner is None and not self._queues:
                self._epoch += 1
                admission = ExecutorAdmission(
                    request_id,
                    api_key_id,
                    "local_primary",
                    api_key_id,
                    self._now(),
                    "acquired",
                    0,
                    self._epoch,
                    "local_idle",
                )
                self._owner = admission
                self._pins[request_id] = admission
                return admission

            owner_key = self._owner.api_key_id if self._owner else None
            same_key = owner_key == api_key_id
            key_queue = self._queues.get(api_key_id)
            key_depth = len(key_queue) if key_queue else 0
            if (
                not high_risk
                and flash_available
                and (not same_key or key_depth >= self.same_key_max_local_queue)
            ):
                admission = ExecutorAdmission(
                    request_id,
                    api_key_id,
                    "remote_overflow",
                    owner_key,
                    self._now(),
                    "overflow",
                    0,
                    self._epoch,
                    "cross_key_overflow" if not same_key else "same_key_queue_limit",
                )
                self._pins[request_id] = admission
                return admission
            total_depth = sum(len(queue) for queue in self._queues.values())
            if (
                key_depth >= self.same_key_max_local_queue
                or total_depth >= self.max_total_local_queue
            ):
                raise ExecutorQueueFull(
                    "high-risk Executor queue is full"
                    if high_risk
                    else "local Executor queue is full and Flash is unavailable"
                )
            future = loop.create_future()
            self._sequence += 1
            entry = _Queued(request_id, api_key_id, future, self._sequence)
            if key_queue is None:
                key_queue = self._queues[api_key_id] = deque()
                self._round_robin.append(api_key_id)
            key_queue.append(entry)
            queued = ExecutorAdmission(
                request_id,
                api_key_id,
                "local_primary",
                owner_key,
                None,
                "queued",
                self._queue_position(request_id),
                self._epoch,
                "high_risk_local_only" if high_risk else "same_key_local_queue",
            )
            self._pins[request_id] = queued
        assert future is not None
        if on_queued is not None:
            on_queued(queued)
        try:
            return await asyncio.wait_for(
                asyncio.shield(future), timeout=self.queue_timeout_seconds
            )
        except TimeoutError as error:
            self.release(request_id)
            raise ExecutorQueueTimeout("local Executor queue timed out") from error
        except asyncio.CancelledError:
            self.release(request_id)
            raise

    def _promote(
        self, last_key: str
    ) -> tuple[asyncio.Future[ExecutorAdmission], ExecutorAdmission] | None:
        if not self._round_robin:
            return None
        if len(self._round_robin) > 1 and self._round_robin[0] == last_key:
            self._round_robin.rotate(-1)
        api_key_id = self._round_robin.popleft()
        queue = self._queues[api_key_id]
        entry = queue.popleft()
        if queue:
            self._round_robin.append(api_key_id)
        else:
            del self._queues[api_key_id]
        self._epoch += 1
        admission = ExecutorAdmission(
            entry.request_id,
            api_key_id,
            "local_primary",
            api_key_id,
            self._now(),
            "acquired",
            0,
            self._epoch,
            "round_robin_promoted",
        )
        self._owner = admission
        self._pins[entry.request_id] = admission
        return entry.future, admission

    def release(self, request_id: str) -> bool:
        promoted: tuple[asyncio.Future[ExecutorAdmission], ExecutorAdmission] | None = None
        with self._lock:
            pin = self._pins.pop(request_id, None)
            if pin is None:
                return False
            if self._owner is not None and self._owner.request_id == request_id:
                last_key = self._owner.api_key_id
                self._owner = None
                promoted = self._promote(last_key)
            elif pin.lease_state == "queued":
                queue = self._queues.get(pin.api_key_id)
                if queue is not None:
                    self._queues[pin.api_key_id] = deque(
                        entry for entry in queue if entry.request_id != request_id
                    )
                    if not self._queues[pin.api_key_id]:
                        del self._queues[pin.api_key_id]
                        self._round_robin = deque(
                            key for key in self._round_robin if key != pin.api_key_id
                        )
        if promoted is not None:
            future, admission = promoted

            def resolve() -> None:
                if not future.done():
                    future.set_result(admission)

            future.get_loop().call_soon_threadsafe(resolve)
        return True
