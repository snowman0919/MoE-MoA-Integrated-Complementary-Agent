from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from fastapi.testclient import TestClient

from .conftest import StubProvider


@contextmanager
def client_with_stub(settings, stub_provider: StubProvider):  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        yield client


def test_auth_models_and_tool_call_preservation(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/models").status_code == 401
        headers = {"Authorization": "Bearer test-secret", "X-Session-ID": "session-1"}
        models = client.get("/v1/models", headers=headers).json()
        assert models["data"][0]["id"] == "dgx-moa-agent"
        assert models["data"][0]["context_length"] == 65536
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
        assert stub_provider.calls == ["reasoner", "planner", "executor"]


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
        assert events[-1]["created_at"]
        trace_path = next((settings.state_db.parent.parent / "traces").rglob("stream.jsonl"))
        trace = json.loads(trace_path.read_text())
        assert {event["event_type"] for event in trace["events"]} >= {
            "request_received",
            "route_selected",
            "tool_call_requested",
        }


def test_streaming_upstream_error_returns_bad_gateway(
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
        assert response.status_code == 502


def test_api_validation(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "wrong", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code == 404


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
        assert response.json()["detail"] == "malformed tool arguments"


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
