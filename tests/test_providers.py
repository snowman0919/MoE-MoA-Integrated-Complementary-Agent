from __future__ import annotations

import json

import httpx
import pytest
from dgx_moa.providers import ModelProvider, parse_json_content


def test_judge_is_read_only(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "judge",
        settings.models["judge"],
        {"messages": [], "tools": [{"type": "function"}], "tool_choice": "required"},
    )
    assert "tools" not in body
    assert "tool_choice" not in body
    assert body["stream"] is False


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

    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, stream=ErrorStream())
    )
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
