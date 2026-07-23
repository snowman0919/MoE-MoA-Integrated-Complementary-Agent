from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import pytest
from dgx_moa.streaming import (
    MAX_BUFFERED_RESPONSE_CHARS,
    StreamObservation,
    forward_sse,
    reported_usage,
    response_usage,
    responses_sse,
)
from dgx_moa.usage import SQLITE_MAX_INTEGER


@pytest.mark.asyncio
async def test_responses_sse_translates_chat_text_and_usage() -> None:
    async def upstream():
        yield b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        yield (
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5,'
            b'"prompt_tokens_details":{"cached_tokens":1},'
            b'"completion_tokens_details":{"reasoning_tokens":1}}}\n\n'
        )
        yield b"data: [DONE]\n\n"

    chunks = [chunk async for chunk in responses_sse(upstream(), "dgx-moa-agent")]
    events = [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    deltas = [event["delta"] for event in events if event["type"] == "response.output_text.delta"]
    assert deltas == ["hel", "lo"]
    completed = events[-1]
    assert completed["type"] == "response.completed"
    assert completed["response"]["output"][0]["content"][0]["text"] == "hello"
    assert completed["response"]["usage"]["total_tokens"] == 5
    assert completed["response"]["usage"]["input_tokens_details"] == {"cached_tokens": 1}
    assert completed["response"]["usage"]["output_tokens_details"] == {"reasoning_tokens": 1}
    assert all(b"data: [DONE]" not in chunk for chunk in chunks)


@pytest.mark.parametrize("invalid", [-1, True, SQLITE_MAX_INTEGER + 1])
def test_response_usage_rejects_malformed_token_details(invalid: object) -> None:
    usage = response_usage(
        {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": invalid},
            "completion_tokens_details": {"reasoning_tokens": invalid},
        }
    )

    assert usage == {
        "input_tokens": 3,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 2,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 5,
    }


@pytest.mark.asyncio
async def test_responses_sse_defers_custom_kind_and_rejects_non_string_input() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-edit","function":{}}]}}]}\n\n'
        )
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"function":{"name":"apply_patch","arguments":"{\\"input\\":42}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    emitted = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(), "dgx-moa-agent", custom_tool_names={"apply_patch"}
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    added = next(
        event
        for event in emitted
        if event["type"] == "response.output_item.added" and event["output_index"] == 1
    )
    custom_done = next(
        event for event in emitted if event["type"] == "response.custom_tool_call_input.done"
    )

    assert added["item"]["type"] == "custom_tool_call"
    assert all("function_call_arguments" not in event["type"] for event in emitted)
    assert custom_done["input"] == '{"input":42}'


@pytest.mark.asyncio
async def test_responses_sse_hides_tool_preamble_and_terminates_failures(caplog) -> None:  # type: ignore[no-untyped-def]
    async def tool_upstream():
        yield b'data: {"choices":[{"delta":{"content":"private plan"}}]}\n\n'
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-one","function":{"name":"exec_command",'
            b'"arguments":"{\\"cmd\\":\\"pwd\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )

    tool_events = [
        json.loads(line[6:])
        async for chunk in responses_sse(tool_upstream(), "dgx-moa", session_id="tool-session")
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    assert all(event.get("delta") != "private plan" for event in tool_events)
    assert tool_events[-1]["type"] == "response.completed"

    async def failed_upstream():
        yield b'data: {"choices":[{"delta":{"content":"must stay private"}}]}\n\n'
        raise RuntimeError("sensitive upstream detail")

    with caplog.at_level(logging.WARNING):
        failed_events = [
            json.loads(line[6:])
            async for chunk in responses_sse(
                failed_upstream(), "dgx-moa", session_id="failed-session"
            )
            for line in chunk.decode().splitlines()
            if line.startswith("data: ")
        ]
    assert failed_events[-1]["type"] == "response.failed"
    assert failed_events[-1]["response"]["error"]["code"] == "backend_error"
    assert "failed-session" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "must stay private" not in caplog.text
    assert "sensitive upstream detail" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal",
    [
        b'data: {"error":{"message":"private backend detail"}}\n\n',
        b"",
    ],
)
async def test_responses_sse_rejects_error_frames_and_unterminated_eof(terminal: bytes) -> None:
    async def upstream():
        yield b'data: {"choices":[{"delta":{"content":"private plan"}}]}\n\n'
        if terminal:
            yield terminal

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(upstream(), "dgx-moa")
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    assert events[-1]["type"] == "response.failed"
    assert all(event.get("delta") != "private plan" for event in events)
    assert not any(event["type"] == "response.completed" for event in events)


@pytest.mark.asyncio
async def test_responses_sse_sanitizes_terminal_log_fields(caplog) -> None:  # type: ignore[no-untyped-def]
    async def upstream():
        raise RuntimeError("private detail")
        yield b""  # pragma: no cover

    with caplog.at_level(logging.WARNING):
        _ = [
            chunk
            async for chunk in responses_sse(
                upstream(), "model\nforged", session_id="session\rforged"
            )
        ]

    assert "session?forged" in caplog.text
    assert "model?forged" in caplog.text
    assert "session\rforged" not in caplog.text


@pytest.mark.asyncio
async def test_responses_sse_rejects_oversized_buffer_without_exposing_text() -> None:
    private_text = "x" * (MAX_BUFFERED_RESPONSE_CHARS + 1)

    async def upstream():
        yield f'data: {{"choices":[{{"delta":{{"content":"{private_text}"}}}}]}}\n\n'

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(upstream(), "dgx-moa")
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    assert events[-1]["type"] == "response.failed"
    assert not any(event["type"] == "response.output_text.delta" for event in events)


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_first_event_is_forwarded_before_upstream_completion() -> None:
    release = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"one"},"finish_reason":null}]}\n\n'
        await release.wait()
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"

    observation = StreamObservation(max_capture_bytes=1000)
    stream = forward_sse(upstream(), observation, max_event_bytes=1000)
    first = await anext(stream)
    assert b'"content":"one"' in first
    release.set()
    remaining = b"".join([chunk async for chunk in stream])
    assert remaining.count(b"data: [DONE]") == 1


