from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings, get_settings
from .controller import Controller, DuplicateFailedCall
from .profiles import ProfileManager
from .providers import ModelProvider, validate_assistant_response
from .routing import (
    MODEL_MODES,
    classify_request,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
)
from .schemas import ChatRequest, ProfileResponse
from .security import admin_dependency, auth_dependency
from .state import StateStore
from .streaming import StreamObservation, forward_sse
from .trace import TraceRecorder


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


def title_request_index(messages: list[dict[str, Any]]) -> int | None:
    """Return OpenCode's trailing automatic title prompt, if present."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") == "user":
            content = str(message.get("content", "")).strip().lower()
            return index if content.startswith("generate a title for this conversation") else None
    return None


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    auth = auth_dependency(configured)
    admin_auth = admin_dependency(configured)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store = StateStore(configured.state_db)
        provider = ModelProvider()
        app.state.settings = configured
        app.state.store = store
        app.state.provider = provider
        app.state.controller = Controller(configured, store, provider)
        app.state.traces = TraceRecorder(
            configured.state_db.parent.parent / "traces", store, configured.models
        )
        app.state.profiles = ProfileManager(
            configured.run_dir, Path(os.getenv("DGX_MOA_PROJECT_ROOT", "."))
        )
        yield

    app = FastAPI(title="DGX MoA Agent", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            error_type, code, param = "authentication_error", "invalid_api_key", None
        elif error.status_code == status.HTTP_404_NOT_FOUND and error.detail == "unknown model":
            error_type, code, param = "invalid_request_error", "model_not_found", "model"
        elif error.status_code < 500:
            error_type, code, param = "invalid_request_error", "invalid_request", None
        else:
            error_type, code, param = "backend_error", "backend_error", None
        return error_response(
            error.status_code,
            str(error.detail),
            error_type,
            code,
            param,
            dict(error.headers) if error.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        first = error.errors()[0]
        message = str(first.get("msg", "invalid request")).removeprefix("Value error, ")
        location = first.get("loc", ())
        param = str(location[-1]) if len(location) > 1 else None
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            message,
            "invalid_request_error",
            "invalid_request",
            param,
        )

    def record_trace_safely(request: Request, state: Any, task_id: str) -> None:
        try:
            request.app.state.traces.record(state, task_id=task_id)
        except OSError as error:
            state.observability_degraded = True
            state.observability_status = "degraded"
            request.app.state.store.event(
                state.session_id,
                "observability_degraded",
                {"component": "trace_archive", "error": type(error).__name__},
            )
            request.app.state.store.save(state)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

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
            "resident": ("executor", "planner", "reviewer"),
            "judge": ("judge",),
        }.get(current, ())
        if not roles:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": {role: "stopped" for role in configured.models},
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        service_status = {role: "stopped" for role in configured.models}
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                results = await asyncio.gather(
                    *(
                        client.get(f"{model.base_url}/v1/models")
                        for model in configured.models.values()
                    ),
                    return_exceptions=True,
                )
            for role, result in zip(configured.models, results, strict=True):
                if isinstance(result, httpx.Response) and result.status_code == 200:
                    service_status[role] = "ready"
        except KeyError:
            pass
        if any(service_status.get(role) != "ready" for role in roles):
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": service_status,
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ready",
                "profile": current,
                "services": service_status,
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
                for alias in MODEL_MODES
            ],
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    async def chat(
        body: ChatRequest,
        request: Request,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
    ) -> Response:
        accepted = time.monotonic()
        profile_state = request.app.state.profiles.current()
        current_profile = profile_state["active_profile"]
        if current_profile == "judge" or profile_state["status"] in {
            "transitioning",
            "failed",
            "degraded",
        }:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "coding requests unavailable during heavy-judge profile",
                headers={"Retry-After": "30"},
            )
        try:
            mode = resolve_runtime_mode(body.model, configured.model_name)
        except ValueError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown model") from error
        if "executor" not in configured.models:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "executor is not configured")
        session_id = x_session_id or str(body.metadata.get("session_id") or uuid.uuid4())
        raw = body.model_dump(exclude_none=True)
        if x_runtime_channel:
            raw["metadata"]["runtime_channel"] = x_runtime_channel
        if x_trace_origin:
            raw["metadata"]["trace_origin"] = x_trace_origin
        if x_task_id:
            raw["metadata"]["task_id"] = x_task_id
        if x_workspace_path:
            raw["metadata"]["repository"] = {
                "workspace_path": x_workspace_path,
                "workspace_identifier": x_workspace_id or x_workspace_path,
                "current_branch": x_repository_branch or "unknown",
                "current_commit": x_repository_commit or "unknown",
                "dirty_status": x_dirty_state or "unknown",
            }
        task_id = str(raw["metadata"].get("task_id", ""))
        title_index = title_request_index(raw["messages"])
        if title_index is not None:
            state_session_id = f"{session_id}:title"
            raw["messages"] = [raw["messages"][title_index]]
        else:
            state_session_id = session_id
        try:
            state = request.app.state.controller.session(state_session_id, raw["messages"])
            request.app.state.store.event(
                state_session_id,
                "request_received",
                {"stream": body.stream, "task_id": task_id},
            )
            request.app.state.controller.select_route(state, raw["metadata"])
            if body.metadata.get("no_progress"):
                request.app.state.controller.note_no_progress(state)
            request_class = classify_request(
                mode, raw["messages"], raw.get("tools"), raw["metadata"]
            )
            roles = required_roles(mode, request_class)
            state.runtime_mode = mode
            state.request_class = request_class
            state.roles_required = list(roles)
            state.review_fail_closed = review_fails_closed(request_class)
            prepared = await request.app.state.controller.prepare_executor(state, raw, roles)
            if body.stream:
                upstream = await request.app.state.provider.stream(
                    "executor", configured.models["executor"], prepared
                )
                observation = StreamObservation(configured.limits.max_stream_capture_bytes)

                async def stream_response() -> AsyncIterator[bytes]:
                    completed = False
                    forwarder = forward_sse(
                        upstream,
                        observation,
                        max_event_bytes=configured.limits.max_sse_event_bytes,
                    )
                    try:
                        async with aclosing(forwarder):
                            async for chunk in forwarder:
                                if "first_downstream_byte" not in state.timings_ms:
                                    state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
                                yield chunk
                        completed = True
                    except asyncio.CancelledError:
                        if not observation.done_seen:
                            state.final_status = "cancelled"
                        raise
                    finally:
                        terminal = completed or observation.done_seen
                        state.finish_reasons = observation.finish_reasons
                        state.truncated = "length" in observation.finish_reasons
                        if terminal and "reviewer" in state.roles_required:
                            state.review_deferred = True
                            state.review_status = "deferred"
                        if state.decisions:
                            state.decisions[-1]["outcome"] = {
                                "status": "success" if terminal else "failure",
                                "progress_made": bool(observation.finish_reasons),
                                "state_changed": False,
                                "scope_changed": False,
                                "validation_triggered": False,
                                "next_phase": state.phase,
                            }
                        request.app.state.store.event(
                            state_session_id,
                            "assistant_stream_finished",
                            {"finish_reasons": observation.finish_reasons},
                        )
                        request.app.state.store.event(
                            state_session_id,
                            "stream_completed" if terminal else "stream_aborted",
                            {},
                        )
                        request.app.state.store.save(state)
                        record_trace_safely(request, state, task_id)

                return StreamingResponse(
                    stream_response(),
                    media_type="text/event-stream",
                    headers={"X-Session-ID": session_id},
                )
            response = await request.app.state.provider.complete(
                "executor", configured.models["executor"], prepared
            )
            validate_assistant_response(response)
            if state.decisions:
                state.decisions[-1]["structured_decision"] = response.get("choices", [{}])[0].get(
                    "message", {}
                )
                state.decisions[-1]["outcome"] = {
                    "status": "success",
                    "progress_made": True,
                    "state_changed": False,
                    "scope_changed": False,
                    "validation_triggered": bool(body.metadata.get("executor_complete")),
                    "next_phase": state.phase,
                }
            finish_reason = response.get("choices", [{}])[0].get("finish_reason")
            state.finish_reasons = [str(finish_reason)] if finish_reason else []
            state.truncated = finish_reason == "length"
            if (
                "reviewer" in state.roles_required
                and request.app.state.controller.has_review_evidence(state, body.metadata)
            ):
                review_observation = request.app.state.controller.review_observation(
                    state, response, body.metadata
                )
                try:
                    await request.app.state.controller.review(state, review_observation)
                except (httpx.HTTPError, ValueError) as error:
                    state.review_status = "failed"
                    request.app.state.store.event(
                        state_session_id,
                        "review_failed",
                        {"error_type": type(error).__name__},
                    )
                    if not state.review_fail_closed:
                        state.observability_degraded = True
                        state.observability_status = "degraded"
                    request.app.state.store.save(state)
                    if state.review_fail_closed:
                        raise
                else:
                    if not state.truncated:
                        request.app.state.controller.apply_metadata(state, body.metadata)
            request.app.state.store.event(
                state_session_id,
                "assistant_stream_finished",
                {"finish_reasons": [finish_reason] if finish_reason else []},
            )
            request.app.state.store.save(state)
            record_trace_safely(request, state, task_id)
            return JSONResponse(response, headers={"X-Session-ID": session_id})
        except DuplicateFailedCall as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except httpx.TimeoutException as error:
            stage = {
                "planning": "planner",
                "reviewing": "reviewer",
                "heavy_review": "judge",
            }.get(state.phase.value, "executor")
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                f"{stage}_timeout",
            )
        except httpx.HTTPStatusError as error:
            try:
                payload = error.response.json()
            except (ValueError, httpx.StreamError):
                payload = None
            upstream_error = payload.get("error") if isinstance(payload, dict) else None
            if (
                isinstance(upstream_error, dict)
                and isinstance(upstream_error.get("message"), str)
                and isinstance(upstream_error.get("type"), str)
                and isinstance(upstream_error.get("code"), str)
                and (
                    upstream_error.get("param") is None
                    or isinstance(upstream_error["param"], str)
                )
            ):
                return JSONResponse(payload, status_code=error.response.status_code)
            if error.response.status_code < 500:
                return error_response(
                    error.response.status_code,
                    str(error),
                    "invalid_request_error",
                    "invalid_request",
                )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except httpx.HTTPError as error:
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except ValueError as error:
            if str(error) == "max_tokens exceeds server maximum 16384":
                return error_response(
                    status.HTTP_400_BAD_REQUEST,
                    str(error),
                    "invalid_request_error",
                    "invalid_request",
                    "max_tokens",
                )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )

    @app.get("/admin/profile", response_model=ProfileResponse, dependencies=[Depends(admin_auth)])
    async def profile(request: Request) -> dict[str, str]:
        return dict(request.app.state.profiles.current())

    async def switch_profile(name: str, request: Request) -> dict[str, str]:
        try:
            return dict(await asyncio.to_thread(request.app.state.profiles.switch, name))
        except Exception as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @app.post(
        "/admin/profile/resident",
        response_model=ProfileResponse,
        dependencies=[Depends(admin_auth)],
    )
    async def resident(request: Request) -> dict[str, str]:
        return await switch_profile("resident", request)

    @app.post(
        "/admin/profile/judge", response_model=ProfileResponse, dependencies=[Depends(admin_auth)]
    )
    async def judge(request: Request) -> dict[str, str]:
        return await switch_profile("judge", request)

    @app.post(
        "/admin/profile/restore", response_model=ProfileResponse, dependencies=[Depends(admin_auth)]
    )
    async def restore(request: Request) -> dict[str, str]:
        return await switch_profile("restore", request)

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)
