from __future__ import annotations

import asyncio

import pytest
from dgx_moa.executor_scheduler import ExecutorQueueFull, ExecutorScheduler


@pytest.mark.asyncio
async def test_executor_scheduler_overflow_fairness_and_high_risk_fail_closed() -> None:
    scheduler = ExecutorScheduler(queue_timeout_seconds=1)
    owner = await scheduler.acquire("key-a", "a1", flash_available=True)
    assert owner.selected_executor == "local_mistral"

    cross_key = await scheduler.acquire("key-b", "b-flash", flash_available=True)
    assert (cross_key.selected_executor, cross_key.reason) == (
        "opencode_go",
        "cross_key_overflow",
    )

    a2 = asyncio.create_task(scheduler.acquire("key-a", "a2", flash_available=True))
    a3 = asyncio.create_task(scheduler.acquire("key-a", "a3", flash_available=True))
    a4 = asyncio.create_task(scheduler.acquire("key-a", "a4", flash_available=True))
    await asyncio.sleep(0)
    overflow = await scheduler.acquire("key-a", "a5", flash_available=True)
    assert (overflow.selected_executor, overflow.reason) == (
        "opencode_go",
        "same_key_queue_limit",
    )

    b_local = asyncio.create_task(
        scheduler.acquire("key-b", "b-local", risk="high", flash_available=True)
    )
    await asyncio.sleep(0)
    scheduler.release("a1")
    assert (await b_local).api_key_id == "key-b"
    scheduler.release("b-local")
    assert (await a2).api_key_id == "key-a"
    scheduler.release("a2")
    assert (await a3).api_key_id == "key-a"
    scheduler.release("a3")
    assert (await a4).api_key_id == "key-a"

    high_risk = ExecutorScheduler(queue_timeout_seconds=1)
    await high_risk.acquire("key-a", "risk-owner", flash_available=True)
    queued = [
        asyncio.create_task(
            high_risk.acquire("key-a", f"risk-{index}", risk="high", flash_available=True)
        )
        for index in range(3)
    ]
    await asyncio.sleep(0)
    with pytest.raises(ExecutorQueueFull, match="high-risk"):
        await high_risk.acquire("key-a", "risk-4", risk="high", flash_available=True)
    pins = [high_risk.pinned(f"risk-{index}") for index in range(3)]
    assert all(pin is not None and pin.selected_executor == "local_mistral" for pin in pins)
    for task in queued:
        task.cancel()
    await asyncio.gather(*queued, return_exceptions=True)


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
