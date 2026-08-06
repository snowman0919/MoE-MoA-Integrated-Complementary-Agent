"""Shared HTTPX client helpers used across gateway modules."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx


def make_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
) -> httpx.AsyncClient:
    """Create a single AsyncClient with optional timeout/transport overrides."""
    kwargs: dict[str, Any] = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if transport is not None:
        kwargs["transport"] = transport
    return client_factory(**kwargs)


@asynccontextmanager
async def managed_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
) -> AsyncIterator[httpx.AsyncClient]:
    """Create one request-scoped AsyncClient and guarantee closure."""
    client = make_http_client(
        timeout=timeout, transport=transport, client_factory=client_factory
    )
    try:
        yield client
    finally:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            result = aclose()
            if inspect.isawaitable(result):
                await result

        close = getattr(client, "close", None)
        if callable(close):
            close()
