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


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.search(r"(?i)token|secret|password|api.?key", key)
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


def verify_bearer(expected: str, authorization: str | None) -> None:
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "gateway API key is not configured"
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")


def auth_dependency(settings: Settings) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate(authorization: str | None = Header(default=None)) -> None:
        if settings.auth_enabled:
            verify_bearer(settings.api_key or "", authorization)

    return authenticate


def admin_dependency(settings: Settings) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate_admin(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        if not settings.admin_api_enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin API is disabled")
        if settings.auth_enabled:
            verify_bearer(settings.api_key or "", authorization)
            return
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin API requires loopback")

    return authenticate_admin
