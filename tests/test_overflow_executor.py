from __future__ import annotations

import json

import httpx
import pytest
from dgx_moa.overflow_executor import (
    OpenCodeGoExecutorProvider,
    OverflowExecutorInvalidOutput,
    OverflowExecutorUnavailable,
)


@pytest.mark.asyncio
async def test_opencode_go_executor_preserves_native_tools_and_strips_private_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "read_file", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        )

    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
        model="mimo-v2.5",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.execute(
        {
            "model": "dgx-moa",
            "messages": [
                {"role": "developer", "content": "Follow the request."},
                {"role": "user", "content": "inspect"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "prior-call", "type": "function"}],
                },
                {"role": "tool", "tool_call_id": "prior-call", "content": "done"},
            ],
            "tools": [{"type": "function", "function": {"name": "read_file"}}],
            "tool_choice": "required",
            "parallel_tool_calls": True,
            "stream": True,
            "stream_options": {"include_usage": True},
            "metadata": {"secret": "never-forward"},
            "_client_workspace_path": "/private/path",
        },
        "request-1:executor",
    )

    assert captured["model"] == "mimo-v2.5"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][2]["reasoning_content"] == ""
    assert captured["tool_choice"] == "auto"
    assert captured["parallel_tool_calls"] is True
    assert captured["stream"] is False
    assert captured["max_tokens"] == 4096
    assert not {"metadata", "stream_options", "_client_workspace_path"} & captured.keys()
    assert result["provider_provenance"]["provider"] == "opencode"
    assert result["provider_provenance"]["route"] == "fallback"


@pytest.mark.asyncio
async def test_opencode_go_executor_treats_region_opt_in_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
        model="mimo-v2.5",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                403,
                json={"error": {"type": "RegionError", "message": "account opt-in required"}},
            )
        ),
    )

    with pytest.raises(OverflowExecutorUnavailable, match="provider authorization"):
        await provider.execute({"messages": []}, "request-1")


@pytest.mark.asyncio
async def test_opencode_go_executor_rejects_hidden_reasoning_without_public_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
        model="mimo-v2.5",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "", "reasoning_content": "hidden"},
                            "finish_reason": "length",
                        }
                    ]
                },
            )
        ),
    )

    with pytest.raises(OverflowExecutorInvalidOutput, match="no public output"):
        await provider.execute({"messages": [], "max_tokens": 128}, "request-1")


@pytest.mark.asyncio
async def test_model_failure_uses_rollback_but_provider_failure_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models: list[str] = []

    async def model_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        models.append(body["model"])
        if body["model"] == "mimo-v2.5":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
        model="mimo-v2.5",
        rollback_model="deepseek-v4-flash",
        transport=httpx.MockTransport(model_handler),
    )
    result = await provider.execute({"messages": []}, "request-1")
    assert models == ["mimo-v2.5", "deepseek-v4-flash"]
    assert result["provider_provenance"]["route"] == "rollback"

    models.clear()
    provider.transport = httpx.MockTransport(
        lambda request: models.append(json.loads(request.content)["model"]) or httpx.Response(503)
    )
    with pytest.raises(OverflowExecutorUnavailable):
        await provider.execute({"messages": []}, "request-2")
    assert models == ["mimo-v2.5"]
