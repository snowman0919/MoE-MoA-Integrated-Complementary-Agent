from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from dgx_moa.execution_graph import (
    ExecutionGraphRuntime,
    GraphCompileInput,
    SchedulingSnapshot,
    compile_execution_graph,
)
from dgx_moa.live_dashboard import LiveDashboardHub
from dgx_moa.security import DASHBOARD_SESSION_COOKIE, DASHBOARD_SESSION_SECONDS
from dgx_moa.state import SessionState
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_live_dashboard_isolates_keys_and_redacts_operator_stream() -> None:
    owners = {"session-a": "key-a", "session-b": "key-b"}
    hub = LiveDashboardHub(owners.get, queue_size=1)
    _, own, _ = hub.subscribe("key-a", operator=False)
    _, other, _ = hub.subscribe("key-b", operator=False)
    subscriber_id, operator, _ = hub.subscribe("operator", operator=True)

    hub.publish(
        "session-a",
        "executor_scheduled",
        {
            "api_key_id": "key-a",
            "lease_owner_api_key_id": "key-b",
            "provider": "opencode_go",
            "prompt": "private prompt",
            "authorization": "Bearer secret-value",
        },
        "2026-08-08T00:00:00+00:00",
    )
    await asyncio.sleep(0)

    own_event = own.get_nowait()
    assert own_event["seq"] == 1
    assert own_event["session_id"] == "session-a"
    assert own_event["payload"]["lease_owner_api_key_id"] == "other"
    assert "secret-value" not in str(own_event)
    assert other.empty()
    operator_event = operator.get_nowait()
    assert operator_event["api_key_id"] == "key-a"
    assert operator_event["payload"] == {"provider": "opencode_go"}

    hub.publish("session-a", "first", {}, "2026-08-08T00:00:01+00:00")
    hub.publish("session-a", "second", {}, "2026-08-08T00:00:02+00:00")
    await asyncio.sleep(0)
    assert operator.get_nowait()["gap"] is True
    hub.unsubscribe(subscriber_id)


@pytest.mark.asyncio
async def test_live_dashboard_replays_bounded_graph_events_or_requires_resync() -> None:
    hub = LiveDashboardHub(lambda _: None, queue_size=4, replay_size=2)
    for index in range(3):
        hub.publish_graph(
            "node_attempt",
            "graph-private",
            "key-a",
            "request-private",
            {"attempt_id": f"attempt-{index}", "role": "executor", "state": "RUNNING"},
            f"2026-08-08T00:00:0{index}+00:00",
        )

    _, replay, _ = hub.subscribe("key-a", operator=False, last_seq=1)
    assert [replay.get_nowait()["seq"], replay.get_nowait()["seq"]] == [2, 3]
    _, stale, _ = hub.subscribe("key-a", operator=False, last_seq=0)
    assert stale.get_nowait() == {"type": "RESYNC_REQUIRED"}
    _, ahead, _ = hub.subscribe("key-a", operator=False, last_seq=99)
    assert ahead.get_nowait() == {"type": "RESYNC_REQUIRED"}

    _, operator, _ = hub.subscribe("operator", operator=True, last_seq=2)
    operator_event = operator.get_nowait()
    assert operator_event["seq"] == 3
    assert "graph_id" not in operator_event and "request_id" not in operator_event
    assert operator_event["payload"] == {
        "attempt_id": "attempt-2",
        "role": "executor",
        "state": "RUNNING",
    }


def graph_request() -> GraphCompileInput:
    return GraphCompileInput(
        request_id="request-graph-live",
        api_key_id="key-a",
        objective="project persisted execution graph",
        request_class="native_agent_turn",
        complexity="simple",
        risk="low",
        policy_version="dashboard-test-v1",
        policy_hash="0" * 64,
        deadline="2099-01-01T00:00:00+00:00",
        scheduling=SchedulingSnapshot(selected_executor="local_mistral"),
    )


