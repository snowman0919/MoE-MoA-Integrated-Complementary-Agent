"""OpenAI-compatible remote Executor fallback with model-only rollback."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, cast

import httpx

from .config import ModelRef, ProviderName, RoleRoute
from .http_client import managed_http_client
from .providers import StageTimeout


class OverflowExecutorUnavailable(RuntimeError):
    """Provider-wide failure: retrying another model on the provider is pointless."""


class OverflowExecutorModelFailure(RuntimeError):
    """Model-specific failure that may use the configured rollback model."""


class OverflowExecutorInvalidOutput(OverflowExecutorModelFailure):
    pass


class OpenAICompatibleExecutorProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key_env: str,
        model: str | None = None,
        rollback_model: str | None = None,
        provider: ProviderName = "opencode",
        role_route: RoleRoute | None = None,
        timeout_seconds: float = 14_400,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if role_route is None:
            if model is None:
                raise ValueError("remote Executor requires a model or RoleRoute")
            fallback = ModelRef(provider=provider, model=model)
            role_route = RoleRoute(
                primary=fallback,
                fallback=fallback,
                rollback=(
                    ModelRef(provider=provider, model=rollback_model) if rollback_model else None
                ),
            )
        selected = role_route.fallback
        if selected is None:
            raise ValueError("remote Executor RoleRoute requires a fallback")
        if any(
            candidate is not None and candidate.provider != selected.provider
            for candidate in (role_route.fallback, role_route.rollback)
        ):
            raise ValueError("remote Executor fallback and rollback must share one provider")
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.role_route = role_route
        self.model = selected.model
        self.rollback_model = role_route.rollback.model if role_route.rollback else None
        self.provider = selected.provider
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _url(self, resource: str) -> str:
        base = self.endpoint if self.endpoint.endswith("/v1") else f"{self.endpoint}/v1"
        return f"{base}/{resource.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise OverflowExecutorUnavailable(
                f"remote Executor credential environment is unset: {self.api_key_env}"
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

    @staticmethod
    def _body(request: dict[str, Any], model: str) -> dict[str, Any]:
        body = {
            key: value
            for key, value in request.items()
            if not key.startswith("_") and key not in {"metadata", "stream_options"}
        }
        body.update({"model": model, "stream": False})
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
        return body

    async def _execute_model(
        self, request: dict[str, Any], correlation_id: str, model: str, route: str
    ) -> dict[str, Any]:
        body = self._body(request, model)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with managed_http_client(timeout=None, transport=self.transport) as client:
                    response = await client.post(
                        self._url("chat/completions"), headers=self._headers(), json=body
                    )
                    if response.status_code in {401, 403, 429} or response.status_code >= 500:
                        raise OverflowExecutorUnavailable(
                            "remote Executor provider authorization, quota, or endpoint "
                            "is unavailable"
                        )
                    if response.status_code in {400, 404, 409, 422}:
                        raise OverflowExecutorModelFailure(
                            f"remote Executor model request failed: HTTP {response.status_code}"
                        )
                    response.raise_for_status()
                    raw_payload = response.json()
        except (TimeoutError, httpx.TimeoutException) as error:
            raise StageTimeout("executor_total") from error
        except httpx.HTTPError as error:
            raise OverflowExecutorUnavailable("remote Executor provider request failed") from error
        if not isinstance(raw_payload, dict):
            raise OverflowExecutorInvalidOutput("remote Executor returned a non-object response")
        payload = cast(dict[str, Any], raw_payload)
        choices = payload.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices else None
        if not isinstance(message, dict) or not (
            message.get("content") or message.get("tool_calls")
        ):
            raise OverflowExecutorInvalidOutput("remote Executor returned no public output")
        payload["provider_provenance"] = {
            "provider": self.provider,
            "model": model,
            "route": route,
            "engine": "remote",
            "executor_slot": "remote_overflow",
            "capabilities": ["text", "native_tools", "responses", "streaming"],
            "correlation_id": correlation_id,
            "transport": "openai_compatible_http",
            "rendered_prompt_bytes": len(
                json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ),
        }
        return payload

    async def execute(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        failed = self.role_route.fallback
        if failed is None:  # guarded during construction
            raise OverflowExecutorUnavailable("remote Executor fallback is not configured")
        try:
            return await self._execute_model(request, correlation_id, failed.model, "fallback")
        except OverflowExecutorModelFailure:
            next_model = self.role_route.after_failure(failed, failure_scope="model")
            if next_model is None or next_model == failed:
                raise
            return await self._execute_model(request, correlation_id, next_model.model, "rollback")


class OpenCodeGoExecutorProvider(OpenAICompatibleExecutorProvider):
    """Compatibility name for existing integrations; model selection is explicit."""
