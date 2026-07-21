from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager

import httpx
import pytest
from dgx_moa import providers
from dgx_moa.api import create_app, has_matching_tool_result, ollama_model_ready
from dgx_moa.config import Settings
from dgx_moa.controller import fingerprint
from dgx_moa.lifecycle import (
    FakeLifecycleDriver,
    calculate_idle_policy,
    continuation_correlation,
)
from dgx_moa.schemas import ChatRequest
from dgx_moa.state import Phase, SessionState
from dgx_moa.streaming import forward_sse as unclosed_forward_sse
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from .conftest import StubProvider


@pytest.fixture(autouse=True)
def block_real_lifecycle_and_profile_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    def tripwire(*args: object, **kwargs: object) -> None:
        pytest.fail(f"unexpected real lifecycle/profile command: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "run", tripwire)
    monkeypatch.setattr("dgx_moa.profiles.ProfileManager.switch", tripwire)


@contextmanager
def client_with_stub(settings, stub_provider: StubProvider):  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        yield client


def chat_endpoint(app):  # type: ignore[no-untyped-def]
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/v1/chat/completions"
        and "POST" in getattr(route, "methods", set())
    )


def endpoint(app, path: str, method: str):  # type: ignore[no-untyped-def]
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    )


def assert_terminal_evidence(settings, store, session_id: str, status: str) -> dict:  # type: ignore[no-untyped-def]
    events = store.events(session_id)
    timing_events = [event for event in events if event["event_type"] == "request_timing"]
    terminal_events = [event for event in events if event["event_type"] == "session_ended"]
    assert len(timing_events) == 1
    assert len(terminal_events) == 1
    assert terminal_events[0]["payload"] == {"request_id": session_id, "status": status}
    trace_path = next((settings.state_db.parent.parent / "traces").rglob(f"{session_id}.jsonl"))
    traces = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(traces) == 1
    assert sum(event["event_type"] == "session_ended" for event in traces[0]["events"]) == 1
    return traces[0]


def assert_usage(app, status: str):  # type: ignore[no-untyped-def]
    records = app.state.usage.recent_requests()
    assert len(records) == 1
    record = records[0]
    assert uuid.UUID(record.request_id).version == 4
    assert record.status == status
    assert record.completed_at is not None
    assert record.active_duration_seconds is not None
    assert_no_request_leases(app)
    return record


def assert_no_request_leases(app) -> None:  # type: ignore[no-untyped-def]
    for role in app.state.settings.models:
        record = app.state.lifecycle_store.get(role)
        assert record.active_request_count == 0
        assert record.open_stream_count == 0
    with sqlite3.connect(app.state.settings.state_db) as database:
        rows = database.execute(
            "SELECT COUNT(*) FROM model_lifecycle_leases "
            "WHERE kind IN ('active_request', 'open_stream')"
        ).fetchone()
    assert rows == (0,)


def block_profile_control(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_control(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("profile control escaped an admin route test")

    monkeypatch.setattr("dgx_moa.profiles.ProfileManager.switch", reject_control)
    monkeypatch.setattr("dgx_moa.profiles.ProfileManager.transition", reject_control)
    monkeypatch.setattr("dgx_moa.profiles.subprocess.run", reject_control)


def test_systemd_lifecycle_driver_uses_model_load_timeout(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def driver(unit_map, *, timeout_seconds):  # type: ignore[no-untyped-def]
        captured.update(unit_map=unit_map, timeout_seconds=timeout_seconds)
        return FakeLifecycleDriver({})

    monkeypatch.setattr("dgx_moa.api.SystemdLifecycleDriver", driver)
    settings.limits.model_load_timeout_seconds = 123.0

    with TestClient(create_app(settings)):
        pass

    assert captured == {"unit_map": {}, "timeout_seconds": 123.0}


async def direct_chat(app, session_id: str, *, stream: bool = False):  # type: ignore[no-untyped-def]
    return await chat_endpoint(app)(
        ChatRequest(
            model="dgx-moa-fast",
            stream=stream,
            messages=[{"role": "user", "content": "work"}],
        ),
        Request({"type": "http", "app": app}),
        x_session_id=session_id,
        x_runtime_channel=None,
        x_trace_origin=None,
        x_task_id=None,
        x_workspace_path=None,
        x_workspace_id=None,
        x_repository_branch=None,
        x_repository_commit=None,
        x_dirty_state=None,
    )


async def direct_review(app, session_id: str, *, high_risk: bool = False):  # type: ignore[no-untyped-def]
    return await chat_endpoint(app)(
        ChatRequest(
            model="dgx-moa-orchestrated",
            messages=[{"role": "user", "content": "review this change"}],
            metadata={
                "diff_summary": "one verified change",
                **({"authentication": True} if high_risk else {}),
            },
        ),
        Request({"type": "http", "app": app}),
        x_session_id=session_id,
        x_runtime_channel=None,
        x_trace_origin=None,
        x_task_id=None,
        x_workspace_path=None,
        x_workspace_id=None,
        x_repository_branch=None,
        x_repository_commit=None,
        x_dirty_state=None,
    )


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        (
            [
                {"role": "assistant", "tool_calls": [{"id": "call-1"}]},
                {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
            ],
            True,
        ),
        (
            [
                {"role": "assistant", "tool_calls": [{"id": "call-1"}]},
                {"role": "tool", "tool_call_id": "call-other", "content": "ok"},
            ],
            False,
        ),
        (
            [
                {"role": "assistant", "tool_calls": [{"id": "call-1"}]},
                {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
                {"role": "user", "content": "ordinary later turn"},
            ],
            False,
        ),
        ([{"role": "tool", "tool_call_id": "call-1", "content": "ok"}], False),
    ],
)
def test_tool_result_matching_requires_the_trailing_assistant_continuation(
    messages: list[dict[str, object]], expected: bool
) -> None:
    assert has_matching_tool_result(messages) is expected  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_nonstream_active_lease_spans_provider_and_terminal_cleanup(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    entered = asyncio.Event()
    release = asyncio.Event()
    original = stub_provider.complete

    async def blocked(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            entered.set()
            await release.wait()
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "completed"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = blocked  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        pending = asyncio.create_task(direct_chat(app, "active-nonstream"))
        await asyncio.wait_for(entered.wait(), timeout=1)

        active = app.state.lifecycle_store.get("executor")
        assert active.active_request_count == 1
        assert app.state.lifecycle_store.unload_blockers("executor") == frozenset(
            {"active_request"}
        )

        release.set()
        response = await asyncio.wait_for(pending, timeout=1)
        finished = app.state.lifecycle_store.get("executor")

    assert response.status_code == 200
    assert finished.active_request_count == 0
    assert app.state.lifecycle_store.unload_blockers("executor") == frozenset()


@pytest.mark.asyncio
async def test_readiness_to_lease_race_returns_typed_503_before_controller_or_provider(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "active"})
    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=lambda role: asyncio.sleep(0, result=True),
        lifecycle_clock=lambda: 1_000.0,
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
    )
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        ready = app.state.lifecycle_store.get("executor")
        if ready.state != "ready":
            for target in (
                "load_queued",
                "process_starting",
                "loading_weights",
                "initializing_engine",
                "warming_up",
                "ready",
            ):
                ready = app.state.lifecycle_store.transition(
                    "executor",
                    target,
                    expected_transition_id=ready.transition_id,
                )
        acquire = app.state.lifecycle.acquire_request_leases

        async def lose_race(*args, **kwargs):  # type: ignore[no-untyped-def]
            admitted = app.state.lifecycle_store.admit_unload(
                "executor",
                expected_transition_id=ready.transition_id,
                memory_before_bytes=1_000,
            )
            assert admitted is not None
            return await acquire(*args, **kwargs)

        app.state.lifecycle.acquire_request_leases = lose_race

        def reject_session(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("controller mutated after losing lifecycle admission")

        app.state.controller.session = reject_session
        response = await direct_chat(app, "acquire-unload-race")
        usage = assert_usage(app, "failed")

    payload = json.loads(response.body)
    assert response.status_code == 503
    assert response.headers["X-DGX-MOA-Model-State"] == "unloading"
    assert payload["error"]["code"] == "model_loading"
    assert payload["model_state"]["state"] == "unloading"
    assert usage.retryable_failure_class == "model_loading"
    assert stub_provider.calls == []


@pytest.mark.asyncio
async def test_profile_switch_holds_exact_managed_role_guards_until_terminal_cleanup(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {
                "executor": "dgx-moa-dev-executor.service",
                "planner": "dgx-moa-dev-planner.service",
            },
        }
    )
    driver = FakeLifecycleDriver({"executor": "active", "planner": "active"})
    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=lambda role: asyncio.sleep(0, result=True),
        lifecycle_clock=lambda: 1_000.0,
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
    )
    entered = threading.Event()
    release = threading.Event()

    def blocked_switch(name: str) -> dict[str, str]:
        entered.set()
        assert release.wait(timeout=2)
        return {"status": "active", "active_profile": name}

    async with app.router.lifespan_context(app):
        app.state.profiles.switch = blocked_switch
        pending = asyncio.create_task(
            endpoint(app, "/admin/profile/resident", "POST")(Request({"type": "http", "app": app}))
        )
        for _ in range(1_000):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set()
        assert app.state.lifecycle_store.get("executor").profile_guard is True
        assert app.state.lifecycle_store.get("planner").profile_guard is True
        assert app.state.lifecycle_store.get("reviewer").profile_guard is False

        release.set()
        response = await asyncio.wait_for(pending, timeout=1)

        assert response["active_profile"] == "resident"
        assert app.state.lifecycle_store.get("executor").profile_guard is False
        assert app.state.lifecycle_store.get("planner").profile_guard is False


@pytest.mark.asyncio
async def test_profile_guard_claim_failure_is_typed_and_never_partially_claims(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {
                "executor": "dgx-moa-dev-executor.service",
                "planner": "dgx-moa-dev-planner.service",
            },
        }
    )
    app = create_app(
        controlled,
        lifecycle_driver=FakeLifecycleDriver({"executor": "active", "planner": "active"}),
        lifecycle_health_probe=lambda role: asyncio.sleep(0, result=True),
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
    )
    switch_called = False
    async with app.router.lifespan_context(app):
        executor = app.state.lifecycle_store.get("executor")
        app.state.lifecycle_store.set_guard(
            "executor",
            "profile_guard",
            True,
            expected_transition_id=executor.transition_id,
        )

        def reject_switch(name: str) -> dict[str, str]:
            nonlocal switch_called
            switch_called = True
            return {"status": "active", "active_profile": name}

        app.state.profiles.switch = reject_switch
        with pytest.raises(HTTPException) as error:
            await endpoint(app, "/admin/profile/resident", "POST")(
                Request({"type": "http", "app": app})
            )

        assert error.value.status_code == 503
        assert error.value.detail == "lifecycle profile guard unavailable"
        assert switch_called is False
        assert app.state.lifecycle_store.get("executor").profile_guard is True
        assert app.state.lifecycle_store.get("planner").profile_guard is False


@pytest.mark.asyncio
async def test_request_after_idle_full_stop_returns_typed_loading_and_starts_once(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    limits = settings.limits.model_copy(
        update={
            "executor_idle_minimum_seconds": 5.0,
            "executor_idle_fallback_seconds": 10.0,
            "executor_idle_maximum_seconds": 100.0,
            "executor_minimum_ready_residency_seconds": 1.0,
        }
    )
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
            "limits": limits.model_dump(),
        }
    )
    clock = [0.0]
    driver = FakeLifecycleDriver({"executor": "active"})
    blocked = asyncio.Event()
    health_ready = True

    async def health(role: str) -> bool:
        return health_ready

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health,
        lifecycle_clock=lambda: clock[0],
        lifecycle_sleeper=lambda seconds: blocked.wait(),
        lifecycle_memory_probe=lambda: 1_000,
    )
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        clock[0] = 100.0
        await app.state.lifecycle.run_scheduler_check(
            "fixed", ("executor",), controlled.limits, app.state.usage
        )
        clock[0] = 101.0
        await app.state.lifecycle.run_scheduler_check(
            "fixed", ("executor",), controlled.limits, app.state.usage
        )
        assert app.state.lifecycle_store.get("executor").state == "cold"
        health_ready = False

        response = await direct_chat(app, "reload-after-unload")
        for _ in range(1_000):
            if driver.calls.count(("start", "executor")) == 1:
                break
            await asyncio.sleep(0.001)

        assert response.status_code == 503
        assert json.loads(response.body)["error"]["code"] == "model_loading"
        assert response.headers["X-DGX-MOA-Model-State"] == "load_queued"
        assert driver.calls.count(("stop", "executor")) == 1
        assert driver.calls.count(("start", "executor")) == 1
        assert stub_provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_scheduler", "expected_driver_calls"),
    [
        ("disabled", False, []),
        ("observe", True, [("status", "executor")]),
        ("fixed", True, [("status", "executor")]),
        ("adaptive", True, [("status", "executor")]),
    ],
)
async def test_lifespan_mode_contract_controls_recovery_and_one_scheduler(
    settings,
    mode: str,
    expected_scheduler: bool,
    expected_driver_calls: list[tuple[str, str]],
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": mode,
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "active"})
    health_calls: list[str] = []

    async def health(role: str) -> bool:
        health_calls.append(role)
        return True

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
        lifecycle_memory_probe=lambda: (_ for _ in ()).throw(
            AssertionError("scheduler sampled memory before first check")
        ),
    )
    async with app.router.lifespan_context(app):
        scheduler = app.state.lifecycle._scheduler_task
        assert (scheduler is not None) is expected_scheduler
        if scheduler is not None:
            assert not scheduler.done()
        assert driver.calls == expected_driver_calls
        assert health_calls == (["executor"] if mode in {"observe", "fixed", "adaptive"} else [])

    assert app.state.lifecycle._scheduler_task is None


