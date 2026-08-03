from __future__ import annotations

import asyncio
import json
import math
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager, suppress
from pathlib import Path
from typing import Any, cast

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .admin_codex import AdminCodexRunner
from .admin_routes import build_admin_router
from .config import Settings, get_settings
from .controller import (
    IMPLEMENTATION_QUALITY_CONTRACT,
    Controller,
    DuplicateFailedCall,
    FrontierRequiredUnavailable,
    JudgeCorrectionRequired,
    JudgeRequired,
    LoopAdmissionError,
    PolicyBlocked,
    ReasonerUnavailable,
)
from .evidence import REPOSITORY_MUTATION_TOOLS, executor_stalled
from .evolution import PromptRegistry
from .frontier import (
    CodexOAuthCollaboration,
    load_frontier_config,
)
from .image_generation import (
    CodexOAuthImageGenerator,
    ImageGenerationStore,
    image_prompt_from_tool_calls,
)
from .image_generation import (
    capability_status as image_generation_status,
)
from .inference import (
    ChatExecutionContext,
    ChatExecutionHeaders,
    ResponseOwnedIterator,
    ResponseOwnedStreamingResponse,
    compaction_request_index,
    elapsed_ms,
    error_response,
    has_matching_tool_result,
    ollama_model_ready,
    register_inference_routes,
    remap_reused_tool_call_ids,
    title_request_index,
    tool_result_call_ids,
    unsafe_frontier_correction_tool_call,
)
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
    ObservationBus,
    ObservationCommandStore,
    ObservationProvider,
    TelegramProvider,
    WorkflowStreamHub,
)
from .policy import PolicyEngine
from .profiles import ProfileManager
from .providers import ModelProvider, StageTimeout, validate_assistant_response
from .remote_judge import (
    JudgeProviderError,
    OpenCodeGoJudgeProvider,
    selective_judge_reasons,
)
from .responses_routes import register_responses_routes
from .review import has_review_evidence, review_observation
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
from .schemas import ChatRequest, latest_user_content
from .security import (
    ApiKeyStore,
    admin_dependency,
    auth_dependency,
)
from .skills import SkillRegistry
from .specialists import (
    LocalPlannerProvider,
    LocalReviewerProvider,
    RemotePlannerProvider,
    RemoteReviewerProvider,
    SpecialistRouter,
)
from .state import StateStore
from .streaming import (
    StreamObservation,
    completed_chat_sse,
    forward_sse,
    keepalive_sse,
    reported_usage,
)
from .trace import TraceRecorder
from .training import (
    ContentStore,
    TrainingCollector,
    TrainingStore,
)
from .training_routes import build_training_router
from .usage import (
    ModelAlias,
    RequestStatus,
    RequestUsageFinalization,
    RequestUsageStart,
    RetryableFailureClass,
    Role,
    UsageQuotaExceeded,
    UsageStore,
    classify_client,
)
from .validation import implementation_completion_ready
from .weekly import (
    ArchiveRegistry,
    WeeklyPackager,
    WeeklyScheduler,
    previous_complete_week,
    snapshot_version,
    weekly_candidate_analysis,
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
    api_keys = ApiKeyStore(
        configured.state_db,
        configured.configured_api_keys(),
        admin_token_ids=configured.admin_token_ids,
        max_admin_keys=configured.max_admin_api_keys,
    )
    auth = auth_dependency(configured, api_keys)
    admin_auth = admin_dependency(configured, api_keys)
    http_client: httpx.AsyncClient | None = None

    async def default_lifecycle_health_probe(role: str) -> bool:
        model = configured.models.get(role)
        if model is None or http_client is None:
            return False
        try:
            if role in {"planner", "reviewer"} and model.provider != "ollama":
                response = await http_client.post(
                    f"{model.base_url.rstrip('/')}/v1/chat/completions",
                    timeout=30,
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
            response = await http_client.get(
                f"{model.base_url.rstrip('/')}/api/ps"
                if model.provider == "ollama"
                else f"{model.base_url.rstrip('/')}/v1/models",
                timeout=30,
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
        nonlocal http_client
        store = StateStore(configured.state_db)
        http_client = httpx.AsyncClient(timeout=None)
        provider = ModelProvider(client=http_client)
        project_root = Path(os.getenv("DGX_MOA_PROJECT_ROOT", ".")).resolve()
        app.state.settings = configured
        app.state.draining = False
        app.state.executor_admission_lock = asyncio.Lock()
        app.state.api_keys = api_keys
        app.state.store = store
        app.state.http_client = http_client
        app.state.runtime_metrics = RuntimeMetrics()
        store.subscribe_events(app.state.runtime_metrics.observe_event)
        observation_providers: list[ObservationProvider] = []
        observation = configured.live_observation
        if observation.enabled and observation.telegram is not None:
            observation_providers.append(
                TelegramProvider(
                    observation.telegram.bot_token.get_secret_value(),
                    observation.telegram.chat_id,
                    message_thread_id=observation.telegram.message_thread_id,
                    timeout=observation.request_timeout_seconds,
                    client=http_client,
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
        app.state.workflow_stream = (
            WorkflowStreamHub(
                queue_size=observation.queue_size,
                replay_size=observation.workflow_replay_size,
            )
            if observation.workflow_websocket_enabled
            else None
        )
        if app.state.workflow_stream is not None:
            app.state.workflow_stream.start()
            store.subscribe_events(app.state.workflow_stream.publish_store_event)
        app.state.observation_commands = (
            ObservationCommandStore(configured.state_db) if observation.controls.enabled else None
        )
        frontier_config = (
            load_frontier_config(configured.frontier_config)
            if configured.frontier_enabled
            else None
        )
        app.state.frontier_config = frontier_config
        app.state.frontier_auth_active = set()
        app.state.admin_codex = AdminCodexRunner(configured, api_keys, store)
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
        app.state.image_generator = None
        if image_generation_status(configured.image_generation)["state"] == "ready":
            app.state.image_generator = CodexOAuthImageGenerator(
                configured.image_generation,
                ImageGenerationStore(configured.state_db),
                run_dir=configured.run_dir,
                project_root=project_root,
                profile_root=configured.image_generation.profile_root,
            )
        frontier = None
        if frontier_config is not None:
            if frontier_config.provider != "codex_oauth":
                raise ValueError("Frontier collaboration requires codex_oauth")
            frontier = CodexOAuthCollaboration(
                frontier_config,
                configured.run_dir,
                project_root,
            )
        app.state.frontier = frontier
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
                client=http_client,
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
                "client": http_client,
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
            if configured.specialist_routing.enabled:
                for role in ("planner", "reviewer"):
                    if configured.models[role].lifecycle_control != "external":
                        continue
                    try:
                        healthy = await (lifecycle_health_probe or default_lifecycle_health_probe)(
                            role
                        )
                    except Exception:
                        healthy = False
                    app.state.lifecycle_store.recover_state(
                        role,
                        "ready" if healthy else "failed",
                        failure_class=None if healthy else "external_unavailable",
                    )
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
                    minimum_free_bytes=configured.weekly_jobs.minimum_free_bytes,
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
                    maintenance_candidates = (
                        app.state.training_store.packageable_candidates(
                            created_from=window.utc_start.isoformat(),
                            created_before=window.utc_end.isoformat(),
                        )
                        if app.state.training_store is not None
                        else []
                    )
                    await asyncio.to_thread(
                        weekly_runtime_improvement_report,
                        report_root,
                        skill_report=skill_report,
                        knowledge_report=knowledge_report,
                        analyses=weekly_candidate_analysis(maintenance_candidates)
                        | {
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
                    skills = app.state.skills.list_skills() if app.state.skills is not None else []
                    knowledge = (
                        app.state.knowledge.list_entries()
                        if app.state.knowledge is not None
                        else []
                    )
                    prompts = (
                        app.state.prompts.registry.list_artifacts()
                        if app.state.prompts is not None
                        else []
                    )
                    policy_set = configured.declarative_policy.policy_set()
                    await asyncio.to_thread(
                        app.state.weekly_packager.package,
                        app.state.training_store.packageable_candidates(
                            created_from=window.utc_start.isoformat(),
                            created_before=window.utc_end.isoformat(),
                        ),
                        window=window,
                        production_commit=configured.controller_commit,
                        policy_version=(
                            f"{configured.declarative_policy.version}@"
                            f"{snapshot_version([policy_set.model_dump_json()])}"
                        ),
                        skill_registry_version=snapshot_version(
                            f"{skill.skill_id}@{skill.version}:{skill.content_hash()}"
                            for skill in skills
                        ),
                        knowledge_registry_version=snapshot_version(
                            f"{entry.knowledge_id}@{entry.version}:{entry.content_hash()}"
                            for entry in knowledge
                        ),
                        prompt_registry_version=snapshot_version(
                            f"{artifact.artifact_id}@{artifact.version}:{artifact.content_hash()}"
                            for artifact in prompts
                        ),
                        routing_version=snapshot_version(
                            [
                                json.dumps(
                                    configured.specialist_routing.model_dump(mode="json"),
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            ]
                        ),
                        judge_configuration={
                            "provider": configured.remote_judge.provider,
                            "model": configured.remote_judge.model,
                            "mode": configured.remote_judge.mode,
                        },
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
            close_provider = getattr(provider, "aclose", None)
            if close_provider is not None:
                await close_provider()
            await app.state.lifecycle.close()
            await http_client.aclose()
            http_client = None

    app = FastAPI(title="DGX MoA Agent", version="2.0.0", lifespan=lifespan)
    app.include_router(build_admin_router(admin_auth))
    app.include_router(build_training_router(admin_auth))

    @app.middleware("http")
    async def reject_new_work_while_draining(request: Request, call_next):  # type: ignore[no-untyped-def]
        if (
            getattr(request.app.state, "draining", False)
            and request.method == "POST"
            and request.url.path in {"/v1/chat/completions", "/v1/responses"}
        ):
            return error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "gateway is draining for a safe restart",
                "server_error",
                "gateway_draining",
                headers={"Retry-After": "2"},
            )
        return await call_next(request)

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

    def record_trace_safely(runtime: Any, state: Any, task_id: str) -> None:
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
            idle = runtime.lifecycle_store.latest_decision(role)
            if idle is None:
                continue
            local = runtime.lifecycle_store.get(role)
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
            runtime.traces.record(state, task_id=task_id)
        except OSError as error:
            state.observability_degraded = True
            state.observability_status = "degraded"
            runtime.store.event(
                state.session_id,
                "observability_degraded",
                {"component": "trace_archive", "error": type(error).__name__},
            )
            runtime.store.save(state)

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

    register_inference_routes(
        app,
        configured,
        auth,
        tuple(MODEL_MODES),
        IMPLEMENTATION_QUALITY_CONTRACT,
        status_lifecycle_record,
        record_trace_safely,
    )

    async def execute_chat(
        body: ChatRequest,
        context: ChatExecutionContext,
        headers: ChatExecutionHeaders,
    ) -> Response:
        runtime = context.runtime
        x_session_id = headers.session_id
        x_runtime_channel = headers.runtime_channel
        x_trace_origin = headers.trace_origin
        x_task_id = headers.task_id
        x_workspace_path = headers.workspace_path
        x_workspace_id = headers.workspace_id
        x_repository_branch = headers.repository_branch
        x_repository_commit = headers.repository_commit
        x_dirty_state = headers.dirty_state
        x_validation_command = headers.validation_command
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
            runtime.store.event(
                state.session_id,
                "request_timing",
                {
                    "timings_ms": dict(state.timings_ms),
                    "stage_status": dict(stage_status),
                },
            )
            timing_recorded = True

        profile_state = runtime.profiles.current()
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
        api_token_id = context.api_token_id
        recovered_tool_owner = False
        if not provided_session_id:
            tool_owner, recovered_tool_owner = runtime.store.recover_tool_owner(
                tool_result_call_ids(raw["messages"]),
                api_token_id,
                latest_user_content(raw["messages"]),
            )
            if tool_owner is not None:
                session_id = tool_owner.session_id
        try:
            raw["max_tokens"] = runtime.controller.executor_tokens(raw)
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
        if isinstance(x_validation_command, str) and x_validation_command.strip():
            if any(character in x_validation_command for character in "\r\n\0"):
                return error_response(
                    status.HTTP_400_BAD_REQUEST,
                    "invalid validation command header",
                    "invalid_request_error",
                    "invalid_request",
                    "x-validation-command",
                )
            raw["metadata"]["validation_command"] = x_validation_command.strip()
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
        elif compaction_request_index(raw["messages"]) is not None:
            state_session_id = (
                session_id if session_id.endswith(":compact") else f"{session_id}:compact"
            )
            raw.pop("tools", None)
            raw.pop("tool_choice", None)
            raw.pop("parallel_tool_calls", None)
            mode = "fast"
        else:
            state_session_id = session_id
        executor_remote = False
        executor_routing_reason = "local_ready"
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
                    record = runtime.lifecycle_store.get(role)
                    role_load = False
                    if role in configured.lifecycle_unit_map and record.state != "ready":
                        check = await runtime.lifecycle.ensure_ready(role)
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
                    external_record = runtime.lifecycle_store.recover_state(
                        role,
                        "ready" if healthy else "failed",
                        failure_class=None if healthy else "external_unavailable",
                    )
                    role_states[role] = "warm" if healthy else "cold"
                    role_ready_at[role] = external_record.ready_at
                    if not healthy:
                        if role == "reasoner" and runtime.frontier is not None:
                            degraded_roles[role] = "local_not_ready_remote_fallback"
                        elif is_optional:
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
                check = await runtime.lifecycle.ensure_ready(role)
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
                        runtime.lifecycle_store.automation_status().automation_disabled
                        or check.record.state == "failed"
                    ):
                        unavailable_record = check.record
                    else:
                        loading_record = check.record
        try:
            runtime.usage.start(
                RequestUsageStart(
                    request_id=usage_request_id,
                    session_id=str(
                        uuid.uuid5(
                            runtime.usage_session_namespace,
                            state_session_id,
                        )
                    ),
                    api_token_id=api_token_id,
                    client_class=classify_client(
                        context.user_agent
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
        except UsageQuotaExceeded as error:
            return error_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                str(error),
                "rate_limit_error",
                "api_key_quota_exceeded",
            )
        runtime.usage.start_roles(
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
                current = current_state or state or runtime.store.get(state_session_id)
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
                        runtime.controller.terminate_loop(current, "CLIENT_CANCELLED")
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
                    runtime.controller.complete_loop_iteration(current, status_value)
                    record_request_timing(current)
                    runtime.store.event(
                        current.session_id,
                        "session_ended",
                        {"request_id": state_session_id, "status": status_value},
                    )
                    runtime.store.save(current)
                    record_trace_safely(runtime, current, task_id)
                if usage_started:
                    completed_at = time.time()
                    runtime.usage.finalize(
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
                    runtime.usage.finalize_roles(
                        usage_request_id,
                        completed_at=completed_at,
                        first_byte_at=first_byte_at,
                        success=status_value == "completed",
                        failure_class=retryable_failure_class or stage,
                        ready_at={
                            role: (
                                runtime.lifecycle_store.get(role).ready_at
                                if role in configured.models
                                else None
                            )
                            for role in tracked_roles
                        },
                        role_failures=degraded_roles,
                    )
            finally:
                runtime.lifecycle_store.release_leases(
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
            async with runtime.executor_admission_lock:
                backend_busy_probe = getattr(
                    runtime.provider,
                    "backend_busy",
                    None,
                )
                backend_busy = (
                    await backend_busy_probe(configured.models["executor"]) is True
                    if runtime.frontier is not None and callable(backend_busy_probe)
                    else False
                )
                executor_remote = (
                    runtime.lifecycle_store.get("executor").active_request_count > 0
                    or backend_busy
                ) and runtime.frontier is not None
                if executor_remote:
                    executor_routing_reason = "local_busy"
                initial_lease_roles = tuple(
                    role
                    for role in roles
                    if not (
                        configured.specialist_routing.enabled and role in {"planner", "reviewer"}
                    )
                    and role not in degraded_roles
                    and not (executor_remote and role == "executor")
                )
                active_lease_ids = tuple(
                    lease.lease_id
                    for lease in await runtime.lifecycle.acquire_request_leases(
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
                    record = runtime.lifecycle_store.get(role)
                    role_load = False
                    if role in configured.lifecycle_unit_map and record.state != "ready":
                        check = await runtime.lifecycle.ensure_ready(role)
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
                record = runtime.lifecycle_store.get(role)
                if configured.lifecycle_mode in {"fixed", "adaptive"}:
                    if model.lifecycle_control == "external":
                        try:
                            healthy = await (
                                lifecycle_health_probe or default_lifecycle_health_probe
                            )(role)
                        except Exception:
                            healthy = False
                        record = runtime.lifecycle_store.recover_state(
                            role,
                            "ready" if healthy else "failed",
                            failure_class=None if healthy else "external_unavailable",
                        )
                    elif role not in configured.lifecycle_unit_map:
                        unmanaged = unmanaged or role
                        not_ready = not_ready or record
                    else:
                        check = await runtime.lifecycle.ensure_ready(role)
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
            runtime.usage.add_required_roles(usage_request_id, new_roles)
            runtime.usage.start_roles(
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
                runtime.usage.update_model_state(usage_request_id, "cold")
                raise DynamicRoleUnmanagedError(unmanaged)
            if not_ready is not None:
                runtime.usage.update_model_state(
                    usage_request_id, "loading" if any(new_loads.values()) else "cold"
                )
                raise LifecycleNotReadyError(not_ready)
            leases = await runtime.lifecycle.acquire_request_leases(
                usage_request_id,
                lease_roles,
                kind="active_request",
                require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
            )
            active_lease_ids = (*active_lease_ids, *(lease.lease_id for lease in leases))

        try:
            continuation_owner = continuation_correlation(state_session_id)
            if recovered_tool_owner or has_matching_tool_result(raw["messages"]):
                runtime.lifecycle_store.release_continuation(
                    "executor", continuation_owner
                )
            previous_state = runtime.store.get(state_session_id)
            previous_failure_count = len(previous_state.failures) if previous_state else 0
            duplicate_failure_recovery = False
            try:
                state = runtime.controller.session(state_session_id, raw["messages"])
            except DuplicateFailedCall:
                recovered = runtime.store.get(state_session_id)
                repeated_actions = (
                    sum(
                        failure.get("failure_class") == "REPEATED_ACTION"
                        for failure in recovered.failures
                    )
                    if recovered is not None
                    else 0
                )
                terminated = bool(
                    recovered is not None
                    and recovered.engineering_loop is not None
                    and recovered.engineering_loop.termination_reason is not None
                )
                if (
                    runtime.frontier is None
                    or recovered is None
                    or repeated_actions != 1
                    or terminated
                ):
                    raise
                state = recovered
                duplicate_failure_recovery = True
                runtime.store.event(
                    state_session_id,
                    "executor_duplicate_failure_recovery",
                    {"provider": "frontier"},
                )
            new_failure_observed = (
                len(state.failures) > previous_failure_count or duplicate_failure_recovery
            )
            state.current_request_id = usage_request_id
            state.api_token_id = api_token_id
            task_id = task_id or state.task_id or state_session_id
            raw["metadata"]["task_id"] = task_id
            state.timings_ms = {"accepted": 0.0}
            for role, reason in degraded_roles.items():
                stage_status[role] = "unavailable"
                runtime.store.event(
                    state_session_id,
                    "role_degraded",
                    {"role": role, "reason": reason},
                )
            runtime.store.event(
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
            runtime.controller.select_route(state, raw["metadata"])
            stream_judge_reasons = (
                selective_judge_reasons(
                    runtime.remote_judge is not None, state, raw["metadata"]
                )
                if body.stream
                else []
            )
            if stream_judge_reasons == ["repeated_failure_fingerprint"]:
                runtime.store.event(
                    state_session_id,
                    "remote_judge_stream_deferred",
                    {
                        "reasons": stream_judge_reasons,
                        "until": "non_streaming_completion_or_high_risk_trigger",
                    },
                )
                stream_judge_reasons = []
            if stream_judge_reasons:
                runtime.store.event(
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
                runtime.controller.note_no_progress(state)

            async def remote_executor_complete(
                executor_request: dict[str, Any], stage: str
            ) -> dict[str, Any]:
                frontier_provider = runtime.frontier
                if frontier_provider is None:
                    raise FrontierRequiredUnavailable("remote Frontier fallback is unavailable")
                scoped_request = {
                    **executor_request,
                    "_client_workspace_path": state.repository.get("workspace_path"),
                }
                response = await frontier_provider.execute(
                    scoped_request,
                    f"{usage_request_id}:{stage}",
                )
                remapped_ids = remap_reused_tool_call_ids(
                    response,
                    {
                        str(execution.get("tool_call_id"))
                        for execution in state.tool_executions
                        if execution.get("tool_call_id")
                    }
                    | set(state.pending_tool_call_ids),
                    f"{usage_request_id}:{stage}",
                )
                if remapped_ids:
                    runtime.store.event(
                        state_session_id,
                        "provider_tool_call_ids_remapped",
                        {"provider": "frontier", "count": remapped_ids},
                    )
                runtime.store.event(
                    state_session_id,
                    "executor_remote_completed",
                    {
                        "stage": stage,
                        "provider": response.get("provider_provenance", {}).get("provider"),
                        "model": response.get("model"),
                    },
                )
                return cast(dict[str, Any], response)

            async def remote_executor_correction(
                executor_request: dict[str, Any], stage: str
            ) -> dict[str, Any]:
                validation_required = state.frontier_correction_mutation_observed
                if validation_required:
                    executor_request = dict(executor_request)
                    executor_request["messages"] = [
                        *executor_request.get("messages", []),
                        {
                            "role": "user",
                            "content": (
                                "The Frontier correction has changed the repository but has not "
                                "been validated. Call exactly one available command tool now to "
                                "run the smallest bounded relevant test suite. Do not inspect or "
                                "edit another file unless that validation fails. Return a native "
                                "tool call, not prose."
                            ),
                        },
                    ]
                completed_retries: list[int] = []
                if state.frontier_correction_required:
                    correction_events = runtime.store.events(state_session_id)
                    last_rejection = max(
                        (
                            index
                            for index, event in enumerate(correction_events)
                            if event["event_type"] == "frontier_review_rejected"
                        ),
                        default=-1,
                    )
                    completed_retries = [
                        index
                        for index, event in enumerate(correction_events)
                        if event["event_type"] == "frontier_correction_tool_retry_completed"
                        and index > last_rejection
                    ]
                    last_retry = completed_retries[-1] if completed_retries else -1
                    tool_executed_after_retry = any(
                        index > last_retry and event["event_type"] == "tool_execution_recorded"
                        for index, event in enumerate(correction_events)
                    )
                    if completed_retries and not tool_executed_after_retry:
                        runtime.store.event(
                            state_session_id,
                            "frontier_correction_tool_retry_exhausted",
                            {"provider": "frontier"},
                        )
                        raise FrontierRequiredUnavailable(
                            "required Frontier correction retry exhausted"
                        )
                response = await remote_executor_complete(executor_request, stage)
                if not state.frontier_correction_required:
                    return response
                message = (response.get("choices") or [{}])[0].get("message", {})
                unsafe_tool_call = unsafe_frontier_correction_tool_call(response)
                if message.get("tool_calls") and not unsafe_tool_call:
                    return response
                if unsafe_tool_call:
                    runtime.store.event(
                        state_session_id,
                        "frontier_correction_tool_rejected",
                        {"reason": "unsafe_low_specificity_edit"},
                    )
                tools = executor_request.get("tools")
                if not isinstance(tools, list) or not tools:
                    runtime.store.event(
                        state_session_id,
                        "frontier_correction_tool_unavailable",
                        {"reason": "client_tools_unavailable"},
                    )
                    raise FrontierRequiredUnavailable(
                        "required Frontier correction cannot run without client tools"
                    )
                allowed_tools = (
                    {"exec_command", "shell", "terminal", "execute_code"}
                    if validation_required
                    else REPOSITORY_MUTATION_TOOLS
                )
                tools = [
                    tool
                    for tool in tools
                    if isinstance(tool, dict)
                    and str(tool.get("name") or tool.get("function", {}).get("name"))
                    in allowed_tools
                ]
                if not tools:
                    runtime.store.event(
                        state_session_id,
                        "frontier_correction_tool_unavailable",
                        {"reason": "mutation_tools_unavailable"},
                    )
                    raise FrontierRequiredUnavailable(
                        "required Frontier correction cannot run without eligible client tools"
                    )
                tool_names = sorted(
                    {
                        str(tool.get("name") or tool.get("function", {}).get("name"))
                        for tool in tools
                        if isinstance(tool, dict)
                        and (tool.get("name") or tool.get("function", {}).get("name"))
                    }
                )
                retry_request = dict(executor_request)
                retry_request["tools"] = tools
                retry_request["stream"] = False
                retry_instruction = (
                    "A required Frontier correction has changed the repository but still lacks "
                    "successful validation. Call exactly one available command tool now to run "
                    "the smallest bounded relevant test suite. Do not inspect or edit another "
                    "file unless that validation fails. Return a native tool call, not prose. "
                    "Available tools: "
                    if validation_required
                    else (
                        "A required code correction remains unresolved. The prior response "
                        + (
                            "called a tool but did not resolve the correction. Use a "
                            "mutation-capable tool and change the affected file now. "
                            if completed_retries
                            else "did not call a tool and cannot complete this request. "
                        )
                        + "Call exactly one available client tool now to apply the concrete "
                        "correction listed in the prior Frontier contribution. Do not repeat an "
                        "inspection or validation that already succeeded unless the prior "
                        "finding explicitly requires that evidence. Never invoke a tool name as "
                        "a shell command; when apply_patch is unavailable, write through an "
                        "available command tool instead. Return a native tool call, not prose. "
                        "For edit tools, identify a unique existing block of at least eight "
                        "non-whitespace characters; otherwise replace the complete file with a "
                        "write tool. Available tools: "
                    )
                )
                retry_request["messages"] = [
                    *executor_request.get("messages", []),
                    {
                        "role": "user",
                        "content": retry_instruction + ", ".join(tool_names),
                    },
                ]
                runtime.store.event(
                    state_session_id,
                    "frontier_correction_tool_retry_requested",
                    {
                        "provider": "frontier",
                        "tools": tool_names,
                        "attempt": len(completed_retries) + 1,
                    },
                )
                response = await remote_executor_complete(
                    retry_request, f"{stage}_correction_tool_retry"
                )
                retry_message = (response.get("choices") or [{}])[0].get("message", {})
                unsafe_retry = unsafe_frontier_correction_tool_call(response)
                if not retry_message.get("tool_calls") or unsafe_retry:
                    runtime.store.event(
                        state_session_id,
                        "frontier_correction_tool_retry_failed",
                        {
                            "provider": "frontier",
                            "reason": (
                                "unsafe_low_specificity_edit"
                                if unsafe_retry
                                else "tool_call_missing"
                            ),
                        },
                    )
                    raise FrontierRequiredUnavailable(
                        "required Frontier correction did not produce a safe client tool call"
                    )
                runtime.store.event(
                    state_session_id,
                    "frontier_correction_tool_retry_completed",
                    {"provider": "frontier"},
                )
                return response

            async def remote_reasoner_complete(
                reasoner_request: dict[str, Any], stage: str
            ) -> dict[str, Any]:
                frontier_provider = runtime.frontier
                if frontier_provider is None:
                    raise FrontierRequiredUnavailable("remote Reasoner fallback is unavailable")
                remote_request = dict(reasoner_request)
                remote_request["max_tokens"] = max(
                    int(remote_request.get("max_tokens") or 0),
                    configured.limits.executor_tokens,
                )
                response = await frontier_provider.execute(
                    remote_request,
                    f"{usage_request_id}:{stage}",
                )
                runtime.store.event(
                    state_session_id,
                    "reasoner_remote_completed",
                    {
                        "provider": response.get("provider_provenance", {}).get("provider"),
                        "model": response.get("model"),
                    },
                )
                return cast(dict[str, Any], response)

            planned_change = (
                state.active_turn_requires_change
                and bool(state.plan)
                and not state.implementation_evidence
            )
            preparation_stalled = executor_stalled(
                state,
                inspection_limit=3 if planned_change else 6,
            )
            planned_change_needs_frontier = (
                not executor_remote
                and runtime.frontier is not None
                and planned_change
                and not preparation_stalled
                and not duplicate_failure_recovery
                and not state.frontier_correction_required
            )
            if (
                not executor_remote
                and runtime.frontier is not None
                and (
                    state.frontier_correction_required
                    or duplicate_failure_recovery
                    or preparation_stalled
                    or planned_change_needs_frontier
                )
            ):
                executor_remote = True
                executor_routing_reason = (
                    "local_duplicate_failure"
                    if duplicate_failure_recovery
                    else "planned_complex_change"
                    if planned_change_needs_frontier
                    else "local_no_progress"
                    if preparation_stalled
                    else "frontier_correction_required"
                )
                executor_lease_id = str(
                    uuid.uuid5(uuid.UUID(usage_request_id), "active_request:executor")
                )
                runtime.lifecycle_store.release_leases((executor_lease_id,))
                active_lease_ids = tuple(
                    lease_id for lease_id in active_lease_ids if lease_id != executor_lease_id
                )
                runtime.store.event(
                    state_session_id,
                    "executor_remote_selected",
                    {
                        "routing_reason": executor_routing_reason,
                        "provider": "frontier",
                    },
                )

            active_stage = "planner" if "planner" in roles else "request"
            tool_continuation = (
                recovered_tool_owner
                or has_matching_tool_result(raw["messages"])
                or context.tool_owner_recovered
            ) and not new_failure_observed
            executor_provider_pin = "frontier" if executor_remote else "local"
            executor_provider_dispatched = False

            async def pinned_executor_complete(
                executor_request: dict[str, Any], stage: str
            ) -> dict[str, Any]:
                nonlocal executor_provider_dispatched
                executor_provider_dispatched = True
                if executor_provider_pin == "frontier":
                    return await remote_executor_complete(executor_request, stage)
                return cast(
                    dict[str, Any],
                    await runtime.provider.complete(
                        "executor",
                        configured.models["executor"],
                        executor_request,
                        timeout_seconds=configured.limits.planner_timeout_seconds,
                        stage=stage,
                    ),
                )

            prepared = await runtime.controller.prepare_executor(
                state,
                raw,
                roles,
                ensure_dynamic_roles,
                tool_continuation=tool_continuation,
                executor_complete=pinned_executor_complete,
                reasoner_complete=(
                    remote_reasoner_complete if runtime.frontier is not None else None
                ),
            )
            context_fits = getattr(runtime.provider, "context_fits", None)
            context_exceeded = (
                not executor_remote
                and runtime.frontier is not None
                and callable(context_fits)
                and await context_fits(
                    configured.models["executor"],
                    prepared,
                    timeout_seconds=10,
                )
                is False
            )
            stalled = (
                not executor_remote
                and runtime.frontier is not None
                and executor_stalled(state)
            )
            completion_stalled = (
                not executor_remote
                and runtime.frontier is not None
                and bool(raw["metadata"].get("responses_progress_retry"))
                and implementation_completion_ready(
                    state, raw["metadata"]
                )
            )
            frontier_correction = (
                not executor_remote
                and runtime.frontier is not None
                and state.frontier_correction_required
            )
            repeated_failure = (
                not executor_remote
                and runtime.frontier is not None
                and any(count >= 2 for count in state.failure_families.values())
            )
            if (
                context_exceeded
                or stalled
                or completion_stalled
                or frontier_correction
                or repeated_failure
            ):
                requested_routing_reason = (
                    "local_context_exceeded"
                    if context_exceeded
                    else "frontier_correction_required"
                    if frontier_correction
                    else "local_completion_stalled"
                    if completion_stalled
                    else "local_repeated_failure"
                    if repeated_failure
                    else "local_no_progress"
                )
                if executor_provider_dispatched:
                    runtime.store.event(
                        state_session_id,
                        "executor_provider_switch_prevented",
                        {
                            "selected_provider": executor_provider_pin,
                            "requested_provider": "frontier",
                            "routing_reason": requested_routing_reason,
                        },
                    )
                else:
                    executor_remote = True
                    executor_routing_reason = requested_routing_reason
                    executor_lease_id = str(
                        uuid.uuid5(uuid.UUID(usage_request_id), "active_request:executor")
                    )
                    runtime.lifecycle_store.release_leases((executor_lease_id,))
                    active_lease_ids = tuple(
                        lease_id for lease_id in active_lease_ids if lease_id != executor_lease_id
                    )
                    runtime.store.event(
                        state_session_id,
                        "executor_remote_selected",
                        {
                            "routing_reason": executor_routing_reason,
                            "provider": "frontier",
                        },
                    )
            image_generator = runtime.image_generator
            if image_generator is not None and not body.stream and not executor_remote:
                image_tool = image_generator.tool_definition()
                if image_tool is not None:
                    tools = list(prepared.get("tools") or [])
                    if any(
                        isinstance(tool, dict)
                        and (
                            tool.get("name") == "generate_image"
                            or (
                                isinstance(tool.get("function"), dict)
                                and tool["function"].get("name") == "generate_image"
                            )
                        )
                        for tool in tools
                    ):
                        raise HTTPException(
                            status.HTTP_400_BAD_REQUEST,
                            "generate_image is a reserved Executor capability",
                        )
                    prepared["tools"] = [*tools, image_tool]
            if executor_remote and executor_routing_reason == "local_no_progress":
                prepared["messages"] = [
                    *prepared.get("messages", []),
                    {
                        "role": "user",
                        "content": (
                            "The local Executor stalled in repeated inspection without changing "
                            "the requested source. Do not inspect another file or repeat a read. "
                            "Call exactly one available write-capable tool now to implement the "
                            "smallest contract-complete change. If no patch tool exists, use the "
                            "terminal tool to write the target source file. Return a native tool "
                            "call, not prose."
                        ),
                    },
                ]
            if state.engineering_loop is not None and prepared.get("tools"):
                if state.frontier_correction_pending_verification:
                    prepared["parallel_tool_calls"] = False
                    runtime.store.event(
                        state_session_id,
                        "frontier_correction_verification_serialized",
                        {"reason": "bounded_validation"},
                    )
                elif prepared.get("parallel_tool_calls") is None:
                    prepared["parallel_tool_calls"] = True
                if state.engineering_loop.remaining_budget.tool_calls == 0:
                    prepared["tool_choice"] = "none"
                    runtime.store.event(
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
            runtime.store.event(
                state_session_id,
                "executor_started",
                {
                    "role": "executor",
                    "phase": state.phase,
                    "provider": "frontier" if executor_remote else "local",
                    "model": (
                        runtime.frontier.config.model
                        if executor_remote
                        else configured.models["executor"].served_name
                    ),
                    "routing_reason": executor_routing_reason,
                },
            )
            if body.stream:
                remote_failure: list[str] = []
                remote_invocation_provenance: dict[str, Any] = {}
                if executor_remote:

                    async def remote_upstream() -> AsyncIterator[bytes]:
                        try:
                            remote_response = await remote_executor_correction(
                                prepared, "executor_first_byte"
                            )
                        except Exception as error:
                            remote_failure.append(type(error).__name__)
                            runtime.controller.record_provider_failure(
                                state, "executor", error
                            )
                            runtime.store.event(
                                state_session_id,
                                "executor_remote_failed",
                                {
                                    "provider": "frontier",
                                    "failure_class": type(error).__name__,
                                    "failure_code": str(error)[:128],
                                    "failure_detail": getattr(error, "detail", "unclassified"),
                                    "failure_terms": getattr(error, "terms", []),
                                    "routing_reason": executor_routing_reason,
                                },
                            )
                            payload = {
                                "error": {
                                    "message": "remote Executor fallback unavailable",
                                    "type": "backend_error",
                                    "code": "frontier_required_unavailable",
                                }
                            }
                            yield (
                                "data: " + json.dumps(payload, separators=(",", ":")) + "\n\n"
                            ).encode()
                            yield b"data: [DONE]\n\n"
                            return
                        provenance = remote_response.get("provider_provenance")
                        if isinstance(provenance, dict):
                            remote_invocation_provenance.update(provenance)
                        if isinstance(remote_response.get("model"), str):
                            remote_invocation_provenance["model"] = remote_response["model"]
                        async for chunk in completed_chat_sse(remote_response):
                            yield chunk

                    upstream = keepalive_sse(remote_upstream(), interval_seconds=10)
                else:
                    stream_lease_ids = tuple(
                        lease.lease_id
                        for lease in await runtime.lifecycle.acquire_request_leases(
                            usage_request_id,
                            ("executor",),
                            kind="open_stream",
                            require_ready=configured.lifecycle_mode in {"fixed", "adaptive"},
                        )
                    )
                    upstream = await runtime.provider.stream(
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
                loop_admission_failed = False
                stream_cleanup_lock = asyncio.Lock()
                stream_cleaned = False

                async def finish_stream() -> None:
                    nonlocal stream_cleaned
                    async with stream_cleanup_lock:
                        if stream_cleaned:
                            return
                        stream_cleaned = True
                        terminal = (
                            stream_completed or observation.done_seen
                        ) and not remote_failure
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
                            if (
                                terminal
                                and "reviewer" in state.roles_required
                                and state.review_status != "approved"
                                and not state.review_status.startswith("rejected")
                            ):
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
                            runtime.controller.record_observed_invocation(
                                state,
                                {
                                    "role": "executor",
                                    "provider": (
                                        remote_invocation_provenance.get("provider", "frontier")
                                        if executor_remote
                                        else "local"
                                    ),
                                    "model": (
                                        remote_invocation_provenance.get(
                                            "model", runtime.frontier.config.model
                                        )
                                        if executor_remote
                                        else configured.models["executor"].served_name
                                    ),
                                    **(
                                        {"fallback_reason": executor_routing_reason}
                                        if executor_remote
                                        else {}
                                    ),
                                    "mode": "final_synthesis",
                                    "latency_ms": state.timings_ms["executor_total"],
                                    "prompt_tokens": observation.usage.get("prompt_tokens"),
                                    "completion_tokens": observation.usage.get("completion_tokens"),
                                    "total_tokens": observation.usage.get("total_tokens"),
                                    "cached_tokens": observation.cached_tokens,
                                    "cache_status": observation.cache_status,
                                    "cost_usd": (
                                        remote_invocation_provenance.get("cost_usd")
                                        if executor_remote
                                        else 0.0
                                    ),
                                    "status": "completed" if terminal else terminal_status,
                                },
                                account_loop_usage=False,
                            )
                            if terminal and (
                                "tool_calls" in observation.finish_reasons
                                or observation.tool_call_ids
                            ):
                                runtime.controller.remember_tool_calls(
                                    state,
                                    [
                                        {
                                            "id": observation.tool_call_ids_by_index[index],
                                            "type": "function",
                                            "function": {
                                                "name": observation.tool_call_names.get(index, ""),
                                                "arguments": observation.tool_call_arguments.get(
                                                    index, ""
                                                ),
                                            },
                                        }
                                        for index in sorted(observation.tool_call_ids_by_index)
                                    ],
                                )
                                runtime.lifecycle_store.refresh_continuation(
                                    usage_request_id,
                                    "executor",
                                    continuation_owner,
                                    expires_at=(
                                        lifecycle_clock()
                                        + configured.lifecycle.continuation_lease_ttl_seconds
                                    ),
                                )
                            runtime.store.event(
                                state_session_id,
                                "assistant_stream_finished",
                                {"finish_reasons": observation.finish_reasons},
                            )
                            runtime.store.event(
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
                                        else None
                                        if loop_admission_failed
                                        else "backend_error"
                                        if terminal_status == "failed"
                                        else None
                                    ),
                                )

                async def stream_response() -> AsyncIterator[bytes]:
                    nonlocal first_byte_at, loop_admission_failed, stream_completed
                    admitted_tool_calls = 0
                    accounted_total_tokens = 0
                    forwarder = forward_sse(
                        upstream,
                        observation,
                        max_event_bytes=configured.limits.max_sse_event_bytes,
                    )

                    try:
                        deadline = (
                            executor_started + configured.limits.executor_total_timeout_seconds
                        )
                        async with aclosing(forwarder):
                            while True:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    raise TimeoutError
                                try:
                                    chunk = await asyncio.wait_for(
                                        anext(forwarder), timeout=remaining
                                    )
                                except StopAsyncIteration:
                                    break
                                required_admissions = max(
                                    len(observation.tool_call_ids),
                                    1 if observation.tool_delta_seen else 0,
                                )
                                while admitted_tool_calls < required_admissions:
                                    runtime.controller.admit_tool_call(
                                        state,
                                        observation.tool_call_names.get(admitted_tool_calls),
                                    )
                                    admitted_tool_calls += 1
                                observed_total_tokens = observation.usage.get("total_tokens", 0)
                                if observed_total_tokens > accounted_total_tokens:
                                    runtime.controller.record_loop_usage(
                                        state,
                                        total_tokens=(
                                            observed_total_tokens - accounted_total_tokens
                                        ),
                                    )
                                    accounted_total_tokens = observed_total_tokens
                                if "first_downstream_byte" not in state.timings_ms:
                                    state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
                                    first_byte_at = time.time()
                                yield chunk
                        stream_completed = not remote_failure
                    except LoopAdmissionError as error:
                        loop_admission_failed = True
                        stage_status["executor_total"] = "failed"
                        termination = (
                            state.engineering_loop.termination_reason
                            if state.engineering_loop is not None
                            else None
                        )
                        code = (
                            "loop_budget_exhausted"
                            if termination == "BUDGET_EXHAUSTED"
                            else "loop_new_evidence_required"
                        )
                        runtime.store.event(
                            state_session_id,
                            "stream_loop_admission_failed",
                            {"code": code},
                        )
                        payload = {
                            "error": {
                                "message": str(error),
                                "type": "loop_admission_error",
                                "code": code,
                            }
                        }
                        if "first_downstream_byte" not in state.timings_ms:
                            state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
                            first_byte_at = time.time()
                        yield (
                            "data: " + json.dumps(payload, separators=(",", ":")) + "\n\n"
                        ).encode()
                        yield b"data: [DONE]\n\n"
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
            response = (
                await remote_executor_correction(prepared, "executor_total")
                if executor_remote
                else await runtime.provider.complete(
                    "executor",
                    configured.models["executor"],
                    prepared,
                    timeout_seconds=configured.limits.executor_total_timeout_seconds,
                    stage="executor_total",
                )
            )
            state.timings_ms["first_upstream_byte"] = elapsed_ms(accepted)
            state.timings_ms["executor_total"] = round(
                (time.monotonic() - executor_started) * 1000, 3
            )
            stage_status["executor_total"] = "completed"
            token_usage.update(reported_usage(response.get("usage")))
            runtime.controller.record_invocation(
                state,
                "executor",
                response,
                executor_started,
                mode="final_synthesis",
                fallback_reason=executor_routing_reason if executor_remote else None,
            )
            validate_assistant_response(response)
            assistant_message = response.get("choices", [{}])[0].get("message", {})
            assistant_tool_calls = assistant_message.get("tool_calls") or []
            image_request = image_prompt_from_tool_calls(assistant_tool_calls)
            if image_request is not None:
                if image_generator is None or executor_remote or body.stream:
                    raise RuntimeError("IMAGE_GENERATION_PROVIDER_BOUNDARY_VIOLATION")
                image_call_id, image_prompt = image_request
                runtime.controller.admit_tool_call(state, "generate_image")
                stage_status["image_generation"] = "started"
                image_generation_id = uuid.uuid4().hex
                image_task = asyncio.create_task(
                    asyncio.to_thread(
                        image_generator.generate,
                        image_prompt,
                        api_token_id,
                        image_generation_id,
                    )
                )
                try:
                    artifact = await asyncio.shield(image_task)
                except asyncio.CancelledError:
                    image_generator.cancel(image_generation_id)
                    with suppress(Exception, asyncio.CancelledError):
                        await asyncio.wait_for(asyncio.shield(image_task), timeout=10)
                    raise
                except Exception as error:
                    stage_status["image_generation"] = "failed"
                    runtime.store.event(
                        state_session_id,
                        "image_generation_failed",
                        {
                            "provider": "codex_oauth",
                            "model": "gpt-image-2",
                            "failure_class": type(error).__name__,
                        },
                    )
                    raise
                stage_status["image_generation"] = "completed"
                runtime.store.event(
                    state_session_id,
                    "image_generation_completed",
                    {
                        "artifact_id": artifact.artifact_id,
                        "provider": "codex_oauth",
                        "model": "gpt-image-2",
                        "byte_size": artifact.byte_size,
                        "validation": "passed",
                    },
                )
                continuation = dict(prepared)
                continuation["messages"] = [
                    *prepared.get("messages", []),
                    assistant_message,
                    {
                        "role": "tool",
                        "tool_call_id": image_call_id,
                        "content": json.dumps(
                            {
                                "artifact_id": artifact.artifact_id,
                                "download_url": (f"/v1/image-artifacts/{artifact.artifact_id}"),
                                "media_type": artifact.media_type,
                                "width": artifact.width,
                                "height": artifact.height,
                                "byte_size": artifact.byte_size,
                                "validation": "passed",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                ]
                continuation["tools"] = [
                    tool
                    for tool in continuation.get("tools", [])
                    if not (
                        isinstance(tool, dict)
                        and (
                            tool.get("name") == "generate_image"
                            or (
                                isinstance(tool.get("function"), dict)
                                and tool["function"].get("name") == "generate_image"
                            )
                        )
                    )
                ]
                image_continuation_started = time.monotonic()
                response = await runtime.provider.complete(
                    "executor",
                    configured.models["executor"],
                    continuation,
                    timeout_seconds=configured.limits.executor_total_timeout_seconds,
                    stage="image_generation_continuation",
                )
                for key, value in reported_usage(response.get("usage")).items():
                    token_usage[key] = token_usage.get(key, 0) + value
                runtime.controller.record_invocation(
                    state,
                    "executor",
                    response,
                    image_continuation_started,
                    mode="image_generation_continuation",
                )
                validate_assistant_response(response)
                assistant_message = response.get("choices", [{}])[0].get("message", {})
                assistant_tool_calls = assistant_message.get("tool_calls") or []
                if image_prompt_from_tool_calls(assistant_tool_calls) is not None:
                    raise RuntimeError("IMAGE_GENERATION_REPEAT_BLOCKED")
            for call in assistant_tool_calls:
                runtime.controller.admit_tool_call(
                    state,
                    str(call.get("function", {}).get("name", "")) or None,
                )
            assistant_tool_call_ids = [
                str(call.get("id"))
                for call in assistant_tool_calls
                if isinstance(call, dict) and call.get("id")
            ]
            if assistant_tool_call_ids:
                runtime.controller.remember_tool_calls(state, assistant_tool_calls)
            runtime.controller.record_evidence(
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
            judge_reasons = selective_judge_reasons(
                runtime.remote_judge is not None, state, body.metadata, response
            )
            if judge_reasons and "reviewer" not in state.roles_required:
                await ensure_dynamic_roles(("reviewer",))
                state.roles_required.append("reviewer")
            if (
                "reviewer" in state.roles_required
                and state.review_status != "approved"
                and (
                    bool(judge_reasons)
                    or has_review_evidence(state, body.metadata)
                )
            ):
                reviewer_observation = review_observation(
                    state,
                    response,
                    body.metadata,
                    runtime.settings.limits.max_review_evidence_characters,
                )
                active_stage = "reviewer"
                try:
                    async with runtime.reviewer_evaluation_lock:
                        guard_transition_id = None
                        if runtime.specialists is None:
                            reviewer = runtime.lifecycle_store.get("reviewer")
                            if reviewer.evaluation_guard:
                                raise ValueError("reviewer evaluation guard is already active")
                            guard_transition_id = reviewer.transition_id
                            runtime.lifecycle_store.set_guard(
                                "reviewer",
                                "evaluation_guard",
                                True,
                                expected_transition_id=guard_transition_id,
                            )
                        try:
                            await runtime.controller.review(
                                state,
                                reviewer_observation,
                                guard_already_owned=guard_transition_id is not None,
                            )
                        finally:
                            if guard_transition_id is not None:
                                runtime.lifecycle_store.set_guard(
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
                    runtime.store.event(
                        state_session_id,
                        "review_failed",
                        {"error_type": type(error).__name__},
                    )
                    if not state.review_fail_closed:
                        state.observability_degraded = True
                        state.observability_status = "degraded"
                    runtime.store.save(state)
                    if state.review_fail_closed:
                        if isinstance(error, StageTimeout):
                            raise
                        raise ValueError(f"review failed: {error}") from error
                else:
                    stage_status["reviewer"] = "completed"
            if not state.truncated:
                runtime.controller.apply_metadata(state, body.metadata)
            judge_reasons = list(
                dict.fromkeys(
                    [
                        *judge_reasons,
                        *selective_judge_reasons(
                            runtime.remote_judge is not None,
                            state,
                            body.metadata,
                            response,
                        ),
                    ]
                )
            )
            if judge_reasons and not state.truncated:
                runtime.store.event(
                    state_session_id,
                    "remote_judge_selected",
                    {"reasons": judge_reasons},
                )
                active_stage = "judge"
                judge_observation = review_observation(
                    state,
                    response,
                    body.metadata,
                    runtime.settings.limits.max_review_evidence_characters,
                )
                verdict = await runtime.controller.judge(state, judge_observation)
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
                        runtime.store.event(
                            state_session_id,
                            "judge_correction_started",
                            {"verdict": correction_verdict},
                        )
                        active_stage = "executor_total"
                        correction_started = time.monotonic()
                        response = (
                            await remote_executor_complete(correction_request, "judge_correction")
                            if executor_remote
                            else await runtime.provider.complete(
                                "executor",
                                configured.models["executor"],
                                correction_request,
                                timeout_seconds=configured.limits.executor_total_timeout_seconds,
                                stage="judge_correction",
                            )
                        )
                        token_usage.update(reported_usage(response.get("usage")))
                        runtime.controller.record_invocation(
                            state,
                            "executor",
                            response,
                            correction_started,
                            mode="judge_correction",
                            fallback_reason=executor_routing_reason if executor_remote else None,
                        )
                        validate_assistant_response(response)
                        assistant_message = response.get("choices", [{}])[0].get("message", {})
                        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
                        state.finish_reasons = [str(finish_reason)] if finish_reason else []
                        state.truncated = finish_reason == "length"
                        if finish_reason == "length" or assistant_message.get("tool_calls"):
                            raise JudgeCorrectionRequired(correction_verdict)
                        runtime.controller.record_evidence(
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
                        corrected_observation = review_observation(
                            state,
                            response,
                            body.metadata,
                            runtime.settings.limits.max_review_evidence_characters,
                        )
                        targeted_review = await runtime.controller.review(
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
                            verdict = await runtime.controller.judge(
                                state, corrected_observation
                            )
                            stage_status["judge"] = "completed"
                            if verdict.get("verdict") != "approve":
                                raise JudgeCorrectionRequired(
                                    str(verdict.get("verdict", correction_verdict))
                                )
                        runtime.store.event(
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
            runtime.store.event(
                state_session_id,
                "assistant_stream_finished",
                {"finish_reasons": [finish_reason] if finish_reason else []},
            )
            if finish_reason == "tool_calls" or assistant_message.get("tool_calls"):
                runtime.lifecycle_store.refresh_continuation(
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
            current = state or runtime.store.get(state_session_id)
            if current is not None:
                current.final_status = "cancelled"
                if body.stream:
                    runtime.store.event(state_session_id, "stream_aborted", {})
            finalize_request(
                active_stage,
                "cancelled",
                downstream_started=False,
                current_state=current,
            )
            raise
        except DuplicateFailedCall as error:
            finalize_request(active_stage, "failed", downstream_started=True)
            return error_response(
                status.HTTP_409_CONFLICT,
                str(error),
                "loop_admission_error",
                "loop_new_evidence_required",
            )
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
                or str(error) == "session step budget exhausted"
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
                runtime.controller.terminate_loop(state, "PROVIDER_UNAVAILABLE")
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
            if str(error).startswith("max_tokens exceeds server maximum "):
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
                runtime.controller.terminate_loop(state, "INTERNAL_FAILURE")
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
        x_validation_command: str | None = Header(default=None, max_length=512),
    ) -> Response:
        return await execute_chat(
            body,
            ChatExecutionContext(
                runtime=request.app.state,
                api_token_id=getattr(request.state, "api_token_id", "legacy"),
                user_agent=(
                    request.headers.get("user-agent") if "headers" in request.scope else None
                ),
            ),
            ChatExecutionHeaders(
                session_id=x_session_id,
                runtime_channel=x_runtime_channel,
                trace_origin=x_trace_origin,
                task_id=x_task_id,
                workspace_path=x_workspace_path,
                workspace_id=x_workspace_id,
                repository_branch=x_repository_branch,
                repository_commit=x_repository_commit,
                dirty_state=x_dirty_state,
                validation_command=x_validation_command,
            ),
        )

    register_responses_routes(
        app,
        auth,
        execute_chat,
        default_model=configured.model_name,
        model_load_timeout_seconds=configured.limits.model_load_timeout_seconds,
    )

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)
