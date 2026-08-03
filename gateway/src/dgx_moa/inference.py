from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, cast

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .schemas import text_content
from .streaming import compatible_edit_call, response_usage


def error_response(
    status_code: int,
    message: str,
    error_type: str,
    code: str,
    param: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": error_type, "code": code, "param": param}},
        status_code=status_code,
        headers=headers,
    )


def register_inference_routes(
    app: FastAPI,
    auth: Callable[..., Any],
    model_aliases: tuple[str, ...],
    implementation_quality_contract: str,
) -> None:
    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "remote_judge": (
                "disabled"
                if request.app.state.remote_judge is None
                else "available"
                if request.app.state.remote_judge_available
                else "unavailable"
            ),
        }

    @app.get("/v1/models", dependencies=[Depends(auth)])
    async def models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": alias,
                    "object": "model",
                    "created": 0,
                    "owned_by": "local",
                    "context_length": 65_536,
                }
                for alias in model_aliases
            ],
            "models": [
                {
                    "slug": alias,
                    "display_name": alias,
                    "description": "Local Executor-directed Dynamic MoA model.",
                    "default_reasoning_level": None,
                    "supported_reasoning_levels": [],
                    "shell_type": "shell_command",
                    "visibility": "list",
                    "supported_in_api": True,
                    "priority": index,
                    "additional_speed_tiers": [],
                    "service_tiers": [],
                    "availability_nux": None,
                    "upgrade": None,
                    "base_instructions": (
                        "You are a coding agent. Follow the user's instructions and use the "
                        "provided tools to inspect, edit, and verify the workspace. Use "
                        "exec_command for local paths and file:// URIs; read_file is not a "
                        "supported Codex tool. Do not discover MCP resources for local paths. "
                        "Batch independent reads and checks. Use only an integer session_id "
                        "returned by exec_command with write_stdin; never invent one. Call "
                        "read_mcp_resource only with an exact server and URI returned by MCP "
                        "resource discovery; integration display names are not MCP server IDs. "
                        + implementation_quality_contract
                    ),
                    "model_messages": None,
                    "include_skills_usage_instructions": False,
                    "supports_reasoning_summaries": False,
                    "default_reasoning_summary": "none",
                    "support_verbosity": False,
                    "default_verbosity": None,
                    "apply_patch_tool_type": "freeform",
                    "web_search_tool_type": "text",
                    "truncation_policy": {"mode": "tokens", "limit": 10_000},
                    "supports_parallel_tool_calls": True,
                    "supports_image_detail_original": False,
                    "context_window": 65_536,
                    "max_context_window": 65_536,
                    "comp_hash": "dgx-moa-65536-v1",
                    "effective_context_window_percent": 95,
                    "experimental_supported_tools": [],
                    "input_modalities": ["text"],
                    "supports_search_tool": False,
                    "use_responses_lite": False,
                    "tool_mode": "direct",
                    "multi_agent_version": None,
                }
                for index, alias in enumerate(model_aliases)
            ],
        }


def title_request_index(messages: list[dict[str, Any]]) -> int | None:
    """Return OpenCode's trailing automatic title prompt, if present."""
    title_generator = any(
        message.get("role") == "system"
        and text_content(message.get("content"))
        .strip()
        .lower()
        .startswith("you are a title generator. you output only a thread title.")
        for message in messages
    )
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") == "user":
            content = text_content(message.get("content")).strip().lower()
            if content.startswith("generate a title for this conversation"):
                return index
            if not title_generator:
                return None
    return None


def compaction_request_index(messages: list[dict[str, Any]]) -> int | None:
    """Return Codex's internal context-compaction request, if present."""
    if len(messages) < 2:
        return None
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") != "user":
            continue
        content = " ".join(text_content(message.get("content")).lower().split())
        if len(content) <= 2_000 and all(
            marker in content for marker in ("compact", "context", "summary", "continue")
        ):
            return index
        return None
    return None


def coerce_responses_input_messages(
    raw_input: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if isinstance(raw_input, list):
        messages: list[dict[str, Any]] = []
        for item in raw_input:
            item_type = item.get("type")
            if item_type == "reasoning":
                continue
            if item_type in {"function_call", "custom_tool_call"}:
                arguments = (
                    item.get("arguments", "")
                    if item_type == "function_call"
                    else json.dumps({"input": item.get("input", "")})
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": arguments,
                                },
                            }
                        ],
                    }
                )
                continue
            if item_type in {"function_call_output", "custom_tool_call_output"}:
                output = item.get("output", "")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": output if isinstance(output, str) else json.dumps(output),
                    }
                )
                continue
            message = dict(item)
            if isinstance(content := message.get("content"), list):
                message["content"] = [
                    {**part, "type": "text"}
                    if part.get("type") in {"input_text", "output_text"}
                    else part
                    for part in content
                ]
            messages.append(message)
        return messages
    raise TypeError("invalid responses input type")


def coerce_responses_tools(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    chat_tools = []
    for tool in tools:
        tool_type = tool.get("type")
        if tool_type not in {"function", "custom"}:
            continue
        nested_function = tool.get("function")
        function: dict[str, Any] = nested_function if isinstance(nested_function, dict) else tool
        if tool_type == "custom":
            function = {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                    "additionalProperties": False,
                },
            }
        chat_tools.append(
            {
                "type": "function",
                "function": {
                    key: function[key]
                    for key in ("name", "description", "parameters", "strict")
                    if key in function
                },
            }
        )
    return chat_tools or None


