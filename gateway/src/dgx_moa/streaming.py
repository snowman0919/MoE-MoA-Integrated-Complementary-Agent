from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

from .controller import fingerprint, is_workspace_objective
from .usage import SQLITE_MAX_INTEGER

LOGGER = logging.getLogger(__name__)
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")
MAX_BUFFERED_RESPONSE_CHARS = 1_000_000
PROGRESS_ONLY_TEXT = {
    "Preparing the next tool action.",
    "다음 도구 작업을 준비합니다.",
    "다음 작업에 필요한 증거를 확인합니다.",
    "Planner 역할이 구조와 구현 순서를 설계합니다.",
}
KOREAN_PROGRESS_ENDINGS = tuple(
    f"{verb}{suffix}"
    for verb in (
        "확인",
        "점검",
        "검토",
        "분석",
        "파악",
        "이해",
        "준비",
        "설계",
        "실행",
        "수정",
        "구현",
        "작성",
        "생성",
        "추가",
        "적용",
        "진행",
        "시작",
    )
    for suffix in ("합니다.", "하겠습니다.")
)
KOREAN_PROGRESS_PREFIXES = ("이제 ", "다음 ", "먼저 ", "이후 ", "계속 ", "곧 ")
ENGLISH_PROGRESS_PREFIXES = (
    "checking ",
    "inspecting ",
    "reviewing ",
    "analyzing ",
    "preparing ",
    "planning ",
    "running ",
    "reading ",
)


class ProgressOnlyResponse(Exception):
    """The model stopped after emitting only a progress marker."""

    def __init__(self, reason: str = "progress_only") -> None:
        super().__init__(reason)
        self.reason = reason


def compatible_edit_call(
    name: str, raw_arguments: str, custom_tool_names: set[str] | None
) -> tuple[str, str]:
    if "apply_patch" not in (custom_tool_names or set()):
        return name, raw_arguments
    try:
        arguments = json.loads(raw_arguments)
        if name == "write_stdin" and "chars" not in arguments:
            path = arguments.get("path", arguments.get("file", arguments.get("file_path")))
            content = arguments.get("content")
            if (
                not isinstance(path, str)
                or not path
                or "\n" in path
                or not isinstance(content, str)
            ):
                raise TypeError
            patch = "\n".join(
                (
                    "*** Begin Patch",
                    f"*** Delete File: {path}",
                    f"*** Add File: {path}",
                    *(f"+{line}" for line in content.splitlines()),
                    "*** End Patch",
                )
            )
            return "apply_patch", json.dumps(
                {"input": patch}, ensure_ascii=False, separators=(",", ":")
            )
        if name not in {"edit", "edit_file"}:
            return name, raw_arguments
        path = arguments.get("file", arguments.get("path", arguments.get("file_path")))
        old_text = arguments.get("old_text", arguments.get("old_string", arguments.get("old")))
        new_text = arguments.get("new_text", arguments.get("new_string", arguments.get("new")))
        if (
            not isinstance(path, str)
            or not path
            or "\n" in path
            or not isinstance(old_text, str)
            or not old_text
            or not isinstance(new_text, str)
        ):
            raise TypeError
    except (TypeError, ValueError):
        return name, raw_arguments
    patch = "\n".join(
        (
            "*** Begin Patch",
            f"*** Update File: {path}",
            "@@",
            *(f"-{line}" for line in old_text.splitlines()),
            *(f"+{line}" for line in new_text.splitlines()),
            "*** End Patch",
        )
    )
    return "apply_patch", json.dumps({"input": patch}, ensure_ascii=False, separators=(",", ":"))


def is_progress_only(text: str) -> bool:
    stripped = text.strip()
    return stripped in PROGRESS_ONLY_TEXT or (
        "\n" not in stripped
        and len(stripped) <= 256
        and (
            stripped.endswith(" 도구를 실행합니다.")
            or stripped.endswith(KOREAN_PROGRESS_ENDINGS)
            or (
                stripped.startswith(KOREAN_PROGRESS_PREFIXES)
                and stripped.endswith(("합니다.", "하겠습니다."))
            )
            or (
                stripped.lower().startswith(ENGLISH_PROGRESS_PREFIXES)
                and stripped.endswith((".", "…"))
            )
        )
    )


