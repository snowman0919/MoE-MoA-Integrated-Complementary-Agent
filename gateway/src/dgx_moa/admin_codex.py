from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from .config import Settings
from .security import ApiKeyRequest, ApiKeyStore, redact
from .state import StateStore


class AdminCodexRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    mode: Literal["chat", "agent"] = "chat"
    workspace: str = Field(default="", max_length=256)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")
    attachments: list[str] = Field(default_factory=list, max_length=10)


class AdminCodexRunner:
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024

    def __init__(self, settings: Settings, api_keys: ApiKeyStore, store: StateStore):
        self.settings = settings
        self.api_keys = api_keys
        self.store = store
        # ponytail: one global turn lock; add per-workspace locks only if concurrent jobs matter.
        self.lock = asyncio.Lock()
        self.sessions: dict[str, tuple[str, str]] = {}
        for event in store.events("admin-codex-sessions"):
            payload = event["payload"]
            thread_id = payload.get("thread_id")
            mode = payload.get("mode")
            workspace = payload.get("workspace")
            if (
                re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(thread_id))
                and mode in {"chat", "agent"}
                and isinstance(workspace, str)
            ):
                self.sessions[str(thread_id)] = (str(mode), workspace)

    @staticmethod
    def code_root() -> Path:
        return (Path.home() / "code").resolve()

    def workspaces(self) -> list[str]:
        root = self.code_root()
        if not root.is_dir():
            return []
        return sorted(
            resolved.relative_to(root).as_posix()
            for candidate in root.iterdir()
            if (resolved := candidate.resolve()).is_relative_to(root)
            and resolved.is_dir()
            and (resolved / ".git").exists()
        )

    def workspace(self, name: str) -> tuple[str, Path]:
        if not name or Path(name).is_absolute():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "select a workspace under ~/code")
        root = self.code_root()
        candidate = (root / name).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError as error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "workspace must remain under ~/code"
            ) from error
        if candidate == root or not candidate.is_dir() or not (candidate / ".git").exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Git workspace not found")
        return relative.as_posix(), candidate

    def provider_key(self) -> str:
        name = "admin-codex-cli"
        try:
            record = self.api_keys.get(name)
        except KeyError:
            token, _ = self.api_keys.create(
                ApiKeyRequest(
                    name=name,
                    kind="general",
                    expires_in_days=365,
                    request_limit=10_000,
                    token_limit=100_000_000,
                )
            )
            self.store.event("admin-codex", "admin_codex_key_created", {"kind": "general"})
            return str(token)
        if record["kind"] != "general" or record["status"] != "active":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "admin-codex-cli key must be an active general key",
            )
        return str(record["api_key"])

    def upload(self, filename: str, content: bytes) -> dict[str, Any]:
        if not filename or len(filename) > 255 or filename in {".", ".."}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid filename")
        if (
            "/" in filename
            or "\\" in filename
            or "\0" in filename
            or any(ord(character) < 32 for character in filename)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid filename")
        if len(content) > self.MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file exceeds 10 MB")
        upload_id = uuid.uuid4().hex
        directory = self.settings.run_dir.resolve() / "admin-codex-uploads" / upload_id
        directory.mkdir(parents=True, mode=0o700)
        path = directory / filename
        path.write_bytes(content)
        path.chmod(0o600)
        self.store.event(
            "admin-codex",
            "admin_codex_file_uploaded",
            {"name": filename, "bytes": len(content)},
        )
        return {"id": upload_id, "name": filename, "bytes": len(content)}

    def attachment_paths(self, attachment_ids: list[str]) -> list[Path]:
        root = (self.settings.run_dir.resolve() / "admin-codex-uploads").resolve()
        paths: list[Path] = []
        for upload_id in dict.fromkeys(attachment_ids):
            if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid attachment")
            directory = (root / upload_id).resolve()
            if not directory.is_relative_to(root) or not directory.is_dir():
                raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
            files = list(directory.iterdir())
            if len(files) != 1 or not files[0].is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
            path = files[0].resolve()
            if not path.is_relative_to(directory):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
            paths.append(path)
        return paths

    def command(self, body: AdminCodexRequest, workspace: Path) -> list[str]:
        sandbox = "workspace-write" if body.mode == "agent" else "read-only"
        provider = "dgx_moa_admin"
        base_url = f"http://127.0.0.1:{self.settings.bind_port}/v1"
        options = [
            "--json",
            "--strict-config",
            "--ignore-user-config",
            "-c",
            f"model={json.dumps(self.settings.model_name)}",
            "-c",
            "model_context_window=65536",
            "-c",
            'model_reasoning_effort="high"',
            "-c",
            'model_verbosity="low"',
            "-c",
            f"model_provider={json.dumps(provider)}",
            "-c",
            f"model_providers.{provider}.name={json.dumps('DGX MoA admin')}",
            "-c",
            f"model_providers.{provider}.base_url={json.dumps(base_url)}",
            "-c",
            f"model_providers.{provider}.env_key={json.dumps('DGX_MOA_ADMIN_CODEX_KEY')}",
            "-c",
            f"model_providers.{provider}.wire_api={json.dumps('responses')}",
            "-c",
            f"sandbox_mode={json.dumps(sandbox)}",
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            "allow_login_shell=false",
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            (
                'shell_environment_policy.include_only=["PATH","HOME","LANG","LC_ALL",'
                '"USER","LOGNAME"]'
            ),
        ]
        if body.mode == "chat":
            options.append("--skip-git-repo-check")
        if body.session_id is not None:
            return ["codex", "exec", "resume", *options, body.session_id, "-"]
        return ["codex", "exec", *options, "-C", str(workspace), "-"]

    @staticmethod
    def public_event(event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get("type")
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id", ""))
            if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_id):
                return {"type": event_type, "thread_id": thread_id}
        if event_type == "turn.started":
            return {"type": event_type}
        if event_type == "turn.completed":
            usage = (
                cast(dict[str, Any], event["usage"]) if isinstance(event.get("usage"), dict) else {}
            )
            return {
                "type": event_type,
                "usage": {
                    key: int(value)
                    for key in ("input_tokens", "cached_input_tokens", "output_tokens")
                    if isinstance((value := usage.get(key)), int) and not isinstance(value, bool)
                },
            }
        if event_type in {"error", "turn.failed"}:
            error = event.get("error", event.get("message", "Codex CLI failed"))
            return {"type": "error", "message": str(redact(error))[:1_000]}
        if event_type != "item.completed" or not isinstance(event.get("item"), dict):
            return None
        item = cast(dict[str, Any], event["item"])
        if item.get("type") == "agent_message":
            return {"type": "message", "text": str(redact(item.get("text", "")))[:100_000]}
        if item.get("type") == "command_execution":
            return {
                "type": "command",
                "command": str(redact(item.get("command", "")))[:1_000],
                "status": str(item.get("status", "completed")),
                "exit_code": item.get("exit_code"),
            }
        if item.get("type") == "file_change":
            return {"type": "file_change", "status": str(item.get("status", "completed"))}
        return None

    async def start(self, body: AdminCodexRequest) -> AsyncIterator[bytes]:
        if not body.prompt.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "prompt must not be blank")
        run_dir = self.settings.run_dir.resolve()
        if body.mode == "agent":
            workspace_name, workspace = self.workspace(body.workspace)
        else:
            workspace_name = ""
            workspace = run_dir / "admin-codex-chat"
            workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        if body.session_id is not None and self.sessions.get(body.session_id) != (
            body.mode,
            workspace_name,
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Codex session not found")
        if self.lock.locked():
            raise HTTPException(status.HTTP_409_CONFLICT, "another Codex turn is active")
        attachment_paths = self.attachment_paths(body.attachments)
        prompt = body.prompt
        if attachment_paths:
            prompt += "\n\nOperator-uploaded files (read these paths as needed):\n" + "\n".join(
                f"- {path}" for path in attachment_paths
            )
        await self.lock.acquire()
        try:
            token = self.provider_key()
            codex_home = run_dir / "admin-codex-home"
            codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
            codex_home.chmod(0o700)
            command = self.command(body, workspace)
        except Exception:
            self.lock.release()
            raise
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "TERM", "USER"}
        }
        environment.update({"CODEX_HOME": str(codex_home), "DGX_MOA_ADMIN_CODEX_KEY": token})
        return self._stream(body, prompt, workspace_name, workspace, command, environment)

    async def _stream(
        self,
        body: AdminCodexRequest,
        prompt: str,
        workspace_name: str,
        workspace: Path,
        command: list[str],
        environment: dict[str, str],
    ) -> AsyncIterator[bytes]:
        process: asyncio.subprocess.Process | None = None
        completed = False
        self.store.event(
            "admin-codex",
            "admin_codex_turn_started",
            {"mode": body.mode, "resumed": body.session_id is not None},
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace,
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=1_000_000,
            )
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()
            deadline = time.monotonic() + 30 * 60
            while time.monotonic() < deadline:
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=15)
                except TimeoutError:
                    yield b'{"type":"heartbeat"}\n'
                    continue
                if not line:
                    break
                public: dict[str, Any] | None
                try:
                    event = json.loads(line)
                except ValueError:
                    public = {
                        "type": "error",
                        "message": str(redact(line.decode(errors="replace")))[:1_000],
                    }
                else:
                    public = self.public_event(event) if isinstance(event, dict) else None
                if public is None:
                    continue
                if public.get("type") == "thread.started":
                    thread_id = str(public["thread_id"])
                    if self.sessions.get(thread_id) != (body.mode, workspace_name):
                        self.sessions[thread_id] = (body.mode, workspace_name)
                        self.store.event(
                            "admin-codex-sessions",
                            "admin_codex_session_saved",
                            {
                                "thread_id": thread_id,
                                "mode": body.mode,
                                "workspace": workspace_name,
                            },
                        )
                if public.get("type") == "turn.completed":
                    completed = True
                yield (
                    json.dumps(public, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode()
            else:
                process.terminate()
                yield b'{"type":"error","message":"Codex turn timed out"}\n'
            return_code = await process.wait()
            if return_code != 0 and not completed:
                yield (
                    json.dumps(
                        {"type": "error", "message": f"Codex CLI exited {return_code}"},
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode()
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
            self.store.event(
                "admin-codex",
                "admin_codex_turn_completed" if completed else "admin_codex_turn_failed",
                {"mode": body.mode},
            )
            self.lock.release()
