from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from dataclasses import dataclass, field

from .usage import SQLITE_MAX_INTEGER

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def reported_usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: token_count
        for key in TOKEN_FIELDS
        if type(token_count := value.get(key)) is int and 0 <= token_count <= SQLITE_MAX_INTEGER
    }


@dataclass
class StreamObservation:
    max_capture_bytes: int
    captured: bytearray = field(default_factory=bytearray)
    assistant_content: list[str] = field(default_factory=list)
    finish_reasons: list[str] = field(default_factory=list)
    tool_delta_seen: bool = False
    tool_call_ids: list[str] = field(default_factory=list)
    done_seen: bool = False
    usage: dict[str, int] = field(default_factory=dict)

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
            self.usage.update(reported_usage(payload.get("usage")))
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                self.assistant_content.append(delta["content"])
            self.tool_delta_seen |= bool(delta.get("tool_calls"))
            for call in delta.get("tool_calls") or []:
                if (
                    isinstance(call, dict)
                    and isinstance(call_id := call.get("id"), str)
                    and call_id
                    and call_id not in self.tool_call_ids
                ):
                    self.tool_call_ids.append(call_id)
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
) -> AsyncGenerator[bytes, None]:
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
                    if not observation.done_seen:
                        observation.done_seen = True
                        yield event
                    return
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


def _response_usage(value: object) -> dict[str, object] | None:
    usage = reported_usage(value)
    if not usage:
        return None
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
    }


async def responses_sse(
    upstream: AsyncIterable[str | bytes | memoryview[int]],
    model: str,
) -> AsyncGenerator[bytes, None]:
    """Translate Chat Completions SSE into Responses text and function-call events."""
    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"
    created_at = int(time.time())
    sequence_number = 0
    text_parts: list[str] = []
    tool_calls: dict[int, dict[str, object]] = {}
    usage: dict[str, object] | None = None

    def response_payload(status: str, output: list[dict[str, object]]) -> dict[str, object]:
        return {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "status": status,
            "error": None,
            "incomplete_details": None,
            "instructions": None,
            "max_output_tokens": None,
            "model": model,
            "output": output,
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "store": False,
            "temperature": 1.0,
            "text": {"format": {"type": "text"}},
            "tool_choice": "auto",
            "tools": [],
            "top_p": 1.0,
            "truncation": "disabled",
            "usage": usage,
            "user": None,
            "metadata": {},
        }

    def event(event_type: str, **payload: object) -> bytes:
        nonlocal sequence_number
        body = {"type": event_type, "sequence_number": sequence_number, **payload}
        sequence_number += 1
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event_type}\ndata: {encoded}\n\n".encode()

    pending_message = {
        "id": message_id,
        "type": "message",
        "status": "in_progress",
        "role": "assistant",
        "content": [],
    }
    yield event("response.created", response=response_payload("in_progress", []))
    yield event("response.in_progress", response=response_payload("in_progress", []))
    yield event("response.output_item.added", output_index=0, item=pending_message)
    yield event(
        "response.content_part.added",
        item_id=message_id,
        output_index=0,
        content_index=0,
        part={"type": "output_text", "text": "", "annotations": [], "logprobs": []},
    )

    try:
        async for chunk in upstream:
            raw_chunk = (
                chunk.encode()
                if isinstance(chunk, str)
                else chunk.tobytes()
                if isinstance(chunk, memoryview)
                else chunk
            )
            for line in raw_chunk.decode(errors="replace").splitlines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    chat_event = json.loads(line[6:])
                except ValueError:
                    continue
                usage = _response_usage(chat_event.get("usage")) or usage
                choice = (chat_event.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_parts.append(content)
                    yield event(
                        "response.output_text.delta",
                        item_id=message_id,
                        output_index=0,
                        content_index=0,
                        delta=content,
                        logprobs=[],
                    )
                for tool_delta in delta.get("tool_calls") or []:
                    index = int(tool_delta.get("index", 0))
                    function = tool_delta.get("function") or {}
                    if index not in tool_calls:
                        item = {
                            "id": f"fc_{uuid.uuid4().hex}",
                            "type": "function_call",
                            "status": "in_progress",
                            "call_id": tool_delta.get("id") or f"call_{uuid.uuid4().hex}",
                            "name": function.get("name", ""),
                            "arguments": "",
                        }
                        tool_calls[index] = item
                        yield event(
                            "response.output_item.added",
                            output_index=index + 1,
                            item=item,
                        )
                    item = tool_calls[index]
                    if tool_delta.get("id"):
                        item["call_id"] = tool_delta["id"]
                    if function.get("name"):
                        item["name"] = function["name"]
                    arguments = function.get("arguments")
                    if isinstance(arguments, str) and arguments:
                        item["arguments"] = str(item["arguments"]) + arguments
                        yield event(
                            "response.function_call_arguments.delta",
                            response_id=response_id,
                            item_id=item["id"],
                            output_index=index + 1,
                            delta=arguments,
                        )

        text = "".join(text_parts)
        part: dict[str, object] = {
            "type": "output_text",
            "text": text,
            "annotations": [],
            "logprobs": [],
        }
        completed_message: dict[str, object] = {
            "id": message_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [part],
        }
        yield event(
            "response.output_text.done",
            item_id=message_id,
            output_index=0,
            content_index=0,
            text=text,
            logprobs=[],
        )
        yield event(
            "response.content_part.done",
            item_id=message_id,
            output_index=0,
            content_index=0,
            part=part,
        )
        yield event("response.output_item.done", output_index=0, item=completed_message)
        completed_output = [completed_message]
        for index, item in sorted(tool_calls.items()):
            item["status"] = "completed"
            yield event(
                "response.function_call_arguments.done",
                response_id=response_id,
                item_id=item["id"],
                output_index=index + 1,
                arguments=item["arguments"],
            )
            yield event("response.output_item.done", output_index=index + 1, item=item)
            completed_output.append(item)
        yield event(
            "response.completed",
            response=response_payload("completed", completed_output),
        )
    finally:
        close = getattr(upstream, "aclose", None)
        if close is not None:
            await close()