def is_context_starved_response(
    text: str,
    usage: dict[str, object] | None,
    context_length: int | None,
    objective: str,
) -> bool:
    if not usage or not context_length:
        return False
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    stripped = text.strip()
    return (
        isinstance(input_tokens, int)
        and not isinstance(input_tokens, bool)
        and isinstance(output_tokens, int)
        and not isinstance(output_tokens, bool)
        and input_tokens * 100 >= context_length * 85
        and output_tokens <= 4
        and len(stripped) <= 64
        and (not stripped or stripped.casefold() not in objective.casefold())
    )


def has_korean_script_leak(text: str, progress_language: str, objective: str) -> bool:
    if progress_language != "ko":
        return False
    prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    prose = re.sub(r"`[^`\n]*`", "", prose)
    foreign_pattern = (
        r"[\u0370-\u052f\u0530-\u058f\u0590-\u08ff\u0900-\u097f"
        r"\u0e00-\u0e7f\u10a0-\u10ff\u3040-\u30ff]"
    )
    allowed_foreign = set(re.findall(foreign_pattern, objective))
    if any(character not in allowed_foreign for character in re.findall(foreign_pattern, prose)):
        return True
    allowed_han = set(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", objective))
    if any(
        character not in allowed_han
        for character in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", prose)
    ):
        return True
    return any(
        not re.search(r"[가-힣]", line)
        and not line.lstrip().startswith(("|", "http://", "https://"))
        and len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", line)) >= 8
        for line in prose.splitlines()
    )


def has_internal_protocol_leak(text: str) -> bool:
    prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return bool(
        re.search(r"</?(?:function|tool|assistant|response)[_:-]", prose, re.IGNORECASE)
        or re.search(r"<\|(?:tool|assistant|function)[^|>]*\|>", prose, re.IGNORECASE)
        or re.search(
            r"\b(?:INNER_THINKING|AgentFinish|RETURN_VALIDATED_OUTPUT|"
            r"REQUIREMENT_ACCEPTED_POSTPROCESSING|INVALID_ROLE_MESSAGE|schema-halt)\b",
            prose,
            re.IGNORECASE,
        )
    )


def is_read_only_evaluation(objective: str) -> bool:
    normalized = objective.lower()
    evaluation = any(
        marker in normalized for marker in ("evaluate", "audit", "review", "평가", "감사", "검토")
    ) and any(
        marker in normalized
        for marker in (
            "codebase",
            "repository",
            "project",
            "platform",
            "코드베이스",
            "저장소",
            "프로젝트",
            "플랫폼",
        )
    )
    requested_change = bool(
        re.search(r"\b(?:implement|modify|fix|create|write|add|refactor)\b", normalized)
        or re.search(
            r"(?:구현|수정|변경|고쳐|생성|만들)(?:해|하|하여|하고|해서|하세요|해줘|해라)",
            normalized,
        )
    )
    return evaluation and not requested_change


def normalize_workspace_inventory_call(
    tool_calls: dict[int, dict[str, object]], objective: str
) -> None:
    if not is_workspace_objective(objective) or len(tool_calls) != 1:
        return
    call = next(iter(tool_calls.values()))
    if call.get("name") != "exec_command":
        return
    try:
        arguments = json.loads(str(call.get("_arguments") or "{}"))
        words = shlex.split(str(arguments.get("cmd") or ""))
    except (TypeError, ValueError):
        return
    if not words or words[0].rsplit("/", 1)[-1] != "ls":
        return
    targets = [word for word in words[1:] if not word.startswith("-")]
    if len(targets) > 1:
        return
    workspace = targets[0] if targets else str(arguments.get("workdir") or ".")
    arguments["cmd"] = f"git -C {shlex.quote(workspace)} ls-files"
    call["_arguments"] = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))


def tool_call_fingerprint(call: dict[str, object]) -> str:
    return fingerprint(
        {
            "function": {
                "name": str(call.get("name") or ""),
                "arguments": str(call.get("_arguments") or ""),
            }
        }
    )