@pytest.mark.asyncio
async def test_lifespan_late_initialization_failure_closes_started_scheduler(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "observe",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    app = create_app(
        controlled,
        lifecycle_driver=FakeLifecycleDriver({"executor": "inactive"}),
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
    )
    captured: dict[str, asyncio.Task[None]] = {}

    def fail_trace_initialization(*args: object, **kwargs: object) -> None:
        scheduler = app.state.lifecycle._scheduler_task
        assert scheduler is not None
        captured["scheduler"] = scheduler
        raise RuntimeError("SENTINEL trace initialization")

    monkeypatch.setattr("dgx_moa.api.TraceRecorder", fail_trace_initialization)
    with pytest.raises(RuntimeError, match="SENTINEL trace initialization"):
        async with app.router.lifespan_context(app):
            pass

    scheduler = captured["scheduler"]
    closed_before_cleanup = scheduler.done() and app.state.lifecycle._scheduler_task is None
    if not closed_before_cleanup:
        await app.state.lifecycle.close()
    assert closed_before_cleanup


@pytest.mark.asyncio
async def test_stream_leases_span_generation_and_generator_terminal_cleanup(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    release = asyncio.Event()
    first_event = b'data: {"choices":[{"delta":{"content":"leased"}}]}\n\n'

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield first_event
            await release.wait()
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, "leased-stream", stream=True)
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == first_event

        active = app.state.lifecycle_store.get("executor")
        assert active.active_request_count == 1
        assert active.open_stream_count == 1
        assert app.state.lifecycle_store.unload_blockers("executor") == frozenset(
            {"active_request", "open_stream"}
        )

        release.set()
        _ = b"".join([chunk async for chunk in response.body_iterator])
        finished = app.state.lifecycle_store.get("executor")

    assert finished.active_request_count == 0
    assert finished.open_stream_count == 0


@pytest.mark.asyncio
async def test_stream_close_before_first_iteration_owns_upstream_and_terminal_cleanup(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    closed = asyncio.Event()

    class UnstartedUpstream:
        def __aiter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __anext__(self) -> bytes:
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def aclose(self) -> None:
            closed.set()

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        return UnstartedUpstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, "unstarted-close", stream=True)
        assert isinstance(response, StreamingResponse)
        active = app.state.lifecycle_store.get("executor")
        assert (active.active_request_count, active.open_stream_count) == (1, 1)

        await response.body_iterator.aclose()

        assert closed.is_set()
        assert_usage(app, "cancelled")
        assert_terminal_evidence(settings, app.state.store, "unstarted-close", "cancelled")


@pytest.mark.asyncio
async def test_asgi_response_cancellation_while_sending_closes_stream_owner(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    closed = asyncio.Event()
    sending_body = asyncio.Event()
    first_event = b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'

    async def upstream():  # type: ignore[no-untyped-def]
        try:
            yield first_event
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        return upstream()

    async def receive() -> dict[str, str]:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.body":
            sending_body.set()
            await asyncio.Event().wait()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, "asgi-send-cancel", stream=True)
        pending = asyncio.create_task(
            response(
                {"type": "http", "asgi": {"spec_version": "2.4"}},
                receive,
                send,
            )
        )
        await asyncio.wait_for(sending_body.wait(), timeout=1)
        active = app.state.lifecycle_store.get("executor")
        assert (active.active_request_count, active.open_stream_count) == (1, 1)

        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        assert closed.is_set()
        assert_usage(app, "cancelled")
        assert_terminal_evidence(settings, app.state.store, "asgi-send-cancel", "cancelled")


@pytest.mark.asyncio
async def test_stream_terminal_event_failure_still_closes_and_finalizes(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    closed = asyncio.Event()
    terminal = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'

    async def upstream():  # type: ignore[no-untyped-def]
        try:
            yield terminal
            yield b"data: [DONE]\n\n"
        finally:
            closed.set()

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        event = app.state.store.event

        def fail_terminal_event(session_id, event_type, payload):  # type: ignore[no-untyped-def]
            if event_type == "assistant_stream_finished":
                raise OSError("terminal event unavailable")
            return event(session_id, event_type, payload)

        app.state.store.event = fail_terminal_event
        response = await direct_chat(app, "terminal-event-failure", stream=True)
        assert isinstance(response, StreamingResponse)
        with pytest.raises(OSError, match="terminal event unavailable"):
            _ = b"".join([chunk async for chunk in response.body_iterator])

        assert closed.is_set()
        assert_usage(app, "completed")
        assert_terminal_evidence(
            settings,
            app.state.store,
            "terminal-event-failure",
            "completed",
        )


@pytest.mark.asyncio
async def test_nonstream_cancellation_releases_active_lease(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    entered = asyncio.Event()

    async def blocked(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    stub_provider.complete = blocked  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        pending = asyncio.create_task(direct_chat(app, "cancelled-nonstream"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert app.state.lifecycle_store.get("executor").active_request_count == 1

        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        assert_usage(app, "cancelled")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_reviewer_evaluation_guard_is_scoped_to_the_real_review_call(
    settings,
    stub_provider: StubProvider,
    failure: bool,
) -> None:  # type: ignore[no-untyped-def]
    entered = asyncio.Event()
    release = asyncio.Event()
    guard_values: list[bool] = []
    original = stub_provider.complete
    app = create_app(settings)

    async def guarded(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "reviewer":
            guard_values.append(app.state.lifecycle_store.get("reviewer").evaluation_guard)
            entered.set()
            await release.wait()
            if failure:
                raise ValueError("review failed")
        return await original(role, model, request, **kwargs)

    stub_provider.complete = guarded  # type: ignore[method-assign]
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        pending = asyncio.create_task(
            chat_endpoint(app)(
                ChatRequest(
                    model="dgx-moa-orchestrated",
                    messages=[{"role": "user", "content": "review this change"}],
                    metadata={"diff_summary": "one verified change"},
                ),
                Request({"type": "http", "app": app}),
                x_session_id=f"review-guard-{failure}",
                x_runtime_channel=None,
                x_trace_origin=None,
                x_task_id=None,
                x_workspace_path=None,
                x_workspace_id=None,
                x_repository_branch=None,
                x_repository_commit=None,
                x_dirty_state=None,
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert guard_values == [True]
        assert app.state.lifecycle_store.unload_blockers("reviewer") >= {
            "active_request",
            "evaluation_guard",
        }

        release.set()
        response = await asyncio.wait_for(pending, timeout=1)
        reviewer = app.state.lifecycle_store.get("reviewer")

    assert response.status_code == 200
    assert reviewer.evaluation_guard is False
    assert reviewer.active_request_count == 0


@pytest.mark.asyncio
async def test_reviewer_transition_change_preserves_uncertain_guard(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete
    app = create_app(settings)

    async def transition_during_review(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "reviewer":
            guarded = app.state.lifecycle_store.get("reviewer")
            assert guarded.evaluation_guard is True
            app.state.lifecycle_store.transition(
                "reviewer",
                "load_queued",
                expected_transition_id=guarded.transition_id,
            )
        return await original(role, model, request, **kwargs)

    stub_provider.complete = transition_during_review  # type: ignore[method-assign]
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_review(app, "review-transition-change")
        reviewer = app.state.lifecycle_store.get("reviewer")

    assert response.status_code == 502
    assert reviewer.state == "load_queued"
    assert reviewer.evaluation_guard is True
    assert_no_request_leases(app)


@pytest.mark.asyncio
async def test_preexisting_reviewer_guard_is_not_claimed_or_cleared(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    reviewer_called = False
    original = stub_provider.complete
    app = create_app(settings)

    async def observe(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal reviewer_called
        if role == "reviewer":
            reviewer_called = True
        return await original(role, model, request, **kwargs)

    stub_provider.complete = observe  # type: ignore[method-assign]
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        reviewer = app.state.lifecycle_store.get("reviewer")
        app.state.lifecycle_store.set_guard(
            "reviewer",
            "evaluation_guard",
            True,
            expected_transition_id=reviewer.transition_id,
        )

        response = await direct_review(app, "preexisting-review-guard", high_risk=True)
        guarded = app.state.lifecycle_store.get("reviewer")

    assert response.status_code == 502
    assert reviewer_called is False
    assert guarded.evaluation_guard is True
    assert_no_request_leases(app)


@pytest.mark.asyncio
async def test_concurrent_reviewer_calls_are_serialized_guard_owners(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()
    release_second = asyncio.Event()
    review_calls = 0
    original = stub_provider.complete
    app = create_app(settings)

    async def serialized(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal review_calls
        if role == "reviewer":
            review_calls += 1
            assert app.state.lifecycle_store.get("reviewer").evaluation_guard is True
            if review_calls == 1:
                first_entered.set()
                await release_first.wait()
            else:
                second_entered.set()
                await release_second.wait()
        return await original(role, model, request, **kwargs)

    stub_provider.complete = serialized  # type: ignore[method-assign]
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        first = asyncio.create_task(direct_review(app, "serialized-review-1"))
        await asyncio.wait_for(first_entered.wait(), timeout=1)
        second = asyncio.create_task(direct_review(app, "serialized-review-2"))
        await asyncio.sleep(0)
        assert second_entered.is_set() is False

        release_first.set()
        first_response = await asyncio.wait_for(first, timeout=1)
        await asyncio.wait_for(second_entered.wait(), timeout=1)
        assert app.state.lifecycle_store.get("reviewer").evaluation_guard is True

        release_second.set()
        second_response = await asyncio.wait_for(second, timeout=1)
        reviewer = app.state.lifecycle_store.get("reviewer")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert review_calls == 2
    assert reviewer.evaluation_guard is False
    assert_no_request_leases(app)


@pytest.mark.asyncio
@pytest.mark.parametrize(("failure", "expected_status"), [("trace", 200), ("usage", 502)])
async def test_reviewer_guard_clears_before_terminal_observability_failure(
    settings,
    stub_provider: StubProvider,
    failure: str,
    expected_status: int,
) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider

        if failure == "trace":

            def fail_trace(*args, **kwargs):  # type: ignore[no-untyped-def]
                raise OSError("trace unavailable")

            app.state.traces.record = fail_trace
        else:

            def fail_usage(*args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("usage unavailable")

            app.state.usage.finalize = fail_usage

        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-orchestrated",
                messages=[{"role": "user", "content": "review this change"}],
                metadata={"diff_summary": "one verified change"},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=f"review-terminal-{failure}",
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        reviewer = app.state.lifecycle_store.get("reviewer")

    assert response.status_code == expected_status
    assert reviewer.evaluation_guard is False
    assert reviewer.active_request_count == 0


def test_nonstream_tool_continuation_requires_same_session_and_matching_call(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    session_id = "strict-continuation"
    original = stub_provider.complete

    async def stop_after_tool(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and any(
            message.get("role") == "tool" for message in request["messages"]
        ):
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "tool accepted"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = stop_after_tool  # type: ignore[method-assign]
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": session_id}
    with client_with_stub(settings, stub_provider) as client:
        first = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        call = first.json()["choices"][0]["message"]
        held = client.app.state.lifecycle_store.get("executor")
        with sqlite3.connect(settings.state_db) as database:
            lease_row = database.execute(
                "SELECT role, kind, owner_correlation, expires_at "
                "FROM model_lifecycle_leases WHERE kind = 'continuation'"
            ).fetchone()

        ordinary = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"stdout":"ok","exit_code":0}',
                    },
                    {"role": "user", "content": "ordinary later turn"},
                ],
            },
        )
        after_ordinary = client.app.state.lifecycle_store.get("executor")
        mismatched = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-other",
                        "content": '{"stdout":"ok","exit_code":0}',
                    },
                ],
            },
        )
        after_mismatch = client.app.state.lifecycle_store.get("executor")
        different_session = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "different-session",
            },
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"stdout":"ok","exit_code":0}',
                    },
                ],
            },
        )
        after_different_session = client.app.state.lifecycle_store.get("executor")
        second = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"stdout":"SENTINEL_TOOL_RESULT","exit_code":0}',
                    },
                ],
            },
        )
        released = client.app.state.lifecycle_store.get("executor")

    assert first.status_code == 200
    assert held.active_request_count == 0
    assert held.continuation_lease_count == 1
    assert lease_row is not None
    assert lease_row[:3] == (
        "executor",
        "continuation",
        continuation_correlation(session_id),
    )
    assert lease_row[3] > 0
    assert "call-preserved" not in repr(lease_row)
    assert ordinary.status_code == 200
    assert mismatched.status_code == 200
    assert different_session.status_code == 200
    assert after_ordinary.continuation_lease_count == 1
    assert after_mismatch.continuation_lease_count == 1
    assert after_different_session.continuation_lease_count == 1
    assert second.status_code == 200
    assert released.continuation_lease_count == 0


def test_nonstream_tool_call_payload_creates_continuation_when_finish_reason_is_stop(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def tool_call_with_stop(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-stop",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = tool_call_with_stop  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "stop-with-tool-call",
            },
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        held = client.app.state.lifecycle_store.get("executor")

    assert response.status_code == 200
    assert response.json()["choices"][0]["finish_reason"] == "stop"
    assert response.json()["choices"][0]["message"]["tool_calls"]
    assert held.continuation_lease_count == 1


@pytest.mark.asyncio
async def test_stream_tool_calls_create_one_continuation_before_stream_release(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    tool_delta = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"stream-call",'
        b'"type":"function","function":{"name":"read_file","arguments":"{}"}}]}}]}\n\n'
    )
    terminal = b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
    done = b"data: [DONE]\n\n"

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield tool_delta
            yield terminal
            yield done

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, "stream-continuation", stream=True)
        assert isinstance(response, StreamingResponse)
        forwarded = b"".join([chunk async for chunk in response.body_iterator])
        record = app.state.lifecycle_store.get("executor")

    assert forwarded == tool_delta + terminal + done
    assert record.active_request_count == 0
    assert record.open_stream_count == 0
    assert record.continuation_lease_count == 1


