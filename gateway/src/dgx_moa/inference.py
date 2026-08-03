from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .config import Settings
from .image_generation import capability_status as image_generation_status
from .providers import StageTimeout
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
    configured: Settings,
    auth: Callable[..., Any],
    model_aliases: tuple[str, ...],
    implementation_quality_contract: str,
    status_lifecycle_record: Callable[[str], dict[str, Any]],
    record_trace_safely: Callable[[Request, Any, str], None],
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

    @app.get("/metrics", dependencies=[Depends(auth)])
    async def metrics(request: Request) -> Response:
        overlays: dict[str, int | float] = {}
        skills = request.app.state.skills
        if skills is not None:
            skill_rows = skills.list_skills()
            skill_metrics = [skills.metrics(item.skill_id, item.version) for item in skill_rows]
            overlays.update(
                skill_invocations_total=sum(item.selected for item in skill_metrics),
                skill_success_total=sum(item.succeeded for item in skill_metrics),
                skill_override_total=sum(item.overridden for item in skill_metrics),
                skill_regression_total=sum(item.regressions for item in skill_metrics),
                skill_candidate_created_total=sum(
                    item.source == "generated" for item in skill_rows
                ),
                skill_promoted_total=sum(
                    item.state == "active" and item.provenance.source_trace_ids
                    for item in skill_rows
                ),
                skill_deprecated_total=sum(
                    item.state == "deprecated" for item in skill_rows
                ),
            )
        knowledge = request.app.state.knowledge
        if knowledge is not None:
            knowledge_rows = knowledge.list_entries()
            knowledge_metrics = [
                knowledge.metrics(item.knowledge_id, item.version) for item in knowledge_rows
            ]
            overlays.update(
                knowledge_retrieval_total=sum(item.retrieved for item in knowledge_metrics),
                knowledge_helpful_total=sum(item.helpful for item in knowledge_metrics),
                knowledge_harmful_total=sum(item.harmful for item in knowledge_metrics),
                knowledge_conflict_total=sum(
                    item.open_conflicts for item in knowledge_metrics
                )
                // 2,
                knowledge_candidate_created_total=sum(
                    item.state == "candidate" for item in knowledge_rows
                ),
                knowledge_promoted_total=sum(
                    item.state == "active" and item.lifecycle.approval_id is not None
                    for item in knowledge_rows
                ),
                knowledge_deprecated_total=sum(
                    item.state == "deprecated" for item in knowledge_rows
                ),
            )
        observation_bus = request.app.state.observation
        if observation_bus is not None:
            overlays.update(
                observer_events_sent_total=observation_bus.metrics["sent"],
                observer_events_dropped_total=observation_bus.metrics["dropped"],
                telegram_errors_total=observation_bus.metrics["telegram_errors"],
            )
        collector = request.app.state.training_collector
        if collector is not None:
            overlays.update(
                training_events_collected_total=collector.metrics["events"],
                training_candidates_created_total=collector.metrics["candidates"],
                training_candidates_excluded_total=collector.metrics["excluded"],
                secret_redactions_total=collector.metrics["secret_redactions"],
                privacy_exclusions_total=collector.metrics["privacy_exclusions"],
                license_exclusions_total=collector.metrics["license_exclusions"],
            )
        packager = request.app.state.weekly_packager
        if packager is not None:
            overlays.update(
                exact_duplicates_removed_total=packager.metrics["exact_duplicates_removed"],
                near_duplicates_removed_total=packager.metrics["near_duplicates_removed"],
                weekly_packages_created_total=packager.metrics["packages_created"],
                weekly_package_failures_total=packager.metrics["package_failures"],
                weekly_package_bytes=packager.metrics["package_bytes"],
                archive_verification_failures_total=packager.metrics[
                    "archive_verification_failures"
                ],
            )
        return Response(
            request.app.state.runtime_metrics.prometheus(overlays),
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        profile_state = request.app.state.profiles.current()
        current = profile_state["active_profile"]
        if profile_state["status"] in {"transitioning", "degraded", "failed"}:
            return JSONResponse(
                {
                    "status": profile_state["status"],
                    "from": profile_state.get("from", current),
                    "to": profile_state.get("to", "unknown"),
                },
                status_code=503,
            )
        roles = {
            "resident": ("executor", "reasoner"),
            "judge": ("judge",),
        }.get(current, ())
        if not roles:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": {role: "stopped" for role in configured.models},
                    "remote_judge": (
                        "disabled" if request.app.state.remote_judge is None else "unavailable"
                    ),
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        service_status = {role: "stopped" for role in configured.models}
        try:
            results = await asyncio.gather(
                *(
                    request.app.state.http_client.get(
                        f"{model.base_url.rstrip('/')}/api/ps"
                        if model.provider == "ollama"
                        else f"{model.base_url.rstrip('/')}/v1/models",
                        timeout=2,
                    )
                    for model in configured.models.values()
                ),
                return_exceptions=True,
            )
            for (role, model), result in zip(configured.models.items(), results, strict=True):
                if isinstance(result, httpx.Response) and (
                    ollama_model_ready(result, model)
                    if model.provider == "ollama"
                    else result.status_code == 200
                ):
                    service_status[role] = "ready"
        except KeyError:
            pass
        remote_judge = (
            "disabled"
            if request.app.state.remote_judge is None
            else "available"
            if request.app.state.remote_judge_available
            else "unavailable"
        )
        if any(service_status.get(role) != "ready" for role in roles):
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": service_status,
                    "remote_judge": remote_judge,
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ready",
                "profile": current,
                "services": service_status,
                "remote_judge": remote_judge,
                "auth_enabled": configured.auth_enabled,
            }
        )

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

    @app.get("/v1/model-status", dependencies=[Depends(auth)])
    async def model_status(request: Request) -> dict[str, Any]:
        mode = configured.lifecycle_mode
        payload: dict[str, Any] = {
            "object": "list",
            "data": [status_lifecycle_record(role) for role in configured.models],
            "lifecycle_mode": mode,
            "control": (
                "disabled"
                if mode == "disabled"
                else "observe_only"
                if mode == "observe"
                else "managed"
            ),
            "unmanaged_roles": sorted(
                configured.models
                if mode == "disabled"
                else {
                    role
                    for role, model in configured.models.items()
                    if role not in configured.lifecycle_unit_map
                    and model.lifecycle_control != "external"
                }
            ),
            "idle_decisions": {
                role: decision.model_dump(mode="json")
                for role in sorted(configured.lifecycle_unit_map)
                if mode != "disabled"
                and (decision := request.app.state.lifecycle_store.latest_decision(role))
                is not None
                and decision.mode == mode
            },
            "automation": request.app.state.lifecycle_store.automation_status().model_dump(
                mode="json"
            ),
            "capabilities": {
                "generate_image": image_generation_status(configured.image_generation)
            },
        }
        if mode == "disabled":
            payload["external_state"] = "not_lifecycle_managed"
        return payload

    @app.get("/v1/model-status/{role}", dependencies=[Depends(auth)], response_model=None)
    async def model_status_detail(role: str) -> Response | dict[str, Any]:
        if role not in configured.models:
            return error_response(
                status.HTTP_404_NOT_FOUND,
                "unknown lifecycle role",
                "invalid_request_error",
                "model_role_not_found",
            )
        return status_lifecycle_record(role)

    @app.get("/v1/image-artifacts/{artifact_id}", dependencies=[Depends(auth)])
    async def image_artifact(artifact_id: str, request: Request) -> Response:
        generator = request.app.state.image_generator
        if generator is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "image artifact not found")
        try:
            artifact = generator.artifact_for(
                artifact_id,
                getattr(request.state, "api_token_id", ""),
            )
        except (KeyError, OSError, ValueError):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "image artifact not found") from None
        return FileResponse(
            artifact.path,
            media_type=artifact.media_type,
            filename=f"{artifact.artifact_id}{artifact.path.suffix}",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/v1/judge/adjudications/{session_id}", dependencies=[Depends(auth)])
    async def adjudicate(session_id: str, request: Request) -> Response:
        profile = request.app.state.profiles.current()
        remote = request.app.state.remote_judge is not None
        if not remote and (
            profile.get("active_profile") != "judge" or profile.get("status") != "ready"
        ):
            return error_response(
                status.HTTP_409_CONFLICT,
                "Heavy Judge profile is not ready",
                "profile_conflict",
                "judge_profile_required",
            )
        state = request.app.state.store.get(session_id)
        if state is None:
            return error_response(
                status.HTTP_404_NOT_FOUND,
                "adjudication session not found",
                "invalid_request_error",
                "session_not_found",
            )
        if state.judge_status != "required" or not state.pending_judge_evidence:
            return error_response(
                status.HTTP_409_CONFLICT,
                "session has no pending Heavy Judge adjudication",
                "invalid_request_error",
                "judge_not_pending",
            )
        request_id = str(uuid.uuid4())
        state.current_request_id = request_id
        leases = await request.app.state.lifecycle.acquire_request_leases(
            request_id,
            () if remote else ("judge",),
            kind="active_request",
            require_ready=False,
        )
        try:
            verdict = await request.app.state.controller.judge(
                state, state.pending_judge_evidence
            )
            request.app.state.store.save(state)
            record_trace_safely(request, state, state.task_id or session_id)
        except StageTimeout as error:
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                "judge_timeout",
            )
        except (httpx.HTTPError, ValueError) as error:
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "judge_backend_error",
            )
        finally:
            request.app.state.lifecycle_store.release_leases(
                tuple(lease.lease_id for lease in leases)
            )
        return JSONResponse(
            {
                "object": "judge.adjudication",
                "session_id": session_id,
                "status": state.judge_status,
                "verdict": verdict,
                "resume_profile": None if remote else "resident",
            }
        )


def ollama_model_ready(response: httpx.Response, model: Any) -> bool:
    if response.status_code != 200:
        return False
    try:
        models = response.json().get("models", [])
    except (ValueError, AttributeError):
        return False
    return any(
        isinstance(item, dict)
        and model.served_name in {item.get("name"), item.get("model")}
        and isinstance(item.get("context_length"), int)
        and item["context_length"] >= model.context_length
        for item in models
    )


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
