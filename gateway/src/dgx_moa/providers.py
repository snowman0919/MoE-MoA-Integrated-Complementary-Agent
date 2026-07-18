from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from .config import ModelConfig


class StageTimeout(TimeoutError):
    def __init__(self, stage: str):
        super().__init__(f"{stage} timed out")
        self.stage = stage


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
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        timeout_seconds = self.timeout if timeout_seconds is None else timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        f"{model.base_url.rstrip('/')}/v1/chat/completions",
                        json=self.body(role, model, request),
                    )
                    response.raise_for_status()
                    return cast(dict[str, Any], response.json())
        except (TimeoutError, httpx.TimeoutException) as error:
            raise StageTimeout(stage or role) from error

    async def stream(
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> AsyncIterator[bytes]:
        body = self.body(role, model, request)
        body["stream"] = True
        timeout_seconds = self.timeout if timeout_seconds is None else timeout_seconds
        timeout_stage = stage or role
        client = httpx.AsyncClient(timeout=None)
        response: httpx.Response | None = None
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await client.send(
                    client.build_request(
                        "POST", f"{model.base_url.rstrip('/')}/v1/chat/completions", json=body
                    ),
                    stream=True,
                )
                if response.is_error:
                    await response.aread()
                response.raise_for_status()
                iterator = response.aiter_bytes()
                first = await anext(iterator, None)
        except (TimeoutError, httpx.TimeoutException) as error:
            if response is not None:
                await response.aclose()
            await client.aclose()
            raise StageTimeout(timeout_stage) from error
        except Exception:
            if response is not None:
                await response.aclose()
            await client.aclose()
            raise

        async def chunks() -> AsyncIterator[bytes]:
            try:
                if first is not None:
                    yield first
                async for chunk in iterator:
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
