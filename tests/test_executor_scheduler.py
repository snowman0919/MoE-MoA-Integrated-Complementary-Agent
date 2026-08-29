from __future__ import annotations

import asyncio

import pytest
from dgx_moa.executor_scheduler import ExecutorQueueFull, ExecutorScheduler


@pytest.mark.asyncio
async def test_executor_scheduler_overflow_fairness_and_high_risk_fail_closed() -> None:
    scheduler = ExecutorScheduler(queue_timeout_seconds=1)
    owner = await scheduler.acquire("key-a", "a1", flash_available=True)
    assert owner.selected_executor == "local_primary"

    queued = asyncio.create_task(
        scheduler.acquire("key-a", "a2", flash_available=True)
    )
    await asyncio.sleep(0)
    assert scheduler.snapshot()["queued"] == 1
    assert scheduler.pinned("a2").reason == "local_busy_queue"  # type: ignore[union-attr]

    cross_key = await scheduler.acquire("key-b", "b-flash", flash_available=True)
    assert (cross_key.selected_executor, cross_key.reason) == (
        "remote_overflow",
        "cross_key_overflow",
    )

    same_key = await scheduler.acquire("key-a", "a3", flash_available=True)
    assert (same_key.selected_executor, same_key.reason) == (
        "remote_overflow",
        "same_key_overflow",
    )

    scheduler.release("a1")
    assert (await queued).request_id == "a2"
    scheduler.release("a2")

    high_risk = ExecutorScheduler(queue_timeout_seconds=1)
    await high_risk.acquire("key-a", "risk-owner", flash_available=True)
    queued = asyncio.create_task(
        high_risk.acquire("key-a", "risk-0", risk="high", flash_available=True)
    )
    await asyncio.sleep(0)
    with pytest.raises(ExecutorQueueFull, match="high-risk"):
        await high_risk.acquire("key-a", "risk-1", risk="high", flash_available=True)
    queued.cancel()
    await asyncio.gather(queued, return_exceptions=True)


@pytest.mark.asyncio
async def test_executor_scheduler_cancellation_removes_queue_and_pin() -> None:
    scheduler = ExecutorScheduler(queue_timeout_seconds=1)
    await scheduler.acquire("key-a", "owner", flash_available=False)
    waiting = asyncio.create_task(scheduler.acquire("key-a", "waiting", flash_available=False))
    await asyncio.sleep(0)
    assert scheduler.pinned("waiting").lease_state == "queued"  # type: ignore[union-attr]
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert scheduler.pinned("waiting") is None
    assert scheduler.snapshot()["queued"] == 0


@pytest.mark.asyncio
async def test_unavailable_local_executor_uses_fallback_for_every_risk() -> None:
    scheduler = ExecutorScheduler(queue_timeout_seconds=1)
    fallback = await scheduler.acquire(
        "key-a", "fallback", flash_available=True, local_available=False
    )
    assert (fallback.selected_executor, fallback.reason) == ("remote_overflow", "local_unavailable")

    high_risk = await scheduler.acquire(
        "key-a",
        "high-risk",
        risk="high",
        flash_available=True,
        local_available=False,
    )
    assert (high_risk.selected_executor, high_risk.reason) == (
        "remote_overflow",
        "local_unavailable",
    )


@pytest.mark.asyncio
async def test_operator_gate_preserves_existing_pin_and_blocks_new_local_pins() -> None:
    scheduler = ExecutorScheduler(queue_timeout_seconds=1)
    pinned = await scheduler.acquire("key-a", "pinned", flash_available=True)
    scheduler.set_local_enabled(False)

    assert scheduler.pinned("pinned") == pinned
    fallback = await scheduler.acquire("key-b", "new", flash_available=True)
    assert (fallback.selected_executor, fallback.reason) == (
        "remote_overflow",
        "local_unavailable",
    )
