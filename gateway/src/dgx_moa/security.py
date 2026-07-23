from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Literal

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .config import Settings

SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b(?:hf|sk)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bmoa_[A-Za-z0-9_-]{32,}\b"),
)
TOKEN_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class ApiKeyRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    kind: Literal["general", "admin"] = "general"
    expires_in_days: int = Field(default=90, ge=1, le=365)
    request_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)


class ApiKeyUpdate(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    request_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)


class ApiKeyStore:
    def __init__(
        self,
        path: str | Path,
        configured: dict[str, str],
        *,
        admin_token_ids: tuple[str, ...] = ("operator",),
        max_admin_keys: int = 3,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self.max_admin_keys = max_admin_keys
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS api_keys ("
                "name TEXT PRIMARY KEY, token TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, "
                "kind TEXT NOT NULL, source TEXT NOT NULL, created_at REAL NOT NULL, "
                "expires_at REAL, revoked_at REAL, request_limit INTEGER, token_limit INTEGER)"
            )
            for name, token in configured.items():
                digest = self._digest(token)
                row = database.execute(
                    "SELECT token_hash, source FROM api_keys WHERE name = ?", (name,)
                ).fetchone()
                if row is None:
                    database.execute(
                        "INSERT INTO api_keys VALUES (?, ?, ?, ?, 'environment', ?, NULL, "
                        "NULL, NULL, NULL)",
                        (
                            name,
                            token,
                            digest,
                            "admin" if name in admin_token_ids else "general",
                            self.clock(),
                        ),
                    )
                elif row["source"] == "environment":
                    database.execute(
                        "UPDATE api_keys SET kind = ? WHERE name = ?",
                        ("admin" if name in admin_token_ids else "general", name),
                    )
                    if row["token_hash"] != digest:
                        database.execute(
                            "UPDATE api_keys SET token = ?, token_hash = ?, "
                            "created_at = ?, expires_at = NULL, revoked_at = NULL WHERE name = ?",
                            (token, digest, self.clock(), name),
                        )
            admin_count = database.execute(
                "SELECT COUNT(*) FROM api_keys WHERE kind = 'admin' AND revoked_at IS NULL "
                "AND (expires_at IS NULL OR expires_at > ?)",
                (self.clock(),),
            ).fetchone()[0]
            if admin_count > self.max_admin_keys:
                raise ValueError("configured admin API keys exceed the limit")
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=30)
        database.row_factory = sqlite3.Row
        return database

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def verify(self, token: str) -> str | None:
        digest = self._digest(token)
        with self._connect() as database:
            row = database.execute(
                "SELECT name, token_hash, expires_at, revoked_at FROM api_keys "
                "WHERE token_hash = ?",
                (digest,),
            ).fetchone()
        if (
            row is None
            or not secrets.compare_digest(digest, row["token_hash"])
            or row["revoked_at"] is not None
            or (row["expires_at"] is not None and row["expires_at"] <= self.clock())
        ):
            return None
        return str(row["name"])

    def limit_error(self, name: str) -> str | None:
        with self._connect() as database:
            key = database.execute(
                "SELECT request_limit, token_limit FROM api_keys WHERE name = ?", (name,)
            ).fetchone()
            usage = database.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0) FROM request_usage "
                "WHERE api_token_id = ?",
                (name,),
            ).fetchone()
        if key is None:
            return "unknown API key"
        if key["request_limit"] is not None and usage[0] >= key["request_limit"]:
            return "API key request limit reached"
        if key["token_limit"] is not None and usage[1] >= key["token_limit"]:
            return "API key token limit reached"
        return None

    def is_admin(self, name: str) -> bool:
        with self._connect() as database:
            row = database.execute("SELECT kind FROM api_keys WHERE name = ?", (name,)).fetchone()
        return bool(row and row["kind"] == "admin")

    def create(
        self,
        request: ApiKeyRequest,
        *,
        replace: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        name = request.name
        if not TOKEN_ID.fullmatch(name):
            raise ValueError("invalid API key name")
        token = "moa_" + secrets.token_urlsafe(32)
        now = self.clock()
        expires_at = now + request.expires_in_days * 86_400
        with self._connect() as database:
            exists = database.execute(
                "SELECT kind, expires_at, revoked_at FROM api_keys WHERE name = ?", (name,)
            ).fetchone()
            if exists and not replace:
                raise ValueError("API key name already exists")
            existing_admin_active = bool(
                exists
                and exists["kind"] == "admin"
                and exists["revoked_at"] is None
                and (exists["expires_at"] is None or exists["expires_at"] > now)
            )
            if request.kind == "admin" and not existing_admin_active:
                admin_count = database.execute(
                    "SELECT COUNT(*) FROM api_keys WHERE kind = 'admin' AND revoked_at IS NULL "
                    "AND (expires_at IS NULL OR expires_at > ?)",
                    (now,),
                ).fetchone()[0]
                if admin_count >= self.max_admin_keys:
                    raise ValueError("admin API key limit reached")
            if exists:
                database.execute(
                    "UPDATE api_keys SET token = ?, token_hash = ?, kind = ?, source = 'managed', "
                    "created_at = ?, expires_at = ?, revoked_at = NULL, request_limit = ?, "
                    "token_limit = ? WHERE name = ?",
                    (
                        token,
                        self._digest(token),
                        request.kind,
                        now,
                        expires_at,
                        request.request_limit,
                        request.token_limit,
                        name,
                    ),
                )
            else:
                database.execute(
                    "INSERT INTO api_keys VALUES (?, ?, ?, ?, 'managed', ?, ?, NULL, ?, ?)",
                    (
                        name,
                        token,
                        self._digest(token),
                        request.kind,
                        now,
                        expires_at,
                        request.request_limit,
                        request.token_limit,
                    ),
                )
        return token, self.get(name)

    def update(self, name: str, update: ApiKeyUpdate) -> dict[str, Any]:
        values = update.model_dump(exclude_none=True)
        assignments: list[str] = []
        parameters: list[Any] = []
        if "expires_in_days" in values:
            assignments.append("expires_at = ?")
            parameters.append(self.clock() + values["expires_in_days"] * 86_400)
        for field in ("request_limit", "token_limit"):
            if field in values:
                assignments.append(f"{field} = ?")
                parameters.append(values[field])
        if not assignments:
            return self.get(name)
        parameters.append(name)
        with self._connect() as database:
            existing = database.execute(
                "SELECT kind, expires_at, revoked_at FROM api_keys WHERE name = ?", (name,)
            ).fetchone()
            if existing is None:
                raise KeyError(name)
            if (
                "expires_in_days" in values
                and existing["kind"] == "admin"
                and existing["revoked_at"] is None
                and existing["expires_at"] is not None
                and existing["expires_at"] <= self.clock()
            ):
                admin_count = database.execute(
                    "SELECT COUNT(*) FROM api_keys WHERE kind = 'admin' AND revoked_at IS NULL "
                    "AND (expires_at IS NULL OR expires_at > ?)",
                    (self.clock(),),
                ).fetchone()[0]
                if admin_count >= self.max_admin_keys:
                    raise ValueError("admin API key limit reached")
            changed = database.execute(
                f"UPDATE api_keys SET {', '.join(assignments)} WHERE name = ?",
                parameters,
            ).rowcount
        if not changed:
            raise KeyError(name)
        return self.get(name)

    def revoke(self, name: str) -> dict[str, Any]:
        with self._connect() as database:
            changed = database.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE name = ? AND revoked_at IS NULL",
                (self.clock(), name),
            ).rowcount
        if not changed:
            raise KeyError(name)
        return self.get(name)

    def delete(self, name: str) -> None:
        with self._connect() as database:
            record = database.execute(
                "SELECT source, revoked_at FROM api_keys WHERE name = ?", (name,)
            ).fetchone()
            if record is None:
                raise KeyError(name)
            if record["source"] == "environment":
                raise ValueError("environment API keys cannot be deleted")
            if record["revoked_at"] is None:
                raise ValueError("revoke the API key before deleting it")
            database.execute("DELETE FROM api_keys WHERE name = ?", (name,))

    def get(self, name: str) -> dict[str, Any]:
        records = {record["name"]: record for record in self.list()}
        if name not in records:
            raise KeyError(name)
        return records[name]

    def list(self) -> list[dict[str, Any]]:
        now = self.clock()
        with self._connect() as database:
            rows = database.execute(
                "SELECT name, token, kind, source, created_at, expires_at, revoked_at, "
                "request_limit, token_limit "
                "FROM api_keys ORDER BY name"
            ).fetchall()
        return [
            {
                "name": row["name"],
                "api_key": row["token"],
                "masked_key": f"{row['token'][:8]}…{row['token'][-4:]}",
                "kind": row["kind"],
                "source": row["source"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "revoked_at": row["revoked_at"],
                "request_limit": row["request_limit"],
                "token_limit": row["token_limit"],
                "status": (
                    "revoked"
                    if row["revoked_at"] is not None
                    else "expired"
                    if row["expires_at"] is not None and row["expires_at"] <= now
                    else "active"
                ),
            }
            for row in rows
        ]


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower().replace("-", "_")
    credential_names = (
        "authorization",
        "cookie",
        "token",
        "secret",
        "password",
        "api_key",
        "api_keys",
    )
    return normalized in credential_names or normalized.endswith(
        tuple(f"_{name}" for name in credential_names)
    )


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if isinstance(item, str) and item in {"[REDACTED]", "[REDACTED_BY_POLICY]"}
                else "[REDACTED]"
            )
            if is_sensitive_key(key)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", value
        )
    return value