@pytest.mark.asyncio
async def test_split_delimiters_and_crlf_are_framed_byte_exactly() -> None:
    first = b"data: first\r\n\r\n"
    second = b"data: second\n\n"
    upstream = chunks(first[:13], first[13:-1], first[-1:] + second[:-1], second[-1:])

    forwarded = [
        event
        async for event in forward_sse(
            upstream, StreamObservation(max_capture_bytes=1000), max_event_bytes=1000
        )
    ]

    assert forwarded == [first, second, b"data: [DONE]\n\n"]


@pytest.mark.asyncio
async def test_duplicate_done_events_are_filtered() -> None:
    content = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    done = b"data: [DONE]\n\n"
    observation = StreamObservation(max_capture_bytes=1000)

    forwarded = b"".join(
        [
            event
            async for event in forward_sse(
                chunks(content, done, done), observation, max_event_bytes=1000
            )
        ]
    )

    assert forwarded == content + done
    assert forwarded.count(b"data: [DONE]") == 1
    assert observation.done_seen


@pytest.mark.asyncio
async def test_first_done_stops_before_blocking_upstream_and_closes_it() -> None:
    read_past_done = False
    closed = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        nonlocal read_past_done
        try:
            yield b"data: [DONE]\n\n"
            read_past_done = True
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = forward_sse(
        upstream(), StreamObservation(max_capture_bytes=1000), max_event_bytes=1000
    )
    assert await anext(stream) == b"data: [DONE]\n\n"
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=1)

    assert not read_past_done
    assert closed.is_set()


