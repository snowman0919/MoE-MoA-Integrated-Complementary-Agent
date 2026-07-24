from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import pytest
from dgx_moa.streaming import (
    MAX_BUFFERED_RESPONSE_CHARS,
    ProgressOnlyResponse,
    StreamObservation,
    forward_sse,
    is_progress_only,
    keepalive_sse,
    reported_usage,
    response_usage,
    responses_sse,
    tool_progress_text,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "다음 도구 작업을 준비합니다.",
        "exec_command 도구를 실행합니다.",
        "Planner 역할이 구조와 구현 순서를 설계합니다.",
        "테스트 코드를 확인합니다.",
        "동시성 테스트를 실행하겠습니다.",
        "구현을 위한 설계를 마친 후, `rate_limiter.py`를 작성합니다.",
        "이제 테스트 파일을 검토하여 구현 요구사항을 정확히 이해합니다.",
        "테스트 코드를 확인하여 구현 사양을 완전히 파악합니다.",
        "테스트 파일을 확인하고 구현을 시작합니다.",
        "Inspecting the tests.",
    ],
)
async def test_responses_sse_rejects_progress_only_stop(text: str) -> None:
    async def upstream():
        yield f'data: {{"choices":[{{"delta":{{"content":"{text}"}}}}]}}\n\n'.encode()
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"

    with pytest.raises(ProgressOnlyResponse):
        _ = [chunk async for chunk in responses_sse(upstream(), "dgx-moa")]


@pytest.mark.parametrize(
    "text",
    [
        "구현을 완료했고 테스트 6개가 통과했습니다.",
        "Inspection complete: 6 tests passed.",
        "수정 파일: rate_limiter.py\n테스트: 4개 통과",
    ],
)
def test_progress_only_detection_preserves_concrete_results(text: str) -> None:
    assert not is_progress_only(text)


@pytest.mark.asyncio
async def test_responses_sse_requires_tool_when_goal_has_no_implementation_evidence() -> None:
    async def upstream():
        yield (
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": (
                                    "필수 문서를 읽었습니다. 이제 현재 구조를 파악하고 "
                                    "설계를 시작합니다."
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode()
        yield b"data: [DONE]\n\n"

    with pytest.raises(ProgressOnlyResponse):
        _ = [
            chunk
            async for chunk in responses_sse(
                upstream(),
                "dgx-moa",
                require_tool_action=True,
            )
        ]


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
async def test_responses_sse_translates_edit_alias_to_apply_patch() -> None:
    arguments = json.dumps(
        {
            "file": "/workspace/rate_limiter.py",
            "old_text": "if isinstance(value, int):\n    return value",
            "new_text": "if isinstance(value, int) and not isinstance(value, bool):\n    return value",
        }
    )

    async def upstream():
        yield (
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-edit",
                                        "function": {
                                            "name": "edit",
                                            "arguments": arguments,
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )
            + "\n\n"
        ).encode()
        yield b"data: [DONE]\n\n"

    emitted = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(), "dgx-moa-agent", custom_tool_names={"apply_patch"}
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    done = next(
        event
        for event in emitted
        if event["type"] == "response.output_item.done" and event["output_index"] == 1
    )

    assert done["item"]["type"] == "custom_tool_call"
    assert done["item"]["name"] == "apply_patch"
    assert "*** Update File: /workspace/rate_limiter.py" in done["item"]["input"]
    assert "-if isinstance(value, int):" in done["item"]["input"]
    assert "+if isinstance(value, int) and not isinstance(value, bool):" in done["item"]["input"]


@pytest.mark.asyncio
async def test_responses_sse_replaces_malformed_edit_alias_with_feedback() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-edit","function":{"name":"edit",'
            b'"arguments":"{\\"file\\":\\"/workspace/example.py\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    emitted = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa-agent",
            custom_tool_names={"apply_patch"},
            function_tool_names={"exec_command"},
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    done = next(
        event
        for event in emitted
        if event["type"] == "response.output_item.done" and event["output_index"] == 1
    )

    assert done["item"]["name"] == "exec_command"
    assert "Unsupported edit arguments" in done["item"]["arguments"]


@pytest.mark.asyncio
async def test_responses_sse_preserves_tool_progress_and_terminates_failures(caplog) -> None:  # type: ignore[no-untyped-def]
    async def tool_upstream():
        yield 'data: {"choices":[{"delta":{"content":"목표 파일을 확인합니다."}}]}\n\n'.encode()
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-one","function":{"name":"exec_command",'
            b'"arguments":"{\\"cmd\\":\\"pwd\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )

    tool_events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            tool_upstream(),
            "dgx-moa",
            session_id="tool-session",
            progress_language="ko",
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event.get("delta") == "다음 작업에 필요한 증거를 확인합니다." for event in tool_events
    )
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
async def test_responses_sse_batches_named_goal_prerequisites() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-read","function":{"name":"read_file",'
            b'"arguments":"{\\"path\\":\\"/work/AGENTS.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command"},
            goal_already_loaded=True,
            goal_prerequisites=(
                "AGENTS.md",
                "docs/STATE.md",
                "docs/OPERATIONS.md",
                "docs/VALIDATION.md",
                "docs/TRACE_SCHEMA.md",
            ),
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    arguments = next(
        event["arguments"]
        for event in events
        if event["type"] == "response.function_call_arguments.done"
    )
    command = json.loads(arguments)["cmd"]
    assert command.startswith("head -n 400 -- ")
    assert "/work/AGENTS.md" in command
    assert "/work/docs/STATE.md" in command
    assert "/work/docs/OPERATIONS.md" in command
    assert "/work/docs/VALIDATION.md" in command
    assert "/work/docs/TRACE_SCHEMA.md" in command


