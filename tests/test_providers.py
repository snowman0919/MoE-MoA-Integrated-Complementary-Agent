from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from dgx_moa.http_client import make_http_client
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


@pytest.mark.asyncio
async def test_explicit_none_disables_httpx_default_timeout() -> None:
    client = make_http_client(timeout=None)
    try:
        assert client.timeout == httpx.Timeout(None)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_backend_contract_reports_identity_and_supports_cancel(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    model = settings.models["executor"].model_copy(
        update={
            "engine": "sglang",
            "executor_slot": "local_candidate",
            "capabilities": frozenset({"text", "vision", "streaming"}),
        }
    )
    provider = ModelProvider()
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": model.served_name}]})
        return httpx.Response(200, json={"count": 7, "max_model_len": 65536})

    def client(**kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = httpx.MockTransport(respond)
        return httpx.AsyncClient(**kwargs)

    monkeypatch.setattr("dgx_moa.providers.make_http_client", client)
    monkeypatch.setattr("dgx_moa.http_client.make_http_client", client)
    assert provider.capabilities(model) == frozenset({"text", "vision", "streaming"})
    assert await provider.health(model) is True
    assert await provider.models(model) == [model.served_name]
    assert await provider.tokenize(model, {"messages": []}) == {
        "count": 7,
        "max_model_len": 65536,
    }
    assert await provider.tokenize(model, {"messages": []}) == {
        "count": 7,
        "max_model_len": 65536,
    }
    assert paths.count("/tokenize") == 1

    closed = False

    async def stream():  # type: ignore[no-untyped-def]
        nonlocal closed
        try:
            yield b"x"
        finally:
            closed = True

    iterator = stream()
    await anext(iterator)
    await provider.cancel(iterator)
    assert closed is True
    await provider.aclose()


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
        "think": False,
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


def test_mistral_executor_maps_developer_role_without_mutating_request(settings) -> None:  # type: ignore[no-untyped-def]
    request = {
        "messages": [
            {"role": "developer", "content": "Follow the client instructions."},
            {"role": "user", "content": "Work."},
        ]
    }

    model = settings.models["executor"].model_copy(update={"reasoning_parser": "mistral"})
    body = ModelProvider.body("executor", model, request)

    assert body["messages"] == [
        {"role": "system", "content": "Follow the client instructions."},
        {"role": "user", "content": "Work."},
    ]
    assert request["messages"][0]["role"] == "developer"

    continuation = ModelProvider.body(
        "executor",
        model,
        {"messages": [{"role": "assistant", "content": "Partial answer"}]},
    )
    assert continuation["continue_final_message"] is True
    assert continuation["add_generation_prompt"] is False


def test_mistral_executor_normalizes_matching_tool_call_ids_without_mutation(settings) -> None:  # type: ignore[no-untyped-def]
    call_id = "call_9e8d4c55b9a64c24985c9d943248048e"
    request = {
        "messages": [
            {"role": "assistant", "tool_calls": [{"id": call_id, "type": "function"}]},
            {"role": "tool", "tool_call_id": call_id, "content": "done"},
        ]
    }
    model = settings.models["executor"].model_copy(update={"reasoning_parser": "mistral"})

    body = ModelProvider.body("executor", model, request)

    normalized_id = body["messages"][0]["tool_calls"][0]["id"]
    assert normalized_id == body["messages"][1]["tool_call_id"]
    assert len(normalized_id) == 9
    assert request["messages"][0]["tool_calls"][0]["id"] == call_id


def test_mistral_executor_keeps_shared_suffix_tool_call_ids_distinct(settings) -> None:  # type: ignore[no-untyped-def]
    first = "call_read_agents_requirements"
    second = "call_read_readme_requirements"
    request = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"id": first}, {"id": second}],
            },
            {"role": "tool", "tool_call_id": first, "content": "agents"},
            {"role": "tool", "tool_call_id": second, "content": "readme"},
        ]
    }
    model = settings.models["executor"].model_copy(update={"reasoning_parser": "mistral"})

    body = ModelProvider.body("executor", model, request)

    call_ids = [call["id"] for call in body["messages"][0]["tool_calls"]]
    result_ids = [message["tool_call_id"] for message in body["messages"][1:]]
    assert len(set(call_ids)) == 2
    assert call_ids == result_ids


def test_mistral_executor_does_not_put_system_messages_after_tools(settings) -> None:  # type: ignore[no-untyped-def]
    request = {
        "messages": [
            {"role": "developer", "content": "Initial instructions"},
            {"role": "assistant", "tool_calls": [{"id": "123456789"}]},
            {"role": "tool", "tool_call_id": "123456789", "content": "done"},
            {"role": "developer", "content": "Repeated instructions"},
        ]
    }
    model = settings.models["executor"].model_copy(update={"reasoning_parser": "mistral"})

    body = ModelProvider.body("executor", model, request)

    assert [message["role"] for message in body["messages"]] == [
        "system",
        "assistant",
        "tool",
        "user",
    ]