def test_stream_tool_continuation_without_session_header_correlates_by_token(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    configured = Settings.model_validate(
        settings.model_dump()
        | {
            "api_key": None,
            "api_keys": {
                "client-a": "isolated-client-a-token-20260721",
                "client-b": "isolated-client-b-token-20260721",
            },
        }
    )
    tool_delta = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"stream-call",'
        b'"type":"function","function":{"name":"read_file","arguments":"{}"}}]}}]}\n\n'
    )
    terminal = b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
    done = b"data: [DONE]\n\n"
    original_complete = stub_provider.complete

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield tool_delta
            yield terminal
            yield done

        return upstream()

    async def continue_after_tool(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and any(
            message.get("role") == "tool" for message in request["messages"]
        ):
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "recovered"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original_complete(role, model, request, **kwargs)

    stub_provider.stream = streamed  # type: ignore[method-assign]
    stub_provider.complete = continue_after_tool  # type: ignore[method-assign]
    continuation = {
        "model": "dgx-moa-agent",
        "messages": [
            {"role": "user", "content": "work"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "stream-call",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "stream-call",
                "content": json.dumps(
                    {
                        "tool_name": "read_file",
                        "stderr": "File not found: x",
                        "exit_code": 0,
                    }
                ),
            },
        ],
    }
    with client_with_stub(configured, stub_provider) as client:
        first = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer isolated-client-a-token-20260721"},
            json={
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        session_id = first.headers["X-Session-ID"]
        original_state = client.app.state.store.get(session_id)
        wrong_token = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer isolated-client-b-token-20260721"},
            json=continuation,
        )
        after_wrong_token = client.app.state.store.get(session_id)
        correct_token = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer isolated-client-a-token-20260721"},
            json=continuation,
        )
        final_state = client.app.state.store.get(session_id)

    assert first.status_code == 200
    assert original_state and original_state.pending_tool_call_ids == ["stream-call"]
    assert wrong_token.status_code == 200
    assert wrong_token.headers["X-Session-ID"] != session_id
    assert after_wrong_token and after_wrong_token.tool_results == []
    assert correct_token.status_code == 200
    assert correct_token.headers["X-Session-ID"] == session_id
    assert final_state and final_state.pending_tool_call_ids == []
    assert final_state.tool_results[0]["stderr"] == "File not found: x"
    assert final_state.failures[0]["root_cause_summary"] == "tool execution failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [False, True])
async def test_synthesized_done_and_malformed_sse_release_stream_leases(
    settings,
    stub_provider: StubProvider,
    malformed: bool,
) -> None:  # type: ignore[no-untyped-def]
    terminal = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield b"data: incomplete" if malformed else terminal

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, f"sse-terminal-{malformed}", stream=True)
        assert isinstance(response, StreamingResponse)
        if malformed:
            with pytest.raises(ValueError, match="incomplete SSE event"):
                _ = b"".join([chunk async for chunk in response.body_iterator])
            assert_usage(app, "failed")
        else:
            forwarded = b"".join([chunk async for chunk in response.body_iterator])
            assert forwarded == terminal + b"data: [DONE]\n\n"
            assert_usage(app, "completed")


def test_expired_continuation_is_not_revived_by_a_late_tool_result(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    clock = [100.0]
    original = stub_provider.complete

    async def stop_after_tool(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and any(
            message.get("role") == "tool" for message in request["messages"]
        ):
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "late result"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = stop_after_tool  # type: ignore[method-assign]
    app = create_app(settings, lifecycle_clock=lambda: clock[0])
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "expires"}
        first = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        call = first.json()["choices"][0]["message"]
        with sqlite3.connect(settings.state_db) as database:
            expires_at = database.execute(
                "SELECT expires_at FROM model_lifecycle_leases WHERE kind = 'continuation'"
            ).fetchone()

        clock[0] = 1_001.0
        assert app.state.lifecycle_store.unload_blockers("executor") == frozenset()
        late = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"stdout":"late","exit_code":0}',
                    },
                ],
            },
        )
        record = app.state.lifecycle_store.get("executor")

    assert expires_at == (1_000.0,)
    assert late.status_code == 200
    assert record.continuation_lease_count == 0


@pytest.mark.asyncio
async def test_concurrent_cold_api_requests_return_one_json_load_and_usage_each(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "inactive"})
    release_poll = asyncio.Event()

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return False

    async def sleeper(seconds: float) -> None:
        assert seconds == controlled.lifecycle_poll_seconds
        await release_poll.wait()

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=sleeper,
    )
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider

        def reject_session(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("controller mutated before lifecycle readiness")

        app.state.controller.session = reject_session
        responses = await asyncio.gather(
            *(direct_chat(app, f"cold-{index}", stream=index == 0) for index in range(20))
        )
        for _ in range(1_000):
            if ("start", "executor") in driver.calls:
                break
            await asyncio.sleep(0.001)
        usage = app.state.usage.recent_requests()
        role_usage = app.state.usage.recent_role_requests("executor")
        assert_no_request_leases(app)

    assert len(responses) == 20
    for response in responses:
        assert response.status_code == 503
        assert response.media_type == "application/json"
        assert response.headers["Retry-After"]
        assert 1 <= int(response.headers["Retry-After"]) <= 300
        assert response.headers["X-DGX-MOA-Model-State"] == "load_queued"
        assert response.headers["X-DGX-MOA-Model-Role"] == "executor"
        assert response.headers["X-DGX-MOA-Load-Generation"] == "1"
        assert response.headers["X-DGX-MOA-Weight-Load-Percent"] == "unavailable"
        payload = json.loads(response.body)
        assert payload["error"]["code"] == "model_loading"
        assert payload["model_state"]["role"] == "executor"
        assert set(payload["model_state"]) == {
            "role",
            "generation",
            "state",
            "transition_id",
            "weight_load_percent",
            "progress_quality",
            "overall_load_percent",
            "estimated_ready_seconds",
            "ready",
        }
        assert payload["model_state"]["generation"] == 1
        assert payload["model_state"]["ready"] is False
        assert payload["model_state"]["overall_load_percent"] == 0.0
        assert payload["model_state"]["weight_load_percent"] is None
        assert payload["model_state"]["progress_quality"] == "unavailable"
        serialized = json.dumps(payload)
        assert "dgx-moa-dev-executor.service" not in serialized
        assert str(controlled.models["executor"].destination) not in serialized
        assert controlled.models["executor"].base_url not in serialized
    assert stub_provider.calls == []
    assert len(usage) == 20
    assert all(record.status == "failed" for record in usage)
    assert all(record.retryable_failure_class == "model_loading" for record in usage)
    assert all(record.model_state == "loading" for record in usage)
    assert sum(record.load_triggered for record in usage) == 1
    assert len(role_usage) == 20
    assert all(record.success is False for record in role_usage)
    assert all(record.failure_class == "model_loading" for record in role_usage)
    assert sum(record.load_triggered for record in role_usage) == 1
    assert driver.calls.count(("start", "executor")) == 1
    assert not any(operation == "stop" for operation, _ in driver.calls)


@pytest.mark.parametrize("reasoner_mode", ["required"])
def test_explicit_reasoner_policy_is_required_when_cold(
    settings,
    stub_provider: StubProvider,
    reasoner_mode: str,
) -> None:  # type: ignore[no-untyped-def]
    managed = ("planner", "executor", "reviewer", "reasoner")
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {role: f"dgx-moa-dev-{role}.service" for role in managed},
        }
    )
    driver = FakeLifecycleDriver(
        {
            "planner": "active",
            "executor": "active",
            "reviewer": "active",
            "reasoner": "inactive",
        }
    )

    async def health_probe(role: str) -> bool:
        return role != "reasoner"

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": reasoner_mode},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "analyze explicitly"}],
                "metadata": {"reasoner_mode": reasoner_mode},
            },
        )
        for _ in range(1_000):
            if ("start", "reasoner") in driver.calls:
                break
            time.sleep(0.001)
        role_usage = app.state.usage.recent_role_requests("reasoner")

    assert len(role_usage) == 1
    assert role_usage[0].load_triggered is True
    assert driver.calls.count(("start", "reasoner")) == 1
    assert response.status_code == 503
    assert response.headers["X-DGX-MOA-Model-Role"] == "reasoner"
    assert role_usage[0].failure_class == "model_loading"
    assert "reasoner" not in stub_provider.calls


def test_explicit_ready_reasoner_is_used_only_when_selected(
    settings,
    stub_provider: StubProvider,
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "analyze explicitly"}],
                "metadata": {"reasoner_mode": "required"},
            },
        )
        reasoner_usage = client.app.state.usage.recent_role_requests("reasoner")

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "executor"]
    assert len(reasoner_usage) == 1
    assert reasoner_usage[0].success is True


@pytest.mark.parametrize(
    ("driver_state", "expected_status"),
    [("inactive", 503), ("active", 200)],
)
def test_failure_circuit_blocks_mutation_but_preserves_ready_traffic(
    settings,
    stub_provider: StubProvider,
    driver_state: str,
    expected_status: int,
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": driver_state})

    async def health_probe(role: str) -> bool:
        return True

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
        lifecycle_clock=lambda: 100.0,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        generation = app.state.lifecycle_store.get("executor").generation
        for index in range(3):
            app.state.lifecycle_store.record_failure(
                "executor",
                "injected_start",
                f"injected_{index}",
                generation,
                failure_limit=3,
                failure_window_seconds=900,
            )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        model_status = client.get(
            "/v1/model-status",
            headers={"Authorization": "Bearer test-secret"},
        ).json()

    assert response.status_code == expected_status
    assert model_status["automation"]["automation_disabled"] is True
    assert model_status["automation"]["failure_count"] == 3
    assert driver.calls.count(("start", "executor")) == 0
    if expected_status == 503:
        assert response.json()["error"]["code"] == "lifecycle_automation_disabled"
        assert stub_provider.calls == []
    else:
        assert stub_provider.calls == ["executor"]


def test_observe_lifecycle_records_state_without_blocking_or_controlling(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    observed = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "observe",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "active"})

    async def health(role: str) -> bool:
        assert role == "executor"
        return True

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"observe lifecycle slept for {seconds}")

    app = create_app(
        observed,
        lifecycle_driver=driver,
        lifecycle_health_probe=health,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=reject_sleep,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        status_response = client.get(
            "/v1/model-status", headers={"Authorization": "Bearer test-secret"}
        )
        lifecycle_record = app.state.lifecycle_store.get("executor")

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor"]
    assert driver.calls == [("status", "executor")]
    assert lifecycle_record.state == "ready"
    assert status_response.json()["control"] == "observe_only"


@pytest.mark.asyncio
async def test_observe_reconciles_read_only_and_records_unload_candidate(settings) -> None:  # type: ignore[no-untyped-def]
    observed = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "observe",
            "lifecycle_unit_map": {"planner": "dgx-moa-dev-planner.service"},
        }
    )
    driver = FakeLifecycleDriver({"planner": "active"})
    clock = [100.0]

    async def health(role: str) -> bool:
        assert role == "planner"
        return True

    app = create_app(
        observed,
        lifecycle_driver=driver,
        lifecycle_health_probe=health,
        lifecycle_clock=lambda: clock[0],
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
        lifecycle_memory_probe=lambda: (_ for _ in ()).throw(
            AssertionError("observe sampled memory")
        ),
    )
    async with app.router.lifespan_context(app):
        assert app.state.lifecycle_store.get("planner").state == "ready"
        clock[0] = 5_000.0
        await app.state.lifecycle.run_scheduler_check(
            "observe", ("planner",), observed.lifecycle, app.state.usage
        )
        await app.state.lifecycle.run_scheduler_check(
            "observe", ("planner",), observed.lifecycle, app.state.usage
        )
        decision = app.state.lifecycle_store.latest_decision("planner")

    assert decision is not None
    assert decision.would_unload is True
    assert decision.action_allowed is False
    assert driver.calls == [("status", "planner")]