@pytest.mark.asyncio
async def test_responses_sse_maps_unsupported_read_file_to_exec_command() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-read","function":{"name":"read_file",'
            b'"arguments":"{\\"path\\":\\"/tmp/goal objective.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command"},
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    added = next(
        event
        for event in events
        if event["type"] == "response.output_item.added" and event["output_index"] == 1
    )
    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )

    assert added["item"]["name"] == "exec_command"
    assert json.loads(done["arguments"]) == {"cmd": "cat -- '/tmp/goal objective.md'"}
    assert all(event.get("item", {}).get("name") != "read_file" for event in events)


@pytest.mark.asyncio
async def test_responses_sse_maps_local_mcp_file_to_exec_command() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-mcp","function":{"name":"read_mcp_resource",'
            b'"arguments":"{\\"server\\":\\"codex-apps\\",'
            b'\\"uri\\":\\"file:///Users/test/goal%20objective.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command", "read_mcp_resource"},
            progress_language="ko",
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    added = next(
        event
        for event in events
        if event["type"] == "response.output_item.added" and event["output_index"] == 1
    )
    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )

    assert added["item"]["name"] == "exec_command"
    progress_index = next(
        index
        for index, event in enumerate(events)
        if event.get("delta") == "다음 작업에 필요한 증거를 확인합니다."
    )
    assert progress_index < events.index(added)
    assert json.loads(done["arguments"]) == {"cmd": "cat -- '/Users/test/goal objective.md'"}
    assert all(event.get("item", {}).get("name") != "read_mcp_resource" for event in events)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"cmd": "pwd", "justification": "작업 공간을 확인합니다."}, "작업 공간을 확인합니다."),
        (
            {"cmd": "cat AGENTS.md docs/STATE.md docs/OPERATIONS.md"},
            "저장소 지침과 필수 운영 문서를 확인합니다.",
        ),
    ],
)
def test_tool_progress_text_describes_immediate_purpose(
    arguments: dict[str, str], expected: str
) -> None:
    calls = {0: {"_arguments": json.dumps(arguments, ensure_ascii=False)}}
    assert tool_progress_text(calls, "ko") == expected


@pytest.mark.asyncio
async def test_responses_sse_replaces_model_commentary_with_document_purpose() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"content":"I will read the required docs first."}}]}\n\n'
        )
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-docs","function":{"name":"exec_command",'
            b'"arguments":"{\\"cmd\\":\\"cat AGENTS.md docs/STATE.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(upstream(), "dgx-moa", progress_language="ko")
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    deltas = [event.get("delta") for event in events if "delta" in event]
    assert "I will read the required docs first." not in deltas
    assert "저장소 지침과 필수 운영 문서를 확인합니다." in deltas


@pytest.mark.asyncio
async def test_responses_sse_maps_absolute_mcp_path_to_exec_command() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-mcp","function":{"name":"read_mcp_resource",'
            b'"arguments":"{\\"server\\":\\"codex_apps\\",'
            b'\\"uri\\":\\"/Users/test/work/docs/STATE.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command", "read_mcp_resource"},
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )

    assert json.loads(done["arguments"]) == {"cmd": "cat -- /Users/test/work/docs/STATE.md"}


@pytest.mark.asyncio
async def test_responses_sse_keeps_exec_command_inside_current_sandbox() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-shell","function":{"name":"exec_command",'
            b'"arguments":"{\\"cmd\\":\\"apt-get update\\",'
            b'\\"sandbox_permissions\\":\\"require_escalated\\",'
            b'\\"justification\\":\\"install dependency\\",'
            b'\\"prefix_rule\\":[\\"apt-get\\"]}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command"},
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )

    assert json.loads(done["arguments"]) == {"cmd": "apt-get update"}


@pytest.mark.asyncio
async def test_responses_sse_replaces_invented_write_stdin_session_id() -> None:
    async def upstream():  # type: ignore[no-untyped-def]
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-write","function":{"name":"write_stdin",'
            b'"arguments":"{\\"session_id\\":1,\\"chars\\":\\"line 1\\\\nline 2\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa-agent",
            function_tool_names={"exec_command", "write_stdin"},
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]

    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )
    output = next(
        event
        for event in events
        if event["type"] == "response.output_item.done" and event["output_index"] == 1
    )
    assert output["item"]["name"] == "exec_command"
    assert json.loads(done["arguments"]) == {
        "cmd": "printf '%s\\n' 'No active process session; use exec_command or apply_patch.'"
    }


@pytest.mark.asyncio
async def test_responses_sse_suppresses_loaded_goal_reread() -> None:
    async def upstream():
        yield (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"id":"call-shell","function":{"name":"exec_command",'
            b'"arguments":"{\\"cmd\\":\\"cat /workspace/goal-objective.md\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n\n'
        )
        yield b"data: [DONE]\n\n"

    events = [
        json.loads(line[6:])
        async for chunk in responses_sse(
            upstream(),
            "dgx-moa",
            function_tool_names={"exec_command"},
            goal_already_loaded=True,
        )
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]
    done = next(
        event for event in events if event["type"] == "response.function_call_arguments.done"
    )

    assert json.loads(done["arguments"]) == {
        "cmd": "printf '%s\\n' 'Goal objective already loaded; continue implementation.'"
    }


@pytest.mark.asyncio
async def test_keepalive_sse_covers_silent_upstream() -> None:
    release = asyncio.Event()

    async def upstream():
        await release.wait()
        yield b"event: done\ndata: done\n\n"

    stream = keepalive_sse(upstream(), interval_seconds=0.01)
    assert await anext(stream) == b": keep-alive\n\n"
    release.set()
    assert await anext(stream) == b"event: done\ndata: done\n\n"
    await stream.aclose()


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
