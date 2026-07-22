from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from dgx_moa.observation import (
    DiscordProvider,
    ObservationBus,
    ObservationCommandStore,
    ObservationEvent,
    TelegramProvider,
    public_event,
    render_events,
)
from dgx_moa.state import StateStore


class RecordingProvider:
    name = "discord"

    def __init__(self) -> None:
        self.batches: list[list[ObservationEvent]] = []

    async def send(self, events: Sequence[ObservationEvent]) -> None:
        self.batches.append(list(events))


def event(number: int = 1) -> ObservationEvent:
    return ObservationEvent(
        event_type="request_received",
        request_id=f"request-{number}",
        created_at="2026-07-22T00:00:00Z",
        details={"phase": "executing"},
    )


def test_public_event_allowlists_fields_and_drops_unpublished_content() -> None:
    published = public_event(
        "request-1",
        "request_received",
        {
            "task_id": "task-1",
            "phase": "intake",
            "prompt": "private repository content",
            "authorization": "Bearer synthetic-secret-token",
        },
        "2026-07-22T00:00:00Z",
    )

    assert published is not None
    assert published.details == {"task_id": "task-1", "phase": "intake"}
    detailed = public_event(
        "request-1",
        "request_received",
        {"prompt": "inspect token=synthetic-secret-value and report", "task_id": "task-1"},
        "2026-07-22T00:00:00Z",
        include_prompt=True,
    )
    assert detailed is not None
    assert detailed.details == {
        "prompt": "inspect token=[REDACTED] and report",
        "task_id": "task-1",
    }
    weekly = public_event(
        "weekly-maintenance",
        "weekly_package_completed",
        {
            "package_id": "package-1",
            "candidate_count": 4,
            "storage_location_identifier": "2026/W29/package.7z",
            "checksum": "a" * 64,
            "verification_status": "verified",
            "archive_path": "/private/path/must-not-leak",
        },
        "2026-07-22T00:00:00Z",
    )
    assert weekly is not None
    assert "archive_path" not in weekly.details
    assert public_event("request-1", "token_delta", {"text": "secret"}, "now") is None

    judge = public_event(
        "request-1",
        "judge_completed",
        {
            "verdict": "revise",
            "risk": "high",
            "recheck_required": True,
            "required_edits": ["private correction prose"],
        },
        "2026-07-22T00:00:00Z",
    )
    assert judge is not None
    assert judge.details == {"verdict": "revise", "risk": "high", "recheck_required": True}


def test_render_events_uses_readable_multiline_cards() -> None:
    rendered = render_events(
        [
            ObservationEvent(
                event_type="reasoner_completed",
                request_id="request-1",
                created_at="2026-07-22T00:00:00Z",
                details={
                    "confidence_category": "high",
                    "conclusions": ["Inspect the runtime", "Validate behavior"],
                    "hypotheses": ["Provider outage"],
                },
            )
        ]
    )

    assert rendered == (
        "🧠 Reasoner completed\n"
        "Request: request-1\n"
        "Confidence: high\n"
        "Conclusions:\n"
        "  • Inspect the runtime\n"
        "  • Validate behavior\n"
        "Hypotheses:\n"
        "  • Provider outage"
    )


@pytest.mark.asyncio
async def test_bus_batches_without_blocking_event_producer() -> None:
    provider = RecordingProvider()
    bus = ObservationBus([provider], queue_size=4, batch_size=2, batch_interval_seconds=0.01)
    bus.start()

    bus.publish_store_event("request-1", "request_received", {}, "now")
    bus.publish_store_event("request-2", "request_received", {}, "now")
    await asyncio.wait_for(bus.queue.join(), 1)
    await bus.close()

    assert [[item.request_id for item in batch] for batch in provider.batches] == [
        ["request-1", "request-2"]
    ]
    assert bus.metrics["sent"] == 2


def test_bus_drops_when_bounded_queue_is_full() -> None:
    bus = ObservationBus([], queue_size=1)

    bus.publish_store_event("request-1", "request_received", {}, "now")
    bus.publish_store_event("request-2", "request_received", {}, "now")

    assert bus.queue.qsize() == 1
    assert bus.metrics["dropped"] == 1


