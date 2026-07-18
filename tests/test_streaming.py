from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from dgx_moa.streaming import StreamObservation, forward_sse


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
