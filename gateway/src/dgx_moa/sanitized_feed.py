from __future__ import annotations

import copy
import json
import math
import re
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|cookie|password|secret)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b(?:hf|sk|nvapi)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bmoa_[A-Za-z0-9_-]{32,}\b"),
)
_SENSITIVE_NAMES = {
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "api_keys",
    "prompt",
    "raw_prompt",
    "reasoning",
    "hidden_reasoning",
    "chain_of_thought",
}


@dataclass(frozen=True, slots=True)
class SanitizedEvent:
    sequence: int
    timestamp: str
    role: str
    stage: str
    status: str
    public_message: Any


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower().replace("-", "_")
    return normalized in _SENSITIVE_NAMES or normalized.endswith(
        tuple(f"_{name}" for name in _SENSITIVE_NAMES)
    )


def _sanitize(value: Any, *, depth: int, nodes: list[int], max_nodes: int) -> Any:
    nodes[0] += 1
    if nodes[0] > max_nodes or depth > 16:
        raise ValueError("public message is too complex")
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("public message keys must be strings")
            sanitized[key] = (
                REDACTED
                if _sensitive_key(key)
                else _sanitize(item, depth=depth + 1, nodes=nodes, max_nodes=max_nodes)
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        return [
            _sanitize(item, depth=depth + 1, nodes=nodes, max_nodes=max_nodes) for item in value
        ]
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(
                lambda match: (match.group(1) if match.lastindex else "") + REDACTED,
                value,
            )
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("public message must contain only JSON values")


class SanitizedEventFeed:
    def __init__(
        self,
        capacity: int = 256,
        *,
        max_message_characters: int = 2_000,
        max_message_nodes: int = 1_024,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if capacity < 1 or max_message_characters < 1 or max_message_nodes < 1:
            raise ValueError("feed limits must be positive")
        self._events: deque[SanitizedEvent] = deque(maxlen=capacity)
        self._subscribers: dict[str, int] = {}
        self._sequence = 0
        self._max_message_characters = max_message_characters
        self._max_message_nodes = max_message_nodes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    @staticmethod
    def _label(name: str, value: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 64
            or not value.isprintable()
        ):
            raise ValueError(f"invalid {name}")
        return value.strip()

    def publish(
        self,
        *,
        role: str,
        stage: str,
        status: str,
        public_message: Any,
    ) -> SanitizedEvent:
        role = self._label("role", role)
        stage = self._label("stage", stage)
        status = self._label("status", status)
        message = _sanitize(
            public_message,
            depth=0,
            nodes=[0],
            max_nodes=self._max_message_nodes,
        )
        encoded = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded) > self._max_message_characters:
            message = TRUNCATED
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("feed clock must return a timezone-aware datetime")
        with self._lock:
            self._sequence += 1
            event = SanitizedEvent(
                sequence=self._sequence,
                timestamp=timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                role=role,
                stage=stage,
                status=status,
                public_message=message,
            )
            self._events.append(event)
            return replace(event, public_message=copy.deepcopy(message))

    def subscribe(self, subscriber: str, *, after_sequence: int | None = None) -> None:
        subscriber = self._label("subscriber", subscriber)
        if after_sequence is not None and (
            not isinstance(after_sequence, int)
            or isinstance(after_sequence, bool)
            or after_sequence < 0
        ):
            raise ValueError("invalid subscriber cursor")
        with self._lock:
            if subscriber in self._subscribers:
                raise ValueError("subscriber already exists")
            if after_sequence is not None and after_sequence > self._sequence:
                raise ValueError("subscriber cursor is ahead of the feed")
            self._subscribers[subscriber] = (
                after_sequence
                if after_sequence is not None
                else self._events[0].sequence - 1
                if self._events
                else self._sequence
            )

    def read(self, subscriber: str, *, limit: int | None = None) -> list[SanitizedEvent]:
        subscriber = self._label("subscriber", subscriber)
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
        ):
            raise ValueError("invalid read limit")
        with self._lock:
            if subscriber not in self._subscribers:
                raise KeyError(subscriber)
            events = [
                event for event in self._events if event.sequence > self._subscribers[subscriber]
            ][:limit]
            if events:
                self._subscribers[subscriber] = events[-1].sequence
            return [
                replace(event, public_message=copy.deepcopy(event.public_message))
                for event in events
            ]
