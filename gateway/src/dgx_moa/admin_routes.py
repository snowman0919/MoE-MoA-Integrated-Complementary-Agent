"""Administrative runtime, Codex, Frontier-auth, and API-key routes."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from .admin_codex import AdminCodexRequest, AdminCodexRunner
from .admin_dashboard import ADMIN_DASHBOARD
from .frontier import CodexOAuthProvider, profile_home, profile_lock, profile_status
from .key_dashboard import API_KEY_DASHBOARD
from .runtime_status import report as runtime_report
from .schemas import ProfileResponse
from .security import (
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_SECONDS,
    ApiKeyRequest,
    ApiKeyUpdate,
)


def build_admin_router(admin_auth: Callable[..., Any]) -> APIRouter:
    router = APIRouter()
    protected = [Depends(admin_auth)]

    def admin_html(content: str) -> HTMLResponse:
        return HTMLResponse(
            content,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                    "form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def key_response(payload: dict[str, Any]) -> JSONResponse:
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    def key_event(request: Request, action: str, name: str) -> None:
        request.app.state.store.event(
            "api-key-admin",
            "api_key_admin_action",
            {
                "action": action,
                "name": name,
                "operator": request.state.api_token_id,
            },
        )

    def frontier_auth_profile(
        profile: str,
        request: Request,
    ) -> tuple[Path, CodexOAuthProvider]:
        frontier_config = request.app.state.frontier_config
        if frontier_config is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Frontier is disabled")
        profiles = {frontier_config.primary_profile, frontier_config.secondary_profile}
        if profile not in profiles:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Frontier profile not found")
        root = frontier_config.profile_root
        home = profile_home(profile, root) if root is not None else profile_home(profile)
        return home, CodexOAuthProvider(profile, root)

    @router.get("/v1/admin/runtime-status", dependencies=protected)
    async def admin_runtime_status(request: Request) -> dict[str, Any]:
        settings = request.app.state.settings
        return await asyncio.to_thread(
            runtime_report,
            settings.state_db,
            request.app.state.project_root,
            lifecycle_mode=settings.lifecycle_mode,
            managed_roles=tuple(settings.lifecycle_unit_map),
        )

    @router.get("/v1/admin/drain", dependencies=protected)
    async def admin_drain_status(request: Request) -> dict[str, Any]:
        return {
            "draining": bool(request.app.state.draining),
            "active_request_count": request.app.state.usage.active_request_count(),
        }

    @router.post("/v1/admin/drain", dependencies=protected)
    async def admin_drain_start(request: Request) -> dict[str, Any]:
        request.app.state.draining = True
        request.app.state.store.event("runtime-drain", "gateway_drain_started", {})
        return await admin_drain_status(request)

    @router.delete("/v1/admin/drain", dependencies=protected)
    async def admin_drain_cancel(request: Request) -> dict[str, Any]:
        request.app.state.draining = False
        request.app.state.store.event("runtime-drain", "gateway_drain_cancelled", {})
        return await admin_drain_status(request)

    @router.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard() -> HTMLResponse:
        return admin_html(ADMIN_DASHBOARD)

    @router.get("/admin/api-keys", response_class=HTMLResponse)
    async def api_key_dashboard() -> HTMLResponse:
        return admin_html(API_KEY_DASHBOARD)

    @router.post("/v1/admin/session", dependencies=protected)
    async def api_key_session(request: Request) -> Response:
        token = request.app.state.api_keys.create_admin_session(request.state.api_token_id)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            token,
            max_age=ADMIN_SESSION_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
        )
        return response

    @router.delete("/v1/admin/session")
    async def api_key_session_delete(request: Request) -> Response:
        if token := request.cookies.get(ADMIN_SESSION_COOKIE):
            request.app.state.api_keys.delete_admin_session(token)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(ADMIN_SESSION_COOKIE, samesite="strict")
        return response

    @router.get("/v1/admin/codex/workspaces", dependencies=protected)
    async def admin_codex_workspaces(request: Request) -> JSONResponse:
        runner = cast(AdminCodexRunner, request.app.state.admin_codex)
        return key_response({"root": "~/code", "workspaces": runner.workspaces()})

    @router.post("/v1/admin/codex", dependencies=protected)
    async def admin_codex(body: AdminCodexRequest, request: Request) -> StreamingResponse:
        stream = await cast(AdminCodexRunner, request.app.state.admin_codex).start(body)
        return StreamingResponse(
            stream,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/v1/admin/api-keys", dependencies=protected)
    async def api_key_list(request: Request) -> JSONResponse:
        settings = request.app.state.settings
        model_catalog = [
            {
                "role": role,
                "served_name": settings.models[role].served_name,
                "repository": settings.models[role].repository,
            }
            for role in ("executor", "planner", "reviewer")
            if role in settings.models
        ]
        frontier_config = request.app.state.frontier_config
        if frontier_config is not None:
            model_catalog.append(
                {
                    "role": "frontier",
                    "served_name": frontier_config.model,
                    "repository": "Codex OAuth",
                }
            )
        return key_response(
            {
                "keys": [
                    {field: value for field, value in key.items() if field != "api_key"}
                    for key in request.app.state.api_keys.list()
                ],
                "usage": request.app.state.usage.api_token_dashboard(),
                "model_catalog": model_catalog,
                "max_admin_keys": settings.max_admin_api_keys,
            }
        )

    @router.get("/v1/admin/frontier-auth", dependencies=protected)
    async def frontier_auth_status(request: Request) -> JSONResponse:
        frontier_config = request.app.state.frontier_config
        if frontier_config is None:
            return key_response({"enabled": False, "profiles": []})
        root = frontier_config.profile_root
        profiles = dict.fromkeys(
            profile
            for profile in (frontier_config.primary_profile, frontier_config.secondary_profile)
            if profile is not None
        )
        return key_response(
            {
                "enabled": True,
                "model": frontier_config.model,
                "profiles": [
                    profile_status(profile, root) if root is not None else profile_status(profile)
                    for profile in profiles
                ],
            }
        )

    @router.post("/v1/admin/frontier-auth/{profile}", dependencies=protected)
    async def frontier_auth_login(profile: str, request: Request) -> StreamingResponse:
        home, provider = frontier_auth_profile(profile, request)
        active = request.app.state.frontier_auth_active
        if profile in active:
            raise HTTPException(status.HTTP_409_CONFLICT, "Frontier authentication already active")
        lock = profile_lock(profile, request.app.state.settings.run_dir)
        try:
            lock.__enter__()
        except RuntimeError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        active.add(profile)

        async def login_stream() -> AsyncIterator[bytes]:
            process: asyncio.subprocess.Process | None = None
            try:
                home.mkdir(parents=True, exist_ok=True, mode=0o700)
                home.chmod(0o700)
                process = await asyncio.create_subprocess_exec(
                    "codex",
                    "login",
                    "--device-auth",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=provider.environment(),
                )
                assert process.stdout is not None
                deadline = time.monotonic() + 16 * 60
                while time.monotonic() < deadline:
                    try:
                        chunk = await asyncio.wait_for(process.stdout.read(1024), timeout=10)
                    except TimeoutError:
                        yield b"\n"
                        continue
                    if not chunk:
                        break
                    text = chunk.decode(errors="replace")
                    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
                    text = "".join(
                        character
                        for character in text
                        if character in "\n\t" or ord(character) >= 32
                    )
                    yield text.encode()
                else:
                    process.terminate()
                    yield "\n인증 시간이 만료되었습니다. 다시 시도하세요.\n".encode()
                return_code = await process.wait()
                auth_file = home / "auth.json"
                if return_code == 0 and auth_file.is_file():
                    auth_file.chmod(0o600)
                yield (
                    "\n인증이 완료되었습니다.\n"
                    if return_code == 0
                    else "\n인증이 완료되지 않았습니다.\n"
                ).encode()
            finally:
                if process is not None and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except TimeoutError:
                        process.kill()
                active.discard(profile)
                lock.__exit__(None, None, None)

        return StreamingResponse(
            login_stream(),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/v1/admin/api-keys/{name}/reveal", dependencies=protected)
    async def api_key_reveal(name: str, request: Request) -> JSONResponse:
        try:
            record = request.app.state.api_keys.get(name)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found") from error
        return key_response({"api_key": record["api_key"]})

    @router.get("/v1/admin/api-keys/{name}/usage", dependencies=protected)
    async def api_key_usage(
        name: str,
        request: Request,
        start: date | None = None,
        end: date | None = None,
    ) -> JSONResponse:
        try:
            request.app.state.api_keys.get(name)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found") from error
        if start and end and end < start:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "end date must not precede start date")
        start_at = (
            datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp() if start else None
        )
        end_at = (
            datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()
            if end
            else None
        )
        return key_response(
            request.app.state.usage.api_token_dashboard(
                name=name,
                start_at=start_at,
                end_at=end_at,
            )
        )

    @router.post("/v1/admin/api-keys", dependencies=protected)
    async def api_key_create(payload: ApiKeyRequest, request: Request) -> JSONResponse:
        try:
            token, record = request.app.state.api_keys.create(payload)
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        key_event(request, "create", payload.name)
        return key_response({"api_key": token, "key": record})

    @router.post("/v1/admin/api-keys/{name}/rotate", dependencies=protected)
    async def api_key_rotate(
        name: str,
        payload: ApiKeyRequest,
        request: Request,
    ) -> JSONResponse:
        if payload.name != name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "key name does not match path")
        if name == request.state.api_token_id and payload.kind != "admin":
            raise HTTPException(status.HTTP_409_CONFLICT, "cannot demote the active admin key")
        try:
            token, record = request.app.state.api_keys.create(payload, replace=True)
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        key_event(request, "rotate", name)
        return key_response({"api_key": token, "key": record})

    @router.post("/v1/admin/api-keys/{name}/update", dependencies=protected)
    async def api_key_update(
        name: str,
        payload: ApiKeyUpdate,
        request: Request,
    ) -> JSONResponse:
        try:
            record = request.app.state.api_keys.update(name, payload)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found") from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        key_event(request, "update", name)
        return key_response({"key": record})

    @router.post("/v1/admin/api-keys/{name}/revoke", dependencies=protected)
    async def api_key_revoke(name: str, request: Request) -> JSONResponse:
        if name == request.state.api_token_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "cannot revoke the active admin key")
        try:
            record = request.app.state.api_keys.revoke(name)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found") from error
        key_event(request, "revoke", name)
        return key_response({"key": record})

    @router.delete("/v1/admin/api-keys/{name}", dependencies=protected)
    async def api_key_delete(name: str, request: Request) -> Response:
        try:
            request.app.state.api_keys.delete(name)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found") from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        key_event(request, "delete", name)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/admin/profile",
        response_model=ProfileResponse,
        dependencies=protected,
    )
    async def profile(request: Request) -> dict[str, str]:
        return dict(request.app.state.profiles.current())

    return router