def has_read_only_evaluation_mutation(
    tool_calls: dict[int, dict[str, object]], objective: str
) -> bool:
    if not is_read_only_evaluation(objective):
        return False
    for call in tool_calls.values():
        if str(call.get("name")) in {"apply_patch", "write_stdin", "edit", "edit_file"}:
            return True
        try:
            arguments = json.loads(str(call.get("_arguments") or "{}"))
        except ValueError:
            continue
        command = str(arguments.get("cmd") or arguments.get("command") or "")
        if re.search(
            r"(?:^|&&|\|\||;|\n)\s*(?:rm\b|mv\b|cp\b|touch\b|mkdir\b|"
            r"(?:brew|pip|pip3|cargo)\s+install\b|git\s+(?:stash|reset|clean|checkout|"
            r"switch|add|commit)\b|\./\S+\s+(?:new|install|setup)\b)",
            command,
        ) or re.search(r"(?:^|\s)(?:\d*)>(?![>&])\s*(?!/dev/null(?:\s|$))", command):
            return True
    return False


def has_non_evidence_evaluation_tool(
    tool_calls: dict[int, dict[str, object]], objective: str
) -> bool:
    if not is_read_only_evaluation(objective):
        return False
    for call in tool_calls.values():
        if call.get("name") != "exec_command":
            continue
        try:
            arguments = json.loads(str(call.get("_arguments") or "{}"))
        except ValueError:
            continue
        command = str(arguments.get("cmd") or arguments.get("command") or "")
        output_only = re.search(r"(?:^|&&|;|\n|['\"])\s*(?:echo|printf)\b", command)
        inspection = re.search(
            r"(?:^|&&|;|\n|['\"])\s*(?:cat|sed|head|tail|rg|grep|find|ls|file|git)\b",
            command,
        )
        if output_only and not inspection:
            return True
    return False


def _log_token(value: str) -> str:
    return "".join(character if character.isprintable() else "?" for character in value)[:256]


def tool_progress_text(tool_calls: dict[int, dict[str, object]], progress_language: str) -> str:
    if len(tool_calls) > 1:
        names = sorted({str(item.get("name") or "tool") for item in tool_calls.values()})
        return (
            f"독립적인 도구 호출 {len(tool_calls)}개({', '.join(names)})를 함께 실행해 "
            "이번 단계의 근거를 모읍니다."
            if progress_language == "ko"
            else f"Running {len(tool_calls)} independent {', '.join(names)} calls together "
            "to collect this phase's evidence."
        )
    first_tool = tool_calls[min(tool_calls)]
    try:
        arguments = json.loads(str(first_tool["_arguments"]))
    except (KeyError, TypeError, ValueError):
        arguments = {}
    command = arguments.get("cmd") if isinstance(arguments, dict) else None
    if isinstance(command, str):
        if "goal-objective" in command:
            return (
                "목표 문서를 확인합니다."
                if progress_language == "ko"
                else "Reading the goal objective."
            )
        if "AGENTS.md" in command or "docs/STATE.md" in command:
            return (
                "저장소 지침과 필수 운영 문서를 확인합니다."
                if progress_language == "ko"
                else "Reading the repository instructions and required operational documents."
            )
        if command.lstrip().startswith("cd ") and "&&" in command:
            try:
                workspace = shlex.split(command.split("&&", 1)[0])[1]
            except (IndexError, ValueError):
                workspace = "the target workspace"
            return (
                f"{workspace}의 주요 소스와 설정을 한 배치로 읽어 구현 범위와 결함을 판정합니다."
                if progress_language == "ko"
                else f"Reading {workspace}'s main sources and configuration as one batch to "
                "assess scope and defects."
            )
        try:
            words = shlex.split(command)
        except ValueError:
            words = command.split()
        action = words[0].rsplit("/", 1)[-1] if words else "command"
        positional = [word for word in words[1:] if not word.startswith("-") and word not in {"|"}]
        target = (
            positional[0]
            if action in {"ls", "find"} and positional
            else positional[-1]
            if positional
            else "."
        )
        if action in {"ls", "find", "rg"}:
            target = (
                "현재 작업 디렉터리"
                if progress_language == "ko" and target in {".", "./"}
                else "the current workspace"
                if target in {".", "./"}
                else target
            )
            return (
                f"{target}의 파일 구조를 확인해 실제 평가 대상을 정합니다."
                if progress_language == "ko"
                else f"Inspecting {target}'s file structure to identify the actual "
                "evaluation scope."
            )
        if action == "git" and "ls-files" in words:
            return (
                "추적 파일 전체 목록으로 구현·테스트·빌드 구성의 평가 범위를 확정합니다."
                if progress_language == "ko"
                else "Using the complete tracked-file inventory to identify implementation, "
                "tests, and build configuration."
            )
        if action in {"cat", "sed", "head", "tail"}:
            return (
                f"{target}의 실제 내용을 읽어 문서의 주장과 구현 증거를 대조합니다."
                if progress_language == "ko"
                else f"Reading {target} to compare documented claims with implementation evidence."
            )
    justification = arguments.get("justification") if isinstance(arguments, dict) else None
    if (
        isinstance(justification, str)
        and 1 <= len(justification.strip()) <= 200
        and "\n" not in justification
        and (progress_language != "ko" or re.search("[가-힣]", justification))
    ):
        return justification.strip()
    name = str(first_tool.get("name") or "tool")
    return (
        f"{name} 실행 결과를 이번 단계의 판정 근거로 사용합니다."
        if progress_language == "ko"
        else f"Using the {name} result as evidence for this phase's decision."
    )