def test_disabled_lifecycle_bypasses_control_and_reports_external_state(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    driver = FakeLifecycleDriver({"executor": "inactive"})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"disabled lifecycle probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"disabled lifecycle slept for {seconds}")

    app = create_app(
        settings,
        lifecycle_driver=driver,
        lifecycle_health_probe=reject_health,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=reject_sleep,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        status_response = client.get(
            "/v1/model-status", headers={"Authorization": "Bearer test-secret"}
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert stub_provider.calls == ["reasoner", "executor"]
    assert driver.calls == []
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["lifecycle_mode"] == "disabled"
    assert payload["control"] == "disabled"
    assert payload["external_state"] == "not_lifecycle_managed"
    assert {item["role"] for item in payload["data"]} == set(settings.models)
    assert all(item["state"] == "unmanaged" for item in payload["data"])
    assert all(item["control"] == "disabled" for item in payload["data"])


def test_model_status_is_authenticated_typed_and_content_free(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "observe",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "inactive"})
    blocked = asyncio.Event()

    async def health_probe(role: str) -> bool:
        return False

    async def sleeper(seconds: float) -> None:
        await blocked.wait()

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=sleeper,
    )
    with TestClient(app) as client:
        record = app.state.lifecycle_store.get("executor")
        queued = app.state.lifecycle_store.transition(
            "executor", "load_queued", expected_transition_id=record.transition_id
        )
        failed = app.state.lifecycle_store.transition(
            "executor",
            "failed",
            expected_transition_id=queued.transition_id,
            failure_class="Health Timeout",
            failure_detail="SENTINEL_FAILURE_DETAIL /unsafe/path http://secret.invalid",
            retry_count=1,
        )
        decision = calculate_idle_policy(
            "executor",
            "observe",
            (),
            failed,
            now=100.0,
            limits=controlled.limits,
        )
        app.state.lifecycle_store.persist_decision(decision)
        unauthorized = client.get("/v1/model-status")
        listed = client.get("/v1/model-status", headers={"Authorization": "Bearer test-secret"})
        detail = client.get(
            "/v1/model-status/executor",
            headers={"Authorization": "Bearer test-secret"},
        )
        unmanaged = client.get(
            "/v1/model-status/planner",
            headers={"Authorization": "Bearer test-secret"},
        )
        unknown = client.get(
            "/v1/model-status/unsafe-role",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert unauthorized.status_code == 401
    assert listed.status_code == 200
    assert listed.json()["idle_decisions"] == {
        "executor": decision.model_dump(mode="json") | {"decided_at": 100.0}
    }
    assert {item["role"] for item in listed.json()["data"]} == set(controlled.models)
    assert next(item for item in listed.json()["data"] if item["role"] == "executor") == (
        detail.json()
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["role"] == "executor"
    assert payload["state"] == "failed"
    assert payload["generation"] == 1
    assert payload["ready"] is False
    assert payload["failure_class"] == "health_timeout"
    assert payload["last_error_class"] == "health_timeout"
    assert payload["retry_count"] == 1
    assert payload["idle_decision"] == decision.model_dump(mode="json") | {"decided_at": 100.0}
    assert payload["lifecycle_mode"] == "observe"
    assert set(payload) == {
        "role",
        "lifecycle_control",
        "state",
        "generation",
        "ready",
        "transition_id",
        "transitioned_at",
        "updated_at",
        "ready_since",
        "last_used_at",
        "load_started_at",
        "ready_at",
        "last_requested_at",
        "last_completed_at",
        "active_requests",
        "open_streams",
        "pending_continuations",
        "weight_load_percent",
        "progress_quality",
        "overall_load_percent",
        "estimated_ready_seconds",
        "failure_class",
        "last_error_class",
        "retry_count",
        "adaptive_timeout_seconds",
        "idle_seconds",
        "automation_disabled",
        "lifecycle_failure_count",
        "automation_disabled_at",
        "idle_decision",
        "lifecycle_mode",
        "control",
    }
    serialized = json.dumps(payload)
    for unsafe in (
        "SENTINEL_FAILURE_DETAIL",
        "dgx-moa-dev-executor.service",
        str(controlled.models["executor"].destination),
        controlled.models["executor"].base_url,
    ):
        assert unsafe not in serialized
    assert unmanaged.status_code == 200
    assert unmanaged.json()["role"] == "planner"
    assert unmanaged.json()["state"] == "unmanaged"
    assert unmanaged.json()["transition_id"] is None
    assert unmanaged.json()["control"] == "unmanaged"
    assert unknown.status_code == 404
    assert unknown.json()["error"] == {
        "message": "unknown lifecycle role",
        "type": "invalid_request_error",
        "code": "model_role_not_found",
        "param": None,
    }


@pytest.mark.asyncio
async def test_health_success_marks_ready_and_later_api_retry_succeeds(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "inactive"})
    health_ready = False
    poll = asyncio.Event()

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return health_ready

    async def sleeper(seconds: float) -> None:
        await poll.wait()

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=sleeper,
    )
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        first = await direct_chat(app, "cold-then-ready")
        health_ready = True
        poll.set()
        for _ in range(100):
            if app.state.lifecycle_store.get("executor").state == "ready":
                break
            await asyncio.sleep(0)
        ready_record = app.state.lifecycle_store.get("executor")
        second = await direct_chat(app, "cold-then-ready")
        usage = app.state.usage.recent_requests()

    assert first.status_code == 503
    assert second.status_code == 200
    assert ready_record.state == "ready"
    assert ready_record.progress_value == 100.0
    assert ready_record.progress_quality == "estimated"
    assert ready_record.eta_seconds is None
    assert driver.calls.count(("start", "executor")) == 1
    assert stub_provider.calls == ["executor"]
    assert [record.status for record in usage] == ["failed", "completed"]
    assert [record.model_state for record in usage] == ["loading", "warm"]
    assert [record.load_triggered for record in usage] == [True, False]


@pytest.mark.asyncio
async def test_completed_retryable_failure_is_requeued_as_loading_on_the_next_request(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "inactive"})
    blocked = asyncio.Event()

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return False

    async def sleeper(seconds: float) -> None:
        await blocked.wait()

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=sleeper,
    )
    async with app.router.lifespan_context(app):
        cold = app.state.lifecycle_store.get("executor")
        queued = app.state.lifecycle_store.transition(
            "executor", "load_queued", expected_transition_id=cold.transition_id
        )
        app.state.lifecycle_store.transition(
            "executor",
            "failed",
            expected_transition_id=queued.transition_id,
            failure_class="health_timeout",
            retry_count=1,
        )
        completed = asyncio.create_task(asyncio.sleep(0))
        await completed
        app.state.lifecycle._tasks["executor"] = completed
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider

        response = await direct_chat(app, "retryable-failure")
        usage = assert_usage(app, "failed")

    assert response.status_code == 503
    assert response.headers["X-DGX-MOA-Model-State"] == "load_queued"
    assert response.headers["Retry-After"]
    assert json.loads(response.body)["error"]["code"] == "model_loading"
    assert usage.load_triggered is True
    assert usage.model_state == "loading"
    assert usage.retryable_failure_class == "model_loading"
    assert stub_provider.calls == []


@pytest.mark.asyncio
async def test_managed_request_rejects_an_unmapped_required_role_honestly(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
            "models": settings.model_dump()["models"]
            | {
                "reasoner": settings.model_dump()["models"]["reasoner"]
                | {"lifecycle_control": "external"}
            },
        }
    )
    driver = FakeLifecycleDriver({"executor": "inactive"})

    async def external_health(role: str) -> bool:
        assert role == "reasoner"
        return True

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"unmapped request slept for {seconds}")

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=external_health,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=reject_sleep,
    )
    async with app.router.lifespan_context(app):
        record = app.state.lifecycle_store.get("executor")
        for target in (
            "load_queued",
            "process_starting",
            "loading_weights",
            "initializing_engine",
            "warming_up",
            "ready",
        ):
            record = app.state.lifecycle_store.transition(
                "executor", target, expected_transition_id=record.transition_id
            )
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider

        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-orchestrated",
                messages=[{"role": "user", "content": "change four files"}],
                metadata={"expected_files": 4},
            ),
            Request({"type": "http", "app": app}),
            x_session_id="unmapped-planner",
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        usage = assert_usage(app, "failed")
        assert_no_request_leases(app)

    assert response.status_code == 503
    assert "retry-after" not in response.headers
    assert response.headers["X-DGX-MOA-Model-State"] == "unmanaged"
    assert response.headers["X-DGX-MOA-Weight-Load-Percent"] == "unavailable"
    payload = json.loads(response.body)
    assert payload["error"]["code"] == "model_not_managed"
    assert payload["model_state"] == {
        "role": "planner",
        "state": "unmanaged",
        "generation": None,
        "ready": False,
        "transition_id": None,
        "weight_load_percent": None,
        "progress_quality": "unavailable",
        "overall_load_percent": None,
        "estimated_ready_seconds": None,
    }
    assert usage.model_state == "cold"
    assert usage.load_triggered is False
    assert usage.retryable_failure_class is None
    assert stub_provider.calls == ["reasoner", "executor"]
    assert driver.calls == [("status", "executor")]


@pytest.mark.asyncio
async def test_retry_exhaustion_returns_non_loading_model_failure(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    from dgx_moa.lifecycle import MAX_LOAD_RETRIES

    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
        }
    )
    driver = FakeLifecycleDriver({"executor": "failed"})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"exhausted load probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"exhausted load slept for {seconds}")

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=reject_health,
        lifecycle_clock=lambda: 100.0,
        lifecycle_sleeper=reject_sleep,
    )
    async with app.router.lifespan_context(app):
        cold = app.state.lifecycle_store.get("executor")
        queued = app.state.lifecycle_store.transition(
            "executor", "load_queued", expected_transition_id=cold.transition_id
        )
        app.state.lifecycle_store.transition(
            "executor",
            "failed",
            expected_transition_id=queued.transition_id,
            failure_class="Start Timeout",
            failure_detail="SENTINEL_FAILURE_DETAIL",
            retry_count=MAX_LOAD_RETRIES,
        )
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await direct_chat(app, "retry-exhausted")
        usage = assert_usage(app, "failed")
        assert_no_request_leases(app)

    assert response.status_code == 503
    assert "retry-after" not in response.headers
    assert response.headers["X-DGX-MOA-Model-State"] == "failed"
    payload = json.loads(response.body)
    assert payload["error"]["type"] == "model_unavailable"
    assert payload["error"]["code"] == "model_load_failed"
    assert payload["model_state"]["state"] == "failed"
    assert payload["model_state"]["failure_class"] == "start_timeout"
    assert payload["model_state"]["retry_count"] == MAX_LOAD_RETRIES
    assert "SENTINEL_FAILURE_DETAIL" not in json.dumps(payload)
    assert usage.model_state == "cold"
    assert usage.load_triggered is False
    assert usage.retryable_failure_class is None
    assert driver.calls == [("status", "executor")]
    assert stub_provider.calls == []


def test_auth_models_and_tool_call_preservation(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/models").status_code == 401
        headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "session-1"}
        models = client.get("/v1/models", headers=headers).json()
        assert [model["id"] for model in models["data"]] == [
            "dgx-moa",
            "dgx-moa-fast",
            "dgx-moa-agent",
            "dgx-moa-orchestrated",
            "dgx-moa-chat",
        ]
        assert all(model["context_length"] == 65536 for model in models["data"])
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        assert response.status_code == 200
        assert response.headers["x-session-id"] == "session-1"
        call = response.json()["choices"][0]["message"]["tool_calls"][0]
        assert call["id"] == "call-preserved"
        assert response.json()["usage"]["total_tokens"] == 3
        assert stub_provider.calls == ["reasoner", "executor"]


def test_multiple_api_tokens_are_attributed_by_safe_id(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    configured = Settings.model_validate(
        settings.model_dump()
        | {"api_key": None, "api_keys": {"opencode": "token-one", "hermes": "token-two"}}
    )
    with client_with_stub(configured, stub_provider) as client:
        for token in ("token-one", "token-two"):
            response = client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={"model": "dgx-moa-fast", "messages": [{"role": "user", "content": "x"}]},
            )
            assert response.status_code == 200
        assert (
            client.get("/v1/models", headers={"Authorization": "Bearer unknown"}).status_code == 401
        )
        records = client.app.state.usage.recent_requests()
        per_token = client.app.state.usage.api_token_statistics()

    assert {record.api_token_id for record in records} == {"opencode", "hermes"}
    assert per_token["opencode"]["requests"] == 1
    assert per_token["hermes"]["requests"] == 1


def test_required_reasoner_failure_is_typed_and_never_degrades(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    async def fail_reasoner(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "reasoner":
            raise httpx.ConnectError("offline")
        return await StubProvider.complete(stub_provider, role, model, request, **kwargs)

    stub_provider.complete = fail_reasoner  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa", "messages": [{"role": "user", "content": "work"}]},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "reasoner_required_unavailable"
    assert response.headers["X-DGX-MOA-Model-Role"] == "reasoner"
    assert stub_provider.calls == []


def test_executor_selected_planner_gets_usage_and_lease_tracking(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def select_planner(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and (
            request.get("response_format", {}).get("json_schema", {}).get("name")
            == "orchestration_decision"
        ):
            stub_provider.calls.append(role)
            stub_provider.requests.append(request)
            stub_provider.call_options.append(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "action": "invoke_agents",
                                    "required_agents": ["planner"],
                                    "optional_agents": [],
                                    "reason": {"planner": "decomposition needed"},
                                    "parallelizable": False,
                                    "continue_after": "synthesize",
                                    "confidence": 0.8,
                                }
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = select_planner  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "make the focused change"}],
                "metadata": {"target_clear": True, "expected_files": 1},
            },
        )
        usage = client.app.state.usage.recent_requests()[0]
        planner_rows = client.app.state.usage.recent_role_requests("planner")
        assert_no_request_leases(client.app)

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "planner", "executor"]
    assert usage.roles_required == ("reasoner", "executor", "planner")
    assert len(planner_rows) == 1 and planner_rows[0].success is True


def test_executor_selected_cold_planner_triggers_load_and_typed_usage(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {
                role: f"dgx-moa-dev-{role}.service" for role in ("reasoner", "executor", "planner")
            },
        }
    )
    driver = FakeLifecycleDriver(
        {"reasoner": "active", "executor": "active", "planner": "inactive"}
    )
    original = stub_provider.complete

    async def select_planner(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and (
            request.get("response_format", {}).get("json_schema", {}).get("name")
            == "orchestration_decision"
        ):
            stub_provider.calls.append(role)
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "action": "invoke_agents",
                                    "required_agents": ["planner"],
                                    "optional_agents": [],
                                    "reason": {"planner": "decomposition needed"},
                                    "parallelizable": False,
                                    "continue_after": "synthesize",
                                    "confidence": 0.8,
                                }
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    async def health_probe(role: str) -> bool:
        return role != "planner"

    stub_provider.complete = select_planner  # type: ignore[method-assign]
    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "make the focused change"}],
                "metadata": {"target_clear": True, "expected_files": 1},
            },
        )
        for _ in range(1_000):
            if ("start", "planner") in driver.calls:
                break
            time.sleep(0.001)
        usage = app.state.usage.recent_requests()[0]
        planner_rows = app.state.usage.recent_role_requests("planner")
        assert_no_request_leases(app)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_loading"
    assert response.headers["X-DGX-MOA-Model-Role"] == "planner"
    assert stub_provider.calls == ["reasoner", "executor"]
    assert usage.roles_required == ("reasoner", "executor", "planner")
    assert usage.retryable_failure_class == "model_loading"
    assert len(planner_rows) == 1
    assert planner_rows[0].load_triggered is True
    assert planner_rows[0].failure_class == "model_loading"
    assert driver.calls.count(("start", "planner")) == 1


