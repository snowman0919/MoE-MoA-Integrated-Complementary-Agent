from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from contextlib import contextmanager

import httpx
import pytest
from dgx_moa import providers
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from dgx_moa.controller import fingerprint
from dgx_moa.schemas import ChatRequest
from dgx_moa.state import Phase, SessionState
from dgx_moa.streaming import forward_sse as unclosed_forward_sse
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from .conftest import StubProvider


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
    return record


def block_profile_control(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_control(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("profile control escaped an admin route test")

    monkeypatch.setattr("dgx_moa.profiles.ProfileManager.switch", reject_control)
    monkeypatch.setattr("dgx_moa.profiles.ProfileManager.transition", reject_control)
    monkeypatch.setattr("dgx_moa.profiles.subprocess.run", reject_control)


def test_auth_models_and_tool_call_preservation(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/models").status_code == 401
        headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "session-1"}
        models = client.get("/v1/models", headers=headers).json()
        assert [model["id"] for model in models["data"]] == [
            "dgx-moa-chat",
            "dgx-moa-agent",
            "dgx-moa-orchestrated",
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
        assert stub_provider.calls == ["executor"]


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
                "model": "dgx-moa-agent",
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

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == raw_response
    assert record.session_id != raw_session
    assert record.client_class == "openai-python"
    assert record.model_alias == "dgx-moa-agent"
    assert record.runtime_mode == "agent"
    assert record.request_class == "native_agent_turn"
    assert record.roles_required == ("executor",)
    assert record.first_byte_at is not None
    assert record.accepted_at <= record.first_byte_at <= record.completed_at
    assert record.streaming is False
    assert record.model_state == "warm"
    assert record.load_triggered is False
    assert record.retryable_failure_class is None
    assert (record.prompt_tokens, record.completion_tokens, record.total_tokens) == (2, 3, 5)
    assert report.status_code == 404
    persisted_usage = repr(usage_row)
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
                    "model": "dgx-moa-agent",
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


@pytest.mark.parametrize("model", ["dgx-moa-chat", "dgx-moa-agent"])
def test_direct_modes_are_executor_only(settings, stub_provider: StubProvider, model: str) -> None:  # type: ignore[no-untyped-def]
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
    assert stub_provider.calls == ["executor"]


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
    assert stub_provider.calls == ["planner", "executor"]


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
    assert stub_provider.calls == ["planner", "executor", "reviewer"]
    assert stub_provider.call_options == [
        {"timeout_seconds": 120, "stage": "planner"},
        {"timeout_seconds": 900, "stage": "executor_total"},
        {"timeout_seconds": 120, "stage": "reviewer"},
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
    assert all(state.timings_ms[stage] >= 0 for stage in ("planner", "executor_total", "reviewer"))
    assert timing_event["payload"]["stage_status"] == {
        "planner": "completed",
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
        ("planner", "dgx-moa-orchestrated", {"authentication": True}, False),
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
        if role == "executor":
            stub_provider.calls.append(role)
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "normal answer"},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request)

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
    assert stub_provider.calls == ["planner", "executor"]


@pytest.mark.parametrize("failure", ["http", "timeout", "value"])
def test_low_risk_review_failure_preserves_executor_response(
    settings, stub_provider: StubProvider, failure: str
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def fail_review(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
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
        return await original(role, model, request)

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
        if role == "executor":
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
        return await original(role, model, request)

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

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "backend_error"
    assert state and state.review_status == "failed"
    assert any(event["event_type"] == "review_failed" for event in events)


def test_length_finish_is_preserved_and_never_completes_session(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def truncated(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "id": "chatcmpl-truncated",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "partial output"},
                        "finish_reason": "length",
                    }
                ],
            }
        return await original(role, model, request)

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
            status_code = 503 if url.endswith(":8110/v1/models") else 200
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
                "planner": "ready",
                "reviewer": "ready",
                "reasoner": "ready",
                "judge": "stopped",
            },
            "auth_enabled": True,
        }
        app.state.profiles.transition("judge")
        transition = client.get("/readyz")
        assert transition.status_code == 503
        assert transition.json()["status"] == "transitioning"


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
        assert stub_provider.calls == ["executor"]
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
        response = await chat_endpoint(app)(
            ChatRequest(
                model="dgx-moa-orchestrated",
                stream=True,
                messages=[{"role": "user", "content": "orchestrate"}],
                metadata={"session_id": "immediate-stream"},
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
        assert stub_provider.calls == ["planner", "executor"]
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
        assert stub_provider.calls == ["planner", "executor"]
        state = app.state.store.get("immediate-stream")
        assert state and state.review_deferred
        assert state.review_status == "deferred"
        assert "first_downstream_byte" in state.timings_ms
        assert_terminal_evidence(settings, app.state.store, "immediate-stream", "completed")


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
                model="dgx-moa-agent",
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
                    model="dgx-moa-agent",
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
                metadata={"session_id": "terminal-close"},
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
            json={"model": "dgx-moa-agent", "messages": [{"role": "user", "content": "x"}]},
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

    assert response.status_code == 409
    assert len(timing_events) == 1
    assert timing_events[0]["payload"]["stage_status"] == {"request": "failed"}
    trace_path = next((settings.state_db.parent.parent / "traces").rglob(f"{session_id}.jsonl"))
    assert len(trace_path.read_text().splitlines()) == 1


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
