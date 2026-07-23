from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from dgx_moa.providers import ModelProvider, parse_json_content


class CountingResponse(httpx.Response):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1
        await super().aclose()


class CountingClient(httpx.AsyncClient):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1
        await super().aclose()


def tracked_stream_transport(
    monkeypatch: pytest.MonkeyPatch,
    stream: httpx.AsyncByteStream,
) -> tuple[list[CountingResponse], list[CountingClient]]:
    responses: list[CountingResponse] = []

    def respond(request: httpx.Request) -> httpx.Response:
        response = CountingResponse(200, stream=stream, request=request)
        responses.append(response)
        return response

    transport = httpx.MockTransport(respond)
    clients: list[CountingClient] = []

    def client(**kwargs):  # type: ignore[no-untyped-def]
        created = CountingClient(transport=transport, **kwargs)
        clients.append(created)
        return created

    monkeypatch.setattr("dgx_moa.providers.httpx.AsyncClient", client)
    return responses, clients


def test_stage_timeout_defaults(settings) -> None:  # type: ignore[no-untyped-def]
    assert settings.limits.planner_timeout_seconds == 120
    assert settings.limits.reasoner_timeout_seconds == 120
    assert settings.limits.executor_first_byte_timeout_seconds == 120
    assert settings.limits.executor_total_timeout_seconds == 900
    assert settings.limits.reviewer_timeout_seconds == 120
    assert settings.limits.model_load_timeout_seconds == 1_200
    assert settings.limits.tool_continuation_timeout_seconds == 600


def test_ollama_reasoner_contract(settings) -> None:  # type: ignore[no-untyped-def]
    model = settings.models["reasoner"].model_copy(
        update={"provider": "ollama", "served_name": "Qwythos-v2-9B:Q5", "ollama_keep_alive": -1}
    )
    schema = {"type": "object", "properties": {"confidence": {"type": "number"}}}
    body = ModelProvider.ollama_body(
        model,
        {
            "messages": [{"role": "system", "content": "reason"}],
            "max_tokens": 321,
            "tools": [{"type": "function"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "reasoner", "schema": schema},
            },
        },
    )
    assert body == {
        "model": "Qwythos-v2-9B:Q5",
        "messages": [{"role": "system", "content": "reason"}],
        "stream": False,
        "keep_alive": -1,
        "options": {"num_ctx": 65536, "num_predict": 321},
        "format": schema,
    }
    response = ModelProvider.ollama_response(
        {
            "message": {"role": "assistant", "content": '{"confidence":0.8}'},
            "done": True,
            "prompt_eval_count": 7,
            "eval_count": 3,
        }
    )
    assert response["usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }
    with pytest.raises(ValueError, match="cannot issue tools"):
        ModelProvider.ollama_response(
            {"message": {"content": "x", "tool_calls": [{"function": {"name": "shell"}}]}}
        )


def test_judge_is_read_only(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "judge",
        settings.models["judge"],
        {"messages": [], "tools": [{"type": "function"}], "tool_choice": "required"},
    )
    assert "tools" not in body
    assert "tool_choice" not in body
    assert body["stream"] is False


def test_nemotron_planner_keeps_bounded_reasoning(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "planner",
        settings.models["planner"].model_copy(update={"reasoning_parser": "nemotron_v3"}),
        {"messages": [{"role": "system", "content": "Plan in English."}]},
    )

    assert body["messages"][-1]["content"] == "Plan in English."
    assert body["chat_template_kwargs"] == {
        "enable_thinking": True,
        "reasoning_budget": 768,
    }


@pytest.mark.asyncio
async def test_executor_context_fit_uses_served_tokenizer_limit(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"count": 65_000, "max_model_len": 65_536},
            request=request,
        )

    transport = httpx.MockTransport(respond)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    fits = await ModelProvider.context_fits(
        settings.models["executor"],
        {
            "messages": [{"role": "user", "content": "large"}],
            "tools": [{"type": "function", "function": {"name": "read_file"}}],
            "max_tokens": 1_024,
        },
    )

    assert fits is False
    assert requests[0].url.path == "/tokenize"
    assert json.loads(requests[0].content)["tools"][0]["function"]["name"] == "read_file"


@pytest.mark.asyncio
async def test_local_specialist_completion_fits_served_context(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    completion_bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tokenize":
            return httpx.Response(
                200,
                json={"count": 6693, "max_model_len": 8192},
                request=request,
            )
        completion_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []}, request=request)

    transport = httpx.MockTransport(respond)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    await ModelProvider().complete(
        "reviewer",
        settings.models["reviewer"],
        {"messages": [{"role": "system", "content": "review"}], "max_tokens": 1500},
    )

    assert completion_bodies[0]["max_tokens"] == 1491


@pytest.mark.asyncio
async def test_nemotron_planner_separates_reasoning_from_final_json(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    completion_bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tokenize":
            return httpx.Response(
                200,
                json={"count": 100, "max_model_len": 8192},
                request=request,
            )
        body = json.loads(request.content)
        completion_bodies.append(body)
        if body["chat_template_kwargs"]["enable_thinking"]:
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_content": "Private English analysis.",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 768,
                    "total_tokens": 868,
                },
            }
        else:
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"summary":"plan","steps":[]}',
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 110,
                    "completion_tokens": 20,
                    "total_tokens": 130,
                },
            }
        return httpx.Response(200, json=payload, request=request)

    transport = httpx.MockTransport(respond)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )
    model = settings.models["planner"].model_copy(update={"reasoning_parser": "nemotron_v3"})

    result = await ModelProvider().complete(
        "planner",
        model,
        {
            "messages": [{"role": "user", "content": "Analyze in English and plan."}],
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        },
    )

    assert len(completion_bodies) == 2
    assert completion_bodies[0]["max_tokens"] == 768
    assert "response_format" not in completion_bodies[0]
    assert completion_bodies[1]["max_tokens"] == 1536
    assert completion_bodies[1]["chat_template_kwargs"] == {
        "enable_thinking": False,
        "truncate_history_thinking": False,
    }
    assert completion_bodies[1]["messages"][-2] == {
        "role": "assistant",
        "reasoning_content": "Private English analysis.",
        "content": "",
    }
    assert result["choices"][0]["message"]["content"] == '{"summary":"plan","steps":[]}'
    assert result["usage"] == {
        "prompt_tokens": 210,
        "completion_tokens": 788,
        "total_tokens": 998,
    }