def test_policy_selected_cold_reviewer_triggers_load_before_review(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {
                role: f"dgx-moa-dev-{role}.service" for role in ("reasoner", "executor", "reviewer")
            },
        }
    )
    driver = FakeLifecycleDriver(
        {"reasoner": "active", "executor": "active", "reviewer": "inactive"}
    )

    async def health_probe(role: str) -> bool:
        return role != "reviewer"

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "review this change"}],
                "metadata": {"diff_summary": "bounded diff"},
            },
        )
        for _ in range(1_000):
            if ("start", "reviewer") in driver.calls:
                break
            time.sleep(0.001)
        usage = app.state.usage.recent_requests()[0]
        reviewer_rows = app.state.usage.recent_role_requests("reviewer")
        assert_no_request_leases(app)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_loading"
    assert response.headers["X-DGX-MOA-Model-Role"] == "reviewer"
    assert stub_provider.calls == ["reasoner", "executor"]
    assert usage.roles_required == ("reasoner", "executor", "reviewer")
    assert usage.model_state == "loading"
    assert len(reviewer_rows) == 1
    assert reviewer_rows[0].load_triggered is True
    assert reviewer_rows[0].failure_class == "model_loading"
    assert driver.calls.count(("start", "reviewer")) == 1


def test_policy_selected_ready_reviewer_gets_one_dynamic_lease(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {
                role: f"dgx-moa-dev-{role}.service" for role in ("reasoner", "executor", "reviewer")
            },
        }
    )
    driver = FakeLifecycleDriver({"reasoner": "active", "executor": "active", "reviewer": "active"})

    async def health_probe(role: str) -> bool:
        return role in {"reasoner", "executor", "reviewer"}

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health_probe,
    )
    acquisitions: list[tuple[tuple[str, ...], str]] = []
    with TestClient(app) as client:
        original = app.state.lifecycle.acquire_request_leases

        async def track_acquisition(request_id, roles, *, kind, require_ready):  # type: ignore[no-untyped-def]
            role_tuple = tuple(roles)
            leases = await original(
                request_id,
                role_tuple,
                kind=kind,
                require_ready=require_ready,
            )
            acquisitions.append((role_tuple, kind))
            return leases

        app.state.lifecycle.acquire_request_leases = track_acquisition
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "review this change"}],
                "metadata": {"diff_summary": "bounded diff"},
            },
        )
        reviewer_rows = app.state.usage.recent_role_requests("reviewer")
        assert_no_request_leases(app)

    assert response.status_code == 200
    assert acquisitions.count((("reviewer",), "active_request")) == 1
    assert len(reviewer_rows) == 1
    assert reviewer_rows[0].success is True


def test_dynamically_selected_unconfigured_role_is_typed_unmanaged(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    models = settings.model_dump()["models"]
    models.pop("planner")
    controlled = Settings.model_validate(settings.model_dump() | {"models": models})
    app = create_app(controlled)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "change four files"}],
                "metadata": {"expected_files": 4},
            },
        )
        usage = app.state.usage.recent_requests()[0]
        planner_rows = app.state.usage.recent_role_requests("planner")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_managed"
    assert response.headers["X-DGX-MOA-Model-Role"] == "planner"
    assert stub_provider.calls == ["reasoner", "executor"]
    assert usage.roles_required == ("reasoner", "executor", "planner")
    assert usage.model_state == "cold"
    assert len(planner_rows) == 1
    assert planner_rows[0].failure_class == "model_unavailable"


def test_nonstream_usage_is_content_free_and_uses_opaque_server_ids(
    settings, stub_provider: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    block_profile_control(monkeypatch)
    raw_session = "SENTINEL_RAW_SESSION_1f3c8d"
    raw_prompt = "SENTINEL_PROMPT_074f95"
    raw_response = "SENTINEL_RESPONSE_f92bb1"
    raw_tool = "SENTINEL_TOOL_953a6e"
    raw_user_agent = "OpenAI/Python 1.109.1 SENTINEL_RAW_UA_4bf4ac"
    raw_secret = "SENTINEL_SECRET_8102d4"

    async def response_with_usage(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": raw_response},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }

    stub_provider.complete = response_with_usage  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": raw_session,
                "User-Agent": raw_user_agent,
            },
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": raw_prompt}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": raw_tool,
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                "metadata": {"secret": raw_secret},
            },
        )
        record = assert_usage(client.app, "completed")
        report = client.get(
            "/v1/admin/runtime-status",
            headers={"Authorization": "Bearer test-secret"},
        )
        with sqlite3.connect(settings.state_db) as database:
            usage_row = database.execute("SELECT * FROM request_usage").fetchone()
            role_usage_row = database.execute("SELECT * FROM role_request_usage").fetchone()
        role_usage = client.app.state.usage.recent_role_requests("executor")

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == raw_response
    assert record.session_id != raw_session
    assert record.client_class == "openai-python"
    assert record.model_alias == "dgx-moa-fast"
    assert record.runtime_mode == "fast"
    assert record.request_class == "plain_chat"
    assert record.roles_required == ("executor",)
    assert record.first_byte_at is not None
    assert record.accepted_at <= record.first_byte_at <= record.completed_at
    assert record.streaming is False
    assert record.model_state == "warm"
    assert record.load_triggered is False
    assert record.retryable_failure_class is None
    assert (record.prompt_tokens, record.completion_tokens, record.total_tokens) == (2, 3, 5)
    assert len(role_usage) == 1
    assert role_usage[0].request_id == record.request_id
    assert role_usage[0].role == "executor"
    assert role_usage[0].success is True
    assert role_usage[0].cold_or_warm == "warm"
    assert role_usage[0].session_id_hash != raw_session
    assert report.status_code == 404
    persisted_usage = repr((usage_row, role_usage_row))
    serialized_record = record.model_dump_json()
    for sentinel in (
        raw_session,
        raw_prompt,
        raw_response,
        raw_tool,
        raw_user_agent,
        raw_secret,
        "test-secret",
    ):
        assert sentinel not in persisted_usage
        assert sentinel not in serialized_record


def test_usage_correlates_repeated_sessions_without_storing_the_raw_value(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    raw_session = "SENTINEL_CORRELATED_SESSION_51c8d4"
    with client_with_stub(settings, stub_provider) as client:
        for _ in range(2):
            response = client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-secret",
                    "X-Session-ID": raw_session,
                },
                json={
                    "model": "dgx-moa-fast",
                    "messages": [{"role": "user", "content": "work"}],
                },
            )
            assert response.status_code == 200
        records = client.app.state.usage.recent_requests()

    assert len(records) == 2
    assert records[0].request_id != records[1].request_id
    assert records[0].session_id == records[1].session_id
    assert records[0].session_id != raw_session


def test_standard_request_gets_safe_identity_and_terminal_trace(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    session_id = "standard-terminal"
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        state = client.app.state.store.get(session_id)
        trace = assert_terminal_evidence(settings, client.app.state.store, session_id, "completed")

    assert response.status_code == 200
    assert state and state.task_id == session_id
    assert state.repository == {
        "workspace_identifier": "external-api",
        "identity_quality": "client_unspecified",
    }
    assert trace["task_id"] == session_id
    assert trace["workspace_identity"]["workspace_identifier"] == "external-api"
    assert all(decision["task_id"] == session_id for decision in trace["agent_decisions"])


def test_executor_request_fields_are_preserved(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
                "tools": tools,
                "tool_choice": "required",
                "parallel_tool_calls": False,
                "temperature": 0.2,
                "top_p": 0.8,
                "max_tokens": 4096,
                "stop": ["END"],
                "stream": True,
                "stream_options": {"include_usage": True},
                "response_format": {"type": "text"},
                "seed": 7,
            },
        )

    assert response.status_code == 200
    expected = {
        "tools": tools,
        "tool_choice": "required",
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 4096,
        "stop": ["END"],
        "parallel_tool_calls": False,
        "stream_options": {"include_usage": True},
        "response_format": {"type": "text"},
        "seed": 7,
    }
    assert expected.items() <= stub_provider.requests[-1].items()


def test_default_executor_output_budget_is_4096(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
            },
        )

    assert response.status_code == 200
    assert stub_provider.requests[-1]["max_tokens"] == 4096


def test_excessive_executor_output_budget_is_rejected(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
                "max_tokens": 16_385,
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "max_tokens exceeds server maximum 16384",
        "type": "invalid_request_error",
        "code": "invalid_request",
        "param": "max_tokens",
    }


def test_excessive_budget_preserves_reused_completed_session(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        client.app.state.store.save(
            SessionState(
                session_id="completed-budget",
                objective="finished task",
                phase=Phase.COMPLETED,
                final_status="completed",
                no_progress_count=2,
            )
        )
        before = client.app.state.store.get("completed-budget")
        events_before = client.app.state.store.events("completed-budget")
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "completed-budget",
            },
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "new task"}],
                "metadata": {"no_progress": True},
                "max_tokens": 16_385,
            },
        )
        state = client.app.state.store.get("completed-budget")
        events = client.app.state.store.events("completed-budget")

    assert response.status_code == 400
    assert state == before
    assert events == events_before
    assert stub_provider.calls == []


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"tool_choice": "required"}, "tool_choice requires tools"),
        ({"parallel_tool_calls": False}, "parallel_tool_calls requires tools"),
        (
            {"stream_options": {"include_usage": True}},
            "stream_options requires stream=true",
        ),
    ],
)
def test_invalid_request_field_combinations_return_typed_validation_errors(
    settings,
    stub_provider: StubProvider,
    fields: dict[str, object],
    message: str,
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
                **fields,
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == message
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("model", "reasoner_mode", "message"),
    [
        (
            "dgx-moa-agent",
            "required",
            "metadata.reasoner_mode requires dgx-moa-orchestrated",
        ),
        (
            "dgx-moa-orchestrated",
            "automatic",
            "Reasoner is required; use dgx-moa-fast to bypass it",
        ),
    ],
)
def test_reasoner_policy_requires_explicit_valid_orchestrated_mode(
    settings,
    stub_provider: StubProvider,
    model: str,
    reasoner_mode: str,
    message: str,
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "work"}],
                "metadata": {"reasoner_mode": reasoner_mode},
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == message
    assert stub_provider.calls == []


@pytest.mark.parametrize(
    ("model", "expected_calls"),
    [
        ("dgx-moa-chat", ["executor"]),
        ("dgx-moa-fast", ["executor"]),
        ("dgx-moa", ["reasoner", "executor"]),
        ("dgx-moa-agent", ["reasoner", "executor"]),
    ],
)
def test_core_and_fast_profile_roles(
    settings, stub_provider: StubProvider, model: str, expected_calls: list[str]
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"authentication": True},
            },
        )
    assert response.status_code == 200
    assert stub_provider.calls == expected_calls


def test_chat_returns_normal_assistant_content(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    async def natural(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)
        return {
            "id": "chatcmpl-natural",
            "model": "dgx-moa-executor",
            "created": 123,
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello from executor."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6},
        }

    stub_provider.complete = natural  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-chat",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        usage = assert_usage(client.app, "completed")
    assert response.json()["choices"][0] == {
        "message": {"role": "assistant", "content": "Hello from executor."},
        "finish_reason": "stop",
    }
    assert response.json()["id"] == "chatcmpl-natural"
    assert response.json()["created"] == 123
    assert response.json()["model"] == "dgx-moa-executor"
    assert response.json()["usage"] == {
        "prompt_tokens": 2,
        "completion_tokens": 4,
        "total_tokens": 6,
    }
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (2, 4, 6)


def test_nonstream_omits_unstorable_token_statistics_without_changing_response(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    huge = 2**63

    async def huge_usage(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "still valid"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": huge,
                "completion_tokens": True,
                "total_tokens": "5",
            },
        }

    stub_provider.complete = huge_usage  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-fast", "messages": [{"role": "user", "content": "x"}]},
        )
        usage = assert_usage(client.app, "completed")

    assert response.status_code == 200
    assert response.json()["usage"] == {
        "prompt_tokens": huge,
        "completion_tokens": True,
        "total_tokens": "5",
    }
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens is None


def test_orchestrated_mode_uses_policy_roles(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "change four files"}],
                "metadata": {"expected_files": 4},
            },
        )
    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "planner", "executor"]


def test_security_architecture_without_implementation_evidence_skips_reviewer(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "design the security architecture"}],
                "metadata": {"architecture": True, "authentication": True},
            },
        )
        usage = client.app.state.usage.recent_requests()[0]

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "planner", "executor"]
    assert usage.roles_required == ("reasoner", "executor", "planner")


def test_role_calls_receive_exact_stage_timeouts(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "review this change"}],
                "metadata": {"diff_summary": "one verified change"},
            },
        )

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "reviewer", "executor"]
    assert stub_provider.call_options == [
        {"timeout_seconds": 120, "stage": "reasoner"},
        {"timeout_seconds": 120, "stage": "orchestration"},
        {"timeout_seconds": 120, "stage": "reviewer"},
        {"timeout_seconds": 900, "stage": "executor_total"},
    ]


def test_orchestrated_timing_records_role_durations(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "role-timing"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "review this change"}],
                "metadata": {"diff_summary": "one verified change"},
            },
        )
        state = client.app.state.store.get("role-timing")
        timing_event = next(
            event
            for event in client.app.state.store.events("role-timing")
            if event["event_type"] == "request_timing"
        )

    assert response.status_code == 200
    assert state
    assert all(state.timings_ms[stage] >= 0 for stage in ("executor_total", "reviewer"))
    assert timing_event["payload"]["stage_status"] == {
        "executor_total": "completed",
        "reviewer": "completed",
    }


