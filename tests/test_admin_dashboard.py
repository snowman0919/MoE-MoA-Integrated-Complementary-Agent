from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from fastapi.testclient import TestClient

from .conftest import StubProvider


def test_admin_dashboard_runs_bounded_custom_provider_codex(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    workspace = home / "code" / "project"
    workspace.mkdir(parents=True)
    (workspace / ".git").mkdir()
    configured = Settings.model_validate(
        settings.model_dump()
        | {
            "api_key": None,
            "api_keys": {
                "operator": "operator-secret-value",
                "general": "general-secret-value",
            },
            "admin_api_enabled": True,
            "admin_token_ids": ["operator"],
        }
    )
    calls: list[tuple[tuple[object, ...], dict[str, Any], bytes]] = []

    class Input:
        value = b""

        def write(self, value: bytes) -> None:
            self.value += value

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    class Output:
        def __init__(self) -> None:
            events = [
                {"type": "thread.started", "thread_id": "thread-123"},
                {
                    "type": "item.completed",
                    "item": {"type": "reasoning", "text": "hidden reasoning"},
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "echo api_key=secret-value",
                        "status": "completed",
                        "exit_code": 0,
                    },
                },
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "작업 완료"},
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                },
            ]
            self.lines = [(json.dumps(event) + "\n").encode() for event in events] + [b""]

        async def readline(self) -> bytes:
            return self.lines.pop(0)

    class Process:
        def __init__(self, args: tuple[object, ...], kwargs: dict[str, Any]) -> None:
            self.stdin = Input()
            self.stdout = Output()
            self.returncode: int | None = None
            calls.append((args, kwargs, self.stdin.value))

        async def wait(self) -> int:
            self.returncode = 0
            calls[-1] = (calls[-1][0], calls[-1][1], self.stdin.value)
            return 0

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

    async def create_subprocess_exec(*args: object, **kwargs: Any) -> Process:
        return Process(args, kwargs)

    monkeypatch.setattr("dgx_moa.admin_codex.Path.home", lambda: home)
    monkeypatch.setattr("dgx_moa.api.ModelProvider", lambda: StubProvider())
    monkeypatch.setattr(
        "dgx_moa.admin_codex.asyncio.create_subprocess_exec", create_subprocess_exec
    )
    with TestClient(create_app(configured), base_url="https://testserver") as client:
        general = {"Authorization": "Bearer general-secret-value"}
        operator = {"Authorization": "Bearer operator-secret-value"}

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert "/admin/api-keys" in dashboard.text
        assert "DGX MoA custom provider" in dashboard.text
        assert client.get("/v1/admin/codex/workspaces", headers=general).status_code == 403
        assert client.get("/v1/admin/codex/workspaces", headers=operator).json() == {
            "root": "~/code",
            "workspaces": ["project"],
        }
        assert (
            client.post(
                "/v1/admin/codex",
                headers=operator,
                json={"mode": "agent", "workspace": "../outside", "prompt": "work"},
            ).status_code
            == 400
        )

        response = client.post(
            "/v1/admin/codex",
            headers=operator,
            json={"mode": "agent", "workspace": "project", "prompt": "파일을 수정해"},
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert {event["type"] for event in events} == {
            "thread.started",
            "command",
            "message",
            "turn.completed",
        }
        assert "hidden reasoning" not in response.text
        assert "secret-value" not in response.text
        assert any(event.get("text") == "작업 완료" for event in events)
        internal = next(
            key
            for key in client.get("/v1/admin/api-keys", headers=operator).json()["keys"]
            if key["name"] == "admin-codex-cli"
        )
        assert internal["kind"] == "general"
        assert internal["request_limit"] == 10_000
        assert internal["token_limit"] == 100_000_000

        resumed = client.post(
            "/v1/admin/codex",
            headers=operator,
            json={
                "mode": "agent",
                "workspace": "project",
                "session_id": "thread-123",
                "prompt": "계속해",
            },
        )
        assert resumed.status_code == 200
        assert (
            client.post(
                "/v1/admin/codex",
                headers=operator,
                json={
                    "mode": "chat",
                    "session_id": "thread-123",
                    "prompt": "잘못된 재개",
                },
            ).status_code
            == 404
        )
        chat = client.post(
            "/v1/admin/codex",
            headers=operator,
            json={"mode": "chat", "prompt": "상태를 설명해"},
        )
        assert chat.status_code == 200

    first_args, first_kwargs, first_input = calls[0]
    assert first_args[:2] == ("codex", "exec")
    assert 'model_providers.dgx_moa_admin.wire_api="responses"' in first_args
    assert 'sandbox_mode="workspace-write"' in first_args
    assert "sandbox_workspace_write.network_access=false" in first_args
    assert 'shell_environment_policy.inherit="core"' in first_args
    assert first_kwargs["cwd"] == workspace
    assert first_kwargs["env"]["DGX_MOA_ADMIN_CODEX_KEY"] not in {
        "operator-secret-value",
        "general-secret-value",
    }
    assert first_kwargs["env"]["CODEX_HOME"] == str(configured.run_dir / "admin-codex-home")
    assert first_input == "파일을 수정해".encode()
    assert calls[1][0][:3] == ("codex", "exec", "resume")
    chat_args, chat_kwargs, chat_input = calls[2]
    assert 'sandbox_mode="read-only"' in chat_args
    assert "--skip-git-repo-check" in chat_args
    assert chat_kwargs["cwd"] == configured.run_dir / "admin-codex-chat"
    assert chat_input == "상태를 설명해".encode()
