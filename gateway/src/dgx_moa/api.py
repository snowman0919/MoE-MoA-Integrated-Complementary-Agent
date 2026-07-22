from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings, get_settings
from .controller import (
    Controller,
    DuplicateFailedCall,
    FrontierRequiredUnavailable,
    JudgeCorrectionRequired,
    JudgeRequired,
    LoopAdmissionError,
    PolicyBlocked,
    ReasonerUnavailable,
)
from .evolution import PromptRegistry
from .frontier import CodexOAuthCollaboration, load_frontier_config
from .knowledge import KnowledgeRegistry
from .lifecycle import (
    LifecycleCoordinator,
    LifecycleDriver,
    LifecycleNotReadyError,
    LifecycleRecord,
    LifecycleStore,
    SystemdLifecycleDriver,
    continuation_correlation,
)
from .metrics import RuntimeMetrics
from .observation import (
    DiscordProvider,
    ObservationBus,
    ObservationCommandRequest,
    ObservationCommandStore,
    ObservationNonceRequest,
    ObservationProvider,
    TelegramProvider,
)
from .policy import PolicyEngine
from .profiles import ProfileManager
from .providers import ModelProvider, StageTimeout, validate_assistant_response
from .remote_judge import JudgeProviderError, OpenCodeGoJudgeProvider
from .replay import ReplayEngine, ReplayRequest
from .routing import (
    COMPATIBILITY_MODEL_ALIASES,
    MODEL_MODES,
    ReasonerMode,
    classify_request,
    optional_roles,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
)
from .runtime_status import memory_available as runtime_memory_available
from .runtime_status import report as runtime_report
from .schemas import ChatMessage, ChatRequest, ProfileResponse, ResponsesRequest
from .security import admin_dependency, auth_dependency
from .skills import SkillRegistry
from .specialists import (
    LocalPlannerProvider,
    LocalReviewerProvider,
    RemotePlannerProvider,
    RemoteReviewerProvider,
    SpecialistRouter,
)
from .state import Phase, StateStore
from .streaming import (
    StreamObservation,
    forward_sse,
    reported_usage,
    response_usage,
    responses_error_sse,
    responses_sse,
)
from .trace import TraceRecorder
from .training import (
    CandidateReviewRequest,
    ContentStore,
    TrainingCollector,
    TrainingRepositoryExclusion,
    TrainingRequestExclusion,
    TrainingRetentionRequest,
    TrainingStore,
    TrainingUserExclusion,
)
from .usage import (
    ModelAlias,
    RequestStatus,
    RequestUsageFinalization,
    RequestUsageStart,
    RetryableFailureClass,
    Role,
    UsageStore,
    classify_client,
)
from .weekly import (
    ArchiveRegistry,
    WeeklyPackageKeyRequest,
    WeeklyPackager,
    WeeklyPackageRevocationRequest,
    WeeklyRetentionRequest,
    WeeklyScheduler,
    previous_complete_week,
    weekly_knowledge_report,
    weekly_runtime_improvement_report,
    weekly_skill_report,
)

TIMEOUT_FAILURE_CLASSES: dict[str, RetryableFailureClass] = {
    "planner": "planner_timeout",
    "reasoner": "reasoner_timeout",
    "executor_first_byte": "executor_first_byte_timeout",
    "executor_total": "executor_total_timeout",
    "executor": "executor_timeout",
    "reviewer": "reviewer_timeout",
    "judge": "judge_timeout",
}


class DynamicRoleUnmanagedError(RuntimeError):
    def __init__(self, role: str):
        self.role = role
        super().__init__(role)


def ollama_model_ready(response: httpx.Response, model: Any) -> bool:
    if response.status_code != 200:
        return False
    try:
        models = response.json().get("models", [])
    except (ValueError, AttributeError):
        return False
    return any(
        isinstance(item, dict)
        and model.served_name in {item.get("name"), item.get("model")}
        and isinstance(item.get("context_length"), int)
        and item["context_length"] >= model.context_length
        for item in models
    )


def error_response(
    status_code: int,
    message: str,
    error_type: str,
    code: str,
    param: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": error_type, "code": code, "param": param}},
        status_code=status_code,
        headers=headers,
    )


def title_request_index(messages: list[dict[str, Any]]) -> int | None:
    """Return OpenCode's trailing automatic title prompt, if present."""
    title_generator = any(
        message.get("role") == "system"
        and str(message.get("content", ""))
        .strip()
        .lower()
        .startswith("you are a title generator. you output only a thread title.")
        for message in messages
    )
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") == "user":
            content = str(message.get("content", "")).strip().lower()
            if content.startswith("generate a title for this conversation"):
                return index
            if not title_generator:
                return None
    return None


def _coerce_responses_input_messages(
    raw_input: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if isinstance(raw_input, list):
        messages: list[dict[str, Any]] = []
        for item in raw_input:
            item_type = item.get("type")
            if item_type == "reasoning":
                continue
            if item_type in {"function_call", "custom_tool_call"}:
                arguments = (
                    item.get("arguments", "")
                    if item_type == "function_call"
                    else json.dumps({"input": item.get("input", "")})
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": arguments,
                                },
                            }
                        ],
                    }
                )
                continue
            if item_type in {"function_call_output", "custom_tool_call_output"}:
                output = item.get("output", "")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": output if isinstance(output, str) else json.dumps(output),
                    }
                )
                continue
            message = dict(item)
            if isinstance(content := message.get("content"), list):
                message["content"] = [
                    {**part, "type": "text"}
                    if part.get("type") in {"input_text", "output_text"}
                    else part
                    for part in content
                ]
            messages.append(message)
        return messages
    raise TypeError("invalid responses input type")


def _coerce_responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    chat_tools = []
    for tool in tools:
        tool_type = tool.get("type")
        if tool_type not in {"function", "custom"}:
            continue
        nested_function = tool.get("function")
        function: dict[str, Any] = nested_function if isinstance(nested_function, dict) else tool
        if tool_type == "custom":
            function = {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                    "additionalProperties": False,
                },
            }
        chat_tools.append(
            {
                "type": "function",
                "function": {
                    key: function[key]
                    for key in ("name", "description", "parameters", "strict")
                    if key in function
                },
            }
        )
    return chat_tools or None


def _responses_payload(
    model: str,
    chat_response: dict[str, Any] | None = None,
    *,
    status: str = "completed",
    custom_tool_names: set[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"resp-{uuid.uuid4().hex}",
        "object": "response",
        "created": int(time.time()),
        "model": model,
        "status": status,
        "output": [],
    }
    if chat_response is None:
        return payload
    if error := chat_response.get("error"):
        payload["error"] = error
        payload["status"] = "failed"
        return payload

    choices = chat_response.get("choices") or []
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content:
            payload["output"] = [
                {
                    "type": "message",
                    "status": "completed",
                    "role": message.get("role", "assistant"),
                    "content": [
                        {"type": "output_text", "text": content},
                    ],
                }
            ]
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            name = function.get("name")
            if name in (custom_tool_names or set()):
                try:
                    parsed_arguments = json.loads(function.get("arguments", ""))
                    custom_input = parsed_arguments["input"]
                    if not isinstance(custom_input, str):
                        raise TypeError
                except (KeyError, TypeError, ValueError):
                    custom_input = function.get("arguments", "")
                payload["output"].append(
                    {
                        "type": "custom_tool_call",
                        "id": f"ctc_{uuid.uuid4().hex}",
                        "call_id": tool_call.get("id"),
                        "name": name,
                        "input": custom_input,
                    }
                )
                continue
            payload["output"].append(
                {
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex}",
                    "call_id": tool_call.get("id"),
                    "name": function.get("name"),
                    "arguments": function.get("arguments", ""),
                    "status": "completed",
                }
            )
    if not payload["output"]:
        payload["status"] = "failed"
        payload["error"] = {
            "message": "upstream response did not contain assistant output",
            "type": "backend_error",
            "code": "backend_error",
        }
    if usage := response_usage(chat_response.get("usage")):
        payload["usage"] = usage
    return payload


def _chat_response_payload(response: Response) -> dict[str, Any] | None:
    raw_body = getattr(response, "body", None)
    if not raw_body:
        return None
    try:
        return cast(
            dict[str, Any],
            json.loads(raw_body.decode() if isinstance(raw_body, bytes) else raw_body),
        )
    except ValueError:
        return None


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def has_matching_tool_result(messages: list[dict[str, Any]]) -> bool:
    assistant_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "assistant" and messages[index].get("tool_calls")
        ),
        None,
    )
    if assistant_index is None:
        return False
    trailing = messages[assistant_index + 1 :]
    if not trailing or any(message.get("role") != "tool" for message in trailing):
        return False
    call_ids = {
        call_id
        for call in (messages[assistant_index].get("tool_calls") or [])
        if isinstance(call, dict) and isinstance(call_id := call.get("id"), str) and call_id.strip()
    }
    result_ids = {
        tool_call_id
        for message in trailing
        if isinstance(tool_call_id := message.get("tool_call_id"), str) and tool_call_id.strip()
    }
    return bool(call_ids & result_ids)


def tool_result_call_ids(messages: list[dict[str, Any]]) -> set[str]:
    return {
        tool_call_id
        for message in messages
        if message.get("role") == "tool"
        and isinstance(tool_call_id := message.get("tool_call_id"), str)
        and tool_call_id.strip()
    }


class ResponseOwnedIterator:
    def __init__(
        self,
        stream: AsyncIterator[bytes],
        cleanup: Callable[[], Awaitable[None]],
    ) -> None:
        self._stream = stream
        self._cleanup = cleanup

    def __aiter__(self) -> ResponseOwnedIterator:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await anext(self._stream)
        except BaseException:
            await self._cleanup()
            raise

    async def aclose(self) -> None:
        try:
            close = getattr(self._stream, "aclose", None)
            if close is not None:
                await close()
        finally:
            await self._cleanup()


class ResponseOwnedStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                await close()


