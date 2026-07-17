from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class StreamObservation:
    max_capture_bytes: int
    captured: bytearray = field(default_factory=bytearray)
    assistant_content: list[str] = field(default_factory=list)
    finish_reasons: list[str] = field(default_factory=list)
    tool_delta_seen: bool = False
    done_seen: bool = False

    def observe(self, event: bytes) -> None:
        remaining = self.max_capture_bytes - len(self.captured)
        if remaining > 0:
            self.captured.extend(event[:remaining])
        for line in event.decode(errors="replace").splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                payload = json.loads(line[6:])
            except ValueError:
                continue
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                self.assistant_content.append(delta["content"])
            self.tool_delta_seen |= bool(delta.get("tool_calls"))
            if choice.get("finish_reason"):
                self.finish_reasons.append(str(choice["finish_reason"]))


def _next_event(buffer: bytearray) -> tuple[int, int] | None:
    delimiters = (
        (index, len(delimiter))
        for delimiter in (b"\n\n", b"\r\n\r\n")
        if (index := buffer.find(delimiter)) >= 0
    )
    return min(delimiters, default=None)


def _is_done(event: bytes) -> bool:
    return any(line == b"data: [DONE]" for line in event.splitlines())


async def forward_sse(
    upstream: AsyncIterator[bytes],
    observation: StreamObservation,
    *,
    max_event_bytes: int,
) -> AsyncIterator[bytes]:
    buffer = bytearray()
    try:
        async for chunk in upstream:
            buffer.extend(chunk)
            while framed := _next_event(buffer):
                index, delimiter_size = framed
                event_size = index + delimiter_size
                if event_size > max_event_bytes:
                    raise ValueError(f"SSE event exceeds {max_event_bytes} bytes")
                event = bytes(buffer[:event_size])
                del buffer[:event_size]
                observation.observe(event)
                if _is_done(event):
                    if observation.done_seen:
                        continue
                    observation.done_seen = True
                yield event
            if len(buffer) > max_event_bytes:
                raise ValueError(f"SSE event exceeds {max_event_bytes} bytes")
        if buffer:
            raise ValueError("incomplete SSE event at EOF")
        if not observation.done_seen:
            observation.done_seen = True
            yield b"data: [DONE]\n\n"
    finally:
        close = getattr(upstream, "aclose", None)
        if close is not None:
            await close()
