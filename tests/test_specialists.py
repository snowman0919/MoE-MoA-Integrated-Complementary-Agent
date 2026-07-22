import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from dgx_moa.config import SpecialistRoutingConfig
from dgx_moa.specialists import (
    MockPlannerProvider,
    MockReviewerProvider,
    RemotePlannerProvider,
    SpecialistRouter,
    SpecialistUnavailable,
)


class Records:
    def __init__(self, **records: Any) -> None:
        self.records = records

    def get(self, role: str) -> Any:
        return self.records.get(role)


def record(state: str, *, generation: int = 1, active: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        state=state,
        generation=generation,
        active_request_count=active,
        failure_class=None,
    )


def config() -> SpecialistRoutingConfig:
    return SpecialistRoutingConfig(
        enabled=True,
        provider="opencode_go",
        local_latency_seconds={"planner": 1.0, "reviewer": 1.0},
        remote_latency_seconds={"planner": 5.0, "reviewer": 5.0},
    )


@pytest.mark.asyncio
async def test_cold_misses_run_remotely_and_share_one_background_warmup() -> None:
    records = Records(planner=record("cold"))
    local = MockPlannerProvider({"provider": "local"})
    remote = MockPlannerProvider({"provider": "remote"})
    warmup_entered = asyncio.Event()
    allow_warmup = asyncio.Event()
    calls = 0

    async def warmup(role: str) -> Any:
        nonlocal calls
        calls += 1
        warmup_entered.set()
        await allow_warmup.wait()
        records.records[role] = record("ready", generation=2)
        return SimpleNamespace(record=records.records[role], load_triggered=True)

    router = SpecialistRouter(
        config(),
        local={"planner": local, "reviewer": MockReviewerProvider({})},
        remote={"planner": remote, "reviewer": MockReviewerProvider({})},
        lifecycle_store=records,
        warmup=warmup,
        runtime_id="runtime",
    )
    results = await asyncio.gather(
        router.complete("planner", {}, request_id="one", revision="rev", timeout_seconds=5),
        router.complete("planner", {}, request_id="two", revision="rev", timeout_seconds=5),
    )
    await asyncio.wait_for(warmup_entered.wait(), timeout=1)

    assert calls == 1
    assert not local.requests
    assert len(remote.requests) == 2
    assert [item[1]["selected_provider"] for item in results] == ["remote", "remote"]
    assert {item[1]["warmup_decision"] for item in results} == {"started", "reused"}

    allow_warmup.set()
    await asyncio.sleep(0)
    await router.close()


@pytest.mark.asyncio
async def test_ready_local_is_selected_by_queue_and_cost_prediction() -> None:
    local = MockPlannerProvider({"provider": "local"})
    remote = MockPlannerProvider({"provider": "remote"})
    acquired: list[tuple[str, str]] = []
    released: list[tuple[str, ...]] = []

    async def acquire(request_id: str, role: str) -> tuple[str, ...]:
        acquired.append((request_id, role))
        return ("lease",)

    router = SpecialistRouter(
        config(),
        local={"planner": local, "reviewer": MockReviewerProvider({})},
        remote={"planner": remote, "reviewer": MockReviewerProvider({})},
        lifecycle_store=Records(planner=record("ready")),
        acquire_local=acquire,
        release_local=released.append,
    )
    response, decision = await router.complete(
        "planner", {}, request_id="one", revision="rev", timeout_seconds=5
    )

    assert response == {"provider": "local"}
    assert decision["selected_provider"] == "local"
    assert decision["routing_reason"] == "local_within_cost_margin"
    assert acquired == [("one", "planner")]
    assert released == [("lease",)]
    assert not remote.requests


@pytest.mark.asyncio
async def test_provider_is_pinned_after_remote_dispatch_failure() -> None:
    local = MockPlannerProvider({"provider": "local"})
    remote = MockPlannerProvider(RuntimeError("remote failed"))
    events: list[tuple[str, dict[str, Any]]] = []
    router = SpecialistRouter(
        config(),
        local={"planner": local, "reviewer": MockReviewerProvider({})},
        remote={"planner": remote, "reviewer": MockReviewerProvider({})},
        lifecycle_store=Records(planner=record("cold")),
        event=lambda _request, event_type, payload: events.append((event_type, payload)),
    )

    with pytest.raises(SpecialistUnavailable, match="required planner provider failed"):
        await router.complete(
            "planner",
            {},
            request_id="one",
            revision="rev",
            timeout_seconds=5,
            mandatory=True,
        )

    assert not local.requests
    failure = next(payload for event, payload in events if event == "specialist_provider_failed")
    assert failure["selected_provider"] == "remote"
    assert failure["provider_switch_prevented"] is True


@pytest.mark.asyncio
async def test_local_only_cold_policy_fails_closed_without_remote_dispatch() -> None:
    remote = MockPlannerProvider({"provider": "remote"})
    router = SpecialistRouter(
        config(),
        local={"planner": MockPlannerProvider({}), "reviewer": MockReviewerProvider({})},
        remote={"planner": remote, "reviewer": MockReviewerProvider({})},
        lifecycle_store=Records(planner=record("loading_weights")),
    )

    with pytest.raises(SpecialistUnavailable, match="required local planner is not ready"):
        await router.complete(
            "planner",
            {},
            request_id="one",
            revision="rev",
            timeout_seconds=5,
            local_only=True,
        )
    assert not remote.requests


@pytest.mark.asyncio
async def test_opencode_specialist_uses_role_model_and_drops_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setenv("TEST_OPENCODE_KEY", "synthetic-secret")
    provider = RemotePlannerProvider(
        endpoint="https://opencode.invalid",
        api_key_env="TEST_OPENCODE_KEY",
        model="deepseek-v4-pro",
        min_completion_tokens=4096,
        transport=httpx.MockTransport(respond),
    )
    await provider.complete(
        {
            "messages": [],
            "tools": [{"type": "function"}],
            "metadata": {"private": True},
            "response_format": {"type": "json_schema", "json_schema": {}},
        },
        timeout_seconds=5,
    )

    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-v4-pro"
    assert body["stream"] is False
    assert body["max_tokens"] == 4096
    assert "tools" not in body
    assert "metadata" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert requests[0].headers["authorization"] == "Bearer synthetic-secret"