def substantive_tool_progress(
    tool_calls: dict[int, dict[str, object]], progress_language: str
) -> str:
    if len(tool_calls) > 1:
        return tool_progress_text(tool_calls, progress_language)
    call = next(iter(tool_calls.values()))
    try:
        arguments = json.loads(str(call.get("_arguments") or "{}"))
    except ValueError:
        return ""
    command = arguments.get("cmd") if isinstance(arguments, dict) else None
    if not isinstance(command, str):
        return ""
    if any(marker in command for marker in ("goal-objective", "AGENTS.md", "docs/STATE.md")):
        return tool_progress_text(tool_calls, progress_language)
    if "git" in command and "ls-files" in command:
        return tool_progress_text(tool_calls, progress_language)
    if "\n" in command or "&&" in command or ";" in command:
        return tool_progress_text(tool_calls, progress_language)
    return ""


def batch_goal_prerequisite_read(
    tool_calls: dict[int, dict[str, object]],
    prerequisites: tuple[str, ...],
) -> bool:
    """Combine a first prerequisite read without creating extra tool calls."""
    if len(prerequisites) < 2 or len(tool_calls) != 1:
        return False
    item = next(iter(tool_calls.values()))
    try:
        arguments = json.loads(str(item.get("_arguments", "")))
    except ValueError:
        return False
    command = arguments.get("cmd") if isinstance(arguments, dict) else None
    path = arguments.get("path") if isinstance(arguments, dict) else None
    if item.get("name") == "exec_command":
        if not isinstance(command, str) or not re.search(r"(?:^|\s)(?:cat|head|sed)\s", command):
            return False
        source = command
    elif item.get("_compat_local_file") and isinstance(path, str):
        source = path
    else:
        return False
    matched = next((candidate for candidate in prerequisites if candidate in source), None)
    if matched is None:
        return False
    absolute = re.search(rf"(?P<path>/[^\s\"';]*{re.escape(matched)})", source)
    root = absolute.group("path")[: -len(matched)] if absolute else ""
    arguments = {
        "cmd": "head -n 400 -- "
        + " ".join(shlex.quote(f"{root}{candidate}") for candidate in prerequisites)
    }
    item["name"] = "exec_command"
    item["_compat_local_file"] = False
    item["_arguments"] = json.dumps(
        arguments,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return True


def reported_usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: token_count
        for key in TOKEN_FIELDS
        if type(token_count := value.get(key)) is int and 0 <= token_count <= SQLITE_MAX_INTEGER
    }


def _token_detail(value: object, group: str, key: str, *, missing: int | None = 0) -> int | None:
    if not isinstance(value, dict) or not isinstance(details := value.get(group), dict):
        return missing
    token_count = details.get(key)
    return (
        token_count
        if type(token_count) is int and 0 <= token_count <= SQLITE_MAX_INTEGER
        else missing
    )


