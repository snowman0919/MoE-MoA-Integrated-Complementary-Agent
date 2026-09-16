"""Shared HTTPX client helpers used across gateway modules."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx


def opencode_headers(api_key: str, session_id: str | None = None) -> dict[str, str]:
    """Return the headers OpenCode Go requires for coding-agent traffic."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "dgx-moa-gateway/1.0",
    }
    if session_id:
        headers["x-opencode-session"] = hmac.new(
            api_key.encode(), session_id.encode(), hashlib.sha256
        ).hexdigest()
    return headers


def make_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create a single AsyncClient with optional timeout/transport overrides."""
    kwargs: dict[str, Any] = {"timeout": timeout}
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.AsyncClient(**kwargs)


@asynccontextmanager
async def managed_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Create one request-scoped AsyncClient and guarantee closure."""
    client = make_http_client(timeout=timeout, transport=transport)
    try:
        yield client
    finally:
        await client.aclose()
