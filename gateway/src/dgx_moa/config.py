from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}
API_KEY_PLACEHOLDERS = {
    "replace-with-a-long-random-token",
    "replace-with-a-long-random-value",
}


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
    max_tool_output_characters: int = 20_000
    max_retained_observations: int = 30
    max_error_lines: int = 40
    max_diff_summary_lines: int = 100
    planner_tokens: int = 1_500
    executor_tokens: int = 1_000
    reviewer_tokens: int = 1_500
    judge_tokens: int = 2_500
    max_steps: int = 100


class ModelConfig(BaseModel):
    repository: str
    revision: str
    classification: str
    base_url: str
    served_name: str
    destination: Path
    context_length: int
    max_num_seqs: int = 1
    quantization: str | None = None
    tool_call_parser: str | None = None
    reasoning_parser: str | None = None
    trust_remote_code: bool = False
    lora_adapter: Path | None = None
    required: bool = True


class Settings(BaseModel):
    model_name: str = "dgx-moa-agent"
    bind_host: str = "127.0.0.1"
    bind_port: int = 9000
    auth_enabled: bool = True
    api_key: str | None = None
    admin_api_enabled: bool = False
    state_db: Path = Path("data/state/gateway.db")
    run_dir: Path = Path("data/run")
    runtime_channel: str = "dev"
    trace_origin: str = "validation"
    controller_commit: str = "unknown"
    vllm_version: str = "unknown"
    frontier_enabled: bool = False
    frontier_disabled_reason: str = "host_sandbox_capability_blocked"
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)

    @field_validator("auth_enabled", "admin_api_enabled", "frontier_enabled", mode="before")
    @classmethod
    def validate_boolean(cls, value: Any) -> bool:
        return parse_bool(value)

    @model_validator(mode="after")
    def validate_authentication(self) -> Settings:
        if self.auth_enabled and (
            not self.api_key
            or self.api_key.strip().lower() in API_KEY_PLACEHOLDERS
            or "replace-with" in self.api_key.strip().lower()
        ):
            raise ValueError(
                "DGX_MOA_API_KEY must contain a non-placeholder token when "
                "DGX_MOA_AUTH_ENABLED=true"
            )
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
    gateway["admin_api_enabled"] = os.getenv(
        "DGX_MOA_ADMIN_API_ENABLED", gateway.get("admin_api_enabled", False)
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
        gateway.get("frontier_disabled_reason", "host_sandbox_capability_blocked"),
    )
    return Settings.model_validate(gateway)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