def verify_bearer(expected: dict[str, str], authorization: str | None) -> str:
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "gateway API key is not configured"
        )
    scheme, _, token = (authorization or "").partition(" ")
    matched = None
    for name, value in expected.items():
        is_match = secrets.compare_digest(token, value)
        if is_match and matched is None:
            matched = name
    if scheme.lower() != "bearer" or matched is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
    return matched


def auth_dependency(
    settings: Settings, keys: ApiKeyStore | None = None
) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        if settings.auth_enabled:
            if keys is None:
                request.state.api_token_id = verify_bearer(
                    settings.configured_api_keys(), authorization
                )
            else:
                scheme, _, token = (authorization or "").partition(" ")
                matched = keys.verify(token) if scheme.lower() == "bearer" else None
                if matched is None:
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
                request.state.api_token_id = matched
                if limit_error := keys.limit_error(matched):
                    raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, limit_error)
        else:
            request.state.api_token_id = "authentication-disabled"

    return authenticate


def admin_dependency(
    settings: Settings, keys: ApiKeyStore | None = None
) -> Callable[..., Coroutine[Any, Any, None]]:
    async def authenticate_admin(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        if not settings.admin_api_enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin API is disabled")
        if settings.auth_enabled:
            if keys is None:
                request.state.api_token_id = verify_bearer(
                    settings.configured_api_keys(), authorization
                )
            else:
                scheme, _, token = (authorization or "").partition(" ")
                matched = keys.verify(token) if scheme.lower() == "bearer" else None
                if matched is None:
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
                request.state.api_token_id = matched
            if keys is not None and not keys.is_admin(request.state.api_token_id):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator API key required")
            if keys is None and request.state.api_token_id not in settings.admin_token_ids:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "operator API key required")
            return
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin API requires loopback")

    return authenticate_admin
