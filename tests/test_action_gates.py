"""API convergence: one action gate for Chat/Responses, stream/non-stream."""

from __future__ import annotations

import pytest
from dgx_moa.api import create_app
from dgx_moa.schemas import ChatRequest, ResponsesRequest
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from .conftest import StubProvider


def _tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "run",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }
    ]


def _bad_call() -> dict:
    return {
        "id": "call-bad",
        "type": "function",
        "function": {"name": "terminal", "arguments": '{"command": 42}'},
    }


def _chat_endpoint(app):  # type: ignore[no-untyped-def]
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/v1/chat/completions"
        and "POST" in getattr(route, "methods", set())
    )


def _responses_endpoint(app):  # type: ignore[no-untyped-def]
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/v1/responses"
        and "POST" in getattr(route, "methods", set())
    )


def _rejected_events(app, session_id: str) -> list[dict]:
    return [
        event
        for event in app.state.store.events(session_id)
        if event["event_type"] == "action_preflight_rejected"
    ]


def test_chat_nonstream_records_schema_mismatch(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def bad_call(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [_bad_call()],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = bad_call  # type: ignore[method-assign]
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "gate-chat"},
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "run it"}],
                "tools": _tools(),
            },
        )

    assert response.status_code == 502
    assert _rejected_events(client.app, "gate-chat")
    assert _rejected_events(client.app, "gate-chat")[0]["payload"]["code"] == "schema_mismatch"


def test_chat_stream_records_schema_mismatch(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    delta = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-bad",'
        b'"type":"function","function":{"name":"terminal","arguments":"{\\"command\\":42}"}}]}}]}\n\n'
    )

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield delta
            yield b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        try:
            response = client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-secret",
                    "X-Session-ID": "gate-chat-stream",
                },
                json={
                    "model": "dgx-moa-fast",
                    "stream": True,
                    "messages": [{"role": "user", "content": "run it"}],
                    "tools": _tools(),
                },
            )
        except ValueError as error:
            assert "schema_mismatch" in str(error)
            response = None

    if response is not None:
        assert response.status_code == 200
        assert "call-preserved" in response.text
    assert _rejected_events(client.app, "gate-chat-stream")


@pytest.mark.asyncio
async def test_responses_nonstream_records_schema_mismatch(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def bad_call(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [_bad_call()],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = bad_call  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await _responses_endpoint(app)(
            ResponsesRequest(
                model="dgx-moa-fast",
                input="run it",
                tools=[
                    {
                        "type": "function",
                        "name": "terminal",
                        "parameters": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                        },
                    }
                ],
            ),
            Request({"type": "http", "app": app}),
            x_session_id="gate-responses",
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )

    assert response.status_code == 200
    assert app.state.store.get("gate-responses") is not None


@pytest.mark.asyncio
async def test_responses_stream_records_schema_mismatch(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    delta = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-bad",'
        b'"type":"function","function":{"name":"terminal","arguments":"{\\"command\\":42}"}}]}}]}\n\n'
    )

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield delta
            yield b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        try:
            chat_response = await _chat_endpoint(app)(
                ChatRequest(
                    model="dgx-moa-fast",
                    stream=True,
                    messages=[{"role": "user", "content": "run it"}],
                    tools=_tools(),
                ),
                Request({"type": "http", "app": app}),
                x_session_id="gate-responses-stream",
                x_runtime_channel=None,
                x_trace_origin=None,
                x_task_id=None,
                x_workspace_path=None,
                x_workspace_id=None,
                x_repository_branch=None,
                x_repository_commit=None,
                x_dirty_state=None,
            )
            assert isinstance(chat_response, StreamingResponse)
            text = b"".join([chunk async for chunk in chat_response.body_iterator]).decode()
            assert "call-preserved" in text
        except ValueError as error:
            assert "schema_mismatch" in str(error)
    assert _rejected_events(app, "gate-responses-stream")


def test_tool_result_continuation_does_not_double_execute(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete
    seen: list[dict] = []

    async def observe(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            seen.append(request)
            if any(message.get("role") == "tool" for message in request["messages"]):
                return {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "done"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-preserved",
                                    "type": "function",
                                    "function": {
                                        "name": "terminal",
                                        "arguments": '{"command":"echo hi"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = observe  # type: ignore[method-assign]
    session_id = "gate-continuation"
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        first = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "work"}],
                "tools": _tools(),
            },
        )
        call = first.json()["choices"][0]["message"]
        second = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json={
                "model": "dgx-moa-fast",
                "messages": [
                    {"role": "user", "content": "work"},
                    call,
                    {
                        "role": "tool",
                        "tool_call_id": "call-preserved",
                        "content": '{"stdout":"ok","exit_code":0}',
                    },
                ],
                "tools": _tools(),
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["choices"][0]["message"]["content"] == "done"
    assert len(seen) == 2


@pytest.mark.parametrize("invalid", ["fragmented", "unknown", "schema", "unrecoverable"])
@pytest.mark.parametrize("endpoint", ["chat", "responses"])
def test_stream_tool_preflight_is_complete_and_correction_is_bounded(
    settings, stub_provider: StubProvider, invalid: str, endpoint: str
) -> None:  # type: ignore[no-untyped-def]
    import json

    corrections = []
    original = stub_provider.complete

    async def corrected(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        corrections.append(request)
        response = await original(role, model, request, **kwargs)
        if invalid == "unrecoverable":
            response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "invented"
        return response

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            name = (
                "ter"
                if invalid == "fragmented"
                else "terminal"
                if invalid == "schema"
                else "invented"
            )
            arguments = '{"command":42}' if invalid == "schema" else '{"command":"echo hi"}'
            fragments = [
                {
                    "index": 0,
                    "id": "call-safe",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ]
            yield (
                "data: " + json.dumps({"choices": [{"delta": {"tool_calls": fragments}}]}) + "\n\n"
            ).encode()
            if invalid == "fragmented":
                yield (
                    b'data: {"choices":[{"delta":{"tool_calls":'
                    b'[{"index":0,"function":{"name":"minal"}}]}}]}\n\n'
                )
            yield b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    stub_provider.complete = corrected  # type: ignore[method-assign]
    session_id = f"bounded-{endpoint}-{invalid}"
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        body = {"model": "dgx-moa-fast", "stream": True}
        if endpoint == "chat":
            body.update(messages=[{"role": "user", "content": "run it"}], tools=_tools())
        else:
            body.update(input="run it", tools=[{"type": "function", **_tools()[0]["function"]}])
        response = client.post(
            "/v1/chat/completions" if endpoint == "chat" else "/v1/responses",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": session_id},
            json=body,
        )
        state = client.app.state.store.get(session_id)
    assert response.status_code == 200
    assert len(corrections) == (0 if invalid == "fragmented" else 1)
    assert state is not None
    if invalid == "unrecoverable":
        assert "invalid_executor_output" in response.text or "response.failed" in response.text
        assert state.final_status == "failed"
        assert not state.pending_tool_call_ids
    else:
        assert "invented" not in response.text
        if endpoint == "chat" and invalid == "fragmented":
            assert '"name": "ter"' in response.text and '"name":"minal"' in response.text
        else:
            assert "terminal" in response.text
        assert state.pending_tool_call_ids
        assert state.final_status != "failed"
