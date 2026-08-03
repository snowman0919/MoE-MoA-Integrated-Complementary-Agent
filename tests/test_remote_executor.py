from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from dgx_moa.config import RemoteExecutorConfig
from dgx_moa.remote_executor import OpenCodeExecutorProvider, RemoteExecutorUnavailable


@pytest.mark.asyncio
async def test_opencode_executor_preserves_tool_call_and_sanitizes_workdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "kimi-k3"
        assert body["stream"] is False
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-kimi",
                "model": "kimi-k3",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "exec_command",
                                        "arguments": json.dumps(
                                            {"cmd": "pwd", "workdir": str(tmp_path)}
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    provider = OpenCodeExecutorProvider(
        RemoteExecutorConfig(enabled=True, provider="opencode_go"),
        transport=httpx.MockTransport(handler),
    )
    result = await provider.execute(
        {
            "messages": [{"role": "user", "content": "작업해"}],
            "tools": [{"type": "function", "function": {"name": "exec_command"}}],
            "_client_workspace_path": str(tmp_path),
        },
        "request:executor",
    )

    call = result["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "exec_command"
    assert json.loads(call["function"]["arguments"]) == {"cmd": "pwd"}
    assert result["provider_provenance"]["provider"] == "opencode_go"
    assert result["provider_provenance"]["sanitized_absolute_workdirs"] == 1


@pytest.mark.asyncio
async def test_opencode_executor_rejects_world_readable_key_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    key_file = tmp_path / "key"
    key_file.write_text("secret")
    key_file.chmod(0o644)
    provider = OpenCodeExecutorProvider(
        RemoteExecutorConfig(
            enabled=True,
            provider="opencode_go",
            api_key_file=key_file,
        )
    )

    with pytest.raises(RemoteExecutorUnavailable, match="permissions"):
        await provider.execute({"messages": []}, "request:executor")
