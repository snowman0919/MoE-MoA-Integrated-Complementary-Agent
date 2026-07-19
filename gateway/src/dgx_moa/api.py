from __future__ import annotations

import asyncio
import math
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings, get_settings
from .controller import Controller, DuplicateFailedCall
from .lifecycle import (
    LifecycleCoordinator,
    LifecycleDriver,
    LifecycleNotReadyError,
    LifecycleRecord,
    LifecycleStore,
    SystemdLifecycleDriver,
    continuation_correlation,
)
from .profiles import ProfileManager
from .providers import ModelProvider, StageTimeout, validate_assistant_response
from .routing import (
    MODEL_MODES,
    classify_request,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
)
from .runtime_status import memory_available as runtime_memory_available
from .runtime_status import report as runtime_report
from .schemas import ChatRequest, ProfileResponse
from .security import admin_dependency, auth_dependency
from .state import StateStore
from .streaming import StreamObservation, forward_sse, reported_usage
from .trace import TraceRecorder
from .usage import (
    ModelAlias,
    RequestStatus,
    RequestUsageFinalization,
    RequestUsageStart,
    RetryableFailureClass,
    Role,
    UsageStore,
    classify_client,
)

TIMEOUT_FAILURE_CLASSES: dict[str, RetryableFailureClass] = {
    "planner": "planner_timeout",
    "executor_first_byte": "executor_first_byte_timeout",
    "executor_total": "executor_total_timeout",
    "executor": "executor_timeout",
    "reviewer": "reviewer_timeout",
    "judge": "judge_timeout",
}


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