def test_dashboard_websocket_uses_cookie_scope_and_operator_aggregate(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = {
        "measured_at": "2026-08-12T00:00:00+00:00",
        "retention": {
            "minimum_days": 90,
            "automatic_purge": False,
            "basis": "durable_store_without_automatic_deletion",
        },
        "hosts": {"gb10": {"status": "available"}, "mathcat": {"status": "available"}},
    }
    frontier_config = settings.state_db.parent / "frontier.yaml"
    frontier_config.write_text(
        "enabled: true\nmodel: gpt-5.6-sol\nreasoning_effort: xhigh\nprimary_profile: primary\n"
    )
    monkeypatch.setattr("dgx_moa.api.dashboard_telemetry", lambda: telemetry)
    controlled = Settings.model_validate(
        settings.model_dump()
        | {
            "api_key": None,
            "api_keys": {
                "operator": "operator-secret-value",
                "key-a": "key-a-secret-value",
                "key-b": "key-b-secret-value",
            },
            "admin_token_ids": ["operator"],
            "dashboard_enabled": True,
            "frontier_enabled": True,
            "frontier_config": frontier_config,
            "execution_graph": {"mode": "shadow"},
        }
    )
    app = create_app(controlled)
    with TestClient(app) as insecure_client:
        response = insecure_client.get("/dashboard")
        assert response.status_code == 200
    with TestClient(app, base_url="https://testserver") as client:
        page = client.get("/dashboard")
        assert page.status_code == 200
        assert all(
            menu in page.text
            for menu in ("LIVE", "REQUESTS", "MODELS", "SYSTEM", "INCIDENTS", "EVALUATION", "AUDIT")
        )
        assert all(
            inspector in page.text
            for inspector in ("SUMMARY", "PROMPT", "OUTPUT", "EVIDENCE", "EXECUTION", "LOGS")
        )
        assert "Audited cross-key request inspector" in page.text
        assert "innerHTML" not in page.text
        assert "new WebSocket" in page.text and "textContent" in page.text
        assert "last_seq" in page.text and "RESYNC_REQUIRED" in page.text
        assert "/v1/dashboard/snapshot" in page.text and "dataset.nodeId" in page.text
        assert "Static Graph Skeleton" in page.text
        assert "runtime-created request subgraph" in page.text
        assert "availability_basis" in page.text
        assert "Runtime-owned canonical evidence" in page.text
        assert "role_context_projections" in page.text
        assert "independent_judgments" in page.text
        assert "final_output" in page.text

        session = client.post(
            "/v1/dashboard/session",
            headers={"Authorization": "Bearer key-a-secret-value"},
        )
        assert session.status_code == 204
        assert f"Max-Age={DASHBOARD_SESSION_SECONDS}" in session.headers["set-cookie"]
        assert "HttpOnly" in session.headers["set-cookie"]
        assert client.get("/v1/dashboard/me").json() == {
            "api_key_id": "key-a",
            "operator": False,
        }
        assert client.get("/v1/dashboard/runtime").json() == telemetry
        cookie = f"{DASHBOARD_SESSION_COOKIE}={client.cookies[DASHBOARD_SESSION_COOKIE]}"
        with client.websocket_connect(
            "wss://testserver/v1/dashboard/live", headers={"cookie": cookie}
        ) as websocket:
            assert websocket.receive_json()["scope"] == "private"
            graph_store = app.state.controller.execution_graph_store
            runtime = ExecutionGraphRuntime(compile_execution_graph(graph_request()), graph_store)
            graph_event = websocket.receive_json()
            assert graph_event["type"] == "execution_graph"
            assert graph_event["event_type"] == "graph_saved"
            assert graph_event["graph_id"] == runtime.graph.graph_id
            assert graph_event["request_id"] == "request-graph-live"
            attempt = runtime.start_attempt(runtime.graph.entry_nodes[0])
            node_event = websocket.receive_json()
            checkpoint_event = websocket.receive_json()
            assert node_event["event_type"] == "node_attempt"
            assert node_event["payload"]["attempt_id"] == attempt.attempt_id
            assert checkpoint_event["event_type"] == "graph_checkpoint"
            app.state.store.save(SessionState(session_id="session-a", api_token_id="key-a"))
            app.state.store.event(
                "session-a",
                "assistant_output",
                {
                    "output": "private output",
                    "lease_owner_api_key_id": "key-b",
                },
            )
            event = websocket.receive_json()
            assert event["session_id"] == "session-a"
            assert event["payload"] == {
                "output": "private output",
                "lease_owner_api_key_id": "other",
            }
        state = app.state.store.get("session-a")
        assert state is not None
        state.execution_graph_mode = "shadow"
        state.execution_graph_id = runtime.graph.graph_id
        app.state.store.save(state)
        snapshot = client.get("/v1/dashboard/snapshot").json()
        assert snapshot["scope"] == "private"
        assert snapshot["execution_graphs"][0]["graph"]["graph_id"] == runtime.graph.graph_id
        assert snapshot["execution_graphs"][0]["attempts"][0]["attempt_id"] == attempt.attempt_id
        assert [item["role"] for item in snapshot["topology"]["roles"]] == [
            "Reasoner",
            "Planner",
            "Frontier A",
            "Executor",
            "Reviewer",
            "Judge",
            "Frontier B",
        ]
        frontier_a = snapshot["topology"]["roles"][2]
        assert frontier_a["model"] == "gpt-5.6-sol"
        assert frontier_a["reasoning_effort"] == "xhigh"
        assert snapshot["topology"]["graph"] == {
            "mode": "shadow",
            "structure": "static_skeleton+runtime_created_request_subgraph",
            "static_templates": [
                "simple-v1",
                "engineering-v1",
                "complex-v1",
                "critical-v1",
            ],
            "runtime_authority": "deterministic_execution_graph_compiler",
            "runtime_mutation": False,
        }
        detail = client.get("/v1/dashboard/requests/session-a").json()
        assert detail["execution_graph"]["checkpoint"]["graph_id"] == runtime.graph.graph_id
        app.state.store.save(SessionState(session_id="session-b", api_token_id="key-b"))
        listing = client.get("/v1/dashboard/requests").json()
        assert listing["scope"] == "private"
        assert listing["usage"] == {
            "summary": [],
            "tasks": [],
            "models": [],
            "daily": [],
            "daily_models": [],
            "fallback_summary": [],
            "fallbacks": [],
        }
        assert [item["session_id"] for item in listing["requests"]] == ["session-a"]
        assert client.get("/v1/dashboard/requests/session-a").status_code == 200
        assert client.get("/v1/dashboard/requests/session-b").status_code == 404

        client.delete("/v1/dashboard/session")
        client.post(
            "/v1/dashboard/session",
            headers={"Authorization": "Bearer operator-secret-value"},
        )
        cookie = f"{DASHBOARD_SESSION_COOKIE}={client.cookies[DASHBOARD_SESSION_COOKIE]}"
        with client.websocket_connect(
            "wss://testserver/v1/dashboard/live", headers={"cookie": cookie}
        ) as websocket:
            assert websocket.receive_json()["scope"] == "operator_aggregate"
            runtime.finish_attempt(attempt.attempt_id, latency_ms=4.0, cost_usd=0.01)
            graph_event = websocket.receive_json()
            graph_checkpoint = websocket.receive_json()
            assert graph_event["type"] == "execution_graph"
            assert graph_event["payload"]["state"] == "SUCCEEDED"
            assert graph_event["payload"]["latency_ms"] == 4.0
            assert "graph_id" not in graph_event and "request_id" not in graph_event
            assert graph_checkpoint["event_type"] == "graph_checkpoint"
            app.state.store.event(
                "session-a",
                "executor_started",
                {"provider": "local", "prompt": "private prompt"},
            )
            event = websocket.receive_json()
            assert "session_id" not in event
            assert event["api_key_id"] == "key-a"
            assert event["payload"] == {"provider": "local"}
        aggregate = client.get("/v1/dashboard/requests").json()
        assert aggregate["scope"] == "operator_aggregate"
        assert "requests" not in aggregate
        graph_aggregate = client.get("/v1/dashboard/snapshot").json()
        assert len(graph_aggregate["topology"]["roles"]) == 7
        assert graph_aggregate["execution_graphs"] == {
            "graph_count": 1,
            "templates": {"simple-v1": 1},
            "terminal_statuses": {"running": 1},
            "active_nodes": 0,
            "pending_nodes": len(runtime.graph.nodes) - 1,
        }
        assert client.get("/v1/dashboard/requests/session-a").status_code == 400
        detail = client.post(
            "/v1/dashboard/requests/session-a",
            json={"reason": "incident secret=do-not-store"},
        )
        assert detail.status_code == 200
        audit = app.state.store.events("dashboard-audit")
        assert audit[-1]["payload"]["reason"] == "incident secret=[REDACTED]"

        with (
            pytest.raises(WebSocketDisconnect) as rejected,
            client.websocket_connect(
                "wss://testserver/v1/dashboard/live",
                headers={"origin": "https://evil.invalid", "cookie": cookie},
            ),
        ):
            pass
        assert rejected.value.code == 4403


def test_dashboard_is_disabled_by_default(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/dashboard").status_code == 404


def test_dashboard_projects_stream_output_and_terminal_status(
    settings: Settings, stub_provider: Any
) -> None:
    controlled = settings.model_copy(update={"dashboard_enabled": True})
    app = create_app(controlled)
    with TestClient(app, base_url="https://testserver") as client:
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "dashboard-output",
            },
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "Return ok"}],
                "stream": True,
            },
        ) as response:
            assert response.status_code == 200
            assert b'"content":"ok"' in response.read()

        session = client.post(
            "/v1/dashboard/session",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert session.status_code == 204
        detail = client.get("/v1/dashboard/requests/dashboard-output").json()

        async def final_complete(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "final answer"},
                        "finish_reason": "stop",
                    }
                ]
            }

        stub_provider.complete = final_complete
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-secret",
                "X-Session-ID": "dashboard-final-output",
            },
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "Return a final answer"}],
            },
        )
        assert response.status_code == 200
        final_detail = client.get("/v1/dashboard/requests/dashboard-final-output").json()

    assert detail["state"]["current_draft"] == "ok"
    assert detail["state"]["final_output"] == "ok"
    assert detail["state"]["client_response_status"] == "completed"
    assert detail["state"]["final_status"] is None
    output_events = [
        item for item in detail["events"] if item["event_type"] == "assistant_output_delta"
    ]
    assert output_events == [
        {
            "event_type": "assistant_output_delta",
            "payload": {"role": "executor", "delta": "ok"},
            "created_at": output_events[0]["created_at"],
        }
    ]
    assert final_detail["state"]["final_output"] == "final answer"
    assert final_detail["state"]["client_response_status"] == "completed"
    assert [
        item["payload"]
        for item in final_detail["events"]
        if item["event_type"] == "assistant_output"
    ] == [{"role": "executor", "output": "final answer"}]
