from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from dgx_moa.security import (
    ADMIN_SESSION_SECONDS,
    ApiKeyRequest,
    ApiKeyStore,
    ApiKeyUpdate,
)
from dgx_moa.usage import RequestUsageStart, UsageStore
from fastapi.testclient import TestClient

from .conftest import StubProvider


def test_key_store_enforces_expiry_limits_admin_cap_and_file_mode(tmp_path: Path) -> None:
    now = [100.0]
    path = tmp_path / "state.db"
    usage = UsageStore(path)
    store = ApiKeyStore(
        path,
        {"operator": "operator-secret-value", "client": "client-secret-value"},
        admin_token_ids=("operator",),
        max_admin_keys=1,
        clock=lambda: now[0],
    )

    assert store.is_admin("operator")
    assert not store.is_admin("client")
    assert {item["api_key"] for item in store.list()} == {
        "operator-secret-value",
        "client-secret-value",
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="admin API key limit"):
        store.create(ApiKeyRequest(name="second-admin", kind="admin"))

    token, _ = store.create(
        ApiKeyRequest(name="limited", expires_in_days=1, request_limit=1, token_limit=10)
    )
    assert store.verify(token) == "limited"
    usage.start(
        RequestUsageStart(
            request_id="request-1",
            session_id="session-1",
            api_token_id="limited",
            client_class="curl",
            model_alias="dgx-moa-fast",
            runtime_mode="fast",
            request_class="plain_chat",
            roles_required=("executor",),
            accepted_at=100,
            streaming=False,
            model_state="warm",
        )
    )
    assert store.limit_error("limited") == "API key request limit reached"
    now[0] += 86_401
    assert store.verify(token) is None

    store.update("limited", ApiKeyUpdate(expires_in_days=2, request_limit=2))
    assert store.verify(token) == "limited"
    store.revoke("limited")
    assert store.verify(token) is None
    store.delete("limited")
    with pytest.raises(KeyError):
        store.get("limited")
    store.revoke("client")
    with pytest.raises(ValueError, match="environment API keys"):
        store.delete("client")
    session_token = store.create_admin_session("operator")
    assert store.verify_admin_session(session_token) == "operator"
    store.delete_admin_session(session_token)
    assert store.verify_admin_session(session_token) is None
    database_bytes = b"".join(file.read_bytes() for file in tmp_path.glob("state.db*"))
    assert token.encode() in database_bytes
    assert session_token.encode() not in database_bytes


def test_admin_key_api_separates_permissions_and_returns_no_store(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
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
            "max_admin_api_keys": 1,
        }
    )
    stub = StubProvider()
    monkeypatch.setattr("dgx_moa.api.ModelProvider", lambda: stub)
    with TestClient(create_app(configured), base_url="https://testserver") as client:
        general = {"Authorization": "Bearer general-secret-value"}
        operator = {"Authorization": "Bearer operator-secret-value"}

        assert client.get("/v1/admin/api-keys", headers=general).status_code == 403
        dashboard = client.get("/admin/api-keys")
        assert dashboard.status_code == 200
        assert dashboard.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in dashboard.headers["content-security-policy"]
        assert 'type="date"' in dashboard.text
        assert "navigator.clipboard" in dashboard.text
        assert "payload.error?.message" in dashboard.text
        assert "JSON.parse(text)" in dashboard.text
        assert "공란=무제한" in dashboard.text
        assert ".value.toLowerCase()" in dashboard.text
        assert all(
            name in dashboard.text for name in ("Qwen3-Next", "Nemotron-30B", "North-Mini-30B")
        )

        listing = client.get("/v1/admin/api-keys", headers=operator)
        assert listing.status_code == 200
        assert listing.headers["cache-control"] == "no-store"
        assert all("api_key" not in item for item in listing.json()["keys"])
        assert listing.json()["model_catalog"] == [
            {
                "role": role,
                "served_name": configured.models[role].served_name,
                "repository": configured.models[role].repository,
            }
            for role in ("executor", "planner", "reviewer")
        ]
        revealed = client.get("/v1/admin/api-keys/general/reveal", headers=operator)
        assert revealed.json()["api_key"] == "general-secret-value"
        session = client.post("/v1/admin/session", headers=operator)
        assert session.status_code == 204
        cookie = session.headers["set-cookie"]
        assert f"Max-Age={ADMIN_SESSION_SECONDS}" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Secure" in cookie
        assert "operator-secret-value" not in cookie
        assert client.get("/v1/admin/api-keys").status_code == 200

        created = client.post(
            "/v1/admin/api-keys",
            headers=operator,
            json={
                "name": "new-client",
                "kind": "general",
                "expires_in_days": 30,
                "request_limit": 10,
                "token_limit": 1_000,
            },
        )
        assert created.status_code == 200
        invalid = client.post(
            "/v1/admin/api-keys",
            headers=operator,
            json={"name": "Invalid Name", "kind": "general", "expires_in_days": 30},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["param"] == "name"
        new_token = created.json()["api_key"]
        assert (
            client.get("/v1/models", headers={"Authorization": f"Bearer {new_token}"}).status_code
            == 200
        )
        completion = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {new_token}"},
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "READY"}],
            },
        )
        assert completion.status_code == 200
        refreshed = client.get("/v1/admin/api-keys", headers=operator).json()
        assert any(
            item["name"] == "new-client" and item["request_class"] == "plain_chat"
            for item in refreshed["usage"]["tasks"]
        )
        assert any(
            item["name"] == "new-client" and item["role"] == "executor"
            for item in refreshed["usage"]["models"]
        )
        usage = client.get(
            "/v1/admin/api-keys/new-client/usage?start=1970-01-01&end=2999-12-31",
            headers=operator,
        )
        assert usage.status_code == 200
        assert {item["name"] for item in usage.json()["summary"]} == {"new-client"}
        assert {(item["name"], item["model"]) for item in usage.json()["daily_models"]} == {
            ("new-client", "executor")
        }
        assert (
            client.get(
                "/v1/admin/api-keys/new-client/usage?start=2026-07-24&end=2026-07-23",
                headers=operator,
            ).status_code
            == 400
        )
        cleared = client.post(
            "/v1/admin/api-keys/new-client/update",
            headers=operator,
            json={"request_limit": None, "token_limit": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["key"]["request_limit"] is None
        assert cleared.json()["key"]["token_limit"] is None
        assert (
            client.post(
                "/v1/admin/api-keys",
                headers=operator,
                json={"name": "another-admin", "kind": "admin", "expires_in_days": 30},
            ).status_code
            == 409
        )
        assert (
            client.post("/v1/admin/api-keys/operator/revoke", headers=operator).status_code == 409
        )
        assert client.delete("/v1/admin/api-keys/new-client", headers=operator).status_code == 409
        assert (
            client.post("/v1/admin/api-keys/new-client/revoke", headers=operator).status_code == 200
        )
        assert client.delete("/v1/admin/api-keys/new-client", headers=operator).status_code == 204
        assert client.delete("/v1/admin/api-keys/new-client", headers=operator).status_code == 404
        assert client.delete("/v1/admin/session").status_code == 204
        assert client.get("/v1/admin/api-keys").status_code == 401
        audit = client.app.state.store.events("api-key-admin")

    assert [event["payload"]["action"] for event in audit] == [
        "create",
        "update",
        "revoke",
        "delete",
    ]
    assert new_token not in json.dumps(audit)