@pytest.mark.asyncio
async def test_first_done_stops_before_later_upstream_error_and_closes_it() -> None:
    read_past_done = False
    closed = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        nonlocal read_past_done
        try:
            yield b"data: [DONE]\n\n"
            read_past_done = True
            raise RuntimeError("after terminal event")
        finally:
            closed.set()

    stream = forward_sse(
        upstream(), StreamObservation(max_capture_bytes=1000), max_event_bytes=1000
    )
    assert await anext(stream) == b"data: [DONE]\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)

    assert not read_past_done
    assert closed.is_set()


@pytest.mark.asyncio
async def test_missing_done_is_synthesized_on_clean_eof() -> None:
    content = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    observation = StreamObservation(max_capture_bytes=1000)

    forwarded = [
        event async for event in forward_sse(chunks(content), observation, max_event_bytes=1000)
    ]

    assert forwarded == [content, b"data: [DONE]\n\n"]
    assert observation.done_seen


@pytest.mark.asyncio
async def test_native_tool_call_delta_bytes_are_preserved_exactly() -> None:
    tool_event = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
        b'"function":{"name":"shell","arguments":"{\\"cmd\\":\\"ls\\"}"}}]},'
        b'"finish_reason":null}]}\n\n'
    )
    observation = StreamObservation(max_capture_bytes=1000)

    forwarded = [
        event
        async for event in forward_sse(
            chunks(tool_event[:31], tool_event[31:]), observation, max_event_bytes=1000
        )
    ]

    assert forwarded[0] == tool_event
    assert bytes(observation.captured).startswith(tool_event)
    assert observation.tool_delta_seen
    assert observation.tool_call_names == {0: "shell"}
    assert observation.tool_call_ids_by_index == {0: "call-1"}
    assert observation.tool_call_arguments == {0: '{"cmd":"ls"}'}


@pytest.mark.asyncio
async def test_observation_capture_is_truncated_at_bound() -> None:
    first = b"data: first\n\n"
    second = b"data: second\n\n"
    observation = StreamObservation(max_capture_bytes=17)

    _ = [
        event
        async for event in forward_sse(chunks(first, second), observation, max_event_bytes=1000)
    ]

    assert bytes(observation.captured) == (first + second)[:17]


@pytest.mark.asyncio
async def test_observation_extracts_only_reported_token_counts() -> None:
    event = (
        b'data: {"choices":[{"delta":{"content":"SENTINEL_RESPONSE"}}],'
        b'"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5,'
        b'"secret":"SENTINEL_SECRET"}}\n\n'
    )
    observation = StreamObservation(max_capture_bytes=1_000)

    _ = [chunk async for chunk in forward_sse(chunks(event), observation, max_event_bytes=1_000)]

    assert observation.usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }


@pytest.mark.parametrize("value", [True, -1, 2**63, "5", 1.0])
def test_reported_usage_omits_non_sqlite_integer_values(value: object) -> None:
    assert reported_usage({"total_tokens": value}) == {}


@pytest.mark.asyncio
async def test_oversized_event_is_rejected() -> None:
    event = b"data: " + (b"x" * 20) + b"\n\n"

    with pytest.raises(ValueError, match="SSE event exceeds 16 bytes"):
        _ = [
            chunk
            async for chunk in forward_sse(
                chunks(event), StreamObservation(max_capture_bytes=1000), max_event_bytes=16
            )
        ]


@pytest.mark.asyncio
async def test_early_close_closes_upstream() -> None:
    closed = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        try:
            yield b"data: first\n\n"
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = forward_sse(
        upstream(), StreamObservation(max_capture_bytes=1000), max_event_bytes=1000
    )
    assert await anext(stream) == b"data: first\n\n"
    await stream.aclose()

    await asyncio.wait_for(closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_cancellation_closes_upstream() -> None:
    entered = asyncio.Event()
    closed = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        try:
            entered.set()
            await asyncio.Event().wait()
            yield b"data: never\n\n"
        finally:
            closed.set()

    stream = forward_sse(
        upstream(), StreamObservation(max_capture_bytes=1000), max_event_bytes=1000
    )
    pending = asyncio.create_task(anext(stream))
    await entered.wait()
    pending.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.wait_for(closed.wait(), timeout=1)
