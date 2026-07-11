from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings, get_settings
from .controller import Controller, DuplicateFailedCall
from .profiles import ProfileManager
from .providers import ModelProvider, validate_assistant_response
from .schemas import ChatRequest, ProfileResponse
from .security import admin_dependency, auth_dependency
from .state import StateStore
from .trace import TraceRecorder


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
        roles = {"resident": ("executor", "planner", "reviewer"), "judge": ("judge",)}.get(
            current, ()
        )
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
                    "id": configured.model_name,
                    "object": "model",
                    "created": 0,
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    async def chat(
        body: ChatRequest,
        request: Request,
        x_session_id: str | None = Header(default=None),
    ) -> Response:
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
        if body.model != configured.model_name:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown model")
        if "executor" not in configured.models:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "executor is not configured")
        session_id = x_session_id or str(body.metadata.get("session_id") or uuid.uuid4())
        raw = body.model_dump(exclude_none=True)
        try:
            state = request.app.state.controller.session(session_id, raw["messages"])
            request.app.state.store.event(
                session_id,
                "request_received",
                {"stream": body.stream, "task_id": str(body.metadata.get("task_id", ""))},
            )
            request.app.state.controller.select_route(state, body.metadata)
            if body.metadata.get("no_progress"):
                request.app.state.controller.note_no_progress(state)
            prepared = await request.app.state.controller.prepare_executor(state, raw)
            if body.stream:
                request.app.state.traces.record(
                    state, task_id=str(body.metadata.get("task_id", ""))
                )

                async def stream_response() -> AsyncIterator[bytes]:
                    completed = False
                    try:
                        async for chunk in request.app.state.provider.stream(
                            "executor", configured.models["executor"], prepared
                        ):
                            yield chunk
                        completed = True
                    finally:
                        request.app.state.store.event(
                            session_id,
                            "stream_completed" if completed else "stream_aborted",
                            {},
                        )

                return StreamingResponse(
                    stream_response(),
                    media_type="text/event-stream",
                    headers={"X-Session-ID": session_id},
                )
            response = await request.app.state.provider.complete(
                "executor", configured.models["executor"], prepared
            )
            validate_assistant_response(response)
            if body.metadata.get("executor_complete") and "reviewer" in configured.models:
                await request.app.state.controller.review(state, str(response))
                request.app.state.controller.apply_metadata(state, body.metadata)
            request.app.state.traces.record(state, task_id=str(body.metadata.get("task_id", "")))
            return JSONResponse(response, headers={"X-Session-ID": session_id})
        except DuplicateFailedCall as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except httpx.TimeoutException as error:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(error)) from error
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

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
