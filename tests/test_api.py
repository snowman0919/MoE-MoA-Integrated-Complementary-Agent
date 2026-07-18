from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import httpx
import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
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
    async def natural(role, model, request):  # type: ignore[no-untyped-def]
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


def test_orchestrated_assistant_answer_without_evidence_skips_review(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def natural(role, model, request):  # type: ignore[no-untyped-def]
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

    async def fail_review(role, model, request):  # type: ignore[no-untyped-def]
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

    async def fail_review(role, model, request):  # type: ignore[no-untyped-def]
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

    async def truncated(role, model, request):  # type: ignore[no-untyped-def]
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


def test_tool_result_continuation_uses_same_session(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def continue_after_tool(role, model, request):  # type: ignore[no-untyped-def]
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
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    disabled = Settings.model_validate(
        settings.model_dump() | {"auth_enabled": False, "api_key": None}
    )
    with client_with_stub(disabled, stub_provider) as client:
        assert client.get("/v1/models").status_code == 200
        assert (
            client.get("/v1/models", headers={"Authorization": "Bearer unused"}).status_code == 200
        )
        assert client.get("/admin/profile").status_code == 404


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
        assert events[-1]["event_type"] == "stream_completed"
        assert stub_provider.calls == ["executor"]
        assert not any(event["event_type"] == "review_completed" for event in events)
        assert events[-1]["created_at"]
        trace_path = next((settings.state_db.parent.parent / "traces").rglob("stream.jsonl"))
        trace = json.loads(trace_path.read_text())
        assert {event["event_type"] for event in trace["events"]} >= {
            "request_received",
            "route_selected",
            "tool_call_requested",
        }


@pytest.mark.asyncio
async def test_streaming_api_forwards_before_upstream_completion_and_defers_review(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    release = asyncio.Event()
    first_event = b'data: {"choices":[{"delta":{"content":"now"}}]}\n\n'

    async def delayed(role, model, request):  # type: ignore[no-untyped-def]
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

        release.set()
        remaining = b"".join([chunk async for chunk in response.body_iterator])
        assert remaining.count(b"data: [DONE]") == 1
        assert stub_provider.calls == ["planner", "executor"]
        state = app.state.store.get("immediate-stream")
        assert state and state.review_deferred
        assert state.review_status == "deferred"
        assert "first_downstream_byte" in state.timings_ms


@pytest.mark.asyncio
async def test_streaming_api_persists_cancellation_and_closes_upstream(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    blocked = asyncio.Event()
    closed = asyncio.Event()

    async def delayed(role, model, request):  # type: ignore[no-untyped-def]
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
        assert app.state.store.events("cancelled-stream")[-1]["event_type"] == "stream_aborted"


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

    async def delayed(role, model, request):  # type: ignore[no-untyped-def]
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
        assert state.decisions[-1]["outcome"]["status"] == "failure"
        assert app.state.store.events("closed-stream")[-1]["event_type"] == "stream_aborted"


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

    async def delayed(role, model, request):  # type: ignore[no-untyped-def]
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
        assert app.state.store.events("terminal-close")[-1]["event_type"] == "stream_completed"


def test_streaming_upstream_400_returns_invalid_request(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    async def rejected(role, model, request):  # type: ignore[no-untyped-def]
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

    async def rejected(role, model, request):  # type: ignore[no-untyped-def]
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

    async def malformed(role, model, request):  # type: ignore[no-untyped-def]
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


def test_multiple_tool_calls_are_preserved(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def multiple(role, model, request):  # type: ignore[no-untyped-def]
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

    async def timeout(role, model, request):  # type: ignore[no-untyped-def]
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

    async def server_error(role, model, request):  # type: ignore[no-untyped-def]
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
