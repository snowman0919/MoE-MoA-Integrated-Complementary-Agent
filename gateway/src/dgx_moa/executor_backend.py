from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from .config import ModelConfig

ExecutorEngine = Literal["vllm", "sglang", "remote", "ollama"]
ExecutorSlot = Literal["local_primary", "local_candidate", "remote_overflow"]
ExecutorCapability = Literal[
    "text",
    "vision",
    "native_tools",
    "responses",
    "streaming",
    "lora",
    "speculative",
]


class ExecutorBackend(Protocol):
    async def health(self, model: ModelConfig) -> bool: ...

    async def models(self, model: ModelConfig) -> list[str]: ...

    async def tokenize(
        self, model: ModelConfig, request: dict[str, Any], *, role: str = "executor"
    ) -> dict[str, Any] | None: ...

    async def context_fits(
        self,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        role: str = "executor",
        timeout_seconds: float = 10,
    ) -> bool | None: ...

    async def complete(
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]: ...

    async def stream(
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> AsyncIterator[bytes]: ...

    async def cancel(self, stream: AsyncIterator[bytes]) -> None: ...

    def capabilities(self, model: ModelConfig) -> frozenset[ExecutorCapability]: ...
