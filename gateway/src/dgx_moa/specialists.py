from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

import httpx

from .config import ModelConfig, SpecialistRoutingConfig
from .providers import ModelProvider, StageTimeout

SpecialistRole = Literal["planner", "reviewer"]
WarmupCallback = Callable[[str], Awaitable[Any]]
AcquireCallback = Callable[[str, str], Awaitable[tuple[str, ...]]]
ReleaseCallback = Callable[[tuple[str, ...]], None]


class SpecialistUnavailable(RuntimeError):
    pass


class SpecialistProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self, request: dict[str, Any], *, timeout_seconds: float
    ) -> dict[str, Any]: ...


class PlannerProvider(SpecialistProvider):
    pass


class ReviewerProvider(SpecialistProvider):
    pass


class _LocalProvider:
    name = "local"

    def __init__(self, role: SpecialistRole, provider: ModelProvider, model: ModelConfig) -> None:
        self.role = role
        self.provider = provider
        self.model = model

    async def complete(self, request: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        return await self.provider.complete(
            self.role,
            self.model,
            request,
            timeout_seconds=timeout_seconds,
            stage=self.role,
        )


class LocalPlannerProvider(_LocalProvider, PlannerProvider):
    def __init__(self, provider: ModelProvider, model: ModelConfig) -> None:
        super().__init__("planner", provider, model)


class LocalReviewerProvider(_LocalProvider, ReviewerProvider):
    def __init__(self, provider: ModelProvider, model: ModelConfig) -> None:
        super().__init__("reviewer", provider, model)


class _RemoteProvider:
    name = "remote"

    def __init__(
        self,
        role: SpecialistRole,
        *,
        endpoint: str,
        api_key_env: str,
        model: str,
        min_completion_tokens: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.role = role
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.min_completion_tokens = min_completion_tokens
        self.transport = transport

    async def complete(self, request: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise SpecialistUnavailable(f"{self.role} remote credential is unavailable")
        body = request.copy()
        body["model"] = self.model
        body["stream"] = False
        body["max_tokens"] = max(int(body.get("max_tokens", 0) or 0), self.min_completion_tokens)
        body.pop("tools", None)
        body.pop("tool_choice", None)
        body.pop("metadata", None)
        response_format = body.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            json_schema = response_format.get("json_schema", {})
            schema = json_schema.get("schema", {}) if isinstance(json_schema, dict) else {}
            messages = body.get("messages", [])
            if isinstance(messages, list) and isinstance(schema, dict):
                body["messages"] = [
                    {
                        "role": "system",
                        "content": (
                            "Return one JSON object matching this schema exactly: "
                            + json.dumps(schema, separators=(",", ":"), sort_keys=True)
                        ),
                    },
                    *messages,
                ]
            body["response_format"] = {"type": "json_object"}
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=None) as client:
                    response = await client.post(
                        f"{self.endpoint}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=body,
                    )
                    response.raise_for_status()
                    return cast(dict[str, Any], response.json())
        except (TimeoutError, httpx.TimeoutException) as error:
            raise StageTimeout(f"remote_{self.role}") from error


class RemotePlannerProvider(_RemoteProvider, PlannerProvider):
    def __init__(self, **values: Any) -> None:
        super().__init__("planner", **values)


class RemoteReviewerProvider(_RemoteProvider, ReviewerProvider):
    def __init__(self, **values: Any) -> None:
        super().__init__("reviewer", **values)


class _MockProvider:
    name = "mock"

    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def complete(self, request: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        del timeout_seconds
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class MockPlannerProvider(_MockProvider, PlannerProvider):
    pass


class MockReviewerProvider(_MockProvider, ReviewerProvider):
    pass


class SpecialistRouter:
    def __init__(
        self,
        config: SpecialistRoutingConfig,
        *,
        local: dict[SpecialistRole, SpecialistProvider],
        remote: dict[SpecialistRole, SpecialistProvider],
        lifecycle_store: Any | None = None,
        warmup: WarmupCallback | None = None,
        event: Callable[[str, str, dict[str, Any]], None] | None = None,
        acquire_local: AcquireCallback | None = None,
        release_local: ReleaseCallback | None = None,
        runtime_id: str | None = None,
    ) -> None:
        self.config = config
        self.local = local
        self.remote = remote
        self.lifecycle_store = lifecycle_store
        self.warmup = warmup
        self.event = event
        self.acquire_local = acquire_local
        self.release_local = release_local
        self.runtime_id = runtime_id or uuid.uuid4().hex
        self._warmups: dict[tuple[str, str, str], asyncio.Task[None]] = {}
        self._completed_warmups: dict[tuple[str, str, str], int] = {}
        self._used_warmups: set[tuple[str, str, str, int]] = set()
        self._unused_watchers: dict[tuple[str, str, str, int], asyncio.Task[None]] = {}

    @staticmethod
    def public_state(state: str) -> str:
        return {
            "disabled": "UNLOADED",
            "cold": "UNLOADED",
            "load_queued": "LOAD_REQUESTED",
            "process_starting": "LOADING",
            "loading_weights": "LOADING",
            "initializing_engine": "LOADING",
            "warming_up": "LOADING",
            "ready": "READY",
            "sleeping": "COOLDOWN",
            "unload_queued": "EVICTING",
            "unloading": "EVICTING",
            "stopping": "EVICTING",
            "failed": "FAILED",
        }.get(state, "DEGRADED")

    def _record(self, request_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self.event is not None:
            self.event(request_id, event_type, payload)

    def _record_for_role(self, role: SpecialistRole) -> Any | None:
        return self.lifecycle_store.get(role) if self.lifecycle_store is not None else None

    def _schedule_warmup(
        self, role: SpecialistRole, revision: str, request_id: str, trigger: str
    ) -> str:
        record = self._record_for_role(role)
        if self.warmup is None or record is None:
            return "unavailable"
        key = (role, revision, self.runtime_id)
        existing = self._warmups.get(key)
        if existing is not None and not existing.done():
            return "reused"
        self._warmups[key] = asyncio.create_task(
            self._watch_warmup(key, request_id, trigger),
            name=f"specialist-warmup-{role}",
        )
        return "started"

    async def _watch_warmup(self, key: tuple[str, str, str], request_id: str, trigger: str) -> None:
        role = cast(SpecialistRole, key[0])
        started = time.monotonic()
        try:
            check = await cast(WarmupCallback, self.warmup)(role)
            record = check.record
            self._record(
                request_id,
                "specialist_warmup_started",
                {
                    "role": role,
                    "reason": trigger,
                    "load_generation": record.generation,
                    "status": "started" if check.load_triggered else "reused",
                },
            )
            deadline = started + self.config.warmup_watch_seconds
            while time.monotonic() < deadline:
                record = self._record_for_role(role)
                if record is None:
                    return
                if record.state == "ready":
                    self._completed_warmups[key] = record.generation
                    self._record(
                        request_id,
                        "specialist_warmup_completed",
                        {
                            "role": role,
                            "load_generation": record.generation,
                            "latency_ms": round((time.monotonic() - started) * 1000, 3),
                            "status": "ready",
                        },
                    )
                    unused_key = (*key, record.generation)
                    self._unused_watchers[unused_key] = asyncio.create_task(
                        self._report_unused(unused_key, request_id),
                        name=f"specialist-unused-warmup-{role}",
                    )
                    return
                if record.state == "failed":
                    self._record(
                        request_id,
                        "specialist_warmup_failed",
                        {
                            "role": role,
                            "load_generation": record.generation,
                            "failure_class": record.failure_class or "load_failed",
                        },
                    )
                    return
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._record(
                request_id,
                "specialist_warmup_failed",
                {"role": role, "failure_class": type(error).__name__},
            )

    async def _report_unused(self, key: tuple[str, str, str, int], request_id: str) -> None:
        try:
            await asyncio.sleep(self.config.warmup_watch_seconds)
            if key not in self._used_warmups:
                self._record(
                    request_id,
                    "specialist_unused_warmup",
                    {"role": key[0], "load_generation": key[3], "status": "unused"},
                )
        finally:
            self._unused_watchers.pop(key, None)

    async def close(self) -> None:
        tasks = [
            task
            for task in (*self._warmups.values(), *self._unused_watchers.values())
            if not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def prewarm(self, metadata: dict[str, Any], request_id: str, revisions: dict[str, str]) -> None:
        planner = any(
            metadata.get(key)
            for key in (
                "repository_wide_change",
                "architecture",
                "migration",
                "multiple_subsystems",
                "complex_dependency_ordering",
            )
        )
        reviewer = any(
            metadata.get(key)
            for key in (
                "file_modifications_begin",
                "high_risk_paths",
                "tests_scheduled",
                "implementation_evidence_expected",
            )
        )
        for role, needed in (("planner", planner), ("reviewer", reviewer)):
            if needed:
                self._schedule_warmup(
                    cast(SpecialistRole, role), revisions[role], request_id, "predictive"
                )

    async def complete(
        self,
        role: SpecialistRole,
        request: dict[str, Any],
        *,
        request_id: str,
        revision: str,
        timeout_seconds: float,
        local_only: bool = False,
        mandatory: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        record = self._record_for_role(role)
        local_state = self.public_state(record.state if record is not None else "cold")
        if local_state == "READY" and record is not None and int(record.active_request_count) > 0:
            local_state = "BUSY"
        local_queue = (
            float(record.active_request_count) * self.config.local_latency_seconds[role]
            if record is not None
            else 0.0
        )
        predicted_local = local_queue + self.config.local_latency_seconds[role]
        predicted_remote = (
            self.config.network_latency_seconds
            + self.config.remote_queue_latency_seconds
            + self.config.remote_latency_seconds[role]
        )
        estimated_remote_tokens = max(
            int(request.get("max_tokens", 0) or 0),
            self.config.remote_min_completion_tokens[role],
        )
        estimated_remote_cost = (
            float(estimated_remote_tokens)
            * self.config.remote_cost_per_million_tokens_usd
            / 1_000_000
        )
        margin = (
            self.config.local_preference_margin_seconds
            + estimated_remote_cost * self.config.cost_seconds_per_usd
        )
        local_ready = local_state in {"READY", "BUSY"}
        use_local = local_ready and predicted_local <= predicted_remote + margin
        if local_only:
            if not local_ready:
                self._schedule_warmup(role, revision, request_id, "local_only_cold_miss")
                raise SpecialistUnavailable(f"required local {role} is not ready")
            use_local = True
        lease_ids: tuple[str, ...] = ()
        local_lease_failed = False
        if use_local and self.acquire_local is not None:
            try:
                lease_ids = await self.acquire_local(request_id, role)
            except Exception as error:
                if local_only:
                    raise SpecialistUnavailable(f"required local {role} lost readiness") from error
                use_local = False
                local_lease_failed = True
        provider_name = "local" if use_local else "remote"
        warmup_status = "not_needed"
        if not use_local and not local_ready:
            warmup_status = self._schedule_warmup(role, revision, request_id, "cold_miss")
        reason = (
            "local_only_policy"
            if local_only
            else "local_within_cost_margin"
            if use_local
            else "local_not_ready"
            if not local_ready
            else "local_readiness_race"
            if local_lease_failed
            else "remote_predicted_faster"
        )
        decision: dict[str, Any] = {
            "specialist_role": role,
            "residency_state": local_state,
            "queue_state": {"local_queue_delay_seconds": local_queue},
            "predicted_local_completion_seconds": predicted_local,
            "predicted_remote_completion_seconds": predicted_remote,
            "selected_provider": provider_name,
            "routing_reason": reason,
            "warmup_decision": warmup_status,
            "load_generation": record.generation if record is not None else 0,
            "remote_cost_usd": 0.0,
            "provider_switch_prevented": False,
        }
        self._record(request_id, "specialist_provider_selected", decision)
        started = time.monotonic()
        provider = self.local[role] if use_local else self.remote[role]
        provider_timeout = (
            timeout_seconds if use_local else min(timeout_seconds, self.config.timeout_seconds)
        )
        try:
            response = await provider.complete(request, timeout_seconds=provider_timeout)
        except Exception as error:
            decision.update(
                actual_completion_latency_seconds=time.monotonic() - started,
                provider_error=type(error).__name__,
                fallback_reason="provider_failed",
                provider_switch_prevented=True,
            )
            self._record(request_id, "specialist_provider_failed", decision)
            if mandatory:
                raise SpecialistUnavailable(f"required {role} provider failed") from error
            raise
        finally:
            if lease_ids and self.release_local is not None:
                self.release_local(lease_ids)
        usage = response.get("usage", {})
        tokens = int(usage.get("total_tokens", 0) or 0)
        cost = (
            tokens * self.config.remote_cost_per_million_tokens_usd / 1_000_000
            if not use_local
            else 0.0
        )
        decision.update(
            actual_completion_latency_seconds=time.monotonic() - started,
            remote_cost_usd=cost,
            quality_outcome="not_yet_evaluated",
            task_outcome="in_progress",
        )
        if use_local:
            key = (role, revision, self.runtime_id)
            generation = self._completed_warmups.get(key)
            if generation is not None:
                unused_key = (*key, generation)
                self._used_warmups.add(unused_key)
                decision["warmup_benefit"] = True
        self._record(request_id, "specialist_provider_completed", decision)
        return response, decision
