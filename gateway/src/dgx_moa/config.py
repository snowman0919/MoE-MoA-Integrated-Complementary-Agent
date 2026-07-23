from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .policy import PolicyRule, PolicySet

TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}
API_KEY_PLACEHOLDERS = {
    "replace-with-a-long-random-token",
    "replace-with-a-long-random-value",
}
MODEL_ROLES = frozenset({"executor", "planner", "reviewer", "reasoner", "judge"})
SYSTEMD_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*\.service$")


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
    raise ValueError("must be one of true, 1, yes, on, false, 0, no, off")


class Limits(BaseModel):
    max_tool_output_characters: int = 1_000
    max_retained_observations: int = 12
    max_error_lines: int = 40
    max_diff_summary_lines: int = 100
    planner_tokens: int = 4_096
    reasoner_tokens: int = 1_500
    executor_tokens: int = 4_096
    executor_max_tokens: int = 16_384
    reviewer_tokens: int = 1_500
    judge_tokens: int = 2_500
    max_stream_capture_bytes: int = 1_000_000
    max_sse_event_bytes: int = 1_000_000
    max_review_evidence_characters: int = 16_000
    planner_timeout_seconds: float = 120
    reasoner_timeout_seconds: float = 120
    executor_first_byte_timeout_seconds: float = 120
    executor_total_timeout_seconds: float = 900
    reviewer_timeout_seconds: float = 120
    judge_timeout_seconds: float = 300
    model_load_timeout_seconds: float = 1_200
    tool_continuation_timeout_seconds: float = 600
    usage_sample_window: int = Field(default=512, ge=1)
    usage_ewma_alpha: float = Field(default=0.25, gt=0, le=1)
    adaptive_minimum_samples: int = Field(default=20, ge=1)
    executor_idle_fallback_seconds: float = Field(default=2_700, gt=0, allow_inf_nan=False)
    executor_idle_minimum_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    executor_idle_maximum_seconds: float = Field(default=7_200, gt=0, allow_inf_nan=False)
    executor_minimum_ready_residency_seconds: float = Field(default=600, gt=0, allow_inf_nan=False)
    optional_idle_fallback_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    optional_idle_minimum_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    optional_idle_maximum_seconds: float = Field(default=2_700, gt=0, allow_inf_nan=False)
    optional_minimum_ready_residency_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    max_steps: int = 100

    @model_validator(mode="after")
    def validate_idle_threshold_order(self) -> Limits:
        for role_class in ("executor", "optional"):
            minimum = getattr(self, f"{role_class}_idle_minimum_seconds")
            fallback = getattr(self, f"{role_class}_idle_fallback_seconds")
            maximum = getattr(self, f"{role_class}_idle_maximum_seconds")
            if not minimum <= fallback <= maximum:
                raise ValueError(
                    f"{role_class} idle thresholds must satisfy minimum <= fallback <= maximum"
                )
        return self


class LifecycleRolePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    normally_resident: bool = False
    idle_unload_enabled: bool = True
    fallback_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    minimum_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    maximum_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    minimum_ready_residency_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_timeout_order(self) -> LifecycleRolePolicy:
        if not (
            self.minimum_timeout_seconds
            <= self.fallback_timeout_seconds
            <= self.maximum_timeout_seconds
        ):
            raise ValueError("role idle thresholds must satisfy minimum <= fallback <= maximum")
        return self


