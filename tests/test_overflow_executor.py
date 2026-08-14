from __future__ import annotations

import json

import httpx
import pytest
from dgx_moa.overflow_executor import (
    OpenCodeGoExecutorProvider,
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

    assert captured["model"] == "deepseek-v4-flash"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][2]["reasoning_content"] == ""
    assert captured["tool_choice"] == "auto"
    assert captured["parallel_tool_calls"] is True
    assert captured["stream"] is False
    assert captured["max_tokens"] == 4096
    assert not {"metadata", "stream_options", "_client_workspace_path"} & captured.keys()
    assert result["provider_provenance"]["provider"] == "opencode_go"


@pytest.mark.asyncio
async def test_opencode_go_executor_treats_region_opt_in_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                403,
                json={"error": {"type": "RegionError", "message": "account opt-in required"}},
            )
        ),
    )

    with pytest.raises(OverflowExecutorUnavailable, match="region opt-in"):
        await provider.execute({"messages": []}, "request-1")


@pytest.mark.asyncio
async def test_opencode_go_executor_rejects_hidden_reasoning_without_public_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    provider = OpenCodeGoExecutorProvider(
        endpoint="https://opencode.invalid",
        api_key_env="OPENCODE_GO_API_KEY",
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

    with pytest.raises(OverflowExecutorUnavailable, match="no public output"):
        await provider.execute({"messages": [], "max_tokens": 128}, "request-1")
