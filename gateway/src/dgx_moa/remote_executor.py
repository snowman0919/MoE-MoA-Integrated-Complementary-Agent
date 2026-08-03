from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, cast

import httpx

from .config import RemoteExecutorConfig
from .frontier import (
    FrontierExecutorResult,
    normalize_openrouter_tool_calls,
    sanitize_executor_tool_paths,
)
from .providers import StageTimeout


class RemoteExecutorUnavailable(RuntimeError):
    pass


class OpenCodeExecutorProvider:
    """One pinned OpenCode Go Executor turn with no host mutation authority."""

    name = "opencode_go"

    def __init__(
        self,
        config: RemoteExecutorConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self._degraded_until = 0.0

    def _api_key(self) -> str:
        key = os.getenv(self.config.api_key_env, "").strip()
        if key or self.config.api_key_file is None:
            return key
        path = Path(self.config.api_key_file)
        try:
            if path.stat().st_mode & 0o077:
                raise RemoteExecutorUnavailable("remote executor key file permissions are unsafe")
            return path.read_text().strip()
        except OSError as error:
            raise RemoteExecutorUnavailable("remote executor credential is unavailable") from error

    async def execute(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        if time.monotonic() < self._degraded_until:
            raise RemoteExecutorUnavailable("remote executor is cooling down")
        key = self._api_key()
        if not key:
            raise RemoteExecutorUnavailable("remote executor credential is unavailable")
        workspace_root = request.get("_client_workspace_path")
        body = {
            name: value
            for name, value in request.items()
            if name
            in {
                "messages",
                "tools",
                "tool_choice",
                "parallel_tool_calls",
                "response_format",
                "max_tokens",
                "temperature",
                "top_p",
                "stop",
            }
        }
        messages = body.get("messages")
        if not isinstance(messages, list):
            raise RemoteExecutorUnavailable("remote executor messages are invalid")
        body.update(
            {
                "model": self.config.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the secondary Executor. Reason privately in English, answer "
                            "in the last user's language, and use only supplied tool definitions. "
                            "Never claim a tool result before the client returns it."
                        ),
                    },
                    *messages,
                ],
            }
        )
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=None) as client:
                    response = await client.post(
                        f"{self.config.endpoint.rstrip('/')}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Accept": "application/json",
                            "User-Agent": "dgx-moa/2.0",
                        },
                        json=body,
                    )
                    response.raise_for_status()
                    payload = cast(dict[str, Any], response.json())
        except (TimeoutError, httpx.TimeoutException) as error:
            self._degraded_until = time.monotonic() + self.config.failure_cooldown_seconds
            raise StageTimeout("remote_executor") from error
        except (httpx.HTTPError, ValueError) as error:
            self._degraded_until = time.monotonic() + self.config.failure_cooldown_seconds
            raise RemoteExecutorUnavailable(
                f"remote executor request failed: {type(error).__name__}"
            ) from error

        try:
            choice = payload["choices"][0]
            raw_message = choice["message"]
            tool_calls = normalize_openrouter_tool_calls(raw_message.get("tool_calls"))
            message, sanitized = sanitize_executor_tool_paths(
                FrontierExecutorResult.model_validate(
                    {
                        "role": "assistant",
                        "content": raw_message.get("content"),
                        "tool_calls": tool_calls,
                        "finish_reason": choice.get(
                            "finish_reason", "tool_calls" if tool_calls else "stop"
                        ),
                    }
                ),
                workspace_root,
            )
        except (KeyError, TypeError, ValueError) as error:
            self._degraded_until = time.monotonic() + self.config.failure_cooldown_seconds
            raise RemoteExecutorUnavailable("remote executor response is invalid") from error

        return {
            "id": payload.get("id", f"chatcmpl-opencode-{correlation_id}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", self.config.model),
            "choices": [
                {
                    "index": 0,
                    "message": message.model_dump(exclude={"finish_reason"}),
                    "finish_reason": message.finish_reason,
                }
            ],
            "usage": payload.get("usage", {}),
            "provider_provenance": {
                "provider": self.name,
                "model": self.config.model,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "cost_usd": 0.0,
                "sanitized_absolute_workdirs": sanitized,
            },
        }