def remap_reused_tool_call_ids(
    response: dict[str, Any], used_ids: set[str], namespace: str
) -> int:
    remapped = 0
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    for index, call in enumerate(message.get("tool_calls") or []):
        call_id = call.get("id") if isinstance(call, dict) else None
        if not isinstance(call_id, str) or not call_id:
            continue
        if call_id in used_ids:
            call["id"] = f"call_{uuid.uuid5(uuid.NAMESPACE_URL, f'{namespace}:{index}').hex}"
            remapped += 1
        used_ids.add(str(call["id"]))
    return remapped


def responses_payload(
    model: str,
    chat_response: dict[str, Any] | None = None,
    *,
    status: str = "completed",
    custom_tool_names: set[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"resp-{uuid.uuid4().hex}",
        "object": "response",
        "created": int(time.time()),
        "model": model,
        "status": status,
        "output": [],
    }
    if chat_response is None:
        return payload
    if error := chat_response.get("error"):
        payload["error"] = error
        payload["status"] = "failed"
        return payload

    choices = chat_response.get("choices") or []
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content:
            payload["output"] = [
                {
                    "type": "message",
                    "status": "completed",
                    "role": message.get("role", "assistant"),
                    "content": [{"type": "output_text", "text": content}],
                }
            ]
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            name, arguments = compatible_edit_call(
                str(function.get("name", "")),
                str(function.get("arguments", "")),
                custom_tool_names,
            )
            if name in (custom_tool_names or set()):
                try:
                    parsed_arguments = json.loads(arguments)
                    custom_input = parsed_arguments["input"]
                    if not isinstance(custom_input, str):
                        raise TypeError
                except (KeyError, TypeError, ValueError):
                    custom_input = arguments
                payload["output"].append(
                    {
                        "type": "custom_tool_call",
                        "id": f"ctc_{uuid.uuid4().hex}",
                        "call_id": tool_call.get("id"),
                        "name": name,
                        "input": custom_input,
                    }
                )
                continue
            payload["output"].append(
                {
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex}",
                    "call_id": tool_call.get("id"),
                    "name": name,
                    "arguments": arguments,
                    "status": "completed",
                }
            )
    if not payload["output"]:
        payload["status"] = "failed"
        payload["error"] = {
            "message": "upstream response did not contain assistant output",
            "type": "backend_error",
            "code": "backend_error",
        }
    if usage := response_usage(chat_response.get("usage")):
        payload["usage"] = usage
    return payload


def chat_response_payload(response: Response) -> dict[str, Any] | None:
    raw_body = getattr(response, "body", None)
    if not raw_body:
        return None
    try:
        return cast(
            dict[str, Any],
            json.loads(raw_body.decode() if isinstance(raw_body, bytes) else raw_body),
        )
    except ValueError:
        return None


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def has_matching_tool_result(messages: list[dict[str, Any]]) -> bool:
    assistant_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "assistant" and messages[index].get("tool_calls")
        ),
        None,
    )
    if assistant_index is None:
        return False
    trailing = messages[assistant_index + 1 :]
    if not trailing or any(message.get("role") != "tool" for message in trailing):
        return False
    call_ids = {
        call_id
        for call in (messages[assistant_index].get("tool_calls") or [])
        if isinstance(call, dict) and isinstance(call_id := call.get("id"), str) and call_id.strip()
    }
    result_ids = {
        tool_call_id
        for message in trailing
        if isinstance(tool_call_id := message.get("tool_call_id"), str) and tool_call_id.strip()
    }
    return bool(call_ids & result_ids)


def tool_result_call_ids(messages: list[dict[str, Any]]) -> set[str]:
    return {
        tool_call_id
        for message in messages
        if message.get("role") == "tool"
        and isinstance(tool_call_id := message.get("tool_call_id"), str)
        and tool_call_id.strip()
    }


def unsafe_frontier_correction_tool_call(response: Mapping[str, Any]) -> bool:
    message = (response.get("choices") or [{}])[0].get("message", {})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        name = function.get("name")
        if name not in {"apply_patch", "edit", "edit_file"}:
            continue
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                return True
        if not isinstance(arguments, dict):
            return True
        if name == "apply_patch":
            patch = next(
                (
                    arguments.get(key)
                    for key in ("input", "patch", "diff")
                    if isinstance(arguments.get(key), str)
                ),
                None,
            )
            return not (
                patch
                and "*** Begin Patch" in patch
                and "*** End Patch" in patch
                and re.search(r"(?m)^\*\*\* (?:Add|Delete|Update) File: ", patch)
            )
        old = next(
            (
                arguments.get(key)
                for key in ("oldString", "old_string", "oldText", "old_text")
                if isinstance(arguments.get(key), str)
            ),
            None,
        )
        new = next(
            (
                arguments.get(key)
                for key in ("newString", "new_string", "newText", "new_text")
                if isinstance(arguments.get(key), str)
            ),
            None,
        )
        if old is None or new is None:
            return True
        if len(old.strip()) < 8 and len(new) >= 256:
            return True
    return False


class ResponseOwnedIterator:
    def __init__(
        self,
        stream: AsyncIterator[bytes],
        cleanup: Callable[[], Awaitable[None]],
    ) -> None:
        self._stream = stream
        self._cleanup = cleanup

    def __aiter__(self) -> ResponseOwnedIterator:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await anext(self._stream)
        except BaseException:
            await self._cleanup()
            raise

    async def aclose(self) -> None:
        try:
            close = getattr(self._stream, "aclose", None)
            if close is not None:
                await close()
        finally:
            await self._cleanup()


class ResponseOwnedStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                await close()
