from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from dgx_moa.lifecycle import FakeLifecycleDriver
from fastapi.testclient import TestClient

from .conftest import StubProvider


class StubFlashExecutor:
    async def available(self) -> bool:
        return True

    async def execute(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return {
            "id": "flash-test",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Flash 처리 완료"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "provider_provenance": {
                "provider": "opencode_go",
                "model": "deepseek-v4-flash",
                "correlation_id": correlation_id,
            },
        }


def test_admin_dashboard_controls_executor_and_uses_flash_while_off(
    settings: Settings,
) -> None:
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
            "lifecycle_mode": "fixed",
            "lifecycle_unit_map": {"executor": "dgx-moa-dev-executor.service"},
            "executor_scheduling": {
                "enabled": True,
                "flash_provider": "opencode_go",
                "flash_endpoint": "https://opencode.invalid",
            },
        }
    )
    driver = FakeLifecycleDriver({"executor": "active"})
    app = create_app(
        configured,
        overflow_executor=StubFlashExecutor(),  # type: ignore[arg-type]
        lifecycle_driver=driver,
        lifecycle_health_probe=lambda role: asyncio.sleep(0, result=True),
        lifecycle_sleeper=lambda seconds: asyncio.Event().wait(),
        lifecycle_memory_probe=lambda: 1_000,
    )
    operator = {"Authorization": "Bearer operator-secret-value"}
    general = {"Authorization": "Bearer general-secret-value"}

    with TestClient(app) as client:
        assert "OFF · Flash 전환" in client.get("/admin").text
        assert client.get("/v1/admin/executor", headers=general).status_code == 403

        stopped = client.post("/v1/admin/executor/off", headers=operator)
        assert stopped.status_code == 200
        assert stopped.json()["operator_enabled"] is False
        assert stopped.json()["active_executor"] == "deepseek-v4-flash"
        assert stopped.json()["weight_load_percent"] is None
        assert driver.calls.count(("stop", "executor")) == 1

        fallback = client.post(
            "/v1/chat/completions",
            headers=general,
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "간단히 답해"}],
            },
        )
        assert fallback.status_code == 200
        assert fallback.json()["choices"][0]["message"]["content"] == "Flash 처리 완료"
        assert app.state.lifecycle_store.get("executor").state == "disabled"

        started = client.post("/v1/admin/executor/on", headers=operator)
        assert started.status_code == 200
        assert started.json()["operator_enabled"] is True
        for _ in range(100):
            current = client.get("/v1/admin/executor", headers=operator).json()
            if current["state"] == "ready":
                break
            time.sleep(0.01)
        assert current["state"] == "ready"
        assert current["weight_load_percent"] == 100.0
        assert driver.calls.count(("start", "executor")) == 1


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
            "run_dir": Path("data/run"),
        }
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DGX_MOA_ADMIN_CODEX_UNSANDBOXED", "true")
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
    assert "model_context_window=131072" in first_args
    assert not any("model_supports_reasoning_summaries" in str(arg) for arg in first_args)
    assert 'sandbox_mode="danger-full-access"' in first_args
    assert "sandbox_workspace_write.network_access=true" in first_args
    assert 'shell_environment_policy.inherit="core"' in first_args
    assert first_kwargs["cwd"] == workspace
    assert first_kwargs["env"]["DGX_MOA_ADMIN_CODEX_KEY"] not in {
        "operator-secret-value",
        "general-secret-value",
    }
    assert first_kwargs["env"]["CODEX_HOME"] == str(
        tmp_path / configured.run_dir / "admin-codex-home"
    )
    assert first_input == "파일을 수정해".encode()
    assert calls[1][0][:3] == ("codex", "exec", "resume")
    chat_args, chat_kwargs, chat_input = calls[2]
    assert 'sandbox_mode="read-only"' in chat_args
    assert "--skip-git-repo-check" in chat_args
    assert chat_kwargs["cwd"] == tmp_path / configured.run_dir / "admin-codex-chat"
    assert chat_input == "상태를 설명해".encode()