def test_request_timing_event_is_numeric_and_content_free(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    secret_content = "never-copy-this-prompt-or-response"
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "timed"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": secret_content}],
            },
        )
        timing_events = [
            event
            for event in client.app.state.store.events("timed")
            if event["event_type"] == "request_timing"
        ]

    assert response.status_code == 200
    assert len(timing_events) == 1
    payload = timing_events[0]["payload"]
    assert set(payload) == {"timings_ms", "stage_status"}
    timings = payload["timings_ms"]
    assert set(timings) == {
        "accepted",
        "upstream_start",
        "first_upstream_byte",
        "first_downstream_byte",
        "completed",
        "executor_total",
    }
    assert all(isinstance(value, int | float) and value >= 0 for value in timings.values())
    assert [
        timings[key]
        for key in (
            "accepted",
            "upstream_start",
            "first_upstream_byte",
            "first_downstream_byte",
            "completed",
        )
    ] == sorted(
        timings[key]
        for key in (
            "accepted",
            "upstream_start",
            "first_upstream_byte",
            "first_downstream_byte",
            "completed",
        )
    )
    assert payload["stage_status"] == {"executor_total": "completed"}
    assert secret_content not in json.dumps(payload)


@pytest.mark.parametrize(
    ("stage", "model", "metadata", "stream"),
    [
        ("planner", "dgx-moa-orchestrated", {"expected_files": 4}, False),
        ("executor_first_byte", "dgx-moa-agent", {}, True),
        ("executor_total", "dgx-moa-agent", {}, False),
        (
            "reviewer",
            "dgx-moa-orchestrated",
            {"authentication": True, "diff_summary": "auth changed"},
            False,
        ),
    ],
)
def test_stage_timeout_returns_exact_typed_error(
    settings,
    stub_provider: StubProvider,
    stage: str,
    model: str,
    metadata: dict[str, object],
    stream: bool,
) -> None:  # type: ignore[no-untyped-def]
    session_id = f"stage-timeout-{stage}"
    timeout_type = getattr(providers, "StageTimeout", TimeoutError)
    original_complete = stub_provider.complete
    original_stream = stub_provider.stream

    async def timed_complete(role, model_config, request, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("stage") == stage:
            raise timeout_type(stage)
        return await original_complete(role, model_config, request, **kwargs)

    async def timed_stream(role, model_config, request, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("stage") == stage:
            raise timeout_type(stage)
        return await original_stream(role, model_config, request, **kwargs)

    stub_provider.complete = timed_complete  # type: ignore[method-assign]
    stub_provider.stream = timed_stream  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": session_id,
            },
            json={
                "model": model,
                "stream": stream,
                "messages": [{"role": "user", "content": "work"}],
                "metadata": metadata,
            },
        )
        trace = assert_terminal_evidence(settings, client.app.state.store, session_id, "timed_out")
        usage = assert_usage(client.app, "timed_out")

    assert response.status_code == 504
    assert response.json()["error"] == {
        "message": f"{stage} timed out",
        "type": "timeout_error",
        "code": f"{stage}_timeout",
        "param": None,
    }
    assert trace["final_status"] == "failed"
    assert usage.retryable_failure_class == f"{stage}_timeout"


def test_orchestrated_assistant_answer_without_evidence_skips_review(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def natural(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and not request.get("response_format"):
            stub_provider.calls.append(role)
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "normal answer"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = natural  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "answer normally"}],
                "metadata": {"completion_evidence": "claimed"},
            },
        )

    assert response.status_code == 200
    assert stub_provider.calls == ["reasoner", "executor", "executor"]


@pytest.mark.parametrize("failure", ["http", "timeout", "value"])
def test_low_risk_review_failure_preserves_executor_response(
    settings, stub_provider: StubProvider, failure: str
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def fail_review(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and not request.get("response_format"):
            return {
                "id": "chatcmpl-preserved",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "executor output"},
                        "finish_reason": "stop",
                    }
                ],
            }
        if role == "reviewer":
            if failure == "http":
                raise httpx.ConnectError("review unavailable")
            if failure == "timeout":
                raise httpx.ReadTimeout("review timed out")
            raise ValueError("invalid review")
        return await original(role, model, request, **kwargs)

    stub_provider.complete = fail_review  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": failure},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "review this"}],
                "metadata": {"diff_summary": "changed one implementation"},
            },
        )
        state = client.app.state.store.get(failure)
        events = client.app.state.store.events(failure)

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "executor output"
    assert state and state.review_status == "failed"
    assert state.observability_degraded is True
    assert state.observability_status == "degraded"
    assert any(event["event_type"] == "review_failed" for event in events)


@pytest.mark.parametrize("failure", ["value", "timeout", "http_4xx"])
def test_high_risk_review_failure_returns_typed_bad_gateway(
    settings, stub_provider: StubProvider, failure: str
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def fail_review(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and not request.get("response_format"):
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "unreviewed output"},
                        "finish_reason": "stop",
                    }
                ]
            }
        if role == "reviewer":
            if failure == "timeout":
                raise httpx.ReadTimeout("review timed out")
            if failure == "http_4xx":
                response = httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "invalid reviewer request",
                            "type": "invalid_request_error",
                            "code": "invalid_request",
                            "param": None,
                        }
                    },
                    request=httpx.Request("POST", model.base_url),
                )
                raise httpx.HTTPStatusError(
                    "invalid reviewer request", request=response.request, response=response
                )
            raise ValueError("invalid review")
        return await original(role, model, request, **kwargs)

    stub_provider.complete = fail_review  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": f"high-risk-{failure}",
            },
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "change authentication"}],
                "metadata": {"authentication": True, "diff_summary": "auth changed"},
            },
        )
        state = client.app.state.store.get(f"high-risk-{failure}")
        events = client.app.state.store.events(f"high-risk-{failure}")

    assert response.status_code == (504 if failure == "timeout" else 502)
    assert response.json()["error"]["type"] == (
        "timeout_error" if failure == "timeout" else "backend_error"
    )
    assert state and state.review_status == "failed"
    assert any(event["event_type"] == "review_failed" for event in events)


def test_length_finish_is_preserved_and_never_completes_session(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def truncated(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and not request.get("response_format"):
            return {
                "id": "chatcmpl-truncated",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "partial output"},
                        "finish_reason": "length",
                    }
                ],
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = truncated  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        client.app.state.store.save(
            SessionState(
                session_id="truncated",
                objective="previous task",
                phase=Phase.COMPLETED,
                final_status="completed",
            )
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "truncated"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "make a change"}],
                "metadata": {
                    "executor_complete": True,
                    "diff_summary": "changed one implementation",
                    "completion_evidence": {"tests pass": "exit 0"},
                },
            },
        )
        state = client.app.state.store.get("truncated")

    assert response.status_code == 200
    assert response.json()["choices"][0]["finish_reason"] == "length"
    assert state and state.finish_reasons == ["length"]
    assert state.truncated is True
    assert state.final_status != "completed"
    assert state.phase != "completed"


def test_request_headers_set_trace_identity(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    headers = {
        "Authorization": "Bearer test-secret",
        "X-Session-ID": "header-identity",
        "X-Runtime-Channel": "dev",
        "X-Trace-Origin": "validation",
        "X-Task-ID": "task-1",
        "X-Workspace-Path": "/tmp/repo",
        "X-Workspace-ID": "repo",
        "X-Repository-Branch": "dev",
        "X-Repository-Commit": "abc",
        "X-Dirty-State": "clean",
    }
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        assert response.status_code == 200
        state = client.app.state.store.get("header-identity")
        assert state and state.task_id == "task-1"
        assert state.repository == {
            "workspace_path": "/tmp/repo",
            "workspace_identifier": "repo",
            "current_branch": "dev",
            "current_commit": "abc",
            "dirty_status": "clean",
        }
        continuation = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "header-identity",
            },
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        continued_state = client.app.state.store.get("header-identity")

    assert continuation.status_code == 200
    assert continued_state and continued_state.task_id == "task-1"
    assert continued_state.repository["workspace_identifier"] == "repo"


def test_request_json_cannot_select_runtime_trace_provenance(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "body-provenance",
            },
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "work"}],
                "metadata": {"runtime_channel": "main", "trace_origin": "production"},
            },
        )
        state = client.app.state.store.get("body-provenance")

    assert response.status_code == 200
    assert state and state.runtime_channel == settings.runtime_channel
    assert state.trace_origin == settings.trace_origin


def test_tool_result_continuation_uses_same_session(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def continue_after_tool(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and any(
            message.get("role") == "tool" for message in request["messages"]
        ):
            return {
                "id": "chatcmpl-final",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "tool result received"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 4},
            }
        return await original(role, model, request)

    stub_provider.complete = continue_after_tool  # type: ignore[method-assign]
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "continued"}
    with client_with_stub(settings, stub_provider) as client:
        first = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        call = first.json()["choices"][0]["message"]
        second = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"tool_name":"shell","stdout":"ok","exit_code":0}',
                    },
                ],
            },
        )
        assert second.status_code == 200
        assert second.json()["choices"][0]["message"]["content"] == "tool result received"
        state = client.app.state.store.get("continued")
        assert state and state.tool_results == [
            {
                "tool_name": "shell",
                "arguments": {},
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 0,
                "truncated": False,
            }
        ]


def test_failed_tool_evidence_reinvokes_reasoner_and_overrides_self_confidence(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def finish_after_failed_tool(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor" and any(
            message.get("role") == "tool" for message in request["messages"]
        ):
            stub_provider.calls.append(role)
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "failure observed"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 4},
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = finish_after_failed_tool  # type: ignore[method-assign]
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "failed-tool"}
    with client_with_stub(settings, stub_provider) as client:
        first = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "work"}]},
        )
        call = first.json()["choices"][0]["message"]
        second = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": json.dumps(
                            {
                                "tool_name": "shell",
                                "stderr": "assertion failed",
                                "exit_code": 2,
                            }
                        ),
                    },
                ],
            },
        )
        state = client.app.state.store.get("failed-tool")
        reasoner_requests = [
            request
            for request in stub_provider.requests
            if request.get("response_format", {}).get("json_schema", {}).get("name")
            == "reasoner_contribution"
        ]

    assert first.status_code == 200
    assert second.status_code == 200
    assert stub_provider.calls.count("reasoner") == 2
    assert state and state.failures
    assert state.derived_confidence == "low"
    assert "assertion failed" in json.dumps(reasoner_requests[-1])


def test_title_request_does_not_set_the_work_session_objective(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "shared-session"}
    with client_with_stub(settings, stub_provider) as client:
        title = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "user", "content": "Create AGENTS.md"},
                    {"role": "user", "content": "Generate a title for this conversation:\n"},
                ],
            },
        )
        work = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "Create AGENTS.md"}],
            },
        )

        assert title.status_code == 200
        assert work.status_code == 200
        title_state = client.app.state.store.get("shared-session:title")
        work_state = client.app.state.store.get("shared-session")
        assert title_state and title_state.objective.startswith("Generate a title")
        assert work_state and work_state.objective == "Create AGENTS.md"


def test_current_opencode_title_prompt_isolated_from_trailing_work_prompt(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "shared-session"}
    with client_with_stub(settings, stub_provider) as client:
        title = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a title generator. You output ONLY a thread title. "
                            "Nothing else."
                        ),
                    },
                    {"role": "user", "content": "Generate a title for this conversation:\n"},
                    {
                        "role": "user",
                        "content": "Architecture task: inspect authentication boundaries.",
                    },
                ],
            },
        )

        assert title.status_code == 200
        title_state = client.app.state.store.get("shared-session:title")
        work_state = client.app.state.store.get("shared-session")
        assert title_state and title_state.objective.startswith("Generate a title")
        assert work_state is None
        assert stub_provider.calls == ["executor"]


def test_auth_enabled_invalid_key_returns_401(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.get("/v1/models", headers={"Authorization": "Bearer definitely-wrong"})
        assert response.status_code == 401


def test_auth_disabled_allows_inference_headers_or_none(
    settings, stub_provider: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    block_profile_control(monkeypatch)
    disabled = Settings.model_validate(
        settings.model_dump() | {"auth_enabled": False, "api_key": None}
    )
    with client_with_stub(disabled, stub_provider) as client:
        assert client.get("/v1/models").status_code == 200
        assert (
            client.get("/v1/models", headers={"Authorization": "Bearer unused"}).status_code == 200
        )
        assert client.get("/admin/profile").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin/profile"),
        ("POST", "/admin/profile/resident"),
        ("POST", "/admin/profile/judge"),
        ("POST", "/admin/profile/restore"),
        ("GET", "/v1/admin/runtime-status"),
    ],
)
@pytest.mark.parametrize("authorization", [None, "Bearer test-secret"])
def test_admin_flag_is_checked_before_authentication_for_every_admin_endpoint(
    settings,
    stub_provider: StubProvider,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    authorization: str | None,
) -> None:  # type: ignore[no-untyped-def]
    block_profile_control(monkeypatch)
    headers = {"Authorization": authorization} if authorization else {}
    with client_with_stub(settings, stub_provider) as client:
        response = client.request(method, path, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "admin API is disabled"


def test_runtime_status_requires_admin_auth_and_returns_safe_usage(
    settings, stub_provider: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    block_profile_control(monkeypatch)
    enabled = Settings.model_validate(settings.model_dump() | {"admin_api_enabled": True})

    def fake_command(*args: str) -> str:
        if args[0] == "systemctl":
            return "ActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0"
        if args[0] == "git":
            return "abc123"
        return ""

    monkeypatch.setattr("dgx_moa.runtime_status.command", fake_command)
    monkeypatch.setattr("dgx_moa.runtime_status.memory_available", lambda: 123)
    raw_session = "SENTINEL_ADMIN_SESSION_e72d60"
    raw_user_agent = "curl/8.14.1 SENTINEL_ADMIN_UA_26c9c7"
    with client_with_stub(enabled, stub_provider) as client:
        created = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": raw_session,
                "User-Agent": raw_user_agent,
            },
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "SENTINEL_ADMIN_PROMPT_41af3e"}],
            },
        )
        unauthorized = client.get("/v1/admin/runtime-status")
        authorized = client.get(
            "/v1/admin/runtime-status",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert created.status_code == 200
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    payload = authorized.json()
    assert payload["usage"]["active_request_count"] == 0
    assert payload["usage"]["last_request"]["client_class"] == "curl"
    assert payload["usage"]["request_statistics"]["request_count"] == 1
    assert payload["usage"]["role_statistics"]["executor"]["request_count"] == 1
    assert payload["usage"]["adaptive_idle_timeout_seconds"] is None
    serialized = json.dumps(payload, sort_keys=True)
    for sentinel in (
        raw_session,
        raw_user_agent,
        "SENTINEL_ADMIN_PROMPT_41af3e",
        "test-secret",
        str(settings.state_db),
        "dgx-moa-executor.service",
        "systemctl",
    ):
        assert sentinel not in serialized


def test_secret_never_appears_in_logs(settings, stub_provider: StubProvider, caplog) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        assert (
            client.get("/v1/models", headers={"Authorization": "Bearer test-secret"}).status_code
            == 200
        )
    assert "test-secret" not in caplog.text


def test_profile_aware_readiness(settings, stub_provider: StubProvider, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class FakeAsyncClient:
        def __init__(self, timeout) -> None:  # type: ignore[no-untyped-def]
            self.timeout = timeout

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args) -> None:  # type: ignore[no-untyped-def]
            return None

        async def get(self, url: str) -> httpx.Response:
            status_code = (
                200 if url.endswith(":8101/v1/models") or url.endswith(":8104/v1/models") else 503
            )
            return httpx.Response(status_code, request=httpx.Request("GET", url))

    monkeypatch.setattr("dgx_moa.api.httpx.AsyncClient", FakeAsyncClient)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        app.state.profiles.record("resident")
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "profile": "resident",
            "services": {
                "executor": "ready",
                "planner": "stopped",
                "reviewer": "stopped",
                "reasoner": "ready",
                "judge": "stopped",
            },
            "auth_enabled": True,
        }
        app.state.profiles.transition("judge")
        transition = client.get("/readyz")
        assert transition.status_code == 503
        assert transition.json()["status"] == "transitioning"