def test_qwen_executor_collapses_leading_instructions_without_mutation(settings) -> None:  # type: ignore[no-untyped-def]
    request = {
        "messages": [
            {"role": "system", "content": "Runtime instructions"},
            {"role": "developer", "content": "Client instructions"},
            {"role": "user", "content": "Work."},
            {"role": "developer", "content": "Continue now."},
        ]
    }

    model = settings.models["executor"].model_copy(update={"reasoning_parser": "qwen3"})
    body = ModelProvider.body("executor", model, request)

    assert body["messages"] == [
        {"role": "system", "content": "Runtime instructions\n\nClient instructions"},
        {"role": "user", "content": "Work."},
        {"role": "user", "content": "Continue now."},
    ]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert request["messages"][1]["role"] == "developer"

    multimodal = ModelProvider.body(
        "executor",
        model,
        {
            "messages": [
                {"role": "system", "content": "Runtime instructions"},
                {
                    "role": "developer",
                    "content": [{"type": "text", "text": "Client instructions"}],
                },
                {"role": "user", "content": "Work."},
            ]
        },
    )
    assert multimodal["messages"][0]["content"] == [
        {"type": "text", "text": "Runtime instructions"},
        {"type": "text", "text": "Client instructions"},
    ]

    required = ModelProvider.body(
        "executor",
        model,
        {
            "messages": [{"role": "user", "content": "Use a tool."}],
            "tool_choice": "required",
            "chat_template_kwargs": {"preserve_thinking": False},
        },
    )
    assert required["chat_template_kwargs"] == {
        "preserve_thinking": False,
        "enable_thinking": False,
    }
    automatic = ModelProvider.body(
        "executor",
        model,
        {
            "messages": [{"role": "user", "content": "Use a tool if needed."}],
            "tools": [{"type": "function", "function": {"name": "terminal"}}],
            "tool_choice": "auto",
        },
    )
    assert automatic["chat_template_kwargs"] == {"enable_thinking": False}


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


def test_qwen_planner_returns_public_structured_content(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "planner",
        settings.models["planner"].model_copy(update={"reasoning_parser": "qwen3"}),
        {
            "messages": [{"role": "system", "content": "Plan in English."}],
            "chat_template_kwargs": {"truncate_history_thinking": False},
        },
    )

    assert body["chat_template_kwargs"] == {
        "truncate_history_thinking": False,
        "enable_thinking": False,
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

    provider = ModelProvider()
    fits = await provider.context_fits(
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
    await provider.aclose()


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

    result = await ModelProvider().complete(
        "reviewer",
        settings.models["reviewer"].model_copy(update={"reasoning_parser": "cohere_command4"}),
        {"messages": [{"role": "system", "content": "review"}], "max_tokens": 1500},
    )

    assert completion_bodies[0]["max_tokens"] == 1491
    assert completion_bodies[0]["chat_template_kwargs"] == {"reasoning": False}
    assert result["_rendered_prompt_bytes"] == len(
        json.dumps(
            completion_bodies[0],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


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
    assert result["_rendered_prompt_bytes"] == sum(
        len(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        for body in completion_bodies
    )


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
    provider = ModelProvider()
    pending = asyncio.create_task(
        provider.stream(
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
    assert not clients[0].is_closed
    await provider.aclose()
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
    provider = ModelProvider()
    stream = await provider.stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    await stream.aclose()  # type: ignore[attr-defined]
    await stream.aclose()  # type: ignore[attr-defined]

    assert responses[0].is_closed
    assert not clients[0].is_closed
    assert responses[0].close_count == 1
    await provider.aclose()
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
    provider = ModelProvider()
    stream = await provider.stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    chunks = [chunk async for chunk in stream]
    await stream.aclose()  # type: ignore[attr-defined]

    assert chunks == [b"first", b"second", b"third"]
    assert responses[0].close_count == 1
    assert clients[0].close_count == 0
    await provider.aclose()
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
    provider = ModelProvider()
    stream = await provider.stream(
        "executor",
        settings.models["executor"],
        {"messages": []},
    )

    assert await anext(stream) == b"first"
    with pytest.raises(RuntimeError, match="stream failed"):
        await anext(stream)
    await stream.aclose()  # type: ignore[attr-defined]

    assert responses[0].close_count == 1
    assert clients[0].close_count == 0
    await provider.aclose()
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
    provider = ModelProvider()
    stream = await provider.stream(
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
    assert clients[0].close_count == 0
    await provider.aclose()
    assert clients[0].close_count == 1
