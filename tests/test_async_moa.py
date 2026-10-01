from __future__ import annotations

import asyncio
import time

import pytest
from dgx_moa.async_moa import (
    AgentFinding,
    ArtifactRef,
    AsyncMoARuntime,
    DelegationSnapshot,
    EvidenceClaim,
    EvidenceClass,
    Staleness,
    reasoner_signal,
)
from dgx_moa.config import AsyncMoAPolicy
from dgx_moa.schemas import ChatRequest, ResponsesRequest


def snapshot(version: int = 1, *, tree: str = "tree-a") -> DelegationSnapshot:
    return DelegationSnapshot(
        task_state_version=version,
        repository_head="a" * 40,
        working_tree_hash=tree,
        decision_version=version,
        artifact_refs=(ArtifactRef("source", "repository", "repo://HEAD", tree),),
    )


@pytest.mark.asyncio
async def test_fast_is_exactly_one_executor_and_never_starts_auxiliary_work() -> None:
    runtime = AsyncMoARuntime("fast")
    calls = 0

    async def worker(_snapshot: DelegationSnapshot) -> AgentFinding:
        nonlocal calls
        calls += 1
        return AgentFinding(())

    for role in ("reasoner", "planner", "reviewer", "frontier"):
        assert (
            runtime.spawn(role, snapshot(), worker, signal_strength=100, semantic_key="same")
            is None
        )
    assert runtime.pending == ()
    assert calls == 0


@pytest.mark.asyncio
async def test_executor_work_overlaps_a_pending_delegate_in_wall_clock_time() -> None:
    runtime = AsyncMoARuntime("medium")
    delegate_started = asyncio.Event()
    delegate_release = asyncio.Event()

    async def worker(_snapshot: DelegationSnapshot) -> AgentFinding:
        delegate_started.set()
        await delegate_release.wait()
        return AgentFinding(())

    handle = runtime.spawn(
        "reasoner", snapshot(), worker, signal_strength=100, semantic_key="failure-analysis"
    )
    assert handle is not None
    await asyncio.wait_for(delegate_started.wait(), 1)
    started = time.monotonic()
    await asyncio.sleep(0.02)  # deterministic stand-in for Executor inspection/tool work
    runtime.record_useful_work("repository_inspection")
    assert not handle.task.done()
    delegate_release.set()
    await runtime.finalize(snapshot())
    assert time.monotonic() - started < 0.5
    assert runtime.useful_work_events == ["repository_inspection"]


def test_reasoner_is_implicitly_event_driven() -> None:
    assert reasoner_signal(["new_subsystem"]) == 60
    assert reasoner_signal(["major_tool_output", "unexpected_test_result"]) == 100
    assert reasoner_signal([]) == 0


def test_effort_policy_is_configurable_and_xhigh_is_an_api_value() -> None:
    policy = AsyncMoAPolicy()
    assert policy.runtime_budgets()["medium"].max_concurrent_delegates == 3
    assert (
        ChatRequest(
            model="dgx-moa",
            messages=[{"role": "user", "content": "work"}],
            reasoning_effort="xhigh",
        ).reasoning_effort
        == "xhigh"
    )
    assert (
        ResponsesRequest(
            model="dgx-moa", input="work", reasoning={"effort": "xhigh"}
        ).reasoning.effort
        == "xhigh"
    )


@pytest.mark.asyncio
async def test_workers_receive_first_party_refs_and_results_keep_provenance() -> None:
    launched = snapshot()
    received: list[DelegationSnapshot] = []

    async def worker(source: DelegationSnapshot) -> AgentFinding:
        received.append(source)
        return AgentFinding(
            (
                EvidenceClaim(
                    EvidenceClass.FACT,
                    "test passed",
                    (source.artifact_refs[0].artifact_id,),
                ),
            )
        )

    runtime = AsyncMoARuntime("xhigh")
    assert runtime.spawn("planner", launched, worker, signal_strength=100, semantic_key="plan")
    assert runtime.spawn("reviewer", launched, worker, signal_strength=100, semantic_key="review")
    result = await runtime.finalize(launched)

    assert received == [launched, launched]
    assert {item.launched_from.evidence_hash for item in result.results} == {launched.evidence_hash}
    assert {item.staleness for item in result.results} == {Staleness.CURRENT}


@pytest.mark.asyncio
async def test_stale_finding_is_advisory_and_cannot_trigger_rollback() -> None:
    runtime = AsyncMoARuntime("high")

    async def worker(_snapshot: DelegationSnapshot) -> AgentFinding:
        return AgentFinding(
            (EvidenceClaim(EvidenceClass.OBSERVATION, "old failure", ("old-log",)),),
            materially_corrective=True,
            invalidates=("current implementation",),
            recommended_direction="restore old implementation",
        )

    assert runtime.spawn("reviewer", snapshot(), worker, signal_strength=100, semantic_key="review")
    result = await runtime.finalize(snapshot(2, tree="tree-b"))
    assert result.results[0].staleness is Staleness.STALE
    assert not result.reloop_required
    assert result.decisions == []


@pytest.mark.asyncio
async def test_current_corrective_finding_records_direction_change_and_reloop() -> None:
    runtime = AsyncMoARuntime("high")

    async def worker(_snapshot: DelegationSnapshot) -> AgentFinding:
        return AgentFinding(
            (
                EvidenceClaim(EvidenceClass.FACT, "shared parser rejects the value", ("test",)),
                EvidenceClaim(
                    EvidenceClass.AGENT_RECOMMENDATION,
                    "fix the shared parser",
                    ("source",),
                ),
            ),
            materially_corrective=True,
            invalidates=("caller-only guard is sufficient",),
            recommended_direction="fix the shared parser",
            requested_actions=("patch", "test"),
        )

    assert runtime.spawn("reviewer", snapshot(), worker, signal_strength=100, semantic_key="review")
    result = await runtime.finalize(snapshot())
    assert result.reloop_required
    assert result.notification and "재루프" in result.notification
    assert result.decisions[0]["type"] == "direction_invalidated"
    assert result.requested_actions == ["patch", "test"]


@pytest.mark.asyncio
async def test_finalization_barrier_waits_and_duplicate_delegation_is_bounded() -> None:
    runtime = AsyncMoARuntime("xhigh")
    release = asyncio.Event()

    async def worker(_snapshot: DelegationSnapshot) -> AgentFinding:
        await release.wait()
        return AgentFinding(())

    first = runtime.spawn("reasoner", snapshot(), worker, signal_strength=100, semantic_key="same")
    duplicate = runtime.spawn(
        "reasoner", snapshot(), worker, signal_strength=100, semantic_key="same"
    )
    assert first is not None
    assert duplicate is None
    barrier = asyncio.create_task(runtime.finalize(snapshot()))
    await asyncio.sleep(0)
    assert not barrier.done()
    release.set()
    assert len((await asyncio.wait_for(barrier, 1)).results) == 1
