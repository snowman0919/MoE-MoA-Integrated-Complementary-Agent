"""Pinned OpenCode Go Executor overflow provider."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, cast

import httpx

from .http_client import managed_http_client
from .providers import StageTimeout


class OverflowExecutorUnavailable(RuntimeError):
    pass


class OverflowExecutorInvalidOutput(OverflowExecutorUnavailable):
    pass


class OpenCodeGoExecutorProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key_env: str,
        model: str = "deepseek-v4-flash",
        timeout_seconds: float = 14_400,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _url(self, resource: str) -> str:
        base = self.endpoint if self.endpoint.endswith("/v1") else f"{self.endpoint}/v1"
        return f"{base}/{resource.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise OverflowExecutorUnavailable(
                f"Executor Flash credential environment is unset: {self.api_key_env}"
            )
        return {"Authorization": f"Bearer {api_key}"}

    async def available(self) -> bool:
        try:
            async with managed_http_client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(self._url("models"), headers=self._headers())
                response.raise_for_status()
                payload = response.json()
                models = payload.get("data", []) if isinstance(payload, dict) else []
            return any(item.get("id") == self.model for item in models if isinstance(item, dict))
        except (httpx.HTTPError, OverflowExecutorUnavailable, TypeError, ValueError):
            return False

    async def execute(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        body = {
            key: value
            for key, value in request.items()
            if not key.startswith("_") and key not in {"metadata", "stream_options"}
        }
        body.update({"model": self.model, "stream": False})
        if isinstance(messages := body.get("messages"), list):
            body["messages"] = [
                {**message, "role": "system"}
                if isinstance(message, dict) and message.get("role") == "developer"
                else {**message, "reasoning_content": ""}
                if isinstance(message, dict)
                and message.get("role") == "assistant"
                and message.get("tool_calls")
                and "reasoning_content" not in message
                else message
                for message in messages
            ]
        if body.get("tool_choice") == "required":
            body["tool_choice"] = "auto"
        body["max_tokens"] = max(int(body.get("max_tokens", 0) or 0), 4_096)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with managed_http_client(timeout=None, transport=self.transport) as client:
                    response = await client.post(
                        self._url("chat/completions"),
                        headers=self._headers(),
                        json=body,
                    )
                    if response.status_code in {401, 403}:
                        raise OverflowExecutorUnavailable(
                            "Executor Flash authorization or region opt-in is unavailable"
                        )
                    response.raise_for_status()
                    raw_payload = response.json()
        except (TimeoutError, httpx.TimeoutException) as error:
            raise StageTimeout("executor_total") from error
        if not isinstance(raw_payload, dict):
            raise OverflowExecutorUnavailable("Executor Flash returned a non-object response")
        payload = cast(dict[str, Any], raw_payload)
        choices = payload.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices else None
        if not isinstance(message, dict) or not (
            message.get("content") or message.get("tool_calls")
        ):
            raise OverflowExecutorInvalidOutput("Executor Flash returned no public output")
        payload["provider_provenance"] = {
            "provider": "opencode_go",
            "model": self.model,
            "engine": "remote",
            "executor_slot": "remote_overflow",
            "capabilities": ["text", "native_tools", "responses", "streaming"],
            "correlation_id": correlation_id,
            "transport": "openai_compatible_http",
            "rendered_prompt_bytes": len(
                json.dumps(
                    body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ),
        }
        return payload
