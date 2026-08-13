"""Shared HTTPX client helpers used across gateway modules."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx


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