def create_app(
    settings: Settings | None = None,
    *,
    lifecycle_driver: LifecycleDriver | None = None,
    lifecycle_health_probe: Callable[[str], Awaitable[bool]] | None = None,
    lifecycle_clock: Callable[[], float] = time.time,
    lifecycle_sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    lifecycle_memory_probe: Callable[[], int] = runtime_memory_available,
) -> FastAPI:
    configured = settings or get_settings()
    auth = auth_dependency(configured)
    admin_auth = admin_dependency(configured)

    async def default_lifecycle_health_probe(role: str) -> bool:
        model = configured.models.get(role)
        if model is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(f"{model.base_url}/v1/models")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store = StateStore(configured.state_db)
        provider = ModelProvider()
        project_root = Path(os.getenv("DGX_MOA_PROJECT_ROOT", ".")).resolve()
        app.state.settings = configured
        app.state.store = store
        app.state.usage = UsageStore(
            configured.state_db,
            sample_window=configured.limits.usage_sample_window,
            ewma_alpha=configured.limits.usage_ewma_alpha,
            adaptive_minimum_samples=configured.limits.adaptive_minimum_samples,
        )
        app.state.usage_session_namespace = uuid.uuid4()
        app.state.project_root = project_root
        app.state.provider = provider
        app.state.controller = Controller(configured, store, provider)
        app.state.lifecycle_store = LifecycleStore(
            configured.state_db,
            configured.models,
            clock=lifecycle_clock,
        )
        app.state.lifecycle_store.recover_leases()
        app.state.lifecycle = LifecycleCoordinator(
            app.state.lifecycle_store,
            lifecycle_driver or SystemdLifecycleDriver(configured.lifecycle_unit_map),
            health_probe=lifecycle_health_probe or default_lifecycle_health_probe,
            timeout_seconds=configured.limits.model_load_timeout_seconds,
            poll_seconds=configured.lifecycle_poll_seconds,
            clock=lifecycle_clock,
            sleeper=lifecycle_sleeper,
            memory_probe=lifecycle_memory_probe,
        )
        try:
            managed_roles = tuple(configured.lifecycle_unit_map)
            if configured.lifecycle_mode in {"fixed", "adaptive"}:
                await app.state.lifecycle.reconcile_managed(managed_roles)
            app.state.lifecycle.start_scheduler(
                configured.lifecycle_mode,
                managed_roles,
                configured.limits,
                app.state.usage,
            )
            app.state.reviewer_evaluation_lock = asyncio.Lock()
            app.state.traces = TraceRecorder(
                configured.state_db.parent.parent / "traces", store, configured.models
            )
            app.state.profiles = ProfileManager(configured.run_dir, project_root)
            yield
        finally:
            await app.state.lifecycle.close()

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

    def public_lifecycle_record(record: LifecycleRecord) -> dict[str, Any]:
        decision = app.state.lifecycle_store.latest_decision(record.role)
        if decision is not None and decision.mode != configured.lifecycle_mode:
            decision = None
        return {
            "role": record.role,
            "state": record.state,
            "transition_id": record.transition_id,
            "transitioned_at": record.transitioned_at,
            "updated_at": record.updated_at,
            "ready_since": record.ready_since,
            "last_used_at": record.last_used_at,
            "weight_load_percent": record.progress_value,
            "progress_quality": record.progress_quality or "unavailable",
            "overall_load_percent": None,
            "estimated_ready_seconds": record.eta_seconds,
            "failure_class": record.failure_class,
            "retry_count": record.retry_count,
            "idle_decision": decision.model_dump(mode="json") if decision else None,
            "lifecycle_mode": configured.lifecycle_mode,
            "control": ("observe_only" if configured.lifecycle_mode == "observe" else "managed"),
        }

    def status_lifecycle_record(role: str) -> dict[str, Any]:
        if configured.lifecycle_mode != "disabled" and role in configured.lifecycle_unit_map:
            return public_lifecycle_record(app.state.lifecycle_store.get(role))
        return {
            "role": role,
            "state": "unmanaged",
            "transition_id": None,
            "transitioned_at": None,
            "updated_at": None,
            "ready_since": None,
            "last_used_at": None,
            "weight_load_percent": None,
            "progress_quality": "unavailable",
            "overall_load_percent": None,
            "estimated_ready_seconds": None,
            "failure_class": None,
            "retry_count": 0,
            "idle_decision": None,
            "lifecycle_mode": configured.lifecycle_mode,
            "control": "disabled" if configured.lifecycle_mode == "disabled" else "unmanaged",
        }

    def loading_response(record: LifecycleRecord) -> JSONResponse:
        eta = record.eta_seconds
        retry_after = 30 if eta is None else min(300, max(1, math.ceil(eta)))
        progress = record.progress_value
        progress_header = "unavailable" if progress is None else f"{progress:g}"
        return JSONResponse(
            {
                "error": {
                    "message": f"Model dgx-moa-{record.role} is loading. Retry later.",
                    "type": "model_loading",
                    "code": "model_loading",
                    "param": None,
                },
                "model_state": {
                    "role": record.role,
                    "state": record.state,
                    "transition_id": record.transition_id,
                    "weight_load_percent": progress,
                    "progress_quality": record.progress_quality or "unavailable",
                    "overall_load_percent": None,
                    "estimated_ready_seconds": eta,
                },
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={
                "Retry-After": str(retry_after),
                "X-DGX-MOA-Model-State": record.state,
                "X-DGX-MOA-Weight-Load-Percent": progress_header,
            },
        )

    def unavailable_response(role: str, *, record: LifecycleRecord | None = None) -> JSONResponse:
        state_value = record.state if record is not None else "unmanaged"
        model_state: dict[str, Any] = {
            "role": role,
            "state": state_value,
            "transition_id": record.transition_id if record is not None else None,
            "weight_load_percent": record.progress_value if record is not None else None,
            "progress_quality": (record.progress_quality if record is not None else None)
            or "unavailable",
            "overall_load_percent": None,
            "estimated_ready_seconds": record.eta_seconds if record is not None else None,
        }
        if record is not None:
            model_state.update(
                failure_class=record.failure_class,
                retry_count=record.retry_count,
            )
        return JSONResponse(
            {
                "error": {
                    "message": (
                        f"Model role {role} is not lifecycle-managed."
                        if record is None
                        else f"Model dgx-moa-{role} failed to load."
                    ),
                    "type": "model_unavailable",
                    "code": "model_not_managed" if record is None else "model_load_failed",
                    "param": None,
                },
                "model_state": model_state,
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={
                "X-DGX-MOA-Model-State": state_value,
                "X-DGX-MOA-Weight-Load-Percent": (
                    "unavailable"
                    if record is None or record.progress_value is None
                    else f"{record.progress_value:g}"
                ),
            },
        )

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
            "resident": ("executor",),
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
                else set(configured.models) - set(configured.lifecycle_unit_map)
            ),
            "idle_decisions": {
                role: decision.model_dump(mode="json")
                for role in sorted(configured.lifecycle_unit_map)
                if mode != "disabled"
                and (decision := request.app.state.lifecycle_store.latest_decision(role))
                is not None
                and decision.mode == mode
            },
        }
        if mode == "disabled":
            payload["external_state"] = "not_lifecycle_managed"
        return payload

    @app.get("/v1/model-status/{role}", dependencies=[Depends(auth)], response_model=None)
    async def model_status_detail(role: str, request: Request) -> Response | dict[str, Any]:
        if role not in configured.models:
            return error_response(
                status.HTTP_404_NOT_FOUND,
                "unknown lifecycle role",
                "invalid_request_error",
                "model_role_not_found",
            )
        return status_lifecycle_record(role)

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
        accepted_at = time.time()
        stage_status: dict[str, str] = {}
        timing_recorded = False
        terminal_finalized = False
        usage_started = False
        usage_request_id = str(uuid.uuid4())
        active_lease_ids: tuple[str, ...] = ()
        stream_lease_ids: tuple[str, ...] = ()
        first_byte_at: float | None = None
        token_usage: dict[str, int] = {}
        state: Any | None = None
        executor_started: float | None = None
        active_stage = "request"

        def record_request_timing(state: Any) -> None:
            nonlocal timing_recorded
            if timing_recorded:
                return
            state.timings_ms["completed"] = elapsed_ms(accepted)
            request.app.state.store.event(
                state.session_id,
                "request_timing",
                {
                    "timings_ms": dict(state.timings_ms),
                    "stage_status": dict(stage_status),
                },
            )
            timing_recorded = True

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
        try:
            raw["max_tokens"] = request.app.state.controller.executor_tokens(raw)
        except ValueError as error:
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                str(error),
                "invalid_request_error",
                "invalid_request",
                "max_tokens",
            )
        raw["metadata"]["runtime_channel"] = x_runtime_channel or configured.runtime_channel
        raw["metadata"]["trace_origin"] = x_trace_origin or configured.trace_origin
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
        title_index = title_request_index(raw["messages"])
        if title_index is not None:
            state_session_id = f"{session_id}:title"
            raw["messages"] = [raw["messages"][title_index]]
        else:
            state_session_id = session_id
        task_id = str(raw["metadata"].get("task_id") or "")
        request_class = classify_request(mode, raw["messages"], raw.get("tools"), raw["metadata"])
        roles = required_roles(mode, request_class)
        loading_record: LifecycleRecord | None = None
        unavailable_record: LifecycleRecord | None = None
        unmanaged_role: str | None = None
        load_triggered = False
        if configured.lifecycle_mode in {"fixed", "adaptive"}:
            for role in roles:
                if role not in configured.lifecycle_unit_map:
                    if (
                        loading_record is None
                        and unavailable_record is None
                        and unmanaged_role is None
                    ):
                        unmanaged_role = role
                    continue
                check = await request.app.state.lifecycle.ensure_ready(role)
                load_triggered = load_triggered or check.load_triggered
                if (
                    loading_record is None
                    and unavailable_record is None
                    and unmanaged_role is None
                    and check.record.state != "ready"
                ):
                    if check.record.state == "failed":
                        unavailable_record = check.record
                    else:
                        loading_record = check.record
        request.app.state.usage.start(
            RequestUsageStart(
                request_id=usage_request_id,
                session_id=str(
                    uuid.uuid5(
                        request.app.state.usage_session_namespace,
                        state_session_id,
                    )
                ),
                client_class=classify_client(
                    request.headers.get("user-agent") if "headers" in request.scope else None
                ),
                model_alias=cast(
                    ModelAlias,
                    next(alias for alias, alias_mode in MODEL_MODES.items() if alias_mode == mode),
                ),
                runtime_mode=mode,
                request_class=request_class,
                roles_required=cast(tuple[Role, ...], roles),
                accepted_at=accepted_at,
                streaming=body.stream,
                model_state=(
                    "loading"
                    if loading_record is not None
                    else "cold"
                    if unavailable_record is not None or unmanaged_role is not None
                    else "warm"
                ),
                load_triggered=load_triggered,
            )
        )
        usage_started = True

        def finalize_request(
            stage: str | None,
            status_value: RequestStatus,
            *,
            downstream_started: bool = False,
            current_state: Any | None = None,
            retryable_failure_class: RetryableFailureClass | None = None,
        ) -> None:
            nonlocal active_lease_ids, first_byte_at, state, stream_lease_ids
            nonlocal terminal_finalized
            if terminal_finalized:
                return
            terminal_finalized = True
            try:
                current = current_state or state or request.app.state.store.get(state_session_id)
                if stage is not None:
                    stage_status[stage] = status_value
                if downstream_started:
                    first_byte_at = first_byte_at or time.time()
                if current is not None:
                    if state is None:
                        current.timings_ms = {"accepted": 0.0}
                        state = current
                    if status_value == "cancelled":
                        current.final_status = "cancelled"
                    elif (
                        status_value in {"failed", "timed_out"}
                        and current.final_status != "blocked"
                    ):
                        current.final_status = "failed"
                    if executor_started is not None:
                        current.timings_ms.setdefault(
                            "executor_total",
                            round((time.monotonic() - executor_started) * 1000, 3),
                        )
                    if downstream_started:
                        current.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
                    record_request_timing(current)
                    request.app.state.store.event(
                        current.session_id,
                        "session_ended",
                        {"request_id": state_session_id, "status": status_value},
                    )
                    request.app.state.store.save(current)
                    record_trace_safely(request, current, task_id)
                if usage_started:
                    request.app.state.usage.finalize(
                        usage_request_id,
                        RequestUsageFinalization(
                            first_byte_at=first_byte_at,
                            completed_at=time.time(),
                            active_duration_seconds=time.monotonic() - accepted,
                            status=status_value,
                            retryable_failure_class=retryable_failure_class,
                            prompt_tokens=token_usage.get("prompt_tokens"),
                            completion_tokens=token_usage.get("completion_tokens"),
                            total_tokens=token_usage.get("total_tokens"),
                        ),
                    )
            finally:
                request.app.state.lifecycle_store.release_leases(
                    (*stream_lease_ids, *active_lease_ids)
                )
                active_lease_ids = ()
                stream_lease_ids = ()

        if loading_record is not None:
            finalize_request(
                "model_loading",
                "failed",
                retryable_failure_class="model_loading",
            )
            return loading_response(loading_record)
        if unavailable_record is not None or unmanaged_role is not None:
            finalize_request(
                "model_unavailable",
                "failed",
            )
            unavailable_role = unmanaged_role
            if unavailable_role is None:
                assert unavailable_record is not None
                unavailable_role = unavailable_record.role
            return unavailable_response(
                unavailable_role,
                record=unavailable_record,
            )

        try:
            active_lease_ids = tuple(
                lease.lease_id
                for lease in await request.app.state.lifecycle.acquire_request_leases(
                    usage_request_id,
                    roles,
                    kind="active_request",
                    require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
                )
            )
        except LifecycleNotReadyError as error:
            record = error.record
            if record.state == "failed":
                finalize_request("model_unavailable", "failed")
                return unavailable_response(record.role, record=record)
            finalize_request(
                "model_loading",
                "failed",
                retryable_failure_class="model_loading",
            )
            return loading_response(record)

        try:
            continuation_owner = continuation_correlation(state_session_id)
            if has_matching_tool_result(raw["messages"]):
                request.app.state.lifecycle_store.release_continuation(
                    "executor", continuation_owner
                )
            state = request.app.state.controller.session(state_session_id, raw["messages"])
            task_id = task_id or state.task_id or state_session_id
            raw["metadata"]["task_id"] = task_id
            state.timings_ms = {"accepted": 0.0}
            request.app.state.store.event(
                state_session_id,
                "request_received",
                {"stream": body.stream, "task_id": task_id},
            )
            request.app.state.controller.select_route(state, raw["metadata"])
            if body.metadata.get("no_progress"):
                request.app.state.controller.note_no_progress(state)
            state.runtime_mode = mode
            state.request_class = request_class
            state.roles_required = list(roles)
            state.review_fail_closed = review_fails_closed(request_class)
            active_stage = "planner" if "planner" in roles else "request"
            prepared = await request.app.state.controller.prepare_executor(state, raw, roles)
            if "planner" in state.timings_ms:
                stage_status["planner"] = "completed"
            active_stage = "executor_first_byte" if body.stream else "executor_total"
            executor_started = time.monotonic()
            state.timings_ms["upstream_start"] = elapsed_ms(accepted)
            if body.stream:
                stream_lease_ids = tuple(
                    lease.lease_id
                    for lease in await request.app.state.lifecycle.acquire_request_leases(
                        usage_request_id,
                        ("executor",),
                        kind="open_stream",
                        require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
                    )
                )
                upstream = await request.app.state.provider.stream(
                    "executor",
                    configured.models["executor"],
                    prepared,
                    timeout_seconds=configured.limits.executor_first_byte_timeout_seconds,
                    stage="executor_first_byte",
                )
                state.timings_ms["first_upstream_byte"] = elapsed_ms(accepted)
                stage_status["executor_first_byte"] = "completed"
                observation = StreamObservation(configured.limits.max_stream_capture_bytes)
                stream_completed = False
                stream_cleanup_lock = asyncio.Lock()
                stream_cleaned = False

                async def finish_stream() -> None:
                    nonlocal stream_cleaned
                    async with stream_cleanup_lock:
                        if stream_cleaned:
                            return
                        stream_cleaned = True
                        terminal = stream_completed or observation.done_seen
                        state.timings_ms["executor_total"] = round(
                            (time.monotonic() - executor_started) * 1000, 3
                        )
                        stage_status.setdefault(
                            "executor_total", "completed" if terminal else "aborted"
                        )
                        terminal_status: RequestStatus = (
                            "completed"
                            if terminal
                            else "timed_out"
                            if stage_status.get("executor_total") == "timed_out"
                            else "failed"
                            if stage_status.get("executor_total") == "failed"
                            else "cancelled"
                        )
                        try:
                            state.finish_reasons = observation.finish_reasons
                            state.truncated = "length" in observation.finish_reasons
                            if terminal and "reviewer" in state.roles_required:
                                state.review_deferred = True
                                state.review_status = "deferred"
                                stage_status["reviewer"] = "deferred"
                            if state.decisions:
                                state.decisions[-1]["outcome"] = {
                                    "status": "success" if terminal else "failure",
                                    "progress_made": bool(observation.finish_reasons),
                                    "state_changed": False,
                                    "scope_changed": False,
                                    "validation_triggered": False,
                                    "next_phase": state.phase,
                                }
                            token_usage.update(observation.usage)
                            if terminal and "tool_calls" in observation.finish_reasons:
                                request.app.state.lifecycle_store.refresh_continuation(
                                    usage_request_id,
                                    "executor",
                                    continuation_owner,
                                    expires_at=(
                                        lifecycle_clock()
                                        + configured.limits.tool_continuation_timeout_seconds
                                    ),
                                )
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
                        finally:
                            try:
                                close = getattr(upstream, "aclose", None)
                                if close is not None:
                                    await close()
                            finally:
                                finalize_request(
                                    None,
                                    terminal_status,
                                    current_state=state,
                                    retryable_failure_class=(
                                        "executor_total_timeout"
                                        if terminal_status == "timed_out"
                                        else "backend_error"
                                        if terminal_status == "failed"
                                        else None
                                    ),
                                )

                async def stream_response() -> AsyncIterator[bytes]:
                    nonlocal first_byte_at, stream_completed
                    forwarder = forward_sse(
                        upstream,
                        observation,
                        max_event_bytes=configured.limits.max_sse_event_bytes,
                    )
                    try:
                        async with asyncio.timeout_at(
                            executor_started + configured.limits.executor_total_timeout_seconds
                        ):
                            async with aclosing(forwarder):
                                async for chunk in forwarder:
                                    if "first_downstream_byte" not in state.timings_ms:
                                        state.timings_ms["first_downstream_byte"] = elapsed_ms(
                                            accepted
                                        )
                                        first_byte_at = time.time()
                                    yield chunk
                        stream_completed = True
                    except TimeoutError as error:
                        stage_status["executor_total"] = "timed_out"
                        raise StageTimeout("executor_total") from error
                    except asyncio.CancelledError:
                        stage_status["executor_total"] = "cancelled"
                        if not observation.done_seen:
                            state.final_status = "cancelled"
                        raise
                    except Exception:
                        stage_status["executor_total"] = "failed"
                        raise
                    finally:
                        await finish_stream()

                return ResponseOwnedStreamingResponse(
                    ResponseOwnedIterator(stream_response(), finish_stream),
                    media_type="text/event-stream",
                    headers={"X-Session-ID": session_id},
                )
            response = await request.app.state.provider.complete(
                "executor",
                configured.models["executor"],
                prepared,
                timeout_seconds=configured.limits.executor_total_timeout_seconds,
                stage="executor_total",
            )
            state.timings_ms["first_upstream_byte"] = elapsed_ms(accepted)
            state.timings_ms["executor_total"] = round(
                (time.monotonic() - executor_started) * 1000, 3
            )
            stage_status["executor_total"] = "completed"
            token_usage.update(reported_usage(response.get("usage")))
            validate_assistant_response(response)
            assistant_message = response.get("choices", [{}])[0].get("message", {})
            if state.decisions:
                state.decisions[-1]["structured_decision"] = assistant_message
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
                active_stage = "reviewer"
                try:
                    async with request.app.state.reviewer_evaluation_lock:
                        reviewer = request.app.state.lifecycle_store.get("reviewer")
                        if reviewer.evaluation_guard:
                            raise ValueError("reviewer evaluation guard is already active")
                        guard_transition_id = reviewer.transition_id
                        request.app.state.lifecycle_store.set_guard(
                            "reviewer",
                            "evaluation_guard",
                            True,
                            expected_transition_id=guard_transition_id,
                        )
                        try:
                            await request.app.state.controller.review(state, review_observation)
                        finally:
                            request.app.state.lifecycle_store.set_guard(
                                "reviewer",
                                "evaluation_guard",
                                False,
                                expected_transition_id=guard_transition_id,
                            )
                except (httpx.HTTPError, StageTimeout, ValueError) as error:
                    state.review_status = "failed"
                    stage_status["reviewer"] = (
                        "timed_out" if isinstance(error, StageTimeout) else "failed"
                    )
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
                        if isinstance(error, StageTimeout):
                            raise
                        raise ValueError(f"review failed: {error}") from error
                else:
                    stage_status["reviewer"] = "completed"
                    if not state.truncated:
                        request.app.state.controller.apply_metadata(state, body.metadata)
            state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
            first_byte_at = time.time()
            request.app.state.store.event(
                state_session_id,
                "assistant_stream_finished",
                {"finish_reasons": [finish_reason] if finish_reason else []},
            )
            if finish_reason == "tool_calls" or assistant_message.get("tool_calls"):
                request.app.state.lifecycle_store.refresh_continuation(
                    usage_request_id,
                    "executor",
                    continuation_owner,
                    expires_at=(
                        lifecycle_clock() + configured.limits.tool_continuation_timeout_seconds
                    ),
                )
            finalize_request(None, "completed", current_state=state)
            return JSONResponse(response, headers={"X-Session-ID": session_id})
        except asyncio.CancelledError:
            current = state or request.app.state.store.get(state_session_id)
            if current is not None:
                current.final_status = "cancelled"
                if body.stream:
                    request.app.state.store.event(state_session_id, "stream_aborted", {})
            finalize_request(
                active_stage,
                "cancelled",
                downstream_started=False,
                current_state=current,
            )
            raise
        except DuplicateFailedCall as error:
            finalize_request(active_stage, "failed", downstream_started=True)
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except StageTimeout as error:
            finalize_request(
                error.stage,
                "timed_out",
                downstream_started=True,
                retryable_failure_class=TIMEOUT_FAILURE_CLASSES.get(error.stage),
            )
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                f"{error.stage}_timeout",
            )
        except httpx.TimeoutException as error:
            phase = state.phase.value if state is not None else ""
            stage = {
                "planning": "planner",
                "reviewing": "reviewer",
                "heavy_review": "judge",
            }.get(phase, "executor")
            finalize_request(
                active_stage,
                "timed_out",
                downstream_started=True,
                retryable_failure_class=TIMEOUT_FAILURE_CLASSES.get(stage),
            )
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                f"{stage}_timeout",
            )
        except httpx.HTTPStatusError as error:
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class=(
                    "backend_error" if error.response.status_code >= 500 else None
                ),
            )
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
                    upstream_error.get("param") is None or isinstance(upstream_error["param"], str)
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
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except ValueError as error:
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
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
        except Exception as error:
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )

    @app.get("/v1/admin/runtime-status", dependencies=[Depends(admin_auth)])
    async def admin_runtime_status(request: Request) -> dict[str, Any]:
        return await asyncio.to_thread(
            runtime_report,
            request.app.state.settings.state_db,
            request.app.state.project_root,
            lifecycle_mode=configured.lifecycle_mode,
            managed_roles=tuple(configured.lifecycle_unit_map),
        )

    @app.get("/admin/profile", response_model=ProfileResponse, dependencies=[Depends(admin_auth)])
    async def profile(request: Request) -> dict[str, str]:
        return dict(request.app.state.profiles.current())

    async def switch_profile(name: str, request: Request) -> dict[str, str]:
        guard_ownership: dict[str, str] = {}
        switch_task: asyncio.Task[Mapping[str, str]] | None = None
        try:
            if configured.lifecycle_mode in {"fixed", "adaptive"}:
                try:
                    guard_ownership = await request.app.state.lifecycle.claim_guards(
                        configured.lifecycle_unit_map,
                        "profile_guard",
                    )
                except Exception as error:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "lifecycle profile guard unavailable",
                    ) from error
            switch_task = asyncio.create_task(
                asyncio.to_thread(request.app.state.profiles.switch, name)
            )
            try:
                return dict(await asyncio.shield(switch_task))
            except asyncio.CancelledError:
                await switch_task
                raise
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        finally:
            if guard_ownership:
                try:
                    await request.app.state.lifecycle.release_guards(
                        guard_ownership,
                        "profile_guard",
                    )
                except Exception as error:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "lifecycle profile guard cleanup unavailable",
                    ) from error

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
