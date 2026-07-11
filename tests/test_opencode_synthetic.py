from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from dgx_moa.api import create_app
from fastapi.testclient import TestClient

from .conftest import StubProvider


@contextmanager
def synthetic_client(settings, provider: StubProvider) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider = provider
        app.state.controller.provider = provider
        yield client


def request(session: str, messages: list[dict], metadata: dict, *, stream: bool = False) -> dict:  # type: ignore[type-arg]
    return {
        "model": "dgx-moa-agent",
        "stream": stream,
        "messages": messages,
        "metadata": metadata,
    }


def tool_call(call_id: str, command: str) -> dict:  # type: ignore[type-arg]
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "shell", "arguments": f'{{"cmd":"{command}"}}'},
            }
        ],
    }


def tool_result(call_id: str, command: str, exit_code: int) -> dict:  # type: ignore[type-arg]
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": (
            '{"tool_name":"shell","arguments":{"cmd":"'
            + command
            + f'"}},"stdout":"","stderr":"","exit_code":{exit_code},'
            '"duration_ms":1,"truncated":false}'
        ),
    }


def test_synthetic_opencode_all_mvp_shapes(settings) -> None:  # type: ignore[no-untyped-def]
    headers = {"Authorization": "Bearer test-secret"}
    provider = StubProvider()
    with synthetic_client(settings, provider) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/models", headers=headers).status_code == 200
        for task_id, metadata in (
            ("read-only", {"target_clear": True, "expected_files": 1}),
            ("one-file", {"target_clear": True, "expected_files": 1, "validation_command": "true"}),
            ("multi-file", {"expected_files": 3, "validation_command": "pytest -q"}),
        ):
            response = client.post(
                "/v1/chat/completions",
                headers=headers | {"X-Session-ID": task_id},
                json=request(task_id, [{"role": "user", "content": task_id}], metadata),
            )
            assert response.status_code == 200
            call = response.json()["choices"][0]["message"]["tool_calls"][0]
            assert call["id"] and call["function"]["arguments"]
            assert response.json()["usage"]["total_tokens"] == 3

        failed = client.post(
            "/v1/chat/completions",
            headers=headers | {"X-Session-ID": "recovery"},
            json=request(
                "recovery",
                [
                    {"role": "user", "content": "recover"},
                    tool_call("failed", "false"),
                    tool_result("failed", "false", 1),
                ],
                {"expected_files": 3},
            ),
        )
        assert failed.status_code == 200
        recovered = client.post(
            "/v1/chat/completions",
            headers=headers | {"X-Session-ID": "recovery"},
            json=request(
                "recovery",
                [
                    {"role": "user", "content": "recover"},
                    tool_call("recovered", "pwd"),
                    tool_result("recovered", "pwd", 0),
                ],
                {"expected_files": 3},
            ),
        )
        assert recovered.status_code == 200

        original = provider.complete
        reviews = 0

        async def reject_once(role, model, body):  # type: ignore[no-untyped-def]
            nonlocal reviews
            if role == "reviewer":
                reviews += 1
                if reviews == 1:
                    return {
                        "choices": [
                            {"message": {"content": '{"status":"rejected","findings":["fix"]}'}}
                        ]
                    }
            return await original(role, model, body)

        provider.complete = reject_once  # type: ignore[method-assign]
        for message in ("first", "corrected"):
            response = client.post(
                "/v1/chat/completions",
                headers=headers | {"X-Session-ID": "review-correction"},
                json=request(
                    "review-correction",
                    [{"role": "user", "content": message}],
                    {
                        "expected_files": 3,
                        "executor_complete": True,
                        "completion_evidence": {"tests": "0"},
                    },
                ),
            )
            assert response.status_code == 200
        assert client.app.state.store.get("review-correction").review_status == "approved"

        streamed = client.post(
            "/v1/chat/completions",
            headers=headers | {"X-Session-ID": "stream"},
            json=request(
                "stream",
                [{"role": "user", "content": "stream"}],
                {"target_clear": True},
                stream=True,
            ),
        )
        assert "data: [DONE]" in streamed.text

    with synthetic_client(settings, StubProvider()) as restarted:
        recovered = restarted.app.state.store.get("recovery")
        assert recovered is not None and len(recovered.tool_results) == 2