@pytest.mark.asyncio
async def test_discord_and_telegram_use_configured_thread_targets() -> None:
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handle)
    await DiscordProvider(
        "https://discord.invalid/webhook",
        thread_id="thread-1",
        transport=transport,
    ).send([event()])
    await TelegramProvider(
        "synthetic-token",
        "chat-1",
        message_thread_id=42,
        transport=transport,
    ).send([event()])

    assert requests[0].url.params["thread_id"] == "thread-1"
    assert b'"message_thread_id":42' in requests[1].content
    assert b"private" not in requests[0].content + requests[1].content


@pytest.mark.asyncio
async def test_provider_rate_limit_and_outage_are_isolated() -> None:
    async def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, headers={"Retry-After": "1"})

    async def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic provider outage", request=request)

    bus = ObservationBus(
        [
            DiscordProvider(
                "https://discord.invalid/webhook", transport=httpx.MockTransport(rate_limited)
            ),
            TelegramProvider(
                "synthetic-token",
                "synthetic-chat",
                transport=httpx.MockTransport(unavailable),
            ),
        ],
        batch_interval_seconds=0.01,
    )
    bus.start()
    bus.publish_store_event("request-1", "request_received", {}, "now")

    await asyncio.wait_for(bus.queue.join(), 1)
    await bus.close()

    assert bus.metrics["discord_errors"] == 1
    assert bus.metrics["telegram_errors"] == 1
    assert bus.metrics["sent"] == 0


@pytest.mark.asyncio
async def test_providers_use_real_loopback_http_and_surface_rate_limit_and_outage() -> None:
    received: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append((self.path, body))
            self.send_response(429 if self.path.startswith("/rate") else 200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    discord = DiscordProvider(f"{base}/discord", thread_id="thread-1", timeout=1)
    telegram = TelegramProvider("synthetic-token", "chat-1", message_thread_id=42, timeout=1)
    telegram.url = f"{base}/telegram"

    await discord.send([event()])
    await telegram.send([event()])
    with pytest.raises(httpx.HTTPStatusError):
        await DiscordProvider(f"{base}/rate", timeout=1).send([event()])
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)
    with pytest.raises(httpx.ConnectError):
        await discord.send([event()])

    assert received[0][0] == "/discord?thread_id=thread-1"
    assert b'"message_thread_id":42' in received[1][1]
    assert received[2][0] == "/rate"


def test_state_store_listener_failure_never_breaks_event_persistence(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.subscribe_events(lambda *args: (_ for _ in ()).throw(RuntimeError("observer down")))

    store.event("request-1", "request_received", {"task_id": "task-1"})

    assert store.events("request-1")[0]["event_type"] == "request_received"


def test_control_command_is_scoped_authorized_audited_and_idempotent(tmp_path: Path) -> None:
    store = ObservationCommandStore(tmp_path / "state.db")
    nonce = store.issue_nonce("discord", "user-1", "request-1", 300)
    arguments = {
        "provider": "discord",
        "user_id": "user-1",
        "request_id": "request-1",
        "command": "pause",
        "nonce": nonce,
        "idempotency_key": "command-1",
        "allowed_users": {"discord:user-1": "operator"},
        "role_permissions": {"operator": ["pause", "resume"]},
    }

    assert store.authorize(**arguments) is False
    assert store.authorize(**arguments) is True
    assert store.audit_log()[0]["command"] == "pause"
    with pytest.raises(ValueError, match="idempotency key reused"):
        store.authorize(**(arguments | {"nonce": "different-synthetic-nonce"}))


def test_control_command_rejects_unauthorized_expired_and_cross_request_nonce(
    tmp_path: Path,
) -> None:
    store = ObservationCommandStore(tmp_path / "state.db")
    nonce = store.issue_nonce("telegram", "user-1", "request-1", -1)
    base = {
        "provider": "telegram",
        "user_id": "user-1",
        "command": "terminate",
        "nonce": nonce,
        "idempotency_key": "command-expired",
        "allowed_users": {"telegram:user-1": "viewer"},
        "role_permissions": {"viewer": ["show-status"]},
    }

    with pytest.raises(PermissionError, match="not authorized"):
        store.authorize(request_id="request-1", **base)

    base["role_permissions"] = {"viewer": ["terminate"]}
    with pytest.raises(PermissionError, match="invalid request-scoped"):
        store.authorize(request_id="request-2", **base)
    with pytest.raises(PermissionError, match="expired"):
        store.authorize(request_id="request-1", **base)