@dataclass
class StreamObservation:
    max_capture_bytes: int
    captured: bytearray = field(default_factory=bytearray)
    assistant_content: list[str] = field(default_factory=list)
    finish_reasons: list[str] = field(default_factory=list)
    tool_delta_seen: bool = False
    tool_call_ids: list[str] = field(default_factory=list)
    tool_call_ids_by_index: dict[int, str] = field(default_factory=dict)
    tool_call_names: dict[int, str] = field(default_factory=dict)
    tool_call_arguments: dict[int, str] = field(default_factory=dict)
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
                if isinstance(call, dict):
                    index = int(call.get("index", 0))
                    function = call.get("function") or {}
                    name = function.get("name") if isinstance(function, dict) else None
                    if isinstance(name, str):
                        self.tool_call_names[index] = self.tool_call_names.get(index, "") + name
                    arguments = function.get("arguments") if isinstance(function, dict) else None
                    if isinstance(arguments, str):
                        self.tool_call_arguments[index] = (
                            self.tool_call_arguments.get(index, "") + arguments
                        )
                if (
                    isinstance(call, dict)
                    and isinstance(call_id := call.get("id"), str)
                    and call_id
                    and call_id not in self.tool_call_ids
                ):
                    self.tool_call_ids.append(call_id)
                    self.tool_call_ids_by_index[index] = call_id
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
            if not observation.finish_reasons:
                raise ValueError("upstream SSE ended before terminal marker")
            observation.done_seen = True
            yield b"data: [DONE]\n\n"
    finally:
        close = getattr(upstream, "aclose", None)
        if close is not None:
            await close()


async def keepalive_sse(
    upstream: AsyncIterator[bytes],
    *,
    interval_seconds: float = 15,
    heartbeat: bytes = b": keep-alive\n\n",
) -> AsyncGenerator[bytes, None]:
    """Keep an SSE connection active while its next real event is pending."""
    if interval_seconds <= 0:
        raise ValueError("keepalive interval must be positive")
    iterator = upstream.__aiter__()
    pending: asyncio.Future[bytes] | None = None
    try:
        while True:
            pending = pending or asyncio.ensure_future(anext(iterator))
            if not (await asyncio.wait((pending,), timeout=interval_seconds))[0]:
                yield heartbeat
                continue
            try:
                yield pending.result()
            except StopAsyncIteration:
                return
            pending = None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


def response_usage(value: object) -> dict[str, object] | None:
    usage = reported_usage(value)
    if not usage:
        return None
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cached_tokens = _token_detail(value, "prompt_tokens_details", "cached_tokens", missing=None)
    converted: dict[str, object] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "output_tokens_details": {
            "reasoning_tokens": _token_detail(
                value, "completion_tokens_details", "reasoning_tokens"
            )
        },
        "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
    }
    if cached_tokens is not None:
        converted["input_tokens_details"] = {"cached_tokens": cached_tokens}
    return converted


async def completed_chat_sse(payload: dict[str, Any]) -> AsyncIterator[bytes]:
    """Expose one completed Chat Completions payload through the SSE translator."""
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = [
        {**tool_call, "index": index}
        for index, tool_call in enumerate(message.get("tool_calls") or [])
    ]
    event = {
        "choices": [
            {
                "delta": {"content": message.get("content"), "tool_calls": tool_calls},
                "finish_reason": choice.get("finish_reason"),
            }
        ],
        "usage": payload.get("usage"),
    }
    yield f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()
    yield b"data: [DONE]\n\n"