def test_ollama_readiness_requires_resident_model_and_configured_context(settings) -> None:  # type: ignore[no-untyped-def]
    model = settings.models["reasoner"].model_copy(
        update={"provider": "ollama", "served_name": "Qwythos-v2-9B:Q5"}
    )
    request = httpx.Request("GET", "http://ollama/api/ps")
    evicted = httpx.Response(200, json={"models": []}, request=request)
    short_context = httpx.Response(
        200,
        json={
            "models": [
                {
                    "name": "Qwythos-v2-9B:Q5",
                    "model": "Qwythos-v2-9B:Q5",
                    "context_length": 8192,
                }
            ]
        },
        request=request,
    )
    ready = httpx.Response(
        200,
        json={
            "models": [
                {
                    "name": "Qwythos-v2-9B:Q5",
                    "model": "Qwythos-v2-9B:Q5",
                    "context_length": 65536,
                }
            ]
        },
        request=request,
    )

    assert ollama_model_ready(evicted, model) is False
    assert ollama_model_ready(short_context, model) is False
    assert ollama_model_ready(ready, model) is True


def test_evicted_external_reasoner_returns_typed_unavailable(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    models = settings.model_dump()["models"]
    models["reasoner"] |= {"provider": "ollama", "lifecycle_control": "external"}
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
            "models": models,
        }
    )
    driver = FakeLifecycleDriver({"executor": "active"})

    async def health(role: str) -> bool:
        return role != "reasoner"

    app = create_app(
        controlled,
        lifecycle_driver=driver,
        lifecycle_health_probe=health,
    )
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa",
                "messages": [{"role": "user", "content": "work"}],
            },
        )

    assert response.status_code == 503
    assert response.headers["X-DGX-MOA-Model-Role"] == "reasoner"
    assert response.json()["error"]["code"] == "model_load_failed"
    assert stub_provider.calls == []


