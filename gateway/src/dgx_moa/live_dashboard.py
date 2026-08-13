"""Bounded API-key-scoped projection of durable runtime events."""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .security import redact

_TOKEN_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_OPERATOR_FIELDS = {
    "failure_class",
    "finish_reasons",
    "lease_state",
    "model",
    "phase",
    "provider",
    "queue_position",
    "reason",
    "role",
    "round_robin_epoch",
    "routing_reason",
    "selected_executor",
    "stage",
    "stage_status",
    "status",
    "timings_ms",
}
_OPERATOR_GRAPH_FIELDS = {
    "attempt_id",
    "cost_usd",
    "failure_code",
    "latency_ms",
    "node_type",
    "parallel_group_id",
    "provider",
    "reason",
    "role",
    "state",
    "template_id",
    "terminal_status",
}


@dataclass(frozen=True)
class _Subscriber:
    api_key_id: str
    operator: bool
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]


class LiveDashboardHub:
    def __init__(
        self,
        owner_lookup: Callable[[str], str | None],
        *,
        queue_size: int = 256,
        replay_size: int = 2_048,
    ) -> None:
        self.owner_lookup = owner_lookup
        self.queue_size = queue_size
        self.replay_size = replay_size
        self._lock = threading.Lock()
        self._subscribers: dict[str, _Subscriber] = {}
        self._sequences: dict[str, int] = {}
        self._replay: dict[str, deque[dict[str, Any]]] = {}

    @staticmethod
    def _scope(api_key_id: str, operator: bool) -> str:
        return "operator" if operator else f"private:{api_key_id}"

    def _record(self, scope: str, event: dict[str, Any]) -> dict[str, Any]:
        sequence = self._sequences.get(scope, 0) + 1
        self._sequences[scope] = sequence
        recorded = {**event, "seq": sequence}
        self._replay.setdefault(scope, deque(maxlen=self.replay_size)).append(recorded)
        return recorded

    def subscribe(
        self, api_key_id: str, *, operator: bool, last_seq: int | None = None
    ) -> tuple[str, asyncio.Queue[dict[str, Any]], int]:
        subscriber_id = uuid.uuid4().hex
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self.queue_size)
        with self._lock:
            scope = self._scope(api_key_id, operator)
            self._subscribers[subscriber_id] = _Subscriber(
                api_key_id, operator, asyncio.get_running_loop(), queue
            )
            replay = tuple(self._replay.get(scope, ()))
            current = self._sequences.get(scope, 0)
        if last_seq is not None:
            pending = [event for event in replay if event["seq"] > last_seq]
            if (
                last_seq > current
                or (replay and last_seq < replay[0]["seq"] - 1)
                or len(pending) > self.queue_size
            ):
                queue.put_nowait({"type": "RESYNC_REQUIRED"})
            else:
                for event in pending:
                    queue.put_nowait(event)
        return subscriber_id, queue, current

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    @staticmethod
    def _enqueue(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        if queue.full():
            queue.get_nowait()
            event = {**event, "gap": True}
        queue.put_nowait(event)

    def publish(
        self, session_id: str, event_type: str, payload: dict[str, Any], created_at: str
    ) -> None:
        owner = self.owner_lookup(session_id)
        claimed_owner = payload.get("api_key_id")
        if owner is None and isinstance(claimed_owner, str) and _TOKEN_ID.fullmatch(claimed_owner):
            owner = claimed_owner
        safe_payload = redact(payload)
        operator_event: dict[str, Any] = {
            "type": "runtime_event",
            "event_type": event_type,
            "created_at": created_at,
            "api_key_id": owner,
            "payload": {
                key: value for key, value in safe_payload.items() if key in _OPERATOR_FIELDS
            },
        }
        own_payload = self._mask_other_owner(safe_payload, owner)
        private_event: dict[str, Any] = {
            "type": "runtime_event",
            "event_type": event_type,
            "created_at": created_at,
            "session_id": session_id,
            "payload": own_payload,
        }
        with self._lock:
            operator_event = self._record("operator", operator_event)
            recorded_private = self._record(f"private:{owner}", private_event) if owner else None
            subscribers = tuple(self._subscribers.values())
        for subscriber in subscribers:
            event = operator_event if subscriber.operator else recorded_private
            if event is None or (not subscriber.operator and owner != subscriber.api_key_id):
                continue
            subscriber.loop.call_soon_threadsafe(self._enqueue, subscriber.queue, event)

    @staticmethod
    def _mask_other_owner(payload: dict[str, Any], owner: str | None) -> dict[str, Any]:
        safe = dict(payload)
        for container in (safe, safe.get("scheduling")):
            if isinstance(container, dict) and container.get("lease_owner_api_key_id") not in {
                None,
                owner,
            }:
                container["lease_owner_api_key_id"] = "other"
        return safe

    def publish_graph(
        self,
        event_type: str,
        graph_id: str,
        api_key_id: str,
        request_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        safe_payload = redact(payload)
        if event_type == "graph_saved":
            scheduling = safe_payload.get("scheduling")
            operator_payload = {
                "template_id": safe_payload.get("template_id"),
                "selected_executor": (
                    scheduling.get("selected_executor") if isinstance(scheduling, dict) else None
                ),
                "node_count": len(safe_payload.get("nodes", [])),
                "edge_count": len(safe_payload.get("edges", [])),
            }
        else:
            operator_payload = {
                key: value for key, value in safe_payload.items() if key in _OPERATOR_GRAPH_FIELDS
            }
            if event_type == "graph_checkpoint":
                operator_payload |= {
                    "active_count": len(safe_payload.get("active_node_ids", [])),
                    "pending_count": len(safe_payload.get("pending_node_ids", [])),
                }
        private_event = {
            "type": "execution_graph",
            "event_type": event_type,
            "created_at": created_at,
            "graph_id": graph_id,
            "request_id": request_id,
            "payload": self._mask_other_owner(safe_payload, api_key_id),
        }
        operator_event = {
            "type": "execution_graph",
            "event_type": event_type,
            "created_at": created_at,
            "api_key_id": api_key_id,
            "payload": operator_payload,
        }
        with self._lock:
            private_event = self._record(f"private:{api_key_id}", private_event)
            operator_event = self._record("operator", operator_event)
            subscribers = tuple(self._subscribers.values())
        for subscriber in subscribers:
            if subscriber.operator:
                event = operator_event
            elif subscriber.api_key_id == api_key_id:
                event = private_event
            else:
                continue
            subscriber.loop.call_soon_threadsafe(self._enqueue, subscriber.queue, event)