async def responses_sse(
    upstream: AsyncIterable[str | bytes | memoryview[int]],
    model: str,
    *,
    custom_tool_names: set[str] | None = None,
    function_tool_names: set[str] | None = None,
    session_id: str = "unknown",
    progress_language: str = "en",
    goal_already_loaded: bool = False,
    goal_prerequisites: tuple[str, ...] = (),
    require_tool_action: bool = False,
    context_length: int | None = None,
    objective: str = "",
    successful_tool_fingerprints: frozenset[str] = frozenset(),
    workspace_inventory_complete: bool = False,
) -> AsyncGenerator[bytes, None]:
    """Translate Chat Completions SSE into Responses text and function-call events."""
    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"
    created_at = int(time.time())
    sequence_number = 0
    text_parts: list[str] = []
    buffered_text_chars = 0
    tool_calls: dict[int, dict[str, object]] = {}
    usage: dict[str, object] | None = None
    terminal_error: dict[str, str] | None = None
    terminal_seen = False
    finish_reasons: list[str] = []

    def response_payload(status: str, output: list[dict[str, object]]) -> dict[str, object]:
        return {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "status": status,
            "error": terminal_error,
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
                if not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    terminal_seen = True
                    continue
                try:
                    chat_event = json.loads(line[6:])
                except ValueError:
                    continue
                if chat_event.get("error"):
                    raise ValueError("upstream stream reported an error")
                usage = response_usage(chat_event.get("usage")) or usage
                choice = (chat_event.get("choices") or [{}])[0]
                if choice.get("finish_reason"):
                    terminal_seen = True
                    finish_reasons.append(str(choice["finish_reason"]))
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_parts.append(content)
                    buffered_text_chars += len(content)
                    if buffered_text_chars > MAX_BUFFERED_RESPONSE_CHARS:
                        raise ValueError("upstream response exceeds buffer limit")
                for tool_delta in delta.get("tool_calls") or []:
                    index = int(tool_delta.get("index", 0))
                    function = tool_delta.get("function") or {}
                    if index not in tool_calls:
                        tool_calls[index] = {
                            "id": "",
                            "call_id": "",
                            "name": "",
                            "_arguments": "",
                            "_arguments_emitted": 0,
                            "_added": False,
                            "_kind": "",
                            "_compat_local_file": False,
                            "_original_name": "",
                        }
                    item = tool_calls[index]
                    if tool_delta.get("id"):
                        item["call_id"] = tool_delta["id"]
                    if function.get("name"):
                        name = str(function["name"])
                        compat_local_file = (
                            name in {"read_file", "read_mcp_resource"}
                            and "exec_command" in (function_tool_names or set())
                            and (
                                name == "read_mcp_resource"
                                or "read_file" not in (function_tool_names or set())
                            )
                        )
                        item["name"] = name
                        item["_original_name"] = name
                        item["_compat_local_file"] = compat_local_file
                    arguments = function.get("arguments")
                    if isinstance(arguments, str) and arguments:
                        item["_arguments"] = str(item["_arguments"]) + arguments
        if not terminal_seen:
            raise ValueError("upstream stream ended before terminal marker")
        normalize_workspace_inventory_call(tool_calls, objective)
        if tool_calls and any(
            tool_call_fingerprint(call) in successful_tool_fingerprints
            for call in tool_calls.values()
        ):
            raise ProgressOnlyResponse("duplicate_tool_call")
        if workspace_inventory_complete and any(
            call.get("name") == "exec_command"
            and (
                "ls-files" in str(call.get("_arguments") or "")
                or "rg --files" in str(call.get("_arguments") or "")
            )
            for call in tool_calls.values()
        ):
            raise ProgressOnlyResponse("duplicate_tool_call")
        if batch_goal_prerequisite_read(tool_calls, goal_prerequisites):
            LOGGER.info(
                "responses_goal_prerequisites_batched session_id=%s count=%d",
                _log_token(session_id),
                len(goal_prerequisites),
            )
        text = "".join(text_parts)
        if "length" in finish_reasons:
            raise ProgressOnlyResponse("truncated_response")
        if tool_calls and has_read_only_evaluation_mutation(tool_calls, objective):
            raise ProgressOnlyResponse("unsafe_tool_call")
        if tool_calls and has_non_evidence_evaluation_tool(tool_calls, objective):
            raise ProgressOnlyResponse("invalid_output")
        if not tool_calls and has_internal_protocol_leak(text):
            raise ProgressOnlyResponse("invalid_output")
        if not tool_calls and has_korean_script_leak(text, progress_language, objective):
            raise ProgressOnlyResponse("language_mismatch")
        if not tool_calls and (
            require_tool_action
            or is_progress_only(text)
            or is_context_starved_response(text, usage, context_length, objective)
        ):
            raise ProgressOnlyResponse
        if tool_calls:
            if (
                not text.strip()
                or is_progress_only(text)
                or has_korean_script_leak(text, progress_language, objective)
                or has_internal_protocol_leak(text)
                or (progress_language == "ko" and not re.search("[가-힣]", text))
            ):
                text = substantive_tool_progress(tool_calls, progress_language)
            text_parts = [text]
        for content in text_parts:
            yield event(
                "response.output_text.delta",
                item_id=message_id,
                output_index=0,
                content_index=0,
                delta=content,
                logprobs=[],
            )
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
            original_name = str(item["name"])
            item["name"], item["_arguments"] = compatible_edit_call(
                original_name,
                str(item["_arguments"]),
                custom_tool_names,
            )
            if (
                original_name in {"edit", "edit_file"}
                and item["name"] == original_name
                and "exec_command" in (function_tool_names or set())
            ):
                item["name"] = "exec_command"
                item["_arguments"] = json.dumps(
                    {
                        "cmd": (
                            "printf '%s\\n' 'Unsupported edit arguments; "
                            "use apply_patch or exec_command.'"
                        )
                    },
                    separators=(",", ":"),
                )
            if item["_compat_local_file"]:
                try:
                    arguments = json.loads(str(item["_arguments"]))
                    if item["_original_name"] == "read_mcp_resource":
                        uri = arguments["uri"]
                        parsed = urlsplit(uri)
                        path = (
                            unquote(parsed.path)
                            if (
                                parsed.scheme == "file"
                                and parsed.netloc in {"", "localhost"}
                                or not parsed.scheme
                                and parsed.path.startswith("/")
                            )
                            else ""
                        )
                    else:
                        path = arguments["path"]
                    if not isinstance(path, str) or not path:
                        raise TypeError
                except (KeyError, TypeError, ValueError):
                    path = ""
                if path:
                    item["name"] = "exec_command"
                    item["_arguments"] = json.dumps(
                        {"cmd": f"cat -- {shlex.quote(path)}"},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                else:
                    item["_compat_local_file"] = False
            if item["name"] == "exec_command":
                try:
                    arguments = json.loads(str(item["_arguments"]))
                except ValueError:
                    arguments = None
                if (
                    isinstance(arguments, dict)
                    and arguments.get("sandbox_permissions") == "require_escalated"
                ):
                    for key in ("sandbox_permissions", "justification", "prefix_rule"):
                        arguments.pop(key, None)
                    item["_arguments"] = json.dumps(
                        arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    LOGGER.info(
                        "responses_exec_escalation_suppressed session_id=%s",
                        _log_token(session_id),
                    )
                command = arguments.get("cmd") if isinstance(arguments, dict) else None
                if (
                    goal_already_loaded
                    and isinstance(command, str)
                    and "goal-objective.md" in command
                    and any(
                        token in f" {command}"
                        for token in (" cat ", " head ", " tail ", " wc ", " od ", " xxd ")
                    )
                ):
                    item["_arguments"] = json.dumps(
                        {
                            "cmd": (
                                "printf '%s\\n' "
                                "'Goal objective already loaded; continue implementation.'"
                            )
                        },
                        separators=(",", ":"),
                    )
                    LOGGER.info(
                        "responses_goal_reread_suppressed session_id=%s",
                        _log_token(session_id),
                    )
            if item["name"] == "write_stdin":
                try:
                    arguments = json.loads(str(item["_arguments"]))
                except ValueError:
                    arguments = None
                if (
                    "exec_command" in (function_tool_names or set())
                    and isinstance(arguments, dict)
                    and (
                        isinstance(arguments.get("session_id"), bool)
                        or not isinstance(arguments.get("session_id"), int)
                        or (
                            isinstance(arguments.get("chars"), str)
                            and ("\n" in arguments["chars"] or len(arguments["chars"]) > 256)
                        )
                    )
                ):
                    item["name"] = "exec_command"
                    item["_arguments"] = json.dumps(
                        {
                            "cmd": (
                                "printf '%s\\n' 'No active process session; "
                                "use apply_patch or exec_command.'"
                            )
                        },
                        separators=(",", ":"),
                    )
                    LOGGER.info(
                        "responses_invalid_write_stdin_rewritten session_id=%s",
                        _log_token(session_id),
                    )
            if not item["_added"]:
                is_custom = item["name"] in (custom_tool_names or set())
                item["id"] = f"{'ctc' if is_custom else 'fc'}_{uuid.uuid4().hex}"
                item["call_id"] = item["call_id"] or f"call_{uuid.uuid4().hex}"
                item["type"] = "custom_tool_call" if is_custom else "function_call"
                item["_kind"] = "custom" if is_custom else "function"
                if is_custom:
                    item["input"] = ""
                else:
                    item["status"] = "in_progress"
                    item["arguments"] = str(item["_arguments"])
                    item["_arguments_emitted"] = len(str(item["_arguments"]))
                yield event(
                    "response.output_item.added",
                    output_index=index + 1,
                    item={key: value for key, value in item.items() if not key.startswith("_")},
                )
            if item["_kind"] == "custom":
                try:
                    parsed_arguments = json.loads(str(item["_arguments"]))
                    custom_input = parsed_arguments["input"]
                    if not isinstance(custom_input, str):
                        raise TypeError
                except (KeyError, TypeError, ValueError):
                    custom_input = str(item["_arguments"])
                custom_item = {
                    "id": item["id"],
                    "type": "custom_tool_call",
                    "call_id": item["call_id"],
                    "name": item["name"],
                    "input": custom_input,
                }
                if custom_input:
                    yield event(
                        "response.custom_tool_call_input.delta",
                        item_id=custom_item["id"],
                        output_index=index + 1,
                        delta=custom_input,
                    )
                yield event(
                    "response.custom_tool_call_input.done",
                    item_id=custom_item["id"],
                    output_index=index + 1,
                    input=custom_input,
                )
                yield event("response.output_item.done", output_index=index + 1, item=custom_item)
                completed_output.append(custom_item)
                continue
            item.pop("_arguments", None)
            item["status"] = "completed"
            if item["arguments"]:
                yield event(
                    "response.function_call_arguments.delta",
                    response_id=response_id,
                    item_id=item["id"],
                    output_index=index + 1,
                    delta=item["arguments"],
                )
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
        LOGGER.info(
            "responses_stream_terminal session_id=%s model=%s status=completed "
            "tool_calls=%d text_chars=%d output_items=%d",
            _log_token(session_id),
            _log_token(model),
            len(tool_calls),
            len(text),
            len(completed_output),
        )
    except ProgressOnlyResponse:
        raise
    except Exception as error:
        terminal_error = {
            "type": "backend_error",
            "code": "backend_error",
            "message": "response stream failed",
        }
        LOGGER.warning(
            "responses_stream_terminal session_id=%s model=%s status=failed "
            "source=upstream_iterator error_type=%s",
            _log_token(session_id),
            _log_token(model),
            type(error).__name__,
        )
        yield event("response.failed", response=response_payload("failed", []))
    finally:
        close = getattr(upstream, "aclose", None)
        if close is not None:
            await close()


async def responses_error_sse(
    model: str,
    *,
    session_id: str,
    error_type: str,
    code: str,
    source: str,
    status_code: int,
    failure_class: str | None = None,
) -> AsyncGenerator[bytes, None]:
    response_id = f"resp_{uuid.uuid4().hex}"
    response = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "failed",
        "error": {"type": error_type, "code": code, "message": "request failed"},
        "incomplete_details": None,
        "model": model,
        "output": [],
        "usage": None,
    }
    LOGGER.warning(
        "responses_stream_terminal session_id=%s model=%s status=failed source=%s "
        "status_code=%d error_type=%s code=%s failure_class=%s",
        _log_token(session_id),
        _log_token(model),
        _log_token(source),
        status_code,
        _log_token(error_type),
        _log_token(code),
        _log_token(failure_class or error_type),
    )
    yield (
        "event: response.failed\ndata: "
        + json.dumps(
            {"type": "response.failed", "sequence_number": 0, "response": response},
            separators=(",", ":"),
        )
        + "\n\n"
    ).encode()
