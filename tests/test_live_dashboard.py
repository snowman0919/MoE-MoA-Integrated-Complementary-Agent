from __future__ import annotations

import asyncio

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
    _, own = hub.subscribe("key-a", operator=False)
    _, other = hub.subscribe("key-b", operator=False)
    subscriber_id, operator = hub.subscribe("operator", operator=True)

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

    _, replay = hub.subscribe("key-a", operator=False, last_seq=1)
    assert [replay.get_nowait()["seq"], replay.get_nowait()["seq"]] == [2, 3]
    _, stale = hub.subscribe("key-a", operator=False, last_seq=0)
    assert stale.get_nowait() == {"type": "RESYNC_REQUIRED"}
    _, ahead = hub.subscribe("key-a", operator=False, last_seq=99)
    assert ahead.get_nowait() == {"type": "RESYNC_REQUIRED"}

    _, operator = hub.subscribe("operator", operator=True, last_seq=2)
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
) -> None:
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
            "execution_graph": {"mode": "shadow"},
        }
    )
    app = create_app(controlled)
    with TestClient(app, base_url="https://testserver") as client:
        page = client.get("/dashboard")
        assert page.status_code == 200
        assert all(
            menu in page.text
            for menu in ("LIVE", "REQUESTS", "MODELS", "SYSTEM", "INCIDENTS", "EVALUATION", "AUDIT")
        )
        assert "new WebSocket" in page.text and "textContent" in page.text
        assert "last_seq" in page.text and "RESYNC_REQUIRED" in page.text
        assert "/v1/dashboard/snapshot" in page.text and "data-node-id" in page.text

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
        cookie = f"{DASHBOARD_SESSION_COOKIE}={client.cookies[DASHBOARD_SESSION_COOKIE]}"
        with client.websocket_connect(
            "/v1/dashboard/live", headers={"cookie": cookie}
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
        detail = client.get("/v1/dashboard/requests/session-a").json()
        assert detail["execution_graph"]["checkpoint"]["graph_id"] == runtime.graph.graph_id
        app.state.store.save(SessionState(session_id="session-b", api_token_id="key-b"))
        listing = client.get("/v1/dashboard/requests").json()
        assert listing["scope"] == "private"
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
            "/v1/dashboard/live", headers={"cookie": cookie}
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
        assert graph_aggregate["execution_graphs"] == {
            "graph_count": 1,
            "templates": {"simple-v1": 1},
            "terminal_statuses": {"running": 1},
            "active_nodes": 0,
            "pending_nodes": len(runtime.graph.nodes) - 1,
        }
        assert client.get("/v1/dashboard/requests/session-a").status_code == 400
        detail = client.get(
            "/v1/dashboard/requests/session-a",
            params={"reason": "incident secret=do-not-store"},
        )
        assert detail.status_code == 200
        audit = app.state.store.events("dashboard-audit")
        assert audit[-1]["payload"]["reason"] == "incident secret=[REDACTED]"

        with (
            pytest.raises(WebSocketDisconnect) as rejected,
            client.websocket_connect(
                "/v1/dashboard/live",
                headers={"origin": "https://evil.invalid", "cookie": cookie},
            ),
        ):
            pass
        assert rejected.value.code == 4403


def test_dashboard_is_disabled_by_default(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/dashboard").status_code == 404
