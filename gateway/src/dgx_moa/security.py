from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Header, HTTPException, Request, status

from .config import Settings

SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b(?:hf|sk)-[A-Za-z0-9_-]{12,}\b"),
)


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower().replace("-", "_")
    credential_names = (
        "authorization",
        "cookie",
        "token",
        "secret",
        "password",
        "api_key",
        "api_keys",
    )
    return normalized in credential_names or normalized.endswith(
        tuple(f"_{name}" for name in credential_names)
    )


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if isinstance(item, str) and item in {"[REDACTED]", "[REDACTED_BY_POLICY]"}
                else "[REDACTED]"
            )
            if is_sensitive_key(key)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", value
        )
    return value


def verify_bearer(expected: dict[str, str], authorization: str | None) -> str:
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "gateway API key is not configured"
        )
    scheme, _, token = (authorization or "").partition(" ")
    matched = None
    for name, value in expected.items():
        is_match = secrets.compare_digest(token, value)
        if is_match and matched is None:
            matched = name
    if scheme.lower() != "bearer" or matched is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
    return matched


def auth_dependency(settings: Settings) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        if settings.auth_enabled:
            request.state.api_token_id = verify_bearer(
                settings.configured_api_keys(), authorization
            )
        else:
            request.state.api_token_id = "authentication-disabled"

    return authenticate


def admin_dependency(settings: Settings) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate_admin(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        if not settings.admin_api_enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin API is disabled")
        if settings.auth_enabled:
            request.state.api_token_id = verify_bearer(
                settings.configured_api_keys(), authorization
            )
            return
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin API requires loopback")

    return authenticate_admin