def default_lifecycle_roles() -> dict[str, LifecycleRolePolicy]:
    return {
        "executor": LifecycleRolePolicy(
            normally_resident=True,
            idle_unload_enabled=False,
            minimum_timeout_seconds=7_200,
            fallback_timeout_seconds=14_400,
            maximum_timeout_seconds=28_800,
            minimum_ready_residency_seconds=600,
        ),
        "planner": LifecycleRolePolicy(
            minimum_timeout_seconds=600,
            fallback_timeout_seconds=1_200,
            maximum_timeout_seconds=3_600,
            minimum_ready_residency_seconds=600,
        ),
        "reviewer": LifecycleRolePolicy(
            minimum_timeout_seconds=600,
            fallback_timeout_seconds=1_200,
            maximum_timeout_seconds=3_600,
            minimum_ready_residency_seconds=600,
        ),
        "reasoner": LifecycleRolePolicy(
            normally_resident=True,
            idle_unload_enabled=False,
            minimum_timeout_seconds=300,
            fallback_timeout_seconds=600,
            maximum_timeout_seconds=1_800,
            minimum_ready_residency_seconds=300,
        ),
        "judge": LifecycleRolePolicy(
            enabled=False,
            idle_unload_enabled=False,
            minimum_timeout_seconds=300,
            fallback_timeout_seconds=600,
            maximum_timeout_seconds=1_800,
            minimum_ready_residency_seconds=300,
        ),
    }


class LifecyclePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: dict[str, LifecycleRolePolicy] = Field(default_factory=default_lifecycle_roles)
    minimum_samples: int = Field(default=20, ge=1)
    recent_sample_window: int = Field(default=100, ge=2, le=10_000)
    percentile: float = Field(default=0.75, gt=0, lt=1, allow_inf_nan=False)
    multiplier: float = Field(default=1.5, gt=0, allow_inf_nan=False)
    load_unload_cooldown_seconds: float = Field(default=300, ge=0, allow_inf_nan=False)
    continuation_lease_ttl_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    failure_limit: int = Field(default=3, ge=1)
    failure_window_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)

    @field_validator("roles", mode="before")
    @classmethod
    def validate_roles(cls, value: Any) -> Any:
        if value is None:
            return default_lifecycle_roles()
        if not isinstance(value, dict):
            raise ValueError("lifecycle roles must be a mapping")
        unknown = set(value) - MODEL_ROLES
        if unknown:
            raise ValueError(f"unknown lifecycle role: {sorted(unknown)[0]}")
        merged: dict[str, Any] = {
            role: policy.model_dump() for role, policy in default_lifecycle_roles().items()
        }
        for role, override in value.items():
            if not isinstance(override, dict):
                raise ValueError(f"lifecycle policy for {role} must be a mapping")
            merged[role].update(override)
        return merged


def default_loop_budgets() -> dict[str, int | float]:
    return {
        "iterations": 4,
        "tool_calls": 30,
        "reasoner_reentries": 4,
        "planner_calls": 2,
        "reviewer_calls": 2,
        "frontier_calls": 2,
        "judge_calls": 2,
        "tokens": 250_000,
        "external_cost_usd": 10,
        "wall_clock_seconds": 1_800,
    }


class LoopEngineeringPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    defaults: dict[str, int | float] = Field(default_factory=default_loop_budgets)
    duplicate_fingerprint_limit: int = Field(default=2, ge=1)
    no_progress_iteration_limit: int = Field(default=2, ge=1)
    local_failures_before_frontier: int = Field(default=2, ge=1)
    request_class_overrides: dict[str, dict[str, int | float]] = Field(default_factory=dict)
    risk_level_overrides: dict[str, dict[str, int | float]] = Field(default_factory=dict)

    @field_validator("defaults")
    @classmethod
    def validate_defaults(cls, value: dict[str, int | float]) -> dict[str, int | float]:
        from .loop_engineering import LoopBudget

        return LoopBudget.model_validate(value).model_dump()

    @field_validator("request_class_overrides", "risk_level_overrides")
    @classmethod
    def validate_budget_overrides(
        cls, value: dict[str, dict[str, int | float]]
    ) -> dict[str, dict[str, int | float]]:
        allowed = set(default_loop_budgets())
        for name, override in value.items():
            if not name or set(override) - allowed:
                raise ValueError("invalid loop budget override")
            if any(
                not isinstance(item, int | float) or isinstance(item, bool) or item < 0
                for item in override.values()
            ):
                raise ValueError("loop budget override must be nonnegative")
        return value

    @model_validator(mode="after")
    def validate_risk_levels(self) -> LoopEngineeringPolicy:
        if set(self.risk_level_overrides) - {"low", "medium", "high"}:
            raise ValueError("invalid loop risk level")
        return self

    def budget_for(self, request_class: str, risk_level: str) -> dict[str, int | float]:
        return (
            self.defaults
            | self.request_class_overrides.get(request_class, {})
            | self.risk_level_overrides.get(risk_level, {})
        )


class RuntimeSkillsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    root: Path = Path("data/skills")
    retrieval_limit: int = Field(default=3, ge=1, le=10)
    max_context_characters: int = Field(default=6_000, ge=256, le=32_000)


class RuntimeKnowledgePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    state_db: Path = Path("data/knowledge/knowledge.db")
    retrieval_limit: int = Field(default=3, ge=1, le=10)
    max_context_characters: int = Field(default=6_000, ge=256, le=32_000)


class RuntimeEvolutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    state_db: Path = Path("data/evolution/evolution.db")


class RemoteJudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: Literal["disabled", "opencode_go", "mock"] = "disabled"
    mode: Literal["selective"] = "selective"
    model: str = "glm-5.2"
    endpoint: str | None = None
    api_key_env: str = "OPENCODE_GO_API_KEY"
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_retries: int = Field(default=1, ge=0, le=3)
    max_calls_per_request: int = Field(default=2, ge=1, le=2)
    fail_closed_for: list[str] = Field(
        default_factory=lambda: [
            "production_deployment",
            "destructive_migration",
            "production_skill_promotion",
            "security_sensitive_change",
        ]
    )

    @model_validator(mode="after")
    def validate_provider(self) -> RemoteJudgeConfig:
        if self.enabled and self.provider == "disabled":
            raise ValueError("enabled Remote Judge requires a provider")
        if self.enabled and self.provider == "opencode_go" and not self.endpoint:
            raise ValueError("OpenCode Go Remote Judge requires an endpoint")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.api_key_env):
            raise ValueError("Remote Judge credential must be an environment variable name")
        return self


class SpecialistRoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: Literal["disabled", "opencode_go", "mock"] = "disabled"
    endpoint: str = "https://opencode.ai/zen/go"
    api_key_env: str = "OPENCODE_GO_API_KEY"
    models: dict[str, str] = Field(
        default_factory=lambda: {
            "planner": "deepseek-v4-pro",
            "reviewer": "deepseek-v4-flash",
        }
    )
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    local_latency_seconds: dict[str, float] = Field(
        default_factory=lambda: {"planner": 30.0, "reviewer": 45.0}
    )
    remote_latency_seconds: dict[str, float] = Field(
        default_factory=lambda: {"planner": 25.0, "reviewer": 5.0}
    )
    remote_min_completion_tokens: dict[str, int] = Field(
        default_factory=lambda: {"planner": 4_096, "reviewer": 2_048}
    )
    network_latency_seconds: float = Field(default=0.25, ge=0, allow_inf_nan=False)
    remote_queue_latency_seconds: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    local_preference_margin_seconds: float = Field(default=5.0, ge=0, allow_inf_nan=False)
    cost_seconds_per_usd: float = Field(default=60.0, ge=0, allow_inf_nan=False)
    remote_cost_per_million_tokens_usd: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    warmup_watch_seconds: float = Field(default=1_200, gt=0, le=7_200)
    race_mode_enabled: bool = False

    @model_validator(mode="after")
    def validate_specialists(self) -> SpecialistRoutingConfig:
        if self.enabled and self.provider == "disabled":
            raise ValueError("enabled specialist routing requires a remote provider")
        if self.enabled and not self.endpoint:
            raise ValueError("enabled specialist routing requires an endpoint")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.api_key_env):
            raise ValueError("specialist credential must be an environment variable name")
        if self.race_mode_enabled:
            raise ValueError("specialist race mode is not supported by the default policy")
        required_roles = {"planner", "reviewer"}
        if set(self.models) != required_roles:
            raise ValueError("specialist models must define planner and reviewer")
        if set(self.local_latency_seconds) != required_roles:
            raise ValueError("local latency estimates must define planner and reviewer")
        if set(self.remote_latency_seconds) != required_roles:
            raise ValueError("remote latency estimates must define planner and reviewer")
        if set(self.remote_min_completion_tokens) != required_roles or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in self.remote_min_completion_tokens.values()
        ):
            raise ValueError("remote token floors must define positive planner and reviewer values")
        return self


class DeclarativePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    version: str = "development-disabled"
    policies: list[PolicyRule] = Field(default_factory=list, max_length=256)

    def policy_set(self) -> PolicySet:
        return PolicySet(version=self.version, policies=self.policies)


class DiscordObservationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    webhook_url: SecretStr
    thread_id: str | None = None


class TelegramObservationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: SecretStr
    chat_id: str
    message_thread_id: int | None = None


class ObservationControlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    nonce_ttl_seconds: int = Field(default=300, ge=30, le=3_600)
    allowed_users: dict[str, str] = Field(default_factory=dict)
    role_permissions: dict[str, list[str]] = Field(default_factory=dict)


class LiveObservationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    level: Literal["minimal", "normal", "verbose", "debug"] = "normal"
    include_prompt: bool = False
    include_reasoner_artifact: bool = False
    max_content_characters: int = Field(default=2_000, ge=200, le=10_000)
    queue_size: int = Field(default=256, ge=1, le=10_000)
    batch_size: int = Field(default=10, ge=1, le=50)
    batch_interval_seconds: float = Field(default=2, ge=0.1, le=60)
    request_timeout_seconds: float = Field(default=10, gt=0, le=60)
    discord: DiscordObservationConfig | None = None
    telegram: TelegramObservationConfig | None = None
    controls: ObservationControlConfig = Field(default_factory=ObservationControlConfig)


class TrainingDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    state_db: Path = Path("data/training-staging/training.db")
    object_root: Path = Path("data/training-staging/objects")
    minimum_free_bytes: int = Field(default=10_000_000_000, ge=0)
    maximum_object_bytes: int = Field(default=1_000_000, ge=1_024, le=16_000_000)
    repository_policies: dict[
        str, Literal["training_allowed", "internal_only", "training_denied"]
    ] = Field(default_factory=dict)
    external_output_permitted: bool = False


class RetentionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_operational_days: int = Field(default=30, ge=1)
    sanitized_candidate_days: int = Field(default=90, ge=1)
    weekly_archive_weeks: int = Field(default=52, ge=1)
    quarantine_days: int = Field(default=14, ge=1)
    failed_staging_days: int = Field(default=7, ge=1)


class WeeklyJobsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    timezone: str = "Asia/Seoul"
    skill_schedule: str = "0 3 * * 0"
    package_schedule: str = "0 2 * * 1"
    package_root: Path = Path("data/weekly-packages")
    archive_registry: Path = Path("data/archive-registry/weekly.db")
    minimum_free_bytes: int = Field(default=10_000_000_000, ge=0)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("invalid weekly timezone") from error
        return value

    @field_validator("skill_schedule", "package_schedule")
    @classmethod
    def validate_schedule(cls, value: str) -> str:
        from .weekly import CronSchedule

        CronSchedule.parse(value)
        return value


class ModelConfig(BaseModel):
    repository: str
    revision: str
    classification: str
    base_url: str
    served_name: str
    destination: Path
    provider: Literal["openai", "ollama"] = "openai"
    lifecycle_control: Literal["systemd", "external"] = "systemd"
    ollama_keep_alive: str | int = -1
    context_length: int = Field(ge=65_536)
    max_num_seqs: int = 1
    quantization: str | None = None
    tool_call_parser: str | None = None
    reasoning_parser: str | None = None
    trust_remote_code: bool = False
    lora_adapter: Path | None = None
    required: bool = True


