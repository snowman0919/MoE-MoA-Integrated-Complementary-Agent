from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from .config import ModelConfig

PLANNER_REASONING_TOKENS = 768
PLANNER_FINAL_TOKENS = 1_536


class StageTimeout(TimeoutError):
    def __init__(self, stage: str):
        super().__init__(f"{stage} timed out")
        self.stage = stage


class OwnedByteStream:
    def __init__(
        self,
        first: bytes | None,
        iterator: AsyncIterator[bytes],
        response: httpx.Response,
        client: httpx.AsyncClient,
    ) -> None:
        self._first = first
        self._first_pending = first is not None
        self._iterator = iterator
        self._response = response
        self._client = client
        self._close_lock = asyncio.Lock()
        self._closed = False

    def __aiter__(self) -> OwnedByteStream:
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        try:
            if self._first_pending:
                self._first_pending = False
                assert self._first is not None
                return self._first
            return await anext(self._iterator)
        except StopAsyncIteration:
            await self.aclose()
            raise
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                if not self._response.is_closed:
                    await self._response.aclose()
            finally:
                if not self._client.is_closed:
                    await self._client.aclose()


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
        if role == "planner" and model.reasoning_parser == "nemotron_v3":
            template_options = dict(body.get("chat_template_kwargs") or {})
            template_options.update(
                enable_thinking=True,
                reasoning_budget=PLANNER_REASONING_TOKENS,
            )
            body["chat_template_kwargs"] = template_options
        return body

    @staticmethod
    async def fit_specialist_completion(
        client: httpx.AsyncClient,
        model: ModelConfig,
        body: dict[str, Any],
    ) -> None:
        """Fit local specialist output to the context actually served by vLLM."""
        requested = body.get("max_tokens")
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
            return
        try:
            response = await client.post(
                f"{model.base_url.rstrip('/')}/tokenize",
                json={
                    "model": model.served_name,
                    "messages": body.get("messages", []),
                    "chat_template_kwargs": body.get("chat_template_kwargs"),
                },
            )
            if response.is_error:
                return
            tokenization = response.json()
        except (httpx.HTTPError, ValueError):
            return
        prompt_tokens = tokenization.get("count")
        context_length = tokenization.get("max_model_len")
        if (
            not isinstance(prompt_tokens, int)
            or isinstance(prompt_tokens, bool)
            or not isinstance(context_length, int)
            or isinstance(context_length, bool)
        ):
            return
        available = max(1, context_length - prompt_tokens - 8)
        body["max_tokens"] = min(requested, available)

    @staticmethod
    async def context_fits(
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float = 10,
    ) -> bool | None:
        """Return measured local context fit, or None when the tokenizer is unavailable."""
        body = ModelProvider.body("executor", model, request)
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        f"{model.base_url.rstrip('/')}/tokenize",
                        json={
                            "model": model.served_name,
                            "messages": body.get("messages", []),
                            "tools": body.get("tools"),
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
        except (TimeoutError, httpx.HTTPError, ValueError):
            return None
        prompt_tokens = payload.get("count")
        context_length = payload.get("max_model_len", model.context_length)
        output_tokens = body.get("max_tokens", 0)
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (prompt_tokens, context_length, output_tokens)
        ):
            return None
        return int(prompt_tokens) + int(output_tokens) <= int(context_length)

    @classmethod
    async def complete_reasoning_planner(
        cls,
        client: httpx.AsyncClient,
        model: ModelConfig,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Run bounded English analysis, then finalize the structured local plan."""
        analysis_body = {
            **body,
            "max_tokens": min(
                int(body.get("max_tokens", PLANNER_REASONING_TOKENS)),
                PLANNER_REASONING_TOKENS,
            ),
        }
        analysis_body.pop("response_format", None)
        await cls.fit_specialist_completion(client, model, analysis_body)
        analysis_response = await client.post(
            f"{model.base_url.rstrip('/')}/v1/chat/completions",
            json=analysis_body,
        )
        analysis_response.raise_for_status()
        analysis_payload = cast(dict[str, Any], analysis_response.json())
        analysis_message = (
            analysis_payload.get("choices", [{}])[0].get("message", {})
            if isinstance(analysis_payload.get("choices"), list)
            else {}
        )
        private_analysis = (
            analysis_message.get("reasoning_content") or analysis_message.get("content") or ""
        )

        final_messages = [dict(message) for message in body.get("messages", [])]
        if isinstance(private_analysis, str) and private_analysis:
            final_messages.append(
                {"role": "assistant", "reasoning_content": private_analysis, "content": ""}
            )
        final_messages.append(
            {
                "role": "user",
                "content": (
                    "Using the private English analysis above, return only one minimal valid "
                    "JSON object matching the required schema. Do not repeat the analysis."
                ),
            }
        )
        final_body = {
            **body,
            "messages": final_messages,
            "max_tokens": min(
                int(body.get("max_tokens", PLANNER_FINAL_TOKENS)),
                PLANNER_FINAL_TOKENS,
            ),
            "chat_template_kwargs": {
                "enable_thinking": False,
                "truncate_history_thinking": False,
            },
        }
        await cls.fit_specialist_completion(client, model, final_body)
        final_response = await client.post(
            f"{model.base_url.rstrip('/')}/v1/chat/completions",
            json=final_body,
        )
        final_response.raise_for_status()
        final_payload = cast(dict[str, Any], final_response.json())
        usage = final_payload.setdefault("usage", {})
        analysis_usage = analysis_payload.get("usage", {})
        if isinstance(usage, dict) and isinstance(analysis_usage, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[key] = int(usage.get(key, 0) or 0) + int(analysis_usage.get(key, 0) or 0)
        return final_payload

    @staticmethod
    def ollama_body(model: ModelConfig, request: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model.served_name,
            "messages": request.get("messages", []),
            "stream": False,
            "keep_alive": model.ollama_keep_alive,
            "options": {
                "num_ctx": model.context_length,
                "num_predict": int(request.get("max_tokens", 1500)),
            },
        }
        response_format = request.get("response_format")
        if isinstance(response_format, dict):
            json_schema = response_format.get("json_schema")
            if isinstance(json_schema, dict) and isinstance(json_schema.get("schema"), dict):
                body["format"] = json_schema["schema"]
        return body

    @staticmethod
    def ollama_response(payload: dict[str, Any]) -> dict[str, Any]:
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Ollama response missing assistant content")
        if message.get("tool_calls"):
            raise ValueError("Reasoner cannot issue tools")
        prompt_tokens = int(payload.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(payload.get("eval_count", 0) or 0)
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": message["content"]},
                    "finish_reason": "stop" if payload.get("done", True) else None,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

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
                    if model.provider == "ollama":
                        response = await client.post(
                            f"{model.base_url.rstrip('/')}/api/chat",
                            json=self.ollama_body(model, request),
                        )
                    else:
                        body = self.body(role, model, request)
                        if role == "planner" and model.reasoning_parser == "nemotron_v3":
                            return await self.complete_reasoning_planner(client, model, body)
                        if role == "reviewer":
                            await self.fit_specialist_completion(client, model, body)
                        response = await client.post(
                            f"{model.base_url.rstrip('/')}/v1/chat/completions",
                            json=body,
                        )
                    response.raise_for_status()
                    payload = cast(dict[str, Any], response.json())
                    return self.ollama_response(payload) if model.provider == "ollama" else payload
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
        if model.provider == "ollama":
            raise ValueError("Ollama streaming is not used for bounded Reasoner turns")
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
        except asyncio.CancelledError:
            if response is not None:
                await response.aclose()
            await client.aclose()
            raise
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

        return OwnedByteStream(first, iterator, response, client)


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