def test_missing_structured_content_is_controlled_error() -> None:
    with pytest.raises(ValueError, match="structured model response missing content"):
        parse_json_content({"choices": [{"message": {"content": None}}]})


@pytest.mark.asyncio
async def test_stream_error_body_is_available_to_the_api(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    envelope = {
        "error": {
            "message": "Unsupported parameter",
            "type": "invalid_request_error",
            "code": "unsupported_parameter",
            "param": "seed",
        }
    }

    class ErrorStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield json.dumps(envelope).encode()

    transport = httpx.MockTransport(lambda request: httpx.Response(400, stream=ErrorStream()))
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    with pytest.raises(httpx.HTTPStatusError) as captured:
        await ModelProvider().stream(
            "executor",
            settings.models["executor"],
            {"messages": [{"role": "user", "content": "hello"}]},
        )

    assert captured.value.response.json() == envelope


@pytest.mark.parametrize("stage", ["planner", "executor_total", "reviewer"])
@pytest.mark.asyncio
async def test_completion_timeout_has_exact_stage(
    settings, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:  # type: ignore[no-untyped-def]
    async def slow_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"choices": []}, request=request)

    transport = httpx.MockTransport(slow_response)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    with pytest.raises(TimeoutError) as captured:
        await ModelProvider().complete(
            "executor",
            settings.models["executor"],
            {"messages": []},
            timeout_seconds=0.001,
            stage=stage,
        )

    assert type(captured.value).__name__ == "StageTimeout"
    assert getattr(captured.value, "stage", None) == stage


@pytest.mark.asyncio
async def test_stream_waits_for_first_byte_with_exact_stage(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    class DelayedStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            await asyncio.sleep(1)
            yield b"data: [DONE]\n\n"

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=DelayedStream(), request=request)
    )
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "dgx_moa.providers.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    with pytest.raises(TimeoutError) as captured:
        await ModelProvider().stream(
            "executor",
            settings.models["executor"],
            {"messages": []},
            timeout_seconds=0.001,
            stage="executor_first_byte",
        )

    assert type(captured.value).__name__ == "StageTimeout"
    assert getattr(captured.value, "stage", None) == "executor_first_byte"


@pytest.mark.asyncio
async def test_stream_setup_cancellation_closes_response_and_client(
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
    pending = asyncio.create_task(
        ModelProvider().stream(
            "executor",
            settings.models["executor"],
            {"messages": []},
            timeout_seconds=10,
            stage="executor_first_byte",
        )
    )
    await asyncio.wait_for(first_byte_waiting.wait(), timeout=1)

    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    assert responses[0].is_closed
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_stream_close_before_first_iteration_closes_response_and_client_once(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"first"
            yield b"second"

    responses, clients = tracked_stream_transport(monkeypatch, Bytes())
    stream = await ModelProvider().stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    await stream.aclose()  # type: ignore[attr-defined]
    await stream.aclose()  # type: ignore[attr-defined]

    assert responses[0].is_closed
    assert clients[0].is_closed
    assert responses[0].close_count == 1
    assert clients[0].close_count == 1


@pytest.mark.asyncio
async def test_stream_preserves_prefetched_byte_order_and_closes_on_exhaustion(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"first"
            yield b"second"
            yield b"third"

    responses, clients = tracked_stream_transport(monkeypatch, Bytes())
    stream = await ModelProvider().stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    chunks = [chunk async for chunk in stream]
    await stream.aclose()  # type: ignore[attr-defined]

    assert chunks == [b"first", b"second", b"third"]
    assert responses[0].close_count == 1
    assert clients[0].close_count == 1


@pytest.mark.asyncio
async def test_stream_iteration_error_closes_response_and_client_once(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    class FailingBytes(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"first"
            raise RuntimeError("stream failed")

    responses, clients = tracked_stream_transport(monkeypatch, FailingBytes())
    stream = await ModelProvider().stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    assert await anext(stream) == b"first"
    with pytest.raises(RuntimeError, match="stream failed"):
        await anext(stream)
    await stream.aclose()  # type: ignore[attr-defined]

    assert responses[0].close_count == 1
    assert clients[0].close_count == 1


@pytest.mark.asyncio
async def test_stream_iteration_cancellation_closes_response_and_client_once(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    waiting = asyncio.Event()

    class BlockingBytes(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"first"
            waiting.set()
            await asyncio.Event().wait()

    responses, clients = tracked_stream_transport(monkeypatch, BlockingBytes())
    stream = await ModelProvider().stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    assert await anext(stream) == b"first"
    pending = asyncio.create_task(anext(stream))
    await asyncio.wait_for(waiting.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await stream.aclose()  # type: ignore[attr-defined]

    assert responses[0].close_count == 1
    assert clients[0].close_count == 1
