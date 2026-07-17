from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from .config import ModelConfig


class ModelProvider:
    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout

    @staticmethod
    def body(role: str, model: ModelConfig, request: dict[str, Any]) -> dict[str, Any]:
        body = request.copy()
        body["model"] = model.served_name
        body.pop("metadata", None)
        if role != "executor":
            body.pop("tools", None)
            body.pop("tool_choice", None)
            body["stream"] = False
        return body

    async def complete(
        self, role: str, model: ModelConfig, request: dict[str, Any]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{model.base_url.rstrip('/')}/v1/chat/completions",
                json=self.body(role, model, request),
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

    async def stream(
        self, role: str, model: ModelConfig, request: dict[str, Any]
    ) -> AsyncIterator[bytes]:
        body = self.body(role, model, request)
        body["stream"] = True
        client = httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.send(
                client.build_request(
                    "POST", f"{model.base_url.rstrip('/')}/v1/chat/completions", json=body
                ),
                stream=True,
            )
            if response.is_error:
                await response.aread()
            response.raise_for_status()
        except Exception:
            await client.aclose()
            raise

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return chunks()


def response_message(response: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], response.get("choices", [{}])[0].get("message", {}))


def parse_json_content(response: dict[str, Any]) -> dict[str, Any]:
    content = response_message(response).get("content")
    if not isinstance(content, str):
        raise ValueError("structured model response missing content")
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return cast(dict[str, Any], json.loads(content))


def validate_assistant_response(response: dict[str, Any]) -> None:
    message = response_message(response)
    calls = message.get("tool_calls") or []
    for call in calls:
        if not call.get("id"):
            raise ValueError("tool call ID missing")
        function = call.get("function") or {}
        if not function.get("name"):
            raise ValueError("tool function name missing")
        try:
            json.loads(function.get("arguments", ""))
        except (TypeError, ValueError) as error:
            raise ValueError("malformed tool arguments") from error
