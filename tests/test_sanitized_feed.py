from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from dgx_moa.sanitized_feed import REDACTED, TRUNCATED, SanitizedEventFeed


def feed(capacity: int = 8, **kwargs: object) -> SanitizedEventFeed:
    return SanitizedEventFeed(
        capacity,
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
        **kwargs,  # type: ignore[arg-type]
    )


def test_publishes_complete_ordered_event() -> None:
    events = feed()
    events.subscribe("viewer")

    published = events.publish(
        role="executor",
        stage="implementation",
        status="running",
        public_message="file created",
    )

    assert published.sequence == 1
    assert published.timestamp == "2026-07-24T00:00:00Z"
    assert events.read("viewer") == [published]


def test_recursively_masks_secrets_prompts_and_reasoning() -> None:
    events = feed()
    events.subscribe("viewer")
    events.publish(
        role="planner",
        stage="design",
        status="completed",
        public_message={
            "api_key": "sk-secret-value-123456",
            "nested": [
                {
                    "Cookie": "session=private",
                    "prompt": "private repository prompt",
                    "reasoning": {"hidden": "private chain"},
                    "note": "Authorization: Bearer private-token",
                }
            ],
            "input_tokens": 42,
        },
    )

    message = events.read("viewer")[0].public_message
    serialized = json.dumps(message)
    assert all(secret not in serialized for secret in ("private", "sk-secret"))
    assert message["api_key"] == REDACTED
    assert message["nested"][0]["Cookie"] == REDACTED
    assert message["input_tokens"] == 42


def test_evicts_oldest_event_at_capacity() -> None:
    events = feed(capacity=2)
    events.subscribe("viewer")
    for number in range(3):
        events.publish(
            role="executor",
            stage="test",
            status="running",
            public_message=number,
        )

    assert [event.sequence for event in events.read("viewer")] == [2, 3]


def test_subscriber_cursors_and_results_are_independent() -> None:
    events = feed()
    events.subscribe("first")
    events.subscribe("second")
    events.publish(
        role="reviewer",
        stage="review",
        status="completed",
        public_message={"findings": []},
    )

    first = events.read("first")
    first[0].public_message["findings"].append("local mutation")

    assert events.read("first") == []
    assert events.read("second")[0].public_message == {"findings": []}


def test_rejects_invalid_input_and_bounds_long_messages() -> None:
    events = feed(max_message_characters=32)
    with pytest.raises(ValueError, match="invalid role"):
        events.publish(role="", stage="test", status="running", public_message="x")
    with pytest.raises(TypeError, match="JSON values"):
        events.publish(role="executor", stage="test", status="running", public_message=object())
    with pytest.raises(KeyError):
        events.read("missing")

    events.subscribe("viewer")
    events.publish(
        role="executor",
        stage="test",
        status="running",
        public_message="x" * 100,
    )
    assert events.read("viewer")[0].public_message == TRUNCATED


def test_publish_and_read_are_thread_safe() -> None:
    events = feed(capacity=300)
    events.subscribe("reader")
    barrier = threading.Barrier(5)
    done = threading.Event()

    def publish(worker: int) -> None:
        barrier.wait()
        for number in range(50):
            events.publish(
                role="executor",
                stage="concurrent",
                status="running",
                public_message={"worker": worker, "number": number},
            )

    def read() -> list[int]:
        seen: list[int] = []
        barrier.wait()
        while not done.wait(0.001):
            seen.extend(event.sequence for event in events.read("reader", limit=17))
        seen.extend(event.sequence for event in events.read("reader"))
        return seen

    with ThreadPoolExecutor(max_workers=5) as pool:
        reader = pool.submit(read)
        publishers = [pool.submit(publish, worker) for worker in range(4)]
        for publisher in publishers:
            publisher.result()
        done.set()
        seen = reader.result()

    assert seen == list(range(1, 201))