class Settings(BaseModel):
    model_name: str = "dgx-moa"
    bind_host: str = "127.0.0.1"
    bind_port: int = 9000
    auth_enabled: bool = True
    api_key: str | None = None
    api_keys: dict[str, str] = Field(default_factory=dict)
    admin_api_enabled: bool = False
    admin_token_ids: tuple[str, ...] = ("operator",)
    max_admin_api_keys: int = Field(default=3, ge=1, le=10)
    state_db: Path = Path("data/state/gateway.db")
    run_dir: Path = Path("data/run")
    runtime_channel: str = "dev"
    trace_origin: str = "validation"
    controller_commit: str = "unknown"
    vllm_version: str = "unknown"
    frontier_enabled: bool = False
    frontier_disabled_reason: str = "configuration_disabled"
    frontier_config: Path = Path("config/codex-frontier.yaml")
    lifecycle_mode: Literal["disabled", "observe", "fixed", "adaptive"] = "disabled"
    lifecycle_poll_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    lifecycle_unit_map: dict[str, str] = Field(default_factory=dict)
    lifecycle: LifecyclePolicy = Field(default_factory=LifecyclePolicy)
    loop_engineering: LoopEngineeringPolicy = Field(default_factory=LoopEngineeringPolicy)
    runtime_skills: RuntimeSkillsPolicy = Field(default_factory=RuntimeSkillsPolicy)
    runtime_knowledge: RuntimeKnowledgePolicy = Field(default_factory=RuntimeKnowledgePolicy)
    runtime_evolution: RuntimeEvolutionConfig = Field(default_factory=RuntimeEvolutionConfig)
    remote_judge: RemoteJudgeConfig = Field(default_factory=RemoteJudgeConfig)
    specialist_routing: SpecialistRoutingConfig = Field(default_factory=SpecialistRoutingConfig)
    declarative_policy: DeclarativePolicyConfig = Field(default_factory=DeclarativePolicyConfig)
    live_observation: LiveObservationConfig = Field(default_factory=LiveObservationConfig)
    training_data: TrainingDataConfig = Field(default_factory=TrainingDataConfig)
    weekly_jobs: WeeklyJobsConfig = Field(default_factory=WeeklyJobsConfig)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)

    @field_validator("auth_enabled", "admin_api_enabled", "frontier_enabled", mode="before")
    @classmethod
    def validate_boolean(cls, value: Any) -> bool:
        return parse_bool(value)

    @model_validator(mode="after")
    def validate_authentication(self) -> Settings:
        keys = self.api_keys or ({"default": self.api_key} if self.api_key else {})
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name) for name in keys):
            raise ValueError("API token IDs must be lowercase safe identifiers")
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name) for name in self.admin_token_ids):
            raise ValueError("admin token IDs must be lowercase safe identifiers")
        invalid = any(
            not value
            or value.strip().lower() in API_KEY_PLACEHOLDERS
            or "replace-with" in value.strip().lower()
            for value in keys.values()
        )
        if self.auth_enabled and (not keys or invalid):
            raise ValueError(
                "DGX_MOA_API_KEY or DGX_MOA_API_KEYS must contain non-placeholder tokens when "
                "DGX_MOA_AUTH_ENABLED=true"
            )
        return self

    def configured_api_keys(self) -> dict[str, str]:
        return self.api_keys or ({"default": self.api_key} if self.api_key else {})

    @field_validator("lifecycle_unit_map")
    @classmethod
    def validate_lifecycle_unit_map(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - MODEL_ROLES
        if unknown:
            raise ValueError(f"unknown lifecycle role: {sorted(unknown)[0]}")
        if any(not SYSTEMD_UNIT_PATTERN.fullmatch(unit) for unit in value.values()):
            raise ValueError("invalid systemd unit")
        if len(set(value.values())) != len(value):
            raise ValueError("duplicate lifecycle unit")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_runtime(self) -> Settings:
        if self.runtime_channel != "main" and any(
            not unit.startswith("dgx-moa-dev-") for unit in self.lifecycle_unit_map.values()
        ):
            raise ValueError("non-main lifecycle units must use the dgx-moa-dev namespace")
        conflicting = sorted(
            role
            for role in self.lifecycle_unit_map
            if role in self.models and self.models[role].lifecycle_control == "external"
        )
        if conflicting:
            raise ValueError(
                f"external lifecycle role cannot have a systemd unit: {conflicting[0]}"
            )
        if self.training_data.enabled and self.training_data.state_db == self.state_db:
            raise ValueError("training state database must be separate from gateway state")
        if self.specialist_routing.enabled:
            missing = {"planner", "reviewer"} - set(self.models)
            if missing:
                raise ValueError(f"specialist routing requires local model: {sorted(missing)[0]}")
        return self


def load_settings(path: str | Path | None = None) -> Settings:
    raw_path: str | Path = (
        path if path is not None else os.getenv("DGX_MOA_CONFIG", "config/models.yaml")
    )
    config_path = Path(raw_path)
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
    gateway = dict(raw.get("gateway", {}))
    gateway["models"] = raw.get("models", {})
    gateway["auth_enabled"] = os.getenv("DGX_MOA_AUTH_ENABLED", gateway.get("auth_enabled", True))
    gateway["api_key"] = os.getenv("DGX_MOA_API_KEY", gateway.get("api_key"))
    api_keys: Any = os.getenv("DGX_MOA_API_KEYS", gateway.get("api_keys", {}))
    if isinstance(api_keys, str):
        try:
            api_keys = json.loads(api_keys)
        except json.JSONDecodeError as error:
            raise ValueError("DGX_MOA_API_KEYS must be a JSON object") from error
    gateway["api_keys"] = api_keys
    gateway["admin_api_enabled"] = os.getenv(
        "DGX_MOA_ADMIN_API_ENABLED", gateway.get("admin_api_enabled", False)
    )
    admin_token_ids: Any = os.getenv(
        "DGX_MOA_ADMIN_TOKEN_IDS", gateway.get("admin_token_ids", ["operator"])
    )
    if isinstance(admin_token_ids, str):
        try:
            admin_token_ids = json.loads(admin_token_ids)
        except json.JSONDecodeError as error:
            raise ValueError("DGX_MOA_ADMIN_TOKEN_IDS must be a JSON array") from error
    gateway["admin_token_ids"] = admin_token_ids
    gateway["max_admin_api_keys"] = os.getenv(
        "DGX_MOA_MAX_ADMIN_API_KEYS", gateway.get("max_admin_api_keys", 3)
    )
    gateway["bind_host"] = os.getenv("DGX_MOA_BIND_HOST", gateway.get("bind_host", "127.0.0.1"))
    gateway["bind_port"] = os.getenv("DGX_MOA_BIND_PORT", gateway.get("bind_port", 9000))
    gateway["state_db"] = os.getenv(
        "DGX_MOA_STATE_DB", gateway.get("state_db", "data/state/gateway.db")
    )
    gateway["runtime_channel"] = os.getenv(
        "DGX_MOA_RUNTIME_CHANNEL", gateway.get("runtime_channel", "dev")
    )
    gateway["trace_origin"] = os.getenv(
        "DGX_MOA_TRACE_ORIGIN", gateway.get("trace_origin", "validation")
    )
    gateway["controller_commit"] = os.getenv(
        "DGX_MOA_CONTROLLER_COMMIT", gateway.get("controller_commit", "unknown")
    )
    gateway["vllm_version"] = os.getenv(
        "DGX_MOA_VLLM_VERSION", gateway.get("vllm_version", "unknown")
    )
    gateway["frontier_enabled"] = os.getenv(
        "DGX_MOA_FRONTIER_ENABLED", gateway.get("frontier_enabled", False)
    )
    gateway["frontier_disabled_reason"] = os.getenv(
        "DGX_MOA_FRONTIER_DISABLED_REASON",
        gateway.get("frontier_disabled_reason", "configuration_disabled"),
    )
    gateway["frontier_config"] = os.getenv(
        "DGX_MOA_FRONTIER_CONFIG",
        gateway.get("frontier_config", "config/codex-frontier.yaml"),
    )
    gateway["lifecycle_mode"] = os.getenv(
        "DGX_MOA_LIFECYCLE_MODE", gateway.get("lifecycle_mode", "disabled")
    )
    gateway["lifecycle_poll_seconds"] = os.getenv(
        "DGX_MOA_LIFECYCLE_POLL_SECONDS", gateway.get("lifecycle_poll_seconds", 30)
    )
    unit_map: Any = os.getenv("DGX_MOA_LIFECYCLE_UNIT_MAP", gateway.get("lifecycle_unit_map", {}))
    if isinstance(unit_map, str):
        with suppress(json.JSONDecodeError):
            unit_map = json.loads(unit_map)
    gateway["lifecycle_unit_map"] = unit_map
    lifecycle: Any = os.getenv("DGX_MOA_LIFECYCLE_POLICY", gateway.get("lifecycle", {}))
    if isinstance(lifecycle, str):
        with suppress(json.JSONDecodeError):
            lifecycle = json.loads(lifecycle)
    gateway["lifecycle"] = lifecycle
    loop_engineering: Any = os.getenv(
        "DGX_MOA_LOOP_ENGINEERING", gateway.get("loop_engineering", {})
    )
    if isinstance(loop_engineering, str):
        with suppress(json.JSONDecodeError):
            loop_engineering = json.loads(loop_engineering)
    gateway["loop_engineering"] = loop_engineering
    runtime_skills: Any = os.getenv("DGX_MOA_RUNTIME_SKILLS", gateway.get("runtime_skills", {}))
    if isinstance(runtime_skills, str):
        with suppress(json.JSONDecodeError):
            runtime_skills = json.loads(runtime_skills)
    gateway["runtime_skills"] = runtime_skills
    runtime_knowledge: Any = os.getenv(
        "DGX_MOA_RUNTIME_KNOWLEDGE", gateway.get("runtime_knowledge", {})
    )
    if isinstance(runtime_knowledge, str):
        with suppress(json.JSONDecodeError):
            runtime_knowledge = json.loads(runtime_knowledge)
    gateway["runtime_knowledge"] = runtime_knowledge
    runtime_evolution: Any = os.getenv(
        "DGX_MOA_RUNTIME_EVOLUTION", gateway.get("runtime_evolution", {})
    )
    if isinstance(runtime_evolution, str):
        with suppress(json.JSONDecodeError):
            runtime_evolution = json.loads(runtime_evolution)
    gateway["runtime_evolution"] = runtime_evolution
    remote_judge: Any = os.getenv("DGX_MOA_REMOTE_JUDGE", gateway.get("remote_judge", {}))
    if isinstance(remote_judge, str):
        with suppress(json.JSONDecodeError):
            remote_judge = json.loads(remote_judge)
    gateway["remote_judge"] = remote_judge
    specialist_routing: Any = os.getenv(
        "DGX_MOA_SPECIALIST_ROUTING", gateway.get("specialist_routing", {})
    )
    if isinstance(specialist_routing, str):
        with suppress(json.JSONDecodeError):
            specialist_routing = json.loads(specialist_routing)
    gateway["specialist_routing"] = specialist_routing
    declarative_policy: Any = os.getenv(
        "DGX_MOA_DECLARATIVE_POLICY", gateway.get("declarative_policy", {})
    )
    if isinstance(declarative_policy, str):
        with suppress(json.JSONDecodeError):
            declarative_policy = json.loads(declarative_policy)
    gateway["declarative_policy"] = declarative_policy
    live_observation: Any = os.getenv(
        "DGX_MOA_LIVE_OBSERVATION", gateway.get("live_observation", {})
    )
    if isinstance(live_observation, str):
        with suppress(json.JSONDecodeError):
            live_observation = json.loads(live_observation)
    gateway["live_observation"] = live_observation
    training_data: Any = os.getenv("DGX_MOA_TRAINING_DATA", gateway.get("training_data", {}))
    if isinstance(training_data, str):
        with suppress(json.JSONDecodeError):
            training_data = json.loads(training_data)
    gateway["training_data"] = training_data
    weekly_jobs: Any = os.getenv("DGX_MOA_WEEKLY_JOBS", gateway.get("weekly_jobs", {}))
    if isinstance(weekly_jobs, str):
        with suppress(json.JSONDecodeError):
            weekly_jobs = json.loads(weekly_jobs)
    gateway["weekly_jobs"] = weekly_jobs
    return Settings.model_validate(gateway)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