def test_coding_request_retries_during_judge(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        app.state.profiles.record("judge")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"


def test_pending_adjudication_runs_only_in_exclusive_judge_profile(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    session_id = "judge-pending"
    with client_with_stub(settings, stub_provider) as client:
        state = SessionState(
            session_id=session_id,
            objective="Resolve a high-risk disagreement",
            judge_status="required",
            pending_judge_evidence="Reasoner and Frontier disagree on verified evidence.",
        )
        client.app.state.store.save(state)
        unavailable = client.post(
            f"/v1/judge/adjudications/{session_id}",
            headers={"Authorization": "Bearer test-secret"},
        )
        client.app.state.profiles.record("judge")
        completed = client.post(
            f"/v1/judge/adjudications/{session_id}",
            headers={"Authorization": "Bearer test-secret"},
        )
        persisted = client.app.state.store.get(session_id)
        assert_no_request_leases(client.app)

    assert unavailable.status_code == 409
    assert completed.status_code == 200
    assert completed.json()["status"] == "accept"
    assert completed.json()["resume_profile"] == "resident"
    assert persisted is not None
    assert persisted.pending_judge_evidence == ""
    assert persisted.judge_verdict is not None
    assert stub_provider.calls == ["judge"]
    assert stub_provider.call_options == [{"timeout_seconds": 300, "stage": "judge"}]


def test_coding_request_retries_during_transition(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        app.state.profiles.record("resident")
        app.state.profiles.transition("judge")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 503


def test_streaming_round_trip(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "stream"},
            json={
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        assert response.status_code == 200
        assert '"content":"ok"' in response.text
        events = [line.removeprefix("data: ") for line in response.text.splitlines() if line]
        assert events[-1] == "[DONE]"
        final = json.loads(events[-2])
        assert final["choices"][0]["finish_reason"] == "stop"
        assert "usage" in final
        events = client.app.state.store.events("stream")
        assert sum(event["event_type"] == "stream_completed" for event in events) == 1
        assert stub_provider.calls == ["reasoner", "executor"]
        assert not any(event["event_type"] == "review_completed" for event in events)
        assert events[-1]["created_at"]
        trace = assert_terminal_evidence(settings, client.app.state.store, "stream", "completed")
        assert {event["event_type"] for event in trace["events"]} >= {
            "request_received",
            "route_selected",
            "tool_call_requested",
            "session_ended",
        }
        assert trace["task_id"] == "stream"
        assert trace["workspace_identity"]["workspace_identifier"] == "external-api"
        assert all(decision["task_id"] == "stream" for decision in trace["agent_decisions"])
        usage = assert_usage(client.app, "completed")
        assert usage.streaming is True
        assert usage.first_byte_at is not None
        assert usage.total_tokens == 1


@pytest.mark.asyncio
async def test_streaming_api_forwards_before_upstream_completion_and_defers_review(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    release = asyncio.Event()
    first_event = b'data: {"choices":[{"delta":{"content":"now"}}]}\n\n'

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)
        stub_provider.requests.append(request)

        async def upstream():  # type: ignore[no-untyped-def]
            yield first_event
            await release.wait()
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        guard_calls: list[tuple[object, ...]] = []
        set_guard = app.state.lifecycle_store.set_guard

        def record_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
            guard_calls.append(args)
            return set_guard(*args, **kwargs)

        app.state.lifecycle_store.set_guard = record_guard
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-orchestrated",
                stream=True,
                messages=[{"role": "user", "content": "orchestrate"}],
                metadata={"session_id": "immediate-stream", "code_review": True},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)

        first = await asyncio.wait_for(anext(response.body_iterator), timeout=1)
        assert first == first_event
        assert not release.is_set()
        assert stub_provider.calls == ["reasoner", "executor", "executor"]
        assert not any(
            event["event_type"] == "session_ended"
            for event in app.state.store.events("immediate-stream")
        )
        assert not list(
            (settings.state_db.parent.parent / "traces").rglob("immediate-stream.jsonl")
        )

        release.set()
        remaining = b"".join([chunk async for chunk in response.body_iterator])
        assert remaining.count(b"data: [DONE]") == 1
        assert stub_provider.calls == ["reasoner", "executor", "executor"]
        state = app.state.store.get("immediate-stream")
        assert state and state.review_deferred
        assert state.review_status == "deferred"
        assert "first_downstream_byte" in state.timings_ms
        assert_terminal_evidence(settings, app.state.store, "immediate-stream", "completed")
        assert app.state.lifecycle_store.get("reviewer").evaluation_guard is False
        assert guard_calls == []
        assert_no_request_leases(app)


@pytest.mark.asyncio
async def test_stream_total_deadline_does_not_retry_after_first_byte(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    settings.limits.executor_total_timeout_seconds = 0.01
    first_event = b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
    stream_attempts = 0

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal stream_attempts
        stream_attempts += 1

        async def upstream():  # type: ignore[no-untyped-def]
            yield first_event
            await asyncio.Event().wait()

        return upstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-fast",
                stream=True,
                messages=[{"role": "user", "content": "work"}],
                metadata={"session_id": "total-timeout"},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == first_event

        with pytest.raises(TimeoutError) as captured:
            await asyncio.wait_for(anext(response.body_iterator), timeout=0.1)

        assert stream_attempts == 1
        assert type(captured.value).__name__ == "StageTimeout"
        assert getattr(captured.value, "stage", None) == "executor_total"
        timing_events = [
            event
            for event in app.state.store.events("total-timeout")
            if event["event_type"] == "request_timing"
        ]
        assert len(timing_events) == 1
        assert timing_events[0]["payload"]["stage_status"]["executor_total"] == "timed_out"
        trace = assert_terminal_evidence(settings, app.state.store, "total-timeout", "timed_out")
        assert trace["final_status"] == "failed"
        usage = assert_usage(app, "timed_out")
        assert usage.streaming is True
        assert usage.first_byte_at is not None
        assert usage.retryable_failure_class == "executor_total_timeout"


@pytest.mark.asyncio
async def test_streaming_api_persists_cancellation_and_closes_upstream(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    blocked = asyncio.Event()
    closed = asyncio.Event()

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)

        async def upstream():  # type: ignore[no-untyped-def]
            try:
                yield b"data: first\n\n"
                await blocked.wait()
            finally:
                closed.set()

        return upstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-agent",
                stream=True,
                messages=[{"role": "user", "content": "work"}],
                metadata={"session_id": "cancelled-stream"},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == b"data: first\n\n"

        pending = asyncio.create_task(anext(response.body_iterator))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await asyncio.wait_for(closed.wait(), timeout=1)

        state = app.state.store.get("cancelled-stream")
        assert state and state.final_status == "cancelled"
        assert (
            sum(
                event["event_type"] == "stream_aborted"
                for event in app.state.store.events("cancelled-stream")
            )
            == 1
        )
        trace = assert_terminal_evidence(settings, app.state.store, "cancelled-stream", "cancelled")
        assert trace["final_status"] == "cancelled"
        usage = assert_usage(app, "cancelled")
        assert usage.first_byte_at is not None
        assert usage.retryable_failure_class is None


@pytest.mark.asyncio
async def test_streaming_api_first_byte_cancellation_persists_terminal_evidence(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    first_byte_waiting = asyncio.Event()

    class BlockingStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            first_byte_waiting.set()
            await asyncio.Event().wait()
            yield b"data: [DONE]\n\n"

    responses: list[httpx.Response] = []

    def respond(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(200, stream=BlockingStream(), request=request)
        responses.append(response)
        return response

    transport = httpx.MockTransport(respond)
    clients: list[httpx.AsyncClient] = []
    async_client = httpx.AsyncClient

    def client(**kwargs):  # type: ignore[no-untyped-def]
        created = async_client(transport=transport, **kwargs)
        clients.append(created)
        return created

    monkeypatch.setattr("dgx_moa.providers.httpx.AsyncClient", client)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        pending = asyncio.create_task(
            chat_endpoint(app)(
                ChatRequest(
                    model="dgx-moa-fast",
                    stream=True,
                    messages=[{"role": "user", "content": "work"}],
                    metadata={"session_id": "first-byte-cancelled"},
                ),
                Request({"type": "http", "app": app}),
                x_session_id=None,
                x_runtime_channel=None,
                x_trace_origin=None,
                x_task_id=None,
                x_workspace_path=None,
                x_workspace_id=None,
                x_repository_branch=None,
                x_repository_commit=None,
                x_dirty_state=None,
            )
        )
        await asyncio.wait_for(first_byte_waiting.wait(), timeout=1)

        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        assert responses[0].is_closed
        assert clients[0].is_closed
        state = app.state.store.get("first-byte-cancelled")
        events = app.state.store.events("first-byte-cancelled")

    assert state and state.final_status == "cancelled"
    assert sum(event["event_type"] == "stream_aborted" for event in events) == 1
    timing_events = [event for event in events if event["event_type"] == "request_timing"]
    assert len(timing_events) == 1
    payload = timing_events[0]["payload"]
    assert payload["stage_status"]["executor_first_byte"] == "cancelled"
    assert "first_downstream_byte" not in payload["timings_ms"]
    trace_path = next(
        (settings.state_db.parent.parent / "traces").rglob("first-byte-cancelled.jsonl")
    )
    traces = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(traces) == 1
    assert traces[0]["final_status"] == "cancelled"
    assert traces[0]["metrics"]["request_timing_ms"] == payload["timings_ms"]
    assert_terminal_evidence(settings, app.state.store, "first-byte-cancelled", "cancelled")
    usage = assert_usage(app, "cancelled")
    assert usage.first_byte_at is None
    assert usage.retryable_failure_class is None


@pytest.mark.asyncio
async def test_streaming_api_consumer_close_closes_upstream_and_persists_abort(
    settings, stub_provider: StubProvider, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    closed = asyncio.Event()
    retained_forwarders = []

    def retain_forwarder(*args, **kwargs):  # type: ignore[no-untyped-def]
        forwarder = unclosed_forward_sse(*args, **kwargs)
        retained_forwarders.append(forwarder)
        return forwarder

    monkeypatch.setattr("dgx_moa.api.forward_sse", retain_forwarder)

    async def upstream():  # type: ignore[no-untyped-def]
        try:
            yield b"data: first\n\n"
            await asyncio.Event().wait()
        finally:
            closed.set()

    upstream_iterator = upstream()

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)
        return upstream_iterator

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-agent",
                stream=True,
                messages=[{"role": "user", "content": "work"}],
                metadata={"session_id": "closed-stream"},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == b"data: first\n\n"

        await response.body_iterator.aclose()
        await asyncio.wait_for(closed.wait(), timeout=1)

        state = app.state.store.get("closed-stream")
        assert state
        assert state.final_status == "cancelled"
        assert state.decisions[-1]["outcome"]["status"] == "failure"
        assert (
            sum(
                event["event_type"] == "stream_aborted"
                for event in app.state.store.events("closed-stream")
            )
            == 1
        )
        trace = assert_terminal_evidence(settings, app.state.store, "closed-stream", "cancelled")
        assert trace["final_status"] == "cancelled"
        usage = assert_usage(app, "cancelled")
        assert usage.streaming is True
        assert usage.first_byte_at is not None


@pytest.mark.asyncio
async def test_streaming_api_close_after_done_persists_terminal_success(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    closed = asyncio.Event()
    stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    done = b"data: [DONE]\n\n"

    async def upstream():  # type: ignore[no-untyped-def]
        try:
            yield stop
            yield done
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def delayed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)
        return upstream()

    stub_provider.stream = delayed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-orchestrated",
                stream=True,
                messages=[{"role": "user", "content": "orchestrate"}],
                metadata={"session_id": "terminal-close", "code_review": True},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == stop
        assert await anext(response.body_iterator) == done

        await response.body_iterator.aclose()
        await asyncio.wait_for(closed.wait(), timeout=1)

        state = app.state.store.get("terminal-close")
        assert state
        assert state.finish_reasons == ["stop"]
        assert (
            sum(
                invocation.get("role") == "executor" and invocation.get("mode") == "final_synthesis"
                for invocation in state.agent_invocations
            )
            == 1
        )
        assert state.review_deferred
        assert state.review_status == "deferred"
        assert state.decisions[-1]["outcome"]["status"] == "success"
        assert (
            sum(
                event["event_type"] == "stream_completed"
                for event in app.state.store.events("terminal-close")
            )
            == 1
        )
        assert_terminal_evidence(settings, app.state.store, "terminal-close", "completed")


@pytest.mark.asyncio
async def test_streaming_omits_unstorable_tokens_without_post_done_error(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    huge = 2**63
    terminal_payload = {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": huge, "completion_tokens": -1, "total_tokens": 5},
    }
    terminal = f"data: {json.dumps(terminal_payload, separators=(',', ':'))}\n\n".encode()
    done = b"data: [DONE]\n\n"

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield terminal
            yield done

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-agent",
                stream=True,
                messages=[{"role": "user", "content": "work"}],
                metadata={"session_id": "huge-stream-usage"},
            ),
            Request({"type": "http", "app": app}),
            x_session_id=None,
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
        assert isinstance(response, StreamingResponse)
        assert await anext(response.body_iterator) == terminal
        assert await anext(response.body_iterator) == done
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        usage = assert_usage(app, "completed")

    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens == 5


def test_streaming_upstream_400_returns_invalid_request(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    async def rejected(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        response = httpx.Response(400, request=httpx.Request("POST", model.base_url))
        raise httpx.HTTPStatusError("context overflow", request=response.request, response=response)

    stub_provider.stream = rejected  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["type"] == "invalid_request_error"
        assert response.json()["error"]["code"] == "invalid_request"


def test_api_validation(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "wrong", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "message": "unknown model",
                "type": "invalid_request_error",
                "code": "model_not_found",
                "param": "model",
            }
        }


def test_responses_post_returns_openai_response_shape(  # type: ignore[no-untyped-def]
    settings, stub_provider: StubProvider
) -> None:
    original = stub_provider.complete

    async def complete(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "id": "chatcmpl-resp",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = complete  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "input": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "response"
    assert body["model"] == "dgx-moa-agent"
    assert body["status"] == "completed"
    assert body["output"][0]["type"] == "message"
    assert body["output"][0]["content"][0]["text"] == "ok"
    assert body["usage"] == {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}


def test_responses_post_maps_upstream_502_to_http_200(  # type: ignore[no-untyped-def]
    settings, stub_provider: StubProvider
) -> None:
    async def connect_failed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("all endpoints unreachable")

    stub_provider.complete = connect_failed  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-fast", "input": "hello"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["type"] == "backend_error"
    assert body["error"]["code"] == "backend_error"


def test_upstream_openai_400_envelope_and_status_are_preserved(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    upstream_error = {
        "error": {
            "message": "Unsupported parameter: seed",
            "type": "invalid_request_error",
            "code": "unsupported_parameter",
            "param": "seed",
        }
    }

    async def rejected(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        response = httpx.Response(
            400,
            json=upstream_error,
            request=httpx.Request("POST", model.base_url),
        )
        raise httpx.HTTPStatusError("bad request", request=response.request, response=response)

    stub_provider.complete = rejected  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-fast", "messages": [{"role": "user", "content": "x"}]},
        )

    assert response.status_code == 400
    assert response.json() == upstream_error


def test_malformed_tool_call_returns_bad_gateway(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def malformed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        response = await original(role, model, request)
        if role == "executor":
            response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{"
        return response

    stub_provider.complete = malformed  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 502
        assert response.json()["error"] == {
            "message": "malformed tool arguments",
            "type": "backend_error",
            "code": "backend_error",
            "param": None,
        }
        usage = assert_usage(client.app, "failed")
        assert usage.retryable_failure_class == "backend_error"


@pytest.mark.parametrize("stream", [False, True])
def test_unexpected_provider_setup_failure_finalizes_typed_error_once(
    settings, stub_provider: StubProvider, stream: bool
) -> None:  # type: ignore[no-untyped-def]
    session_id = f"unexpected-{'stream' if stream else 'nonstream'}"

    async def unexpected(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("unexpected backend failure")

    if stream:
        stub_provider.stream = unexpected  # type: ignore[method-assign]
    else:
        stub_provider.complete = unexpected  # type: ignore[method-assign]

    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={
                "model": "dgx-moa-agent",
                "stream": stream,
                "messages": [{"role": "user", "content": "work"}],
            },
        )
        trace = assert_terminal_evidence(settings, client.app.state.store, session_id, "failed")
        usage = assert_usage(client.app, "failed")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "unexpected backend failure",
            "type": "backend_error",
            "code": "backend_error",
            "param": None,
        }
    }
    assert trace["final_status"] == "failed"
    assert usage.retryable_failure_class == "backend_error"


@pytest.mark.parametrize(
    ("failure", "status_code"),
    [
        ("upstream_400", 400),
        ("upstream_500", 502),
        ("http_error", 502),
        ("malformed", 502),
    ],
)
def test_non_timeout_terminal_failure_records_one_timing_and_trace(
    settings,
    stub_provider: StubProvider,
    failure: str,
    status_code: int,
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete
    session_id = f"terminal-{failure}"
    secret_content = f"content-must-not-leak-{failure}"

    async def fail(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role != "executor":
            return await original(role, model, request, **kwargs)
        if failure == "http_error":
            raise httpx.ConnectError("unavailable")
        if failure.startswith("upstream_"):
            upstream_status = int(failure.removeprefix("upstream_"))
            response = httpx.Response(
                upstream_status,
                request=httpx.Request("POST", model.base_url),
            )
            raise httpx.HTTPStatusError(
                "upstream rejected request", request=response.request, response=response
            )
        response = await original(role, model, request, **kwargs)
        response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{"
        return response

    stub_provider.complete = fail  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": secret_content}],
            },
        )
        timing_events = [
            event
            for event in client.app.state.store.events(session_id)
            if event["event_type"] == "request_timing"
        ]
        trace = assert_terminal_evidence(settings, client.app.state.store, session_id, "failed")

    assert response.status_code == status_code
    assert len(timing_events) == 1
    payload = timing_events[0]["payload"]
    assert payload["stage_status"]["executor_total"] == "failed"
    assert isinstance(payload["timings_ms"]["completed"], int | float)
    assert secret_content not in json.dumps(payload)
    assert trace["final_status"] == "failed"
    assert trace["metrics"]["request_timing_ms"] == payload["timings_ms"]


def test_duplicate_failed_call_records_one_timing_and_trace(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    session_id = "duplicate-terminal"
    call = {
        "id": "call-duplicate",
        "type": "function",
        "function": {"name": "shell", "arguments": '{"cmd":"false"}'},
    }
    with client_with_stub(settings, stub_provider) as client:
        client.app.state.store.save(
            SessionState(
                session_id=session_id,
                failed_call_fingerprints=[fingerprint(call)],
            )
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={
                "model": "dgx-moa-agent",
                "messages": [
                    {"role": "assistant", "tool_calls": [call]},
                    {
                        "role": "tool",
                        "tool_call_id": "call-duplicate",
                        "content": '{"exit_code":2,"error":"bad"}',
                    },
                ],
            },
        )
        timing_events = [
            event
            for event in client.app.state.store.events(session_id)
            if event["event_type"] == "request_timing"
        ]
        usage = assert_usage(client.app, "failed")

    assert response.status_code == 409
    assert len(timing_events) == 1
    assert timing_events[0]["payload"]["stage_status"] == {"request": "failed"}
    trace_path = next((settings.state_db.parent.parent / "traces").rglob(f"{session_id}.jsonl"))
    assert len(trace_path.read_text().splitlines()) == 1
    assert usage.retryable_failure_class is None


def test_step_budget_failure_finalizes_one_usage_row(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    settings.limits.max_steps = 1
    session_id = "usage-step-budget"
    with client_with_stub(settings, stub_provider) as client:
        client.app.state.store.save(SessionState(session_id=session_id, step_count=1))
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        usage = assert_usage(client.app, "failed")

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "session step budget exhausted"
    assert stub_provider.calls == []
    assert usage.retryable_failure_class == "backend_error"


def test_provenance_failure_finalizes_exactly_one_failed_usage_row(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    session_id = "usage-provenance"
    headers = {"Authorization": "Bearer test-secret", "X-Session-ID": session_id}
    with client_with_stub(settings, stub_provider) as client:
        first = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "one"}]},
        )
        second = client.post(
            "/v1/chat/completions",
            headers=headers
            | {
                "X-Runtime-Channel": "candidate",
                "X-Trace-Origin": "candidate_evaluation",
            },
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "two"}]},
        )
        records = client.app.state.usage.recent_requests()

    assert first.status_code == 200
    assert second.status_code == 502
    assert second.json()["error"]["message"] == "session runtime provenance changed"
    assert [record.status for record in records] == ["completed", "failed"]
    assert sum(record.status == "failed" for record in records) == 1
    assert stub_provider.calls == ["reasoner", "executor"]


def test_route_failure_finalizes_one_usage_row(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-agent",
                "messages": [{"role": "user", "content": "x"}],
                "metadata": {"expected_files": "not-an-integer"},
            },
        )
        usage = assert_usage(client.app, "failed")

    assert response.status_code == 502
    assert "invalid literal for int" in response.json()["error"]["message"]
    assert stub_provider.calls == []
    assert usage.request_class == "native_agent_turn"
    assert usage.roles_required == ("reasoner", "executor")


def test_session_setup_failure_finalizes_usage_without_state(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:

        def fail_session(*args, **kwargs):  # type: ignore[no-untyped-def]
            assert len(client.app.state.usage.recent_requests()) == 1
            raise ValueError("session setup failed")

        client.app.state.controller.session = fail_session
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        usage = assert_usage(client.app, "failed")

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "session setup failed"
    assert usage.retryable_failure_class == "backend_error"


def test_multiple_tool_calls_are_preserved(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def multiple(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        response = await original(role, model, request)
        if role == "executor":
            response["choices"][0]["message"]["tool_calls"].append(
                {
                    "id": "call-second",
                    "type": "function",
                    "function": {"name": "glob", "arguments": '{"pattern":"*"}'},
                }
            )
        return response

    stub_provider.complete = multiple  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 200
        assert len(response.json()["choices"][0]["message"]["tool_calls"]) == 2


def test_timeout_and_http_500_mapping(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def timeout(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            raise httpx.ReadTimeout("timed out")
        return await original(role, model, request)

    stub_provider.complete = timeout  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 504
        assert response.json()["error"] == {
            "message": "timed out",
            "type": "timeout_error",
            "code": "executor_timeout",
            "param": None,
        }

    async def server_error(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            response = httpx.Response(500, request=httpx.Request("POST", "http://model"))
            raise httpx.HTTPStatusError("server error", request=response.request, response=response)
        return await original(role, model, request)

    stub_provider.complete = server_error  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 502
        assert response.json()["error"]["type"] == "backend_error"
        assert response.json()["error"]["code"] == "backend_error"


def test_secondary_trace_failure_marks_degraded_and_continues(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:

        def fail_trace(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("archive unavailable")

        client.app.state.traces.record = fail_trace
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "degraded"},
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 200
        state = client.app.state.store.get("degraded")
        assert state and state.observability_degraded
        assert (
            client.app.state.store.events("degraded")[-1]["event_type"] == "observability_degraded"
        )
        assert_no_request_leases(client.app)


def test_primary_state_failure_fails_closed(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:

        def fail_state(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("state unavailable")

        client.app.state.store.save = fail_state
        with pytest.raises(OSError, match="state unavailable"):
            client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-secret"},
                json={
                    "model": "dgx-moa-agent",
                    "messages": [{"role": "user", "content": "x"}],
                },
            )
        assert_no_request_leases(client.app)


def test_terminal_state_lookup_failure_still_releases_active_lease(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:

        def fail_session(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("session setup failed")

        def fail_lookup(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("state lookup unavailable")

        client.app.state.controller.session = fail_session
        client.app.state.store.get = fail_lookup
        with pytest.raises(OSError, match="state lookup unavailable"):
            client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-secret"},
                json={
                    "model": "dgx-moa-agent",
                    "messages": [{"role": "user", "content": "x"}],
                },
            )
        assert_no_request_leases(client.app)