def create_app(
    settings: Settings | None = None,
    *,
    lifecycle_driver: LifecycleDriver | None = None,
    lifecycle_health_probe: Callable[[str], Awaitable[bool]] | None = None,
    lifecycle_clock: Callable[[], float] = time.time,
    lifecycle_sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    lifecycle_memory_probe: Callable[[], int] = runtime_memory_available,
) -> FastAPI:
    configured = settings or get_settings()
    auth = auth_dependency(configured)
    admin_auth = admin_dependency(configured)

    async def default_lifecycle_health_probe(role: str) -> bool:
        model = configured.models.get(role)
        if model is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if role in {"planner", "reviewer"} and model.provider != "ollama":
                    response = await client.post(
                        f"{model.base_url.rstrip('/')}/v1/chat/completions",
                        json={
                            "model": model.served_name,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": "Reply with exactly READY.",
                                }
                            ],
                            "temperature": 0,
                            "max_tokens": 256,
                            "stream": False,
                        },
                    )
                    if response.status_code != 200:
                        return False
                    payload = response.json()
                    choices = payload.get("choices", [])
                    return bool(
                        choices
                        and isinstance(choices[0], dict)
                        and choices[0].get("message", {}).get("content")
                    )
                response = await client.get(
                    f"{model.base_url.rstrip('/')}/api/ps"
                    if model.provider == "ollama"
                    else f"{model.base_url.rstrip('/')}/v1/models"
                )
        except httpx.HTTPError:
            return False
        except (TypeError, ValueError):
            return False
        return (
            ollama_model_ready(response, model)
            if model.provider == "ollama"
            else response.status_code == 200
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store = StateStore(configured.state_db)
        provider = ModelProvider()
        project_root = Path(os.getenv("DGX_MOA_PROJECT_ROOT", ".")).resolve()
        app.state.settings = configured
        app.state.store = store
        app.state.runtime_metrics = RuntimeMetrics()
        store.subscribe_events(app.state.runtime_metrics.observe_event)
        observation_providers: list[ObservationProvider] = []
        observation = configured.live_observation
        if observation.enabled and observation.discord is not None:
            observation_providers.append(
                DiscordProvider(
                    observation.discord.webhook_url.get_secret_value(),
                    thread_id=observation.discord.thread_id,
                    timeout=observation.request_timeout_seconds,
                )
            )
        if observation.enabled and observation.telegram is not None:
            observation_providers.append(
                TelegramProvider(
                    observation.telegram.bot_token.get_secret_value(),
                    observation.telegram.chat_id,
                    message_thread_id=observation.telegram.message_thread_id,
                    timeout=observation.request_timeout_seconds,
                )
            )
        app.state.observation = (
            ObservationBus(
                observation_providers,
                queue_size=observation.queue_size,
                batch_size=observation.batch_size,
                batch_interval_seconds=observation.batch_interval_seconds,
                include_prompt=observation.include_prompt,
                include_reasoner_artifact=observation.include_reasoner_artifact,
                max_content_characters=observation.max_content_characters,
            )
            if observation.enabled and observation_providers
            else None
        )
        if app.state.observation is not None:
            store.subscribe_events(app.state.observation.publish_store_event)
        app.state.observation_commands = (
            ObservationCommandStore(configured.state_db) if observation.controls.enabled else None
        )
        frontier_config = (
            load_frontier_config(configured.frontier_config)
            if configured.frontier_enabled
            else None
        )
        model_catalog = {role: model.served_name for role, model in configured.models.items()}
        if frontier_config is not None:
            model_catalog["frontier"] = frontier_config.model
        app.state.usage = UsageStore(
            configured.state_db,
            sample_window=configured.limits.usage_sample_window,
            ewma_alpha=configured.limits.usage_ewma_alpha,
            adaptive_minimum_samples=configured.limits.adaptive_minimum_samples,
            invocation_report_path=configured.run_dir / "model-invocation-rates.csv",
            model_catalog=model_catalog,
        )
        app.state.usage_session_namespace = uuid.uuid4()
        app.state.project_root = project_root
        app.state.provider = provider
        frontier = None
        if frontier_config is not None:
            if frontier_config.provider != "codex_oauth":
                raise ValueError("Frontier collaboration requires codex_oauth")
            frontier = CodexOAuthCollaboration(
                frontier_config,
                configured.run_dir,
                project_root,
            )
        app.state.skills = (
            SkillRegistry(configured.runtime_skills.root)
            if configured.runtime_skills.enabled
            else None
        )
        app.state.knowledge = (
            KnowledgeRegistry(configured.runtime_knowledge.state_db)
            if configured.runtime_knowledge.enabled
            else None
        )
        app.state.prompts = (
            PromptRegistry(configured.runtime_evolution.state_db)
            if configured.runtime_evolution.enabled
            else None
        )
        app.state.policy = (
            PolicyEngine(configured.declarative_policy.policy_set())
            if configured.declarative_policy.enabled
            else None
        )
        remote_judge = None
        if configured.remote_judge.enabled:
            if configured.remote_judge.provider != "opencode_go":
                raise ValueError("only OpenCode Go is supported outside tests")
            endpoint = os.path.expandvars(configured.remote_judge.endpoint or "")
            if not endpoint or "$" in endpoint:
                raise ValueError("Remote Judge endpoint environment is unresolved")
            remote_judge = OpenCodeGoJudgeProvider(
                endpoint=endpoint,
                api_key_env=configured.remote_judge.api_key_env,
                model=configured.remote_judge.model,
                timeout_seconds=configured.remote_judge.timeout_seconds,
                max_retries=configured.remote_judge.max_retries,
                max_calls_per_request=configured.remote_judge.max_calls_per_request,
            )
        app.state.remote_judge = remote_judge
        if remote_judge is None:
            app.state.remote_judge_available = None
        else:
            try:
                app.state.remote_judge_available = await asyncio.wait_for(
                    remote_judge.available(),
                    timeout=min(5, configured.remote_judge.timeout_seconds),
                )
            except TimeoutError:
                app.state.remote_judge_available = False
        app.state.controller = Controller(
            configured,
            store,
            provider,
            frontier,
            app.state.usage,
            skills=app.state.skills,
            policy=app.state.policy,
            knowledge=app.state.knowledge,
            prompts=app.state.prompts,
            remote_judge=remote_judge,
        )
        app.state.lifecycle_store = LifecycleStore(
            configured.state_db,
            configured.models,
            clock=lifecycle_clock,
            unit_map=(
                configured.lifecycle_unit_map
                if configured.lifecycle_mode in {"observe", "fixed", "adaptive"}
                else None
            ),
        )
        app.state.controller.lifecycle_store = app.state.lifecycle_store
        app.state.lifecycle_store.recover_leases()
        app.state.lifecycle = LifecycleCoordinator(
            app.state.lifecycle_store,
            lifecycle_driver
            or SystemdLifecycleDriver(
                configured.lifecycle_unit_map,
                timeout_seconds=configured.limits.model_load_timeout_seconds,
            ),
            health_probe=lifecycle_health_probe or default_lifecycle_health_probe,
            timeout_seconds=configured.limits.model_load_timeout_seconds,
            poll_seconds=configured.lifecycle_poll_seconds,
            clock=lifecycle_clock,
            sleeper=lifecycle_sleeper,
            memory_probe=lifecycle_memory_probe,
            lifecycle_policy=configured.lifecycle,
        )
        app.state.specialists = None
        if configured.specialist_routing.enabled:
            if configured.specialist_routing.provider != "opencode_go":
                raise ValueError("only OpenCode Go specialist routing is supported")
            remote_values = {
                "endpoint": configured.specialist_routing.endpoint,
                "api_key_env": configured.specialist_routing.api_key_env,
            }

            async def acquire_specialist(request_id: str, role: str) -> tuple[str, ...]:
                leases = await app.state.lifecycle.acquire_request_leases(
                    request_id,
                    (role,),
                    kind="active_request",
                    require_ready=True,
                )
                return tuple(lease.lease_id for lease in leases)

            app.state.specialists = SpecialistRouter(
                configured.specialist_routing,
                local={
                    "planner": LocalPlannerProvider(provider, configured.models["planner"]),
                    "reviewer": LocalReviewerProvider(provider, configured.models["reviewer"]),
                },
                remote={
                    "planner": RemotePlannerProvider(
                        **remote_values,
                        model=configured.specialist_routing.models["planner"],
                        min_completion_tokens=configured.specialist_routing.remote_min_completion_tokens[
                            "planner"
                        ],
                    ),
                    "reviewer": RemoteReviewerProvider(
                        **remote_values,
                        model=configured.specialist_routing.models["reviewer"],
                        min_completion_tokens=configured.specialist_routing.remote_min_completion_tokens[
                            "reviewer"
                        ],
                    ),
                },
                lifecycle_store=app.state.lifecycle_store,
                warmup=app.state.lifecycle.ensure_ready,
                event=store.event,
                acquire_local=acquire_specialist,
                release_local=app.state.lifecycle_store.release_leases,
            )
            app.state.controller.specialists = app.state.specialists
        try:
            managed_roles = tuple(configured.lifecycle_unit_map)
            if configured.lifecycle_mode in {"observe", "fixed", "adaptive"}:
                await app.state.lifecycle.reconcile_managed(managed_roles)
            app.state.lifecycle.start_scheduler(
                configured.lifecycle_mode,
                managed_roles,
                configured.lifecycle,
                app.state.usage,
            )
            app.state.reviewer_evaluation_lock = asyncio.Lock()
            app.state.training_collector = None
            app.state.training_store = None
            if configured.training_data.enabled:
                training_store = TrainingStore(
                    configured.training_data.state_db,
                    ContentStore(
                        configured.training_data.object_root,
                        maximum_bytes=configured.training_data.maximum_object_bytes,
                    ),
                    minimum_free_bytes=configured.training_data.minimum_free_bytes,
                )
                app.state.training_store = training_store
                app.state.training_collector = TrainingCollector(
                    training_store,
                    store,
                    external_output_permitted=(configured.training_data.external_output_permitted),
                )
            app.state.weekly_packager = (
                WeeklyPackager(
                    configured.weekly_jobs.package_root,
                    ArchiveRegistry(configured.weekly_jobs.archive_registry),
                    notifier=lambda event_type, payload: store.event(
                        "weekly-maintenance", event_type, payload
                    ),
                )
                if configured.weekly_jobs.enabled
                else None
            )
            app.state.weekly_scheduler = None
            if configured.weekly_jobs.enabled:

                def notify_weekly(event_type: str, payload: dict[str, Any]) -> None:
                    store.event("weekly-maintenance", event_type, payload)

                async def run_weekly_skill_job() -> None:
                    if app.state.skills is None and app.state.knowledge is None:
                        raise RuntimeError("runtime Skills and Knowledge are disabled")
                    window = previous_complete_week(timezone=configured.weekly_jobs.timezone)
                    report_root = (
                        configured.weekly_jobs.package_root / "runtime-reports" / window.week
                    )
                    skill_report = (
                        await asyncio.to_thread(
                            weekly_skill_report,
                            app.state.skills,
                            report_root,
                            notifier=notify_weekly,
                        )
                        if app.state.skills is not None
                        else None
                    )
                    knowledge_report = (
                        await asyncio.to_thread(
                            weekly_knowledge_report,
                            app.state.knowledge,
                            report_root,
                            notifier=notify_weekly,
                        )
                        if app.state.knowledge is not None
                        else None
                    )
                    evolution_artifacts = (
                        app.state.prompts.registry.list_artifacts()
                        if app.state.prompts is not None
                        else []
                    )
                    candidate_rows = [
                        artifact.model_dump(mode="json")
                        for artifact in evolution_artifacts
                        if artifact.state == "candidate"
                    ]
                    await asyncio.to_thread(
                        weekly_runtime_improvement_report,
                        report_root,
                        skill_report=skill_report,
                        knowledge_report=knowledge_report,
                        analyses={
                            "prompt_regressions": [
                                artifact.model_dump(mode="json")
                                for artifact in evolution_artifacts
                                if artifact.kind in {"prompt", "judge_prompt"}
                                and artifact.state == "rejected"
                            ],
                            "prompt_candidates": [
                                row
                                for row in candidate_rows
                                if row["kind"] in {"prompt", "judge_prompt"}
                            ],
                            "policy_candidates": [
                                row for row in candidate_rows if row["kind"] == "policy"
                            ],
                            "routing_candidates": [
                                row
                                for row in candidate_rows
                                if row["kind"] in {"routing", "failure_handling"}
                            ],
                        },
                        notifier=notify_weekly,
                    )

                async def run_weekly_package_job() -> None:
                    if app.state.training_store is None or app.state.weekly_packager is None:
                        raise RuntimeError("weekly training pipeline is disabled")
                    window = previous_complete_week(timezone=configured.weekly_jobs.timezone)
                    await asyncio.to_thread(
                        app.state.weekly_packager.package,
                        app.state.training_store.packageable_candidates(
                            created_from=window.utc_start.isoformat(),
                            created_before=window.utc_end.isoformat(),
                        ),
                        window=window,
                        production_commit=configured.controller_commit,
                        policy_version=configured.declarative_policy.version,
                        skill_registry_version="runtime-skill-schema-v1",
                        model_configuration={
                            role: {
                                "repository": model.repository,
                                "revision": model.revision,
                                "served_name": model.served_name,
                            }
                            for role, model in configured.models.items()
                        },
                    )

                app.state.weekly_scheduler = WeeklyScheduler(
                    timezone=configured.weekly_jobs.timezone,
                    skill_schedule=configured.weekly_jobs.skill_schedule,
                    package_schedule=configured.weekly_jobs.package_schedule,
                    skill_job=run_weekly_skill_job,
                    package_job=run_weekly_package_job,
                    notifier=notify_weekly,
                )
            app.state.traces = TraceRecorder(
                configured.state_db.parent.parent / "traces",
                store,
                configured.models,
                (
                    app.state.training_collector.collect
                    if app.state.training_collector is not None
                    else None
                ),
            )
            app.state.profiles = ProfileManager(configured.run_dir, project_root)
            if app.state.observation is not None:
                app.state.observation.start()
            if app.state.weekly_scheduler is not None:
                app.state.weekly_scheduler.start()
            yield
        finally:
            if app.state.weekly_scheduler is not None:
                await app.state.weekly_scheduler.close()
            if app.state.observation is not None:
                await app.state.observation.close()
            if app.state.specialists is not None:
                await app.state.specialists.close()
            await app.state.lifecycle.close()

    app = FastAPI(title="DGX MoA Agent", version="2.0.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            error_type, code, param = "authentication_error", "invalid_api_key", None
        elif error.status_code == status.HTTP_404_NOT_FOUND and error.detail == "unknown model":
            error_type, code, param = "invalid_request_error", "model_not_found", "model"
        elif error.status_code < 500:
            error_type, code, param = "invalid_request_error", "invalid_request", None
        else:
            error_type, code, param = "backend_error", "backend_error", None
        return error_response(
            error.status_code,
            str(error.detail),
            error_type,
            code,
            param,
            dict(error.headers) if error.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        first = error.errors()[0]
        message = str(first.get("msg", "invalid request")).removeprefix("Value error, ")
        location = first.get("loc", ())
        param = str(location[-1]) if len(location) > 1 else None
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            message,
            "invalid_request_error",
            "invalid_request",
            param,
        )

    def record_trace_safely(request: Request, state: Any, task_id: str) -> None:
        for decision in getattr(state, "specialist_routing", []):
            if isinstance(decision, dict):
                decision["quality_outcome"] = (
                    getattr(state, "review_status", None)
                    or getattr(state, "judge_status", None)
                    or "not_evaluated"
                )
                decision["task_outcome"] = getattr(state, "final_status", None) or str(
                    getattr(state, "phase", "unknown")
                )
        state.specialist_eviction_decisions = []
        for role in ("planner", "reviewer"):
            if role not in configured.models:
                continue
            idle = request.app.state.lifecycle_store.latest_decision(role)
            if idle is None:
                continue
            local = request.app.state.lifecycle_store.get(role)
            state.specialist_eviction_decisions.append(
                idle.model_dump(mode="json")
                | {
                    "residency_state": SpecialistRouter.public_state(local.state),
                    "task_queue": {
                        "active_requests": local.active_request_count,
                        "open_streams": local.open_stream_count,
                    },
                    "reload_latency_seconds": local.last_load_duration_seconds,
                    "remote_api_cost_per_million_tokens_usd": (
                        configured.specialist_routing.remote_cost_per_million_tokens_usd
                    ),
                    "model_importance": "optional_specialist",
                }
            )
        try:
            request.app.state.traces.record(state, task_id=task_id)
        except OSError as error:
            state.observability_degraded = True
            state.observability_status = "degraded"
            request.app.state.store.event(
                state.session_id,
                "observability_degraded",
                {"component": "trace_archive", "error": type(error).__name__},
            )
            request.app.state.store.save(state)

    def public_lifecycle_record(record: LifecycleRecord) -> dict[str, Any]:
        decision = app.state.lifecycle_store.latest_decision(record.role)
        automation = app.state.lifecycle_store.automation_status()
        model = configured.models.get(record.role)
        if decision is not None and decision.mode != configured.lifecycle_mode:
            decision = None
        specialist_state = None
        if configured.specialist_routing.enabled and record.role in {"planner", "reviewer"}:
            specialist_state = SpecialistRouter.public_state(record.state)
            if specialist_state == "READY" and record.active_request_count:
                specialist_state = "BUSY"
        return {
            "role": record.role,
            "lifecycle_control": model.lifecycle_control if model else "unconfigured",
            "state": record.state,
            **({"specialist_state": specialist_state} if specialist_state is not None else {}),
            "generation": record.generation,
            "ready": record.state == "ready",
            "transition_id": record.transition_id,
            "transitioned_at": record.transitioned_at,
            "updated_at": record.updated_at,
            "ready_since": record.ready_since,
            "last_used_at": record.last_used_at,
            "load_started_at": record.load_started_at,
            "ready_at": record.ready_at,
            "last_requested_at": record.last_requested_at,
            "last_completed_at": record.last_completed_at,
            "active_requests": record.active_request_count,
            "open_streams": record.open_stream_count,
            "pending_continuations": record.continuation_lease_count,
            "weight_load_percent": record.weight_load_percent,
            "progress_quality": record.progress_quality or "unavailable",
            "overall_load_percent": record.overall_load_percent,
            "estimated_ready_seconds": record.eta_seconds,
            "failure_class": record.failure_class,
            "last_error_class": record.last_error_class,
            "retry_count": record.retry_count,
            "adaptive_timeout_seconds": decision.threshold_seconds if decision else None,
            "idle_seconds": decision.idle_seconds if decision else None,
            "automation_disabled": automation.automation_disabled,
            "lifecycle_failure_count": automation.failure_count,
            "automation_disabled_at": automation.disabled_at,
            "idle_decision": decision.model_dump(mode="json") if decision else None,
            "lifecycle_mode": configured.lifecycle_mode,
            "control": ("observe_only" if configured.lifecycle_mode == "observe" else "managed"),
        }

    def status_lifecycle_record(role: str) -> dict[str, Any]:
        if (
            configured.lifecycle_mode != "disabled"
            and configured.models.get(role) is not None
            and configured.models[role].lifecycle_control == "external"
        ):
            status = public_lifecycle_record(app.state.lifecycle_store.get(role))
            status["control"] = "external"
            return status
        if configured.lifecycle_mode != "disabled" and role in configured.lifecycle_unit_map:
            return public_lifecycle_record(app.state.lifecycle_store.get(role))
        automation = app.state.lifecycle_store.automation_status()
        return {
            "role": role,
            "state": "unmanaged",
            "generation": None,
            "ready": False,
            "transition_id": None,
            "transitioned_at": None,
            "updated_at": None,
            "ready_since": None,
            "last_used_at": None,
            "load_started_at": None,
            "ready_at": None,
            "last_requested_at": None,
            "last_completed_at": None,
            "active_requests": 0,
            "open_streams": 0,
            "pending_continuations": 0,
            "weight_load_percent": None,
            "progress_quality": "unavailable",
            "overall_load_percent": None,
            "estimated_ready_seconds": None,
            "failure_class": None,
            "last_error_class": None,
            "retry_count": 0,
            "adaptive_timeout_seconds": None,
            "idle_seconds": None,
            "automation_disabled": automation.automation_disabled,
            "lifecycle_failure_count": automation.failure_count,
            "automation_disabled_at": automation.disabled_at,
            "idle_decision": None,
            "lifecycle_mode": configured.lifecycle_mode,
            "control": "disabled" if configured.lifecycle_mode == "disabled" else "unmanaged",
        }

    def loading_response(record: LifecycleRecord) -> JSONResponse:
        eta = record.eta_seconds
        retry_after = 30 if eta is None else min(300, max(1, math.ceil(eta)))
        progress = record.weight_load_percent
        progress_header = "unavailable" if progress is None else f"{progress:g}"
        return JSONResponse(
            {
                "error": {
                    "message": "Required model role is loading. Retry later.",
                    "type": "model_loading",
                    "code": "model_loading",
                    "param": None,
                },
                "model_state": {
                    "role": record.role,
                    "generation": record.generation,
                    "state": record.state,
                    "transition_id": record.transition_id,
                    "weight_load_percent": progress,
                    "progress_quality": record.progress_quality or "unavailable",
                    "overall_load_percent": record.overall_load_percent,
                    "estimated_ready_seconds": eta,
                    "ready": False,
                },
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={
                "Retry-After": str(retry_after),
                "X-DGX-MOA-Model-Role": record.role,
                "X-DGX-MOA-Model-State": record.state,
                "X-DGX-MOA-Load-Generation": str(record.generation),
                "X-DGX-MOA-Weight-Load-Percent": progress_header,
            },
        )

    def unavailable_response(role: str, *, record: LifecycleRecord | None = None) -> JSONResponse:
        automation_disabled = app.state.lifecycle_store.automation_status().automation_disabled
        state_value = record.state if record is not None else "unmanaged"
        model_state: dict[str, Any] = {
            "role": role,
            "state": state_value,
            "generation": record.generation if record is not None else None,
            "ready": False,
            "transition_id": record.transition_id if record is not None else None,
            "weight_load_percent": record.weight_load_percent if record is not None else None,
            "progress_quality": (record.progress_quality if record is not None else None)
            or "unavailable",
            "overall_load_percent": (record.overall_load_percent if record is not None else None),
            "estimated_ready_seconds": record.eta_seconds if record is not None else None,
        }
        if record is not None:
            model_state.update(
                failure_class=record.failure_class,
                retry_count=record.retry_count,
            )
        return JSONResponse(
            {
                "error": {
                    "message": (
                        f"Model role {role} is not lifecycle-managed."
                        if record is None
                        else "Lifecycle automation is disabled after repeated failures."
                        if automation_disabled
                        else f"Model dgx-moa-{role} failed to load."
                    ),
                    "type": "model_unavailable",
                    "code": (
                        "model_not_managed"
                        if record is None
                        else "lifecycle_automation_disabled"
                        if automation_disabled
                        else "model_load_failed"
                    ),
                    "param": None,
                },
                "model_state": model_state,
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={
                "X-DGX-MOA-Model-Role": role,
                "X-DGX-MOA-Model-State": state_value,
                "X-DGX-MOA-Load-Generation": (
                    str(record.generation) if record is not None else "unavailable"
                ),
                "X-DGX-MOA-Weight-Load-Percent": (
                    "unavailable"
                    if record is None or record.weight_load_percent is None
                    else f"{record.weight_load_percent:g}"
                ),
            },
        )

    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "remote_judge": (
                "disabled"
                if request.app.state.remote_judge is None
                else "available"
                if request.app.state.remote_judge_available
                else "unavailable"
            ),
        }

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        profile_state = request.app.state.profiles.current()
        current = profile_state["active_profile"]
        if profile_state["status"] in {"transitioning", "degraded", "failed"}:
            return JSONResponse(
                {
                    "status": profile_state["status"],
                    "from": profile_state.get("from", current),
                    "to": profile_state.get("to", "unknown"),
                },
                status_code=503,
            )
        roles = {
            "resident": ("executor", "reasoner"),
            "judge": ("judge",),
        }.get(current, ())
        if not roles:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": {role: "stopped" for role in configured.models},
                    "remote_judge": (
                        "disabled" if request.app.state.remote_judge is None else "unavailable"
                    ),
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        service_status = {role: "stopped" for role in configured.models}
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                results = await asyncio.gather(
                    *(
                        client.get(
                            f"{model.base_url.rstrip('/')}/api/ps"
                            if model.provider == "ollama"
                            else f"{model.base_url.rstrip('/')}/v1/models"
                        )
                        for model in configured.models.values()
                    ),
                    return_exceptions=True,
                )
            for (role, model), result in zip(configured.models.items(), results, strict=True):
                if isinstance(result, httpx.Response) and (
                    ollama_model_ready(result, model)
                    if model.provider == "ollama"
                    else result.status_code == 200
                ):
                    service_status[role] = "ready"
        except KeyError:
            pass
        if any(service_status.get(role) != "ready" for role in roles):
            return JSONResponse(
                {
                    "status": "not_ready",
                    "profile": current,
                    "services": service_status,
                    "remote_judge": (
                        "disabled"
                        if request.app.state.remote_judge is None
                        else "available"
                        if request.app.state.remote_judge_available
                        else "unavailable"
                    ),
                    "auth_enabled": configured.auth_enabled,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ready",
                "profile": current,
                "services": service_status,
                "remote_judge": (
                    "disabled"
                    if request.app.state.remote_judge is None
                    else "available"
                    if request.app.state.remote_judge_available
                    else "unavailable"
                ),
                "auth_enabled": configured.auth_enabled,
            }
        )

    @app.post("/v1/admin/observation/nonces", dependencies=[Depends(admin_auth)])
    async def issue_observation_nonce(
        body: ObservationNonceRequest, request: Request
    ) -> dict[str, Any]:
        controls = configured.live_observation.controls
        command_store = request.app.state.observation_commands
        if not controls.enabled or command_store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "observation controls are disabled")
        if f"{body.provider}:{body.user_id}" not in controls.allowed_users:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "observation user not allowlisted")
        if request.app.state.store.get(body.request_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown observation request")
        nonce = command_store.issue_nonce(
            body.provider,
            body.user_id,
            body.request_id,
            controls.nonce_ttl_seconds,
        )
        return {"nonce": nonce, "expires_in_seconds": controls.nonce_ttl_seconds}

    @app.post("/v1/admin/observation/commands", dependencies=[Depends(admin_auth)])
    async def apply_observation_command(
        body: ObservationCommandRequest, request: Request
    ) -> dict[str, Any]:
        controls = configured.live_observation.controls
        command_store = request.app.state.observation_commands
        if not controls.enabled or command_store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "observation controls are disabled")
        state = request.app.state.store.get(body.request_id)
        if state is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown observation request")
        try:
            replayed = command_store.authorize(
                provider=body.provider,
                user_id=body.user_id,
                request_id=body.request_id,
                command=body.command,
                nonce=body.nonce,
                idempotency_key=body.idempotency_key,
                allowed_users=controls.allowed_users,
                role_permissions=controls.role_permissions,
            )
        except PermissionError as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        if body.command == "pause":
            state.control_state = "paused"
        elif body.command == "resume":
            state.control_state = "running"
        elif body.command in {"reject", "terminate"}:
            state.control_state = "terminated"
            state.phase = Phase.BLOCKED
            state.final_status = "cancelled"
            request.app.state.controller.terminate_loop(state, "CLIENT_CANCELLED")
        elif body.command == "approve":
            approval_role = controls.allowed_users[f"{body.provider}:{body.user_id}"]
            if approval_role not in state.control_approvals:
                state.control_approvals.append(approval_role)
        request.app.state.store.event(
            state.session_id,
            "observation_command_applied",
            {
                "provider": body.provider,
                "command": body.command,
                "replayed": replayed,
            },
        )
        request.app.state.store.save(state)
        response: dict[str, Any] = {
            "command": body.command,
            "request_id": body.request_id,
            "replayed": replayed,
            "control_state": state.control_state,
        }
        if body.command == "show-status":
            response["status"] = {
                "phase": state.phase,
                "final_status": state.final_status,
                "review_status": state.review_status,
            }
        elif body.command == "show-findings":
            response["findings"] = [
                node
                for node in state.evidence_nodes[-20:]
                if node.get("node_type") in {"reviewer_finding", "frontier_finding"}
            ]
        elif body.command == "show-budget":
            response["budget"] = (
                state.engineering_loop.remaining_budget.model_dump(mode="json")
                if state.engineering_loop is not None
                else None
            )
        return response

    def training_store(request: Request) -> TrainingStore:
        store = request.app.state.training_store
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "training data workflow is disabled")
        return cast(TrainingStore, store)

    @app.get(
        "/v1/admin/training/candidates/{candidate_id}",
        dependencies=[Depends(admin_auth)],
    )
    async def inspect_training_candidate(candidate_id: str, request: Request) -> dict[str, Any]:
        store = training_store(request)
        try:
            candidate = store.candidate(candidate_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        return {
            "candidate": candidate.model_dump(mode="json"),
            "review_history": store.review_history(candidate_id),
        }

    @app.post(
        "/v1/admin/training/candidates/{candidate_id}/state",
        dependencies=[Depends(admin_auth)],
    )
    async def transition_training_candidate(
        candidate_id: str, body: CandidateReviewRequest, request: Request
    ) -> dict[str, Any]:
        store = training_store(request)
        actor = str(getattr(request.state, "api_token_id", "loopback-admin"))
        try:
            candidate = store.transition_candidate(
                candidate_id,
                body.target_state,
                actor=actor,
                reason=body.reason,
            )
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except PermissionError as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "candidate_id": candidate.candidate_id,
            "review_state": candidate.review_state,
        }

    @app.post(
        "/v1/admin/training/exclusions/requests",
        dependencies=[Depends(admin_auth)],
    )
    async def exclude_training_request(
        body: TrainingRequestExclusion, request: Request
    ) -> dict[str, Any]:
        store = training_store(request)
        store.tombstone(body.request_id, body.reason)
        return {"request_id": body.request_id, "excluded": True}

    @app.post(
        "/v1/admin/training/exclusions/repositories",
        dependencies=[Depends(admin_auth)],
    )
    async def exclude_training_repository(
        body: TrainingRepositoryExclusion, request: Request
    ) -> dict[str, Any]:
        store = training_store(request)
        identity_hash = store.exclude_repository(body.repository_identity, body.reason)
        return {"repository_identity_hash": identity_hash, "excluded": True}

    @app.post(
        "/v1/admin/training/exclusions/users",
        dependencies=[Depends(admin_auth)],
    )
    async def exclude_training_user(
        body: TrainingUserExclusion, request: Request
    ) -> dict[str, Any]:
        subject_hash = training_store(request).exclude_user(body.subject_id, body.reason)
        return {"training_subject_hash": subject_hash, "excluded": True}

    @app.post(
        "/v1/admin/training/retention",
        dependencies=[Depends(admin_auth)],
    )
    async def apply_training_retention(
        body: TrainingRetentionRequest, request: Request
    ) -> dict[str, Any]:
        return training_store(request).purge_retention(
            event_before=body.event_before,
            candidate_before=body.candidate_before,
            apply=body.apply,
        )

    def weekly_packager(request: Request) -> WeeklyPackager:
        packager = request.app.state.weekly_packager
        if packager is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "weekly packaging is disabled")
        return cast(WeeklyPackager, packager)

    @app.post(
        "/v1/admin/weekly-packages/verify",
        dependencies=[Depends(admin_auth)],
    )
    async def verify_weekly_package(
        body: WeeklyPackageKeyRequest, request: Request
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).verify(body.idempotency_key)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @app.post(
        "/v1/admin/weekly-packages/revoke",
        dependencies=[Depends(admin_auth)],
    )
    async def revoke_weekly_package(
        body: WeeklyPackageRevocationRequest, request: Request
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).registry.revoke(body.idempotency_key, body.reason)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @app.post(
        "/v1/admin/weekly-packages/regenerate",
        dependencies=[Depends(admin_auth)],
    )
    async def regenerate_weekly_package(
        body: WeeklyPackageKeyRequest, request: Request
    ) -> dict[str, Any]:
        try:
            packager = weekly_packager(request)
            window = packager.package_window(body.idempotency_key)
            candidates = training_store(request).packageable_candidates(
                created_from=window.utc_start.isoformat(),
                created_before=window.utc_end.isoformat(),
            )
            return packager.regenerate(body.idempotency_key, candidates)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (OSError, ValueError, PermissionError, subprocess.SubprocessError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @app.post(
        "/v1/admin/weekly-packages/retention",
        dependencies=[Depends(admin_auth)],
    )
    async def apply_weekly_retention(
        body: WeeklyRetentionRequest, request: Request
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).purge_retention(body.before, apply=body.apply)
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @app.post("/v1/admin/replay", dependencies=[Depends(admin_auth)])
    async def replay_execution(body: ReplayRequest) -> dict[str, Any]:
        if not body.exact and body.mode != "audit":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "live comparative replay requires an internal provider callback",
            )
        try:
            result = await ReplayEngine().run(
                body.snapshot,
                mode=body.mode,
                exact=body.exact,
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return result.model_dump(mode="json")

    @app.get("/metrics", dependencies=[Depends(auth)])
    async def metrics(request: Request) -> Response:
        overlays: dict[str, int | float] = {}
        skills = request.app.state.skills
        if skills is not None:
            skill_rows = skills.list_skills()
            skill_metrics = [skills.metrics(item.skill_id, item.version) for item in skill_rows]
            overlays.update(
                skill_invocations_total=sum(item.selected for item in skill_metrics),
                skill_success_total=sum(item.succeeded for item in skill_metrics),
                skill_override_total=sum(item.overridden for item in skill_metrics),
                skill_regression_total=sum(item.regressions for item in skill_metrics),
                skill_candidate_created_total=sum(
                    item.source == "generated" for item in skill_rows
                ),
                skill_promoted_total=sum(
                    item.state == "active" and item.provenance.source_trace_ids
                    for item in skill_rows
                ),
                skill_deprecated_total=sum(item.state == "deprecated" for item in skill_rows),
            )
        knowledge = request.app.state.knowledge
        if knowledge is not None:
            knowledge_rows = knowledge.list_entries()
            knowledge_metrics = [
                knowledge.metrics(item.knowledge_id, item.version) for item in knowledge_rows
            ]
            overlays.update(
                knowledge_retrieval_total=sum(item.retrieved for item in knowledge_metrics),
                knowledge_helpful_total=sum(item.helpful for item in knowledge_metrics),
                knowledge_harmful_total=sum(item.harmful for item in knowledge_metrics),
                knowledge_conflict_total=sum(item.open_conflicts for item in knowledge_metrics)
                // 2,
                knowledge_candidate_created_total=sum(
                    item.state == "candidate" for item in knowledge_rows
                ),
                knowledge_promoted_total=sum(
                    item.state == "active" and item.lifecycle.approval_id is not None
                    for item in knowledge_rows
                ),
                knowledge_deprecated_total=sum(
                    item.state == "deprecated" for item in knowledge_rows
                ),
            )
        observation_bus = request.app.state.observation
        if observation_bus is not None:
            overlays.update(
                observer_events_sent_total=observation_bus.metrics["sent"],
                observer_events_dropped_total=observation_bus.metrics["dropped"],
                discord_errors_total=observation_bus.metrics["discord_errors"],
                telegram_errors_total=observation_bus.metrics["telegram_errors"],
            )
        collector = request.app.state.training_collector
        if collector is not None:
            overlays.update(
                training_events_collected_total=collector.metrics["events"],
                training_candidates_created_total=collector.metrics["candidates"],
                training_candidates_excluded_total=collector.metrics["excluded"],
                secret_redactions_total=collector.metrics["secret_redactions"],
                privacy_exclusions_total=collector.metrics["privacy_exclusions"],
                license_exclusions_total=collector.metrics["license_exclusions"],
            )
        packager = request.app.state.weekly_packager
        if packager is not None:
            overlays.update(
                exact_duplicates_removed_total=packager.metrics["exact_duplicates_removed"],
                near_duplicates_removed_total=packager.metrics["near_duplicates_removed"],
                weekly_packages_created_total=packager.metrics["packages_created"],
                weekly_package_failures_total=packager.metrics["package_failures"],
                weekly_package_bytes=packager.metrics["package_bytes"],
                archive_verification_failures_total=packager.metrics[
                    "archive_verification_failures"
                ],
            )
        return Response(
            request.app.state.runtime_metrics.prometheus(overlays),
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/v1/models", dependencies=[Depends(auth)])
    async def models() -> dict[str, Any]:
        aliases = list(MODEL_MODES)
        return {
            "object": "list",
            "data": [
                {
                    "id": alias,
                    "object": "model",
                    "created": 0,
                    "owned_by": "local",
                    "context_length": 65_536,
                }
                for alias in aliases
            ],
            "models": [
                {
                    "slug": alias,
                    "display_name": alias,
                    "description": "Local Executor-directed Dynamic MoA model.",
                    "default_reasoning_level": None,
                    "supported_reasoning_levels": [],
                    "shell_type": "shell_command",
                    "visibility": "list",
                    "supported_in_api": True,
                    "priority": index,
                    "additional_speed_tiers": [],
                    "service_tiers": [],
                    "availability_nux": None,
                    "upgrade": None,
                    "base_instructions": (
                        "You are a coding agent. Follow the user's instructions and use the "
                        "provided tools to inspect, edit, and verify the workspace. Use native "
                        "file tools or shell for local paths and file:// URIs. Call "
                        "read_mcp_resource only with an exact server and URI returned by MCP "
                        "resource discovery; integration display names are not MCP server IDs."
                    ),
                    "model_messages": None,
                    "include_skills_usage_instructions": False,
                    "supports_reasoning_summaries": False,
                    "default_reasoning_summary": "none",
                    "support_verbosity": False,
                    "default_verbosity": None,
                    "apply_patch_tool_type": "freeform",
                    "web_search_tool_type": "text",
                    "truncation_policy": {"mode": "tokens", "limit": 10_000},
                    "supports_parallel_tool_calls": True,
                    "supports_image_detail_original": False,
                    "context_window": 65_536,
                    "max_context_window": 65_536,
                    "comp_hash": "dgx-moa-65536-v1",
                    "effective_context_window_percent": 95,
                    "experimental_supported_tools": [],
                    "input_modalities": ["text"],
                    "supports_search_tool": False,
                    "use_responses_lite": False,
                    "tool_mode": "direct",
                    "multi_agent_version": None,
                }
                for index, alias in enumerate(aliases)
            ],
        }

    @app.get("/v1/model-status", dependencies=[Depends(auth)])
    async def model_status(request: Request) -> dict[str, Any]:
        mode = configured.lifecycle_mode
        payload: dict[str, Any] = {
            "object": "list",
            "data": [status_lifecycle_record(role) for role in configured.models],
            "lifecycle_mode": mode,
            "control": (
                "disabled"
                if mode == "disabled"
                else "observe_only"
                if mode == "observe"
                else "managed"
            ),
            "unmanaged_roles": sorted(
                configured.models
                if mode == "disabled"
                else {
                    role
                    for role, model in configured.models.items()
                    if role not in configured.lifecycle_unit_map
                    and model.lifecycle_control != "external"
                }
            ),
            "idle_decisions": {
                role: decision.model_dump(mode="json")
                for role in sorted(configured.lifecycle_unit_map)
                if mode != "disabled"
                and (decision := request.app.state.lifecycle_store.latest_decision(role))
                is not None
                and decision.mode == mode
            },
            "automation": request.app.state.lifecycle_store.automation_status().model_dump(
                mode="json"
            ),
        }
        if mode == "disabled":
            payload["external_state"] = "not_lifecycle_managed"
        return payload

    @app.get("/v1/model-status/{role}", dependencies=[Depends(auth)], response_model=None)
    async def model_status_detail(role: str, request: Request) -> Response | dict[str, Any]:
        if role not in configured.models:
            return error_response(
                status.HTTP_404_NOT_FOUND,
                "unknown lifecycle role",
                "invalid_request_error",
                "model_role_not_found",
            )
        return status_lifecycle_record(role)

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    async def chat(
        body: ChatRequest,
        request: Request,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
    ) -> Response:
        accepted = time.monotonic()
        accepted_at = time.time()
        stage_status: dict[str, str] = {}
        timing_recorded = False
        terminal_finalized = False
        usage_started = False
        usage_request_id = str(uuid.uuid4())
        active_lease_ids: tuple[str, ...] = ()
        stream_lease_ids: tuple[str, ...] = ()
        first_byte_at: float | None = None
        token_usage: dict[str, int] = {}
        state: Any | None = None
        executor_started: float | None = None
        active_stage = "request"

        def record_request_timing(state: Any) -> None:
            nonlocal timing_recorded
            if timing_recorded:
                return
            state.timings_ms["completed"] = elapsed_ms(accepted)
            request.app.state.store.event(
                state.session_id,
                "request_timing",
                {
                    "timings_ms": dict(state.timings_ms),
                    "stage_status": dict(stage_status),
                },
            )
            timing_recorded = True

        profile_state = request.app.state.profiles.current()
        current_profile = profile_state["active_profile"]
        if current_profile == "judge" or profile_state["status"] in {
            "transitioning",
            "failed",
            "degraded",
        }:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "coding requests unavailable during heavy-judge profile",
                headers={"Retry-After": "30"},
            )
        model_alias = COMPATIBILITY_MODEL_ALIASES.get(body.model, body.model)
        try:
            mode = resolve_runtime_mode(model_alias, configured.model_name)
        except ValueError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown model") from error
        if "executor" not in configured.models:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "executor is not configured")
        raw = body.model_dump(exclude_none=True)
        raw["model"] = model_alias
        provided_session_id = x_session_id or str(body.metadata.get("session_id") or "")
        session_id = provided_session_id or str(uuid.uuid4())
        api_token_id = getattr(request.state, "api_token_id", "legacy")
        if not provided_session_id:
            tool_owner = request.app.state.store.find_tool_owner(
                tool_result_call_ids(raw["messages"]), api_token_id
            )
            if tool_owner is not None:
                session_id = tool_owner.session_id
        try:
            raw["max_tokens"] = request.app.state.controller.executor_tokens(raw)
        except ValueError as error:
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                str(error),
                "invalid_request_error",
                "invalid_request",
                "max_tokens",
            )
        raw["metadata"]["runtime_channel"] = x_runtime_channel or configured.runtime_channel
        raw["metadata"]["trace_origin"] = x_trace_origin or configured.trace_origin
        if x_task_id:
            raw["metadata"]["task_id"] = x_task_id
        if x_workspace_path:
            raw["metadata"]["repository"] = {
                "workspace_path": x_workspace_path,
                "workspace_identifier": x_workspace_id or x_workspace_path,
                "current_branch": x_repository_branch or "unknown",
                "current_commit": x_repository_commit or "unknown",
                "dirty_status": x_dirty_state or "unknown",
            }
        title_index = title_request_index(raw["messages"])
        if title_index is not None:
            state_session_id = f"{session_id}:title"
            raw["messages"] = [raw["messages"][title_index]]
            mode = "fast"
        else:
            state_session_id = session_id
        task_id = str(raw["metadata"].get("task_id") or "")
        request_class = classify_request(mode, raw["messages"], raw.get("tools"), raw["metadata"])
        reasoner_mode = cast(ReasonerMode | None, raw["metadata"].get("reasoner_mode"))
        required = required_roles(mode, request_class, reasoner_mode=reasoner_mode)
        optional = optional_roles(mode, reasoner_mode=reasoner_mode)
        candidate_roles = required + optional
        tracked_roles = list(candidate_roles)
        roles = required if configured.lifecycle_mode in {"fixed", "adaptive"} else candidate_roles
        degraded_roles: dict[str, str] = {}
        loading_record: LifecycleRecord | None = None
        unavailable_record: LifecycleRecord | None = None
        unmanaged_role: str | None = None
        load_triggered = False
        role_states = {role: "warm" for role in candidate_roles}
        role_load_triggered = {role: False for role in candidate_roles}
        role_ready_at: dict[str, float | None] = {role: None for role in candidate_roles}
        if configured.lifecycle_mode in {"fixed", "adaptive"}:
            for role in candidate_roles:
                is_optional = role in optional
                model = configured.models.get(role)
                if configured.specialist_routing.enabled and role in {"planner", "reviewer"}:
                    record = request.app.state.lifecycle_store.get(role)
                    role_load = False
                    if role in configured.lifecycle_unit_map and record.state != "ready":
                        check = await request.app.state.lifecycle.ensure_ready(role)
                        record = check.record
                        role_load = check.load_triggered
                    role_states[role] = "warm" if record.state == "ready" else record.state
                    role_load_triggered[role] = role_load
                    role_ready_at[role] = record.ready_at
                    load_triggered = load_triggered or role_load
                    if record.state == "ready" and is_optional:
                        roles += (role,)
                    continue
                if model is None:
                    role_states[role] = "cold"
                    if is_optional:
                        degraded_roles[role] = f"{role}_unavailable"
                    elif loading_record is None and unavailable_record is None:
                        unmanaged_role = role
                    continue
                if model.lifecycle_control == "external":
                    try:
                        healthy = await (lifecycle_health_probe or default_lifecycle_health_probe)(
                            role
                        )
                    except Exception:
                        healthy = False
                    external_record = request.app.state.lifecycle_store.recover_state(
                        role,
                        "ready" if healthy else "failed",
                        failure_class=None if healthy else "external_unavailable",
                    )
                    role_states[role] = "warm" if healthy else "cold"
                    role_ready_at[role] = external_record.ready_at
                    if not healthy:
                        if is_optional:
                            degraded_roles[role] = f"{role}_unavailable"
                        elif loading_record is None and unavailable_record is None:
                            unavailable_record = external_record
                    continue
                if role not in configured.lifecycle_unit_map:
                    role_states[role] = "cold"
                    if is_optional:
                        degraded_roles[role] = f"{role}_unavailable"
                        continue
                    if (
                        loading_record is None
                        and unavailable_record is None
                        and unmanaged_role is None
                    ):
                        unmanaged_role = role
                    continue
                check = await request.app.state.lifecycle.ensure_ready(role)
                role_states[role] = check.record.state
                role_load_triggered[role] = check.load_triggered
                role_ready_at[role] = check.record.ready_at
                load_triggered = load_triggered or check.load_triggered
                if is_optional and check.record.state != "ready":
                    degraded_roles[role] = f"{role}_unavailable"
                    continue
                if is_optional:
                    roles += (role,)
                if (
                    loading_record is None
                    and unavailable_record is None
                    and unmanaged_role is None
                    and check.record.state != "ready"
                ):
                    if (
                        request.app.state.lifecycle_store.automation_status().automation_disabled
                        or check.record.state == "failed"
                    ):
                        unavailable_record = check.record
                    else:
                        loading_record = check.record
        request.app.state.usage.start(
            RequestUsageStart(
                request_id=usage_request_id,
                session_id=str(
                    uuid.uuid5(
                        request.app.state.usage_session_namespace,
                        state_session_id,
                    )
                ),
                api_token_id=api_token_id,
                client_class=classify_client(
                    request.headers.get("user-agent") if "headers" in request.scope else None
                ),
                model_alias=cast(
                    ModelAlias,
                    model_alias,
                ),
                runtime_mode=mode,
                request_class=request_class,
                roles_required=cast(tuple[Role, ...], candidate_roles),
                accepted_at=accepted_at,
                streaming=body.stream,
                model_state=(
                    "loading"
                    if loading_record is not None
                    else "cold"
                    if unavailable_record is not None or unmanaged_role is not None
                    else "warm"
                ),
                load_triggered=load_triggered,
            )
        )
        request.app.state.usage.start_roles(
            usage_request_id,
            candidate_roles,
            session_id=state_session_id,
            requested_at=accepted_at,
            client_mode=mode,
            request_class=request_class,
            states=role_states,
            load_triggered=role_load_triggered,
            ready_at=role_ready_at,
        )
        usage_started = True

        def finalize_request(
            stage: str | None,
            status_value: RequestStatus,
            *,
            downstream_started: bool = False,
            current_state: Any | None = None,
            retryable_failure_class: RetryableFailureClass | None = None,
        ) -> None:
            nonlocal active_lease_ids, first_byte_at, state, stream_lease_ids
            nonlocal terminal_finalized
            if terminal_finalized:
                return
            terminal_finalized = True
            try:
                current = current_state or state or request.app.state.store.get(state_session_id)
                if stage is not None:
                    stage_status[stage] = status_value
                if downstream_started:
                    first_byte_at = first_byte_at or time.time()
                if current is not None:
                    if state is None:
                        current.timings_ms = {"accepted": 0.0}
                        state = current
                    if status_value == "cancelled":
                        current.final_status = "cancelled"
                        request.app.state.controller.terminate_loop(current, "CLIENT_CANCELLED")
                    elif (
                        status_value in {"failed", "timed_out"}
                        and current.final_status != "blocked"
                    ):
                        current.final_status = "failed"
                    if executor_started is not None:
                        current.timings_ms.setdefault(
                            "executor_total",
                            round((time.monotonic() - executor_started) * 1000, 3),
                        )
                    if downstream_started:
                        current.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
                    request.app.state.controller.complete_loop_iteration(current, status_value)
                    record_request_timing(current)
                    request.app.state.store.event(
                        current.session_id,
                        "session_ended",
                        {"request_id": state_session_id, "status": status_value},
                    )
                    request.app.state.store.save(current)
                    record_trace_safely(request, current, task_id)
                if usage_started:
                    completed_at = time.time()
                    request.app.state.usage.finalize(
                        usage_request_id,
                        RequestUsageFinalization(
                            first_byte_at=first_byte_at,
                            completed_at=completed_at,
                            active_duration_seconds=time.monotonic() - accepted,
                            status=status_value,
                            retryable_failure_class=retryable_failure_class,
                            prompt_tokens=token_usage.get("prompt_tokens"),
                            completion_tokens=token_usage.get("completion_tokens"),
                            total_tokens=token_usage.get("total_tokens"),
                        ),
                    )
                    request.app.state.usage.finalize_roles(
                        usage_request_id,
                        completed_at=completed_at,
                        first_byte_at=first_byte_at,
                        success=status_value == "completed",
                        failure_class=retryable_failure_class or stage,
                        ready_at={
                            role: (
                                request.app.state.lifecycle_store.get(role).ready_at
                                if role in configured.models
                                else None
                            )
                            for role in tracked_roles
                        },
                        role_failures=degraded_roles,
                    )
            finally:
                request.app.state.lifecycle_store.release_leases(
                    (*stream_lease_ids, *active_lease_ids)
                )
                active_lease_ids = ()
                stream_lease_ids = ()

        if loading_record is not None:
            finalize_request(
                "model_loading",
                "failed",
                retryable_failure_class="model_loading",
            )
            return loading_response(loading_record)
        if unavailable_record is not None or unmanaged_role is not None:
            finalize_request(
                "model_unavailable",
                "failed",
            )
            unavailable_role = unmanaged_role
            if unavailable_role is None:
                assert unavailable_record is not None
                unavailable_role = unavailable_record.role
            return unavailable_response(
                unavailable_role,
                record=unavailable_record,
            )

        ensured_roles = list(roles)
        try:
            initial_lease_roles = tuple(
                role
                for role in roles
                if not (configured.specialist_routing.enabled and role in {"planner", "reviewer"})
            )
            active_lease_ids = tuple(
                lease.lease_id
                for lease in await request.app.state.lifecycle.acquire_request_leases(
                    usage_request_id,
                    initial_lease_roles,
                    kind="active_request",
                    require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
                )
            )
        except LifecycleNotReadyError as error:
            record = error.record
            if record.state == "failed":
                finalize_request("model_unavailable", "failed")
                return unavailable_response(record.role, record=record)
            finalize_request(
                "model_loading",
                "failed",
                retryable_failure_class="model_loading",
            )
            return loading_response(record)

        async def ensure_dynamic_roles(selected_roles: tuple[str, ...]) -> None:
            nonlocal active_lease_ids, load_triggered
            new_roles = tuple(role for role in selected_roles if role not in ensured_roles)
            if not new_roles:
                return
            new_states: dict[str, str] = {}
            new_loads: dict[str, bool] = {}
            new_ready_at: dict[str, float | None] = {}
            not_ready: LifecycleRecord | None = None
            unmanaged: str | None = None
            lease_roles: list[str] = []
            for role in new_roles:
                model = configured.models.get(role)
                if configured.specialist_routing.enabled and role in {"planner", "reviewer"}:
                    record = request.app.state.lifecycle_store.get(role)
                    role_load = False
                    if role in configured.lifecycle_unit_map and record.state != "ready":
                        check = await request.app.state.lifecycle.ensure_ready(role)
                        record = check.record
                        role_load = check.load_triggered
                        load_triggered = load_triggered or role_load
                    new_states[role] = "warm" if record.state == "ready" else record.state
                    new_loads[role] = role_load
                    new_ready_at[role] = record.ready_at
                    continue
                if model is None:
                    unmanaged = unmanaged or role
                    new_states[role] = "cold"
                    new_loads[role] = False
                    new_ready_at[role] = None
                    continue
                role_load = False
                record = request.app.state.lifecycle_store.get(role)
                if configured.lifecycle_mode in {"fixed", "adaptive"}:
                    if model.lifecycle_control == "external":
                        try:
                            healthy = await (
                                lifecycle_health_probe or default_lifecycle_health_probe
                            )(role)
                        except Exception:
                            healthy = False
                        record = request.app.state.lifecycle_store.recover_state(
                            role,
                            "ready" if healthy else "failed",
                            failure_class=None if healthy else "external_unavailable",
                        )
                    elif role not in configured.lifecycle_unit_map:
                        unmanaged = unmanaged or role
                        not_ready = not_ready or record
                    else:
                        check = await request.app.state.lifecycle.ensure_ready(role)
                        record = check.record
                        role_load = check.load_triggered
                        load_triggered = load_triggered or role_load
                    if record.state != "ready":
                        not_ready = not_ready or record
                new_states[role] = (
                    "warm"
                    if record.state == "ready" or configured.lifecycle_mode == "disabled"
                    else record.state
                )
                new_loads[role] = role_load
                new_ready_at[role] = record.ready_at
                lease_roles.append(role)
            tracked_roles.extend(role for role in new_roles if role not in tracked_roles)
            ensured_roles.extend(new_roles)
            request.app.state.usage.add_required_roles(usage_request_id, new_roles)
            request.app.state.usage.start_roles(
                usage_request_id,
                new_roles,
                session_id=state_session_id,
                requested_at=accepted_at,
                client_mode=mode,
                request_class=request_class,
                states=new_states,
                load_triggered=new_loads,
                ready_at=new_ready_at,
            )
            if unmanaged is not None:
                request.app.state.usage.update_model_state(usage_request_id, "cold")
                raise DynamicRoleUnmanagedError(unmanaged)
            if not_ready is not None:
                request.app.state.usage.update_model_state(
                    usage_request_id, "loading" if any(new_loads.values()) else "cold"
                )
                raise LifecycleNotReadyError(not_ready)
            leases = await request.app.state.lifecycle.acquire_request_leases(
                usage_request_id,
                lease_roles,
                kind="active_request",
                require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
            )
            active_lease_ids = (*active_lease_ids, *(lease.lease_id for lease in leases))

        try:
            continuation_owner = continuation_correlation(state_session_id)
            if has_matching_tool_result(raw["messages"]):
                request.app.state.lifecycle_store.release_continuation(
                    "executor", continuation_owner
                )
            state = request.app.state.controller.session(state_session_id, raw["messages"])
            state.current_request_id = usage_request_id
            state.api_token_id = api_token_id
            task_id = task_id or state.task_id or state_session_id
            raw["metadata"]["task_id"] = task_id
            state.timings_ms = {"accepted": 0.0}
            for role, reason in degraded_roles.items():
                stage_status[role] = "unavailable"
                request.app.state.store.event(
                    state_session_id,
                    "role_degraded",
                    {"role": role, "reason": reason},
                )
            request.app.state.store.event(
                state_session_id,
                "request_received",
                {
                    "stream": body.stream,
                    "task_id": task_id,
                    **(
                        {
                            "prompt": state.objective[
                                : configured.live_observation.max_content_characters
                            ]
                        }
                        if configured.live_observation.include_prompt
                        else {}
                    ),
                },
            )
            state.runtime_mode = mode
            state.request_class = request_class
            state.roles_required = list(roles)
            state.review_fail_closed = review_fails_closed(request_class)
            request.app.state.controller.select_route(state, raw["metadata"])
            stream_judge_reasons = (
                request.app.state.controller.remote_judge_invocation_reasons(state, raw["metadata"])
                if body.stream
                else []
            )
            if stream_judge_reasons:
                request.app.state.store.event(
                    state_session_id,
                    "remote_judge_non_stream_required",
                    {"reasons": stream_judge_reasons},
                )
                finalize_request("judge", "failed", current_state=state)
                return error_response(
                    status.HTTP_409_CONFLICT,
                    "selective Remote Judge validation requires a non-streaming request",
                    "judge_non_stream_required",
                    "retry_without_streaming",
                    headers={"X-Session-ID": state_session_id},
                )
            if body.metadata.get("no_progress"):
                request.app.state.controller.note_no_progress(state)
            active_stage = "planner" if "planner" in roles else "request"
            prepared = await request.app.state.controller.prepare_executor(
                state, raw, roles, ensure_dynamic_roles
            )
            if state.engineering_loop is not None and prepared.get("tools"):
                prepared["parallel_tool_calls"] = False
                if state.engineering_loop.remaining_budget.tool_calls == 0:
                    prepared["tool_choice"] = "none"
                    request.app.state.store.event(
                        state_session_id,
                        "engineering_loop_tool_budget_closed",
                        {"loop_id": state.engineering_loop.loop_id},
                    )
            if "planner" in state.timings_ms:
                stage_status["planner"] = "completed"
            if "reviewer" in state.timings_ms:
                stage_status["reviewer"] = (
                    "completed" if state.review_status in {"approved", "rejected"} else "failed"
                )
            active_stage = "executor_first_byte" if body.stream else "executor_total"
            executor_started = time.monotonic()
            state.timings_ms["upstream_start"] = elapsed_ms(accepted)
            request.app.state.store.event(
                state_session_id,
                "executor_started",
                {"role": "executor", "phase": state.phase},
            )
            if body.stream:
                stream_lease_ids = tuple(
                    lease.lease_id
                    for lease in await request.app.state.lifecycle.acquire_request_leases(
                        usage_request_id,
                        ("executor",),
                        kind="open_stream",
                        require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
                    )
                )
                upstream = await request.app.state.provider.stream(
                    "executor",
                    configured.models["executor"],
                    prepared,
                    timeout_seconds=configured.limits.executor_first_byte_timeout_seconds,
                    stage="executor_first_byte",
                )
                state.timings_ms["first_upstream_byte"] = elapsed_ms(accepted)
                stage_status["executor_first_byte"] = "completed"
                observation = StreamObservation(configured.limits.max_stream_capture_bytes)
                stream_completed = False
                stream_cleanup_lock = asyncio.Lock()
                stream_cleaned = False

                async def finish_stream() -> None:
                    nonlocal stream_cleaned
                    async with stream_cleanup_lock:
                        if stream_cleaned:
                            return
                        stream_cleaned = True
                        terminal = stream_completed or observation.done_seen
                        state.timings_ms["executor_total"] = round(
                            (time.monotonic() - executor_started) * 1000, 3
                        )
                        stage_status.setdefault(
                            "executor_total", "completed" if terminal else "aborted"
                        )
                        terminal_status: RequestStatus = (
                            "completed"
                            if terminal
                            else "timed_out"
                            if stage_status.get("executor_total") == "timed_out"
                            else "failed"
                            if stage_status.get("executor_total") == "failed"
                            else "cancelled"
                        )
                        try:
                            state.finish_reasons = observation.finish_reasons
                            state.truncated = "length" in observation.finish_reasons
                            if terminal and "reviewer" in state.roles_required:
                                state.review_deferred = True
                                state.review_status = "deferred"
                                stage_status["reviewer"] = "deferred"
                            if state.decisions:
                                state.decisions[-1]["outcome"] = {
                                    "status": "success" if terminal else "failure",
                                    "progress_made": bool(observation.finish_reasons),
                                    "state_changed": False,
                                    "scope_changed": False,
                                    "validation_triggered": False,
                                    "next_phase": state.phase,
                                }
                            token_usage.update(observation.usage)
                            request.app.state.controller.record_observed_invocation(
                                state,
                                {
                                    "role": "executor",
                                    "mode": "final_synthesis",
                                    "latency_ms": state.timings_ms["executor_total"],
                                    "prompt_tokens": observation.usage.get("prompt_tokens"),
                                    "completion_tokens": observation.usage.get("completion_tokens"),
                                    "total_tokens": observation.usage.get("total_tokens"),
                                    "status": "completed" if terminal else terminal_status,
                                },
                                account_loop_usage=False,
                            )
                            if terminal and "tool_calls" in observation.finish_reasons:
                                state.pending_tool_call_ids = list(
                                    dict.fromkeys(
                                        [
                                            *state.pending_tool_call_ids,
                                            *observation.tool_call_ids,
                                        ]
                                    )
                                )[-configured.limits.max_steps :]
                                if observation.tool_call_ids:
                                    state.last_tool_call = {"id": observation.tool_call_ids[-1]}
                                request.app.state.lifecycle_store.refresh_continuation(
                                    usage_request_id,
                                    "executor",
                                    continuation_owner,
                                    expires_at=(
                                        lifecycle_clock()
                                        + configured.lifecycle.continuation_lease_ttl_seconds
                                    ),
                                )
                            request.app.state.store.event(
                                state_session_id,
                                "assistant_stream_finished",
                                {"finish_reasons": observation.finish_reasons},
                            )
                            request.app.state.store.event(
                                state_session_id,
                                "stream_completed" if terminal else "stream_aborted",
                                {},
                            )
                        finally:
                            try:
                                close = getattr(upstream, "aclose", None)
                                if close is not None:
                                    await close()
                            finally:
                                finalize_request(
                                    None,
                                    terminal_status,
                                    current_state=state,
                                    retryable_failure_class=(
                                        "executor_total_timeout"
                                        if terminal_status == "timed_out"
                                        else "backend_error"
                                        if terminal_status == "failed"
                                        else None
                                    ),
                                )

                async def stream_response() -> AsyncIterator[bytes]:
                    nonlocal first_byte_at, stream_completed
                    admitted_tool_calls = 0
                    accounted_total_tokens = 0
                    forwarder = forward_sse(
                        upstream,
                        observation,
                        max_event_bytes=configured.limits.max_sse_event_bytes,
                    )
                    try:
                        async with asyncio.timeout_at(
                            executor_started + configured.limits.executor_total_timeout_seconds
                        ):
                            async with aclosing(forwarder):
                                async for chunk in forwarder:
                                    required_admissions = max(
                                        len(observation.tool_call_ids),
                                        1 if observation.tool_delta_seen else 0,
                                    )
                                    while admitted_tool_calls < required_admissions:
                                        request.app.state.controller.admit_tool_call(
                                            state,
                                            observation.tool_call_names.get(admitted_tool_calls),
                                        )
                                        admitted_tool_calls += 1
                                    observed_total_tokens = observation.usage.get("total_tokens", 0)
                                    if observed_total_tokens > accounted_total_tokens:
                                        request.app.state.controller.record_loop_usage(
                                            state,
                                            total_tokens=(
                                                observed_total_tokens - accounted_total_tokens
                                            ),
                                        )
                                        accounted_total_tokens = observed_total_tokens
                                    if "first_downstream_byte" not in state.timings_ms:
                                        state.timings_ms["first_downstream_byte"] = elapsed_ms(
                                            accepted
                                        )
                                        first_byte_at = time.time()
                                    yield chunk
                        stream_completed = True
                    except TimeoutError as error:
                        stage_status["executor_total"] = "timed_out"
                        raise StageTimeout("executor_total") from error
                    except asyncio.CancelledError:
                        stage_status["executor_total"] = "cancelled"
                        if not observation.done_seen:
                            state.final_status = "cancelled"
                        raise
                    except Exception:
                        stage_status["executor_total"] = "failed"
                        raise
                    finally:
                        await finish_stream()

                return ResponseOwnedStreamingResponse(
                    ResponseOwnedIterator(stream_response(), finish_stream),
                    media_type="text/event-stream",
                    headers={"X-Session-ID": session_id},
                )
            response = await request.app.state.provider.complete(
                "executor",
                configured.models["executor"],
                prepared,
                timeout_seconds=configured.limits.executor_total_timeout_seconds,
                stage="executor_total",
            )
            state.timings_ms["first_upstream_byte"] = elapsed_ms(accepted)
            state.timings_ms["executor_total"] = round(
                (time.monotonic() - executor_started) * 1000, 3
            )
            stage_status["executor_total"] = "completed"
            token_usage.update(reported_usage(response.get("usage")))
            request.app.state.controller.record_invocation(
                state,
                "executor",
                response,
                executor_started,
                mode="final_synthesis",
            )
            validate_assistant_response(response)
            assistant_message = response.get("choices", [{}])[0].get("message", {})
            assistant_tool_calls = assistant_message.get("tool_calls") or []
            for call in assistant_tool_calls:
                request.app.state.controller.admit_tool_call(
                    state,
                    str(call.get("function", {}).get("name", "")) or None,
                )
            assistant_tool_call_ids = [
                str(call.get("id"))
                for call in assistant_tool_calls
                if isinstance(call, dict) and call.get("id")
            ]
            if assistant_tool_call_ids:
                state.pending_tool_call_ids = list(
                    dict.fromkeys([*state.pending_tool_call_ids, *assistant_tool_call_ids])
                )[-configured.limits.max_steps :]
                state.last_tool_call = assistant_tool_calls[-1]
            request.app.state.controller.record_evidence(
                state,
                "final_synthesis",
                "executor",
                {
                    "finish_reason": response.get("choices", [{}])[0].get("finish_reason"),
                    "has_tool_calls": bool(assistant_message.get("tool_calls")),
                    "derived_confidence": state.derived_confidence,
                },
                generated_from=state.last_decision_id,
            )
            if state.decisions:
                state.decisions[-1]["structured_decision"] = assistant_message
                state.decisions[-1]["outcome"] = {
                    "status": "success",
                    "progress_made": True,
                    "state_changed": False,
                    "scope_changed": False,
                    "validation_triggered": bool(body.metadata.get("executor_complete")),
                    "next_phase": state.phase,
                }
            finish_reason = response.get("choices", [{}])[0].get("finish_reason")
            state.finish_reasons = [str(finish_reason)] if finish_reason else []
            state.truncated = finish_reason == "length"
            judge_reasons = request.app.state.controller.remote_judge_invocation_reasons(
                state, body.metadata, response
            )
            if judge_reasons and "reviewer" not in state.roles_required:
                await ensure_dynamic_roles(("reviewer",))
                state.roles_required.append("reviewer")
            if (
                "reviewer" in state.roles_required
                and state.review_status != "approved"
                and (
                    bool(judge_reasons)
                    or request.app.state.controller.has_review_evidence(state, body.metadata)
                )
            ):
                review_observation = request.app.state.controller.review_observation(
                    state, response, body.metadata
                )
                active_stage = "reviewer"
                try:
                    async with request.app.state.reviewer_evaluation_lock:
                        reviewer = request.app.state.lifecycle_store.get("reviewer")
                        if reviewer.evaluation_guard:
                            raise ValueError("reviewer evaluation guard is already active")
                        guard_transition_id = reviewer.transition_id
                        request.app.state.lifecycle_store.set_guard(
                            "reviewer",
                            "evaluation_guard",
                            True,
                            expected_transition_id=guard_transition_id,
                        )
                        try:
                            await request.app.state.controller.review(
                                state,
                                review_observation,
                                guard_already_owned=True,
                            )
                        finally:
                            request.app.state.lifecycle_store.set_guard(
                                "reviewer",
                                "evaluation_guard",
                                False,
                                expected_transition_id=guard_transition_id,
                            )
                except (httpx.HTTPError, StageTimeout, ValueError) as error:
                    state.review_status = "failed"
                    stage_status["reviewer"] = (
                        "timed_out" if isinstance(error, StageTimeout) else "failed"
                    )
                    request.app.state.store.event(
                        state_session_id,
                        "review_failed",
                        {"error_type": type(error).__name__},
                    )
                    if not state.review_fail_closed:
                        state.observability_degraded = True
                        state.observability_status = "degraded"
                    request.app.state.store.save(state)
                    if state.review_fail_closed:
                        if isinstance(error, StageTimeout):
                            raise
                        raise ValueError(f"review failed: {error}") from error
                else:
                    stage_status["reviewer"] = "completed"
                    if not state.truncated:
                        request.app.state.controller.apply_metadata(state, body.metadata)
            judge_reasons = list(
                dict.fromkeys(
                    [
                        *judge_reasons,
                        *request.app.state.controller.remote_judge_invocation_reasons(
                            state, body.metadata, response
                        ),
                    ]
                )
            )
            if judge_reasons and not state.truncated:
                request.app.state.store.event(
                    state_session_id,
                    "remote_judge_selected",
                    {"reasons": judge_reasons},
                )
                active_stage = "judge"
                observation = request.app.state.controller.review_observation(
                    state, response, body.metadata
                )
                verdict = await request.app.state.controller.judge(state, observation)
                stage_status["judge"] = "completed"
                if verdict.get("verdict") != "approve":
                    correction_verdict = str(verdict.get("verdict", "revise"))
                    if correction_verdict in {
                        "approve_with_edits",
                        "revise",
                        "retry_with_evidence",
                    }:
                        correction_request = dict(prepared)
                        correction_request["stream"] = False
                        correction_request["messages"] = [
                            *prepared.get("messages", []),
                            assistant_message,
                            {
                                "role": "system",
                                "content": (
                                    "Apply only the bounded Remote Judge corrections below. "
                                    "Preserve verified content, do not claim unobserved tests or "
                                    "tool results, and return a complete corrected final answer.\n"
                                    + json.dumps(
                                        {
                                            "findings": verdict.get("findings", []),
                                            "required_edits": verdict.get("required_edits", []),
                                        },
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    )
                                ),
                            },
                        ]
                        request.app.state.store.event(
                            state_session_id,
                            "judge_correction_started",
                            {"verdict": correction_verdict},
                        )
                        active_stage = "executor_total"
                        correction_started = time.monotonic()
                        response = await request.app.state.provider.complete(
                            "executor",
                            configured.models["executor"],
                            correction_request,
                            timeout_seconds=configured.limits.executor_total_timeout_seconds,
                            stage="judge_correction",
                        )
                        token_usage.update(reported_usage(response.get("usage")))
                        request.app.state.controller.record_invocation(
                            state,
                            "executor",
                            response,
                            correction_started,
                            mode="judge_correction",
                        )
                        validate_assistant_response(response)
                        assistant_message = response.get("choices", [{}])[0].get("message", {})
                        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
                        state.finish_reasons = [str(finish_reason)] if finish_reason else []
                        state.truncated = finish_reason == "length"
                        if finish_reason == "length" or assistant_message.get("tool_calls"):
                            raise JudgeCorrectionRequired(correction_verdict)
                        request.app.state.controller.record_evidence(
                            state,
                            "final_synthesis",
                            "executor",
                            {
                                "finish_reason": finish_reason,
                                "has_tool_calls": False,
                                "correction_applied": True,
                            },
                            generated_from=state.last_decision_id,
                        )
                        active_stage = "reviewer"
                        corrected_observation = request.app.state.controller.review_observation(
                            state, response, body.metadata
                        )
                        targeted_review = await request.app.state.controller.review(
                            state, corrected_observation
                        )
                        stage_status["reviewer"] = "completed"
                        if targeted_review.get("status") != "approved":
                            raise JudgeCorrectionRequired(correction_verdict)
                        important_correction = any(
                            finding.get("severity") in {"important", "critical"}
                            for finding in verdict.get("findings", [])
                            if isinstance(finding, dict)
                        )
                        recheck_needed = bool(
                            important_correction and verdict.get("recheck_required")
                        )
                        if recheck_needed:
                            active_stage = "judge"
                            verdict = await request.app.state.controller.judge(
                                state, corrected_observation
                            )
                            stage_status["judge"] = "completed"
                            if verdict.get("verdict") != "approve":
                                raise JudgeCorrectionRequired(
                                    str(verdict.get("verdict", correction_verdict))
                                )
                        request.app.state.store.event(
                            state_session_id,
                            "judge_correction_completed",
                            {
                                "targeted_validation": "approved",
                                "rechecked": recheck_needed,
                            },
                        )
                    else:
                        raise JudgeCorrectionRequired(correction_verdict)
            state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
            first_byte_at = time.time()
            request.app.state.store.event(
                state_session_id,
                "assistant_stream_finished",
                {"finish_reasons": [finish_reason] if finish_reason else []},
            )
            if finish_reason == "tool_calls" or assistant_message.get("tool_calls"):
                request.app.state.lifecycle_store.refresh_continuation(
                    usage_request_id,
                    "executor",
                    continuation_owner,
                    expires_at=(
                        lifecycle_clock() + configured.lifecycle.continuation_lease_ttl_seconds
                    ),
                )
            finalize_request(None, "completed", current_state=state)
            return JSONResponse(response, headers={"X-Session-ID": session_id})
        except asyncio.CancelledError:
            current = state or request.app.state.store.get(state_session_id)
            if current is not None:
                current.final_status = "cancelled"
                if body.stream:
                    request.app.state.store.event(state_session_id, "stream_aborted", {})
            finalize_request(
                active_stage,
                "cancelled",
                downstream_started=False,
                current_state=current,
            )
            raise
        except DuplicateFailedCall as error:
            finalize_request(active_stage, "failed", downstream_started=True)
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except LoopAdmissionError as error:
            termination = (
                state.engineering_loop.termination_reason
                if state is not None and state.engineering_loop is not None
                else None
            )
            finalize_request(active_stage, "failed", downstream_started=True)
            return error_response(
                status.HTTP_409_CONFLICT,
                str(error),
                "loop_admission_error",
                "loop_budget_exhausted"
                if termination == "BUDGET_EXHAUSTED"
                else "loop_new_evidence_required",
            )
        except PolicyBlocked as error:
            finalize_request(active_stage, "failed", downstream_started=True)
            return error_response(
                status.HTTP_403_FORBIDDEN,
                str(error),
                "policy_blocked",
                "approval_required" if "approval" in str(error) else "request_denied",
            )
        except FrontierRequiredUnavailable as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                "frontier",
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(error),
                "frontier_unavailable",
                "frontier_required_unavailable",
                headers={"Retry-After": "30"},
            )
        except JudgeRequired as error:
            finalize_request("judge", "failed")
            return error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(error),
                "judge_required",
                "heavy_judge_adjudication_required",
                headers={
                    "Retry-After": "30",
                    "X-Session-ID": error.session_id,
                    "X-DGX-MOA-Required-Profile": "judge",
                },
            )
        except JudgeCorrectionRequired as error:
            finalize_request("judge", "failed", downstream_started=True)
            return error_response(
                status.HTTP_409_CONFLICT,
                str(error),
                "judge_correction_required",
                error.verdict,
                headers={"X-Session-ID": state_session_id},
            )
        except JudgeProviderError as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                "judge",
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(error),
                "judge_unavailable",
                "remote_judge_provider_unavailable",
                headers={"Retry-After": "30", "X-Session-ID": state_session_id},
            )
        except ReasonerUnavailable as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                "reasoner",
                "failed",
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(error),
                "reasoner_unavailable",
                "reasoner_required_unavailable",
                headers={"Retry-After": "30", "X-DGX-MOA-Model-Role": "reasoner"},
            )
        except DynamicRoleUnmanagedError as error:
            finalize_request("model_unavailable", "failed")
            return unavailable_response(error.role)
        except LifecycleNotReadyError as error:
            record = error.record
            retryable = record.state != "failed"
            finalize_request(
                "model_loading" if retryable else "model_unavailable",
                "failed",
                retryable_failure_class="model_loading" if retryable else None,
            )
            return (
                loading_response(record)
                if retryable
                else unavailable_response(record.role, record=record)
            )
        except StageTimeout as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                error.stage,
                "timed_out",
                downstream_started=True,
                retryable_failure_class=TIMEOUT_FAILURE_CLASSES.get(error.stage),
            )
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                f"{error.stage}_timeout",
            )
        except httpx.TimeoutException as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            phase = state.phase.value if state is not None else ""
            stage = {
                "planning": "planner",
                "reviewing": "reviewer",
                "heavy_review": "judge",
            }.get(phase, "executor")
            finalize_request(
                active_stage,
                "timed_out",
                downstream_started=True,
                retryable_failure_class=TIMEOUT_FAILURE_CLASSES.get(stage),
            )
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                f"{stage}_timeout",
            )
        except httpx.HTTPStatusError as error:
            if state is not None and error.response.status_code >= 500:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class=(
                    "backend_error" if error.response.status_code >= 500 else None
                ),
            )
            try:
                payload = error.response.json()
            except (ValueError, httpx.StreamError):
                payload = None
            upstream_error = payload.get("error") if isinstance(payload, dict) else None
            if (
                isinstance(upstream_error, dict)
                and isinstance(upstream_error.get("message"), str)
                and isinstance(upstream_error.get("type"), str)
                and isinstance(upstream_error.get("code"), str)
                and (
                    upstream_error.get("param") is None or isinstance(upstream_error["param"], str)
                )
            ):
                return JSONResponse(payload, status_code=error.response.status_code)
            if error.response.status_code < 500:
                return error_response(
                    error.response.status_code,
                    str(error),
                    "invalid_request_error",
                    "invalid_request",
                )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except httpx.HTTPError as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except ValueError as error:
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            if str(error) == "max_tokens exceeds server maximum 16384":
                return error_response(
                    status.HTTP_400_BAD_REQUEST,
                    str(error),
                    "invalid_request_error",
                    "invalid_request",
                    "max_tokens",
                )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )
        except Exception as error:
            if state is not None:
                request.app.state.controller.terminate_loop(state, "INTERNAL_FAILURE")
            finalize_request(
                active_stage,
                "failed",
                downstream_started=True,
                retryable_failure_class="backend_error",
            )
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "backend_error",
            )

    @app.post("/v1/judge/adjudications/{session_id}", dependencies=[Depends(auth)])
    async def adjudicate(session_id: str, request: Request) -> Response:
        profile = request.app.state.profiles.current()
        remote = request.app.state.remote_judge is not None
        if not remote and (
            profile.get("active_profile") != "judge" or profile.get("status") != "ready"
        ):
            return error_response(
                status.HTTP_409_CONFLICT,
                "Heavy Judge profile is not ready",
                "profile_conflict",
                "judge_profile_required",
            )
        state = request.app.state.store.get(session_id)
        if state is None:
            return error_response(
                status.HTTP_404_NOT_FOUND,
                "adjudication session not found",
                "invalid_request_error",
                "session_not_found",
            )
        if state.judge_status != "required" or not state.pending_judge_evidence:
            return error_response(
                status.HTTP_409_CONFLICT,
                "session has no pending Heavy Judge adjudication",
                "invalid_request_error",
                "judge_not_pending",
            )
        request_id = str(uuid.uuid4())
        state.current_request_id = request_id
        leases = await request.app.state.lifecycle.acquire_request_leases(
            request_id,
            () if remote else ("judge",),
            kind="active_request",
            require_ready=False,
        )
        try:
            verdict = await request.app.state.controller.judge(state, state.pending_judge_evidence)
            request.app.state.store.save(state)
            record_trace_safely(request, state, state.task_id or session_id)
        except StageTimeout as error:
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(error),
                "timeout_error",
                "judge_timeout",
            )
        except (httpx.HTTPError, ValueError) as error:
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                str(error),
                "backend_error",
                "judge_backend_error",
            )
        finally:
            request.app.state.lifecycle_store.release_leases(
                tuple(lease.lease_id for lease in leases)
            )
        return JSONResponse(
            {
                "object": "judge.adjudication",
                "session_id": session_id,
                "status": state.judge_status,
                "verdict": verdict,
                "resume_profile": None if remote else "resident",
            }
        )

    @app.post("/v1/responses", dependencies=[Depends(auth)])
    async def responses(
        body: ResponsesRequest,
        request: Request,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
    ) -> Response:
        messages = _coerce_responses_input_messages(body.input)
        if body.instructions:
            messages.insert(0, {"role": "developer", "content": body.instructions})
        tools = _coerce_responses_tools(body.tools)
        custom_tool_names = {
            str(tool.get("name"))
            for tool in body.tools or []
            if tool.get("type") == "custom" and tool.get("name")
        }
        response_model = COMPATIBILITY_MODEL_ALIASES.get(body.model, body.model)

        tool_choice = body.tool_choice
        if isinstance(tool_choice, dict) and tool_choice.get("type") in {"function", "custom"}:
            tool_choice = {
                "type": "function",
                "function": {"name": tool_choice.get("name")},
            }
        chat_body = ChatRequest(
            model=response_model,
            messages=[ChatMessage.model_validate(message) for message in messages],
            stream=body.stream,
            stream_options={"include_usage": True} if body.stream else None,
            tools=tools,
            tool_choice=tool_choice if tools else None,
            parallel_tool_calls=body.parallel_tool_calls if tools else None,
            metadata=body.metadata,
            max_tokens=body.max_output_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            stop=body.stop,
        )
        if body.stream:
            response_session_id = (
                x_session_id or str(body.metadata.get("session_id") or "") or str(uuid.uuid4())
            )

            async def response_stream() -> AsyncIterator[bytes]:
                chat_task: asyncio.Task[Response] | None = None
                loading_deadline = time.monotonic() + configured.limits.model_load_timeout_seconds
                initial_heartbeat_sent = False
                try:
                    while True:
                        chat_task = asyncio.create_task(
                            chat(
                                chat_body,
                                request,
                                response_session_id,
                                x_runtime_channel,
                                x_trace_origin,
                                x_task_id,
                                x_workspace_path,
                                x_workspace_id,
                                x_repository_branch,
                                x_repository_commit,
                                x_dirty_state,
                            )
                        )
                        if not initial_heartbeat_sent:
                            initial_heartbeat_sent = True
                            yield b": keep-alive\n\n"
                        while not chat_task.done():
                            await asyncio.wait((chat_task,), timeout=15)
                            if not chat_task.done():
                                yield b": keep-alive\n\n"
                        try:
                            chat_result = chat_task.result()
                        except HTTPException as error:
                            error_type = (
                                "invalid_request_error"
                                if error.status_code
                                in {
                                    status.HTTP_503_SERVICE_UNAVAILABLE,
                                    status.HTTP_404_NOT_FOUND,
                                }
                                else "backend_error"
                            )
                            async for chunk in responses_error_sse(
                                response_model,
                                session_id=response_session_id,
                                error_type=error_type,
                                code=(
                                    "invalid_request"
                                    if error_type == "invalid_request_error"
                                    else "backend_error"
                                ),
                                source="chat_http_exception",
                                status_code=error.status_code,
                            ):
                                yield chunk
                            return
                        except Exception as error:
                            async for chunk in responses_error_sse(
                                response_model,
                                session_id=response_session_id,
                                error_type="backend_error",
                                code="backend_error",
                                source="chat_unhandled_exception",
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                failure_class=type(error).__name__,
                            ):
                                yield chunk
                            return
                        if isinstance(chat_result, StreamingResponse):
                            async for chunk in responses_sse(
                                chat_result.body_iterator,
                                response_model,
                                custom_tool_names=custom_tool_names,
                                session_id=response_session_id,
                            ):
                                yield chunk
                            return
                        chat_payload = _chat_response_payload(chat_result)
                        upstream_error = chat_payload.get("error") if chat_payload else None
                        if (
                            chat_result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                            and isinstance(upstream_error, dict)
                            and upstream_error.get("code") == "model_loading"
                            and time.monotonic() < loading_deadline
                        ):
                            retry_after = min(
                                float(chat_result.headers.get("Retry-After", "30")),
                                max(0.0, loading_deadline - time.monotonic()),
                            )
                            while retry_after > 0:
                                delay = min(15.0, retry_after)
                                await asyncio.sleep(delay)
                                retry_after -= delay
                                yield b": keep-alive\n\n"
                            continue
                        async for chunk in responses_error_sse(
                            response_model,
                            session_id=response_session_id,
                            error_type=(
                                str(upstream_error.get("type", "backend_error"))
                                if isinstance(upstream_error, dict)
                                else "backend_error"
                            ),
                            code=(
                                str(upstream_error.get("code", "backend_error"))
                                if isinstance(upstream_error, dict)
                                else "backend_error"
                            ),
                            source="chat_non_stream_response",
                            status_code=chat_result.status_code,
                        ):
                            yield chunk
                        return
                finally:
                    if chat_task is not None and not chat_task.done():
                        chat_task.cancel()
                        await asyncio.gather(chat_task, return_exceptions=True)

            return StreamingResponse(
                response_stream(),
                media_type="text/event-stream",
                headers={"X-Session-ID": response_session_id, "Cache-Control": "no-cache"},
            )
        try:
            chat_response = await chat(
                chat_body,
                request,
                x_session_id,
                x_runtime_channel,
                x_trace_origin,
                x_task_id,
                x_workspace_path,
                x_workspace_id,
                x_repository_branch,
                x_repository_commit,
                x_dirty_state,
            )
        except HTTPException as error:
            if error.status_code in {
                status.HTTP_503_SERVICE_UNAVAILABLE,
                status.HTTP_404_NOT_FOUND,
            }:
                return error_response(
                    error.status_code, str(error.detail), "invalid_request_error", "invalid_request"
                )
            return JSONResponse(
                _responses_payload(
                    response_model,
                    {
                        "error": {
                            "message": str(error.detail),
                            "type": "backend_error",
                            "code": "backend_error",
                        }
                    },
                    status="failed",
                ),
                status_code=200,
            )
        chat_payload = _chat_response_payload(chat_response)
        if chat_payload is None:
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                "upstream response could not be parsed",
                "backend_error",
                "backend_error",
            )
        if chat_response.status_code == status.HTTP_502_BAD_GATEWAY:
            return JSONResponse(
                _responses_payload(response_model, chat_payload, status="failed"),
                status_code=status.HTTP_200_OK,
            )
        return JSONResponse(
            _responses_payload(
                response_model,
                chat_payload,
                custom_tool_names=custom_tool_names,
            )
        )

    @app.get("/v1/responses", dependencies=[Depends(auth)])
    async def responses_get(
        request: Request,
        input: str | None = None,
        model: str | None = None,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
    ) -> Response:
        if input is None:
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Method Not Allowed")
        return await responses(
            body=ResponsesRequest(model=model or configured.model_name, input=input),
            request=request,
            x_session_id=x_session_id,
            x_runtime_channel=x_runtime_channel,
            x_trace_origin=x_trace_origin,
            x_task_id=x_task_id,
            x_workspace_path=x_workspace_path,
            x_workspace_id=x_workspace_id,
            x_repository_branch=x_repository_branch,
            x_repository_commit=x_repository_commit,
            x_dirty_state=x_dirty_state,
        )

    @app.get("/v1/admin/runtime-status", dependencies=[Depends(admin_auth)])
    async def admin_runtime_status(request: Request) -> dict[str, Any]:
        return await asyncio.to_thread(
            runtime_report,
            request.app.state.settings.state_db,
            request.app.state.project_root,
            lifecycle_mode=configured.lifecycle_mode,
            managed_roles=tuple(configured.lifecycle_unit_map),
        )

    @app.get("/admin/profile", response_model=ProfileResponse, dependencies=[Depends(admin_auth)])
    async def profile(request: Request) -> dict[str, str]:
        return dict(request.app.state.profiles.current())

    async def switch_profile(name: str, request: Request) -> dict[str, str]:
        guard_ownership: dict[str, str] = {}
        switch_task: asyncio.Task[Mapping[str, str]] | None = None
        try:
            if configured.lifecycle_mode in {"fixed", "adaptive"}:
                try:
                    guard_ownership = await request.app.state.lifecycle.claim_guards(
                        configured.lifecycle_unit_map,
                        "profile_guard",
                    )
                except Exception as error:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "lifecycle profile guard unavailable",
                    ) from error
            switch_task = asyncio.create_task(
                asyncio.to_thread(request.app.state.profiles.switch, name)
            )
            try:
                return dict(await asyncio.shield(switch_task))
            except asyncio.CancelledError:
                await switch_task
                raise
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        finally:
            if guard_ownership:
                try:
                    await request.app.state.lifecycle.release_guards(
                        guard_ownership,
                        "profile_guard",
                    )
                except Exception as error:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "lifecycle profile guard cleanup unavailable",
                    ) from error

    @app.post(
        "/admin/profile/resident",
        response_model=ProfileResponse,
        dependencies=[Depends(admin_auth)],
    )
    async def resident(request: Request) -> dict[str, str]:
        return await switch_profile("resident", request)

    @app.post(
        "/admin/profile/judge", response_model=ProfileResponse, dependencies=[Depends(admin_auth)]
    )
    async def judge(request: Request) -> dict[str, str]:
        return await switch_profile("judge", request)

    @app.post(
        "/admin/profile/restore", response_model=ProfileResponse, dependencies=[Depends(admin_auth)]
    )
    async def restore(request: Request) -> dict[str, str]:
        return await switch_profile("restore", request)

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)
