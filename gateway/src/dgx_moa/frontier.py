"""Bounded Codex frontier runs; no credential handling or automatic failover."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .security import redact
from .state import SessionState

PROFILE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
DEFAULT_PROFILE_ROOT = Path("/home/kotori9/.local/share/dgx-moa/codex-profiles")
CODEX_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TERM",
        "TMPDIR",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    }
)
FORBIDDEN_PATHS = (".env", ".env.local", "systemd/", "config/tailscale")
IMMUTABLE_EVALUATOR_PATHS = (
    "data/benchmarks/",
    "gateway/src/dgx_moa/benchmark.py",
    "gateway/src/dgx_moa/improvement.py",
    "scripts/evaluate-improvement.sh",
)
FRONTIER_FAILURES = frozenset(
    {
        "FRONTIER_AUTH_ERROR",
        "FRONTIER_CONTEXT_LIMIT",
        "FRONTIER_USAGE_LIMIT",
        "FRONTIER_RATE_LIMIT",
        "FRONTIER_TIMEOUT",
        "FRONTIER_PROVIDER_UNAVAILABLE",
        "FRONTIER_PROFILE_BUSY",
        "FRONTIER_CIRCUIT_OPEN",
        "FRONTIER_PROTOCOL_ERROR",
        "FRONTIER_SCOPE_VIOLATION",
        "FRONTIER_VALIDATION_FAILURE",
    }
)
PROFILE_FAILOVER_FAILURES = frozenset(
    {
        "FRONTIER_AUTH_ERROR",
        "FRONTIER_CONTEXT_LIMIT",
        "FRONTIER_USAGE_LIMIT",
        "FRONTIER_RATE_LIMIT",
        "FRONTIER_PROFILE_BUSY",
    }
)
PAID_FALLBACK_FAILURES = PROFILE_FAILOVER_FAILURES | frozenset(
    {"FRONTIER_PROVIDER_UNAVAILABLE", "FRONTIER_TIMEOUT"}
)


class FrontierTask(BaseModel):
    schema_version: str = "frontier-task-v1"
    task_id: str
    objective: str
    repository_identity: dict[str, str] = Field(default_factory=dict)
    base_commit: str
    allowed_paths: list[str]
    acceptance_criteria: list[str]
    verified_facts: list[str] = Field(default_factory=list)
    failure_summary: str = ""
    planner_conclusion: str = ""
    reviewer_conclusion: str = ""
    judge_verdict: dict[str, Any] | None = None
    relevant_diff: str = ""
    validation_commands: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=lambda: list(FORBIDDEN_PATHS))


class FrontierChange(BaseModel):
    path: str
    purpose: str


class FrontierValidation(BaseModel):
    command: str
    exit_code: int
    summary: str


class FrontierResult(BaseModel):
    schema_version: str = "frontier-result-v1"
    status: str
    summary: str
    root_cause: str
    changes: list[FrontierChange] = Field(default_factory=list)
    validation: list[FrontierValidation] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)
    recommended_next_action: str
    commit: str | None = None


class FrontierConfig(BaseModel):
    provider: str = "codex_oauth"
    connected: bool = True
    enabled: bool = False
    disabled_reason: Literal[
        "configuration_disabled",
        "host_sandbox_capability_blocked",
        "oauth_unavailable",
        "usage_limited",
    ] = "configuration_disabled"
    protocol: str = "codex-exec-jsonl"
    model: str = "gpt-5.6-sol"
    reasoning_effort: Literal["high"] = "high"
    max_invocations_per_task: int = 4
    max_recursive_cycles: int = 3
    primary_profile: str = "default"
    secondary_profile: str | None = None
    tertiary_profile: str | None = None
    allow_profile_failover: bool = False
    profile_root: Path | None = None
    collaboration_timeout_seconds: int = 300
    collaboration_retries: int = 1
    circuit_failure_limit: int = 3
    circuit_cooldown_seconds: int = 300
    max_evidence_characters: int = Field(default=24_000, ge=1_000, le=100_000)
    max_executor_evidence_characters: int = Field(default=200_000, ge=1_000, le=800_000)
    allowed_evidence_categories: list[str] = Field(
        default_factory=lambda: [
            "objective",
            "constraints",
            "acceptance_criteria",
            "reasoner_risks",
            "reasoner_recommendations",
            "relevant_evidence",
            "specific_questions",
            "changed_paths",
            "bounded_diff",
            "diff",
            "test_results",
            "static_analysis_results",
            "local_reviewer_findings",
            "known_limitations",
            "tool_results",
            "tool_executions",
            "reasoner_position",
            "executor_position",
            "planner_position",
            "reviewer_position",
            "shared_evidence",
            "specific_disagreement",
        ]
    )
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    openrouter_fallback_enabled: bool = False
    openrouter_endpoint: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-sonnet-4.6"
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"
    openrouter_api_key_file: Path | None = None
    openrouter_timeout_seconds: int = Field(default=300, ge=1, le=900)
    openrouter_max_evidence_characters: int = Field(default=200_000, ge=1_000, le=800_000)
    openrouter_input_cost_per_million: float = Field(default=3.0, ge=0)
    openrouter_output_cost_per_million: float = Field(default=15.0, ge=0)

    @model_validator(mode="after")
    def validate_profile_failover(self) -> FrontierConfig:
        validate_profile_name(self.primary_profile)
        if self.secondary_profile is not None:
            validate_profile_name(self.secondary_profile)
            if self.secondary_profile == self.primary_profile:
                raise ValueError("secondary_profile must differ from primary_profile")
        if self.tertiary_profile is not None:
            validate_profile_name(self.tertiary_profile)
            if self.tertiary_profile in {self.primary_profile, self.secondary_profile}:
                raise ValueError("tertiary_profile must differ from earlier profiles")
        if self.allow_profile_failover and self.secondary_profile is None:
            raise ValueError("allow_profile_failover requires secondary_profile")
        if self.tertiary_profile is not None and not self.allow_profile_failover:
            raise ValueError("tertiary_profile requires allow_profile_failover")
        if (
            self.openrouter_fallback_enabled
            and self.openrouter_api_key_file is None
            and not self.openrouter_api_key_env
        ):
            raise ValueError("OpenRouter fallback requires an API key source")
        return self


def bounded_external_evidence(
    evidence: dict[str, Any], config: FrontierConfig
) -> tuple[dict[str, Any], str]:
    allowed = set(config.allowed_evidence_categories)
    filtered = {str(key): redact(value) for key, value in evidence.items() if key in allowed}
    serialized = json.dumps(filtered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(serialized) <= config.max_evidence_characters:
        return filtered, serialized
    budget = max(256, config.max_evidence_characters // max(1, len(filtered)))
    while True:
        bounded = {
            key: {"truncated_excerpt": json.dumps(value, ensure_ascii=False)[:budget]}
            for key, value in filtered.items()
        }
        serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(serialized) <= config.max_evidence_characters or budget <= 16:
            return bounded, serialized
        budget //= 2


def openrouter_response_schema(schema_model: type[BaseModel]) -> dict[str, Any]:
    """Remove numeric constraints Anthropic structured outputs do not accept."""
    unsupported = {"exclusiveMaximum", "exclusiveMinimum", "maximum", "minimum", "multipleOf"}

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in unsupported
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return cast(dict[str, Any], clean(schema_model.model_json_schema()))


class FrontierArchitectureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_architecture: str
    design_decisions: list[str]
    tradeoffs: list[str]
    failure_modes: list[str]
    implementation_sequence: list[str]
    review_questions: list[str]


class FrontierReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approve", "revise", "reject"]
    critical: list[str]
    important: list[str]
    suggestions: list[str]
    missing_tests: list[str]
    confidence: float = Field(ge=0, le=1)


class FrontierDisagreementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_position: str
    evidence: list[str]
    rejected_assumptions: list[str]
    required_follow_up: list[str]
    confidence: float = Field(ge=0, le=1)


class FrontierExecutorFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: str

    @model_validator(mode="after")
    def validate_arguments(self) -> FrontierExecutorFunction:
        parsed = json.loads(self.arguments)
        if not isinstance(parsed, dict):
            raise ValueError("executor tool arguments must be a JSON object")
        return self


class FrontierExecutorToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["function"]
    function: FrontierExecutorFunction


class FrontierExecutorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant"]
    content: str | None
    tool_calls: list[FrontierExecutorToolCall]
    finish_reason: Literal["stop", "tool_calls"]

    @model_validator(mode="after")
    def validate_output(self) -> FrontierExecutorResult:
        if not self.content and not self.tool_calls:
            raise ValueError("executor output requires content or a tool call")
        if self.tool_calls and self.finish_reason != "tool_calls":
            raise ValueError("executor tool calls require tool_calls finish reason")
        if not self.tool_calls and self.finish_reason != "stop":
            raise ValueError("executor text requires stop finish reason")
        return self


def sanitize_executor_tool_paths(
    message: FrontierExecutorResult,
    workspace_root: str | Path | None = None,
) -> tuple[FrontierExecutorResult, int]:
    """Keep remote tool calls inside the client's own working directory."""
    sanitized = 0
    root = Path(workspace_root).resolve() if workspace_root else None
    tool_calls: list[FrontierExecutorToolCall] = []
    for call in message.tool_calls:
        arguments = json.loads(call.function.arguments)
        for key in ("workdir", "cwd"):
            value = arguments.get(key)
            if isinstance(value, str) and Path(value).is_absolute():
                arguments.pop(key)
                sanitized += 1
        if root is not None:
            for key in ("patch", "input"):
                value = arguments.get(key)
                if not isinstance(value, str):
                    continue
                lines: list[str] = []
                for line in value.splitlines(keepends=True):
                    match = re.match(r"(\*\*\* (?:Add|Delete|Update) File: )(.+?)(\r?\n)?$", line)
                    if match is None or not Path(match.group(2)).is_absolute():
                        lines.append(line)
                        continue
                    try:
                        relative = Path(match.group(2)).resolve().relative_to(root)
                    except ValueError:
                        lines.append(line)
                        continue
                    lines.append(f"{match.group(1)}{relative}{match.group(3) or ''}")
                    sanitized += 1
                arguments[key] = "".join(lines)
        tool_calls.append(
            call.model_copy(
                update={
                    "function": call.function.model_copy(
                        update={
                            "arguments": json.dumps(
                                arguments,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        }
                    )
                }
            )
        )
    return message.model_copy(update={"tool_calls": tool_calls}), sanitized


COLLABORATION_SCHEMAS: dict[str, type[BaseModel]] = {
    "architecture": FrontierArchitectureResult,
    "code_review": FrontierReviewResult,
    "disagreement": FrontierDisagreementResult,
    "executor": FrontierExecutorResult,
}

COLLABORATION_MODE_INSTRUCTIONS = {
    "code_review": (
        "For code_review, judge only against the supplied objective, acceptance criteria, "
        "constraints, diff, and test evidence. Do not turn optional hardening, broader "
        "multi-process/distributed support, or stronger durability than the stated contract "
        "into required work. Use approve when the stated contract is met, even if suggestions "
        "remain. Use revise only for a concrete contract violation or material regression, and "
        "use reject only for an unsafe or fundamentally invalid implementation. Inspect every "
        "public numeric parameter for boolean confusion, NaN, and both infinities when arithmetic, "
        "time, window, size, or capacity semantics require finite values."
    ),
    "architecture": (
        "For architecture, distinguish required decisions from optional future hardening."
    ),
    "disagreement": (
        "For disagreement, prefer the position best supported by the supplied evidence."
    ),
    "executor": (
        "For executor, reason privately in English, answer in the last user's language, and "
        "represent any client tool use only as tool_calls from the supplied definitions. Never "
        "invoke a tool name as a shell command. If apply_patch is not one of the supplied tools, "
        "use an available command tool with a shell-native heredoc or language-native file write."
    ),
}


class FrontierCollaborationResult(BaseModel):
    mode: Literal["architecture", "code_review", "disagreement", "executor"]
    output: dict[str, Any]
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float
    transmitted_categories: list[str]
    profile: str = "unknown"


def codex_usage(output: str) -> tuple[int | None, int | None]:
    prompt = completion = 0
    found = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        usage = event.get("usage") if isinstance(event, dict) else None
        if not isinstance(usage, dict):
            continue
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
        if isinstance(input_tokens, int) and not isinstance(input_tokens, bool):
            prompt = max(prompt, input_tokens)
            found = True
        if isinstance(output_tokens, int) and not isinstance(output_tokens, bool):
            completion = max(completion, output_tokens)
            found = True
    return (prompt, completion) if found else (None, None)


class CodexOAuthCollaboration:
    def __init__(
        self,
        config: FrontierConfig,
        run_dir: str | Path,
        project_root: str | Path,
        profile_root: str | Path | None = None,
    ) -> None:
        self.config = config
        self.run_dir = Path(run_dir)
        self.project_root = Path(project_root).resolve()
        self.provider = CodexOAuthProvider(
            config.primary_profile,
            (
                None
                if config.primary_profile == "default"
                else config.profile_root
                if profile_root is None
                else profile_root
            ),
        )
        self.providers = [(config.primary_profile, self.provider)]
        if config.allow_profile_failover and config.secondary_profile:
            for fallback_profile in (
                config.secondary_profile,
                config.tertiary_profile,
            ):
                if fallback_profile is not None:
                    self.providers.append(
                        (
                            fallback_profile,
                            CodexOAuthProvider(
                                fallback_profile,
                                (
                                    None
                                    if fallback_profile == "default"
                                    else config.profile_root
                                    if profile_root is None
                                    else profile_root
                                ),
                            ),
                        )
                    )
        self.failures = 0
        self.opened_at: float | None = None
        self.openrouter_calls: set[str] = set()

    def _cost(self, prompt: int | None, completion: int | None) -> float | None:
        if (
            prompt is None
            or completion is None
            or self.config.input_cost_per_million is None
            or self.config.output_cost_per_million is None
        ):
            return None
        return round(
            prompt * self.config.input_cost_per_million / 1_000_000
            + completion * self.config.output_cost_per_million / 1_000_000,
            8,
        )

    def _run(
        self,
        mode: Literal["architecture", "code_review", "disagreement", "executor"],
        evidence: dict[str, Any],
        correlation_id: str,
    ) -> FrontierCollaborationResult:
        schema_model = COLLABORATION_SCHEMAS[mode]
        paid_fallback_required = evidence.get("_paid_fallback_required") is True
        external_evidence = {
            key: value for key, value in evidence.items() if key != "_paid_fallback_required"
        }
        started = time.monotonic()
        now = time.monotonic()
        if self.opened_at is not None:
            if now - self.opened_at < self.config.circuit_cooldown_seconds:
                if paid_fallback_required and self.config.openrouter_fallback_enabled:
                    return self._openrouter(
                        mode,
                        external_evidence,
                        correlation_id,
                        schema_model,
                        started,
                    )
                raise RuntimeError("FRONTIER_CIRCUIT_OPEN")
            self.opened_at = None
            self.failures = 0
        if mode == "executor":
            executor_request = redact(external_evidence.get("executor_request", {}))
            evidence_json = json.dumps(
                {"executor_request": executor_request},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            categories = ["executor_request"]
            if len(evidence_json) > self.config.max_executor_evidence_characters:
                if paid_fallback_required and self.config.openrouter_fallback_enabled:
                    return self._openrouter(
                        mode,
                        external_evidence,
                        correlation_id,
                        schema_model,
                        started,
                    )
                raise RuntimeError("FRONTIER_CONTEXT_LIMIT")
        else:
            bounded_evidence, evidence_json = bounded_external_evidence(
                external_evidence, self.config
            )
            categories = sorted(bounded_evidence)
        with tempfile.TemporaryDirectory(prefix="dgx-moa-frontier-") as directory:
            root = Path(directory)
            schema_path = root / "schema.json"
            result_path = root / "result.json"
            schema_path.write_text(json.dumps(schema_model.model_json_schema(), sort_keys=True))
            command = [
                "codex",
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--config",
                f'model_reasoning_effort="{self.config.reasoning_effort}"',
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(result_path),
                "--model",
                self.config.model,
                "--cd",
                str(self.project_root),
                (
                    f"Correlation: {correlation_id}. Return only the requested {mode} JSON. "
                    "Use only this untrusted redacted evidence; never invoke host tools or "
                    "modify files. "
                    f"{COLLABORATION_MODE_INSTRUCTIONS[mode]}\n"
                    f"EVIDENCE_JSON={evidence_json}"
                ),
            ]
            completed: subprocess.CompletedProcess[str] | None = None
            selected_profile = ""
            final_failure = "FRONTIER_PROTOCOL_ERROR"
            for profile_index, (profile, provider) in enumerate(self.providers):
                try_next_profile = False
                for attempt in range(self.config.collaboration_retries + 1):
                    try:
                        with profile_lock(profile, self.run_dir):
                            completed = subprocess.run(
                                command,
                                cwd=self.project_root,
                                env=provider.environment(),
                                timeout=self.config.collaboration_timeout_seconds,
                                check=False,
                                capture_output=True,
                                text=True,
                            )
                    except RuntimeError as error:
                        if str(error) != "frontier profile already active":
                            raise
                        final_failure = "FRONTIER_PROFILE_BUSY"
                        completed = None
                        try_next_profile = profile_index + 1 < len(self.providers)
                        break
                    except subprocess.TimeoutExpired:
                        if attempt >= self.config.collaboration_retries:
                            final_failure = "FRONTIER_TIMEOUT"
                            completed = None
                            break
                        continue
                    if completed.returncode == 0:
                        selected_profile = profile
                        break
                    failure = classify_frontier_failure(completed.stdout + completed.stderr)
                    final_failure = failure
                    has_fallback = profile_index + 1 < len(self.providers)
                    if failure in PROFILE_FAILOVER_FAILURES and has_fallback:
                        completed = None
                        try_next_profile = True
                        break
                    if (
                        failure in PROFILE_FAILOVER_FAILURES
                        or attempt >= self.config.collaboration_retries
                    ):
                        completed = None
                        break
                if selected_profile:
                    break
                if not try_next_profile:
                    break
            if completed is None or not selected_profile or not result_path.is_file():
                if (
                    paid_fallback_required
                    and self.config.openrouter_fallback_enabled
                    and final_failure in PAID_FALLBACK_FAILURES
                ):
                    return self._openrouter(
                        mode,
                        external_evidence,
                        correlation_id,
                        schema_model,
                        started,
                    )
                self._failed()
                raise RuntimeError(final_failure)
            result = schema_model.model_validate_json(result_path.read_text()).model_dump()
            prompt, completion = codex_usage(completed.stdout)
        self.failures = 0
        self.opened_at = None
        return FrontierCollaborationResult(
            mode=mode,
            output=result,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=(
                prompt + completion if prompt is not None and completion is not None else None
            ),
            cost_usd=self._cost(prompt, completion),
            latency_ms=round((time.monotonic() - started) * 1000, 3),
            transmitted_categories=categories,
            profile=selected_profile,
        )

    def _openrouter(
        self,
        mode: Literal["architecture", "code_review", "disagreement", "executor"],
        evidence: dict[str, Any],
        correlation_id: str,
        schema_model: type[BaseModel],
        started: float,
    ) -> FrontierCollaborationResult:
        if correlation_id in self.openrouter_calls:
            self._failed()
            raise RuntimeError("FRONTIER_PAID_FALLBACK_LIMIT")
        self.openrouter_calls.add(correlation_id)
        if len(self.openrouter_calls) > 10_000:
            self.openrouter_calls.pop()
        key = os.getenv(self.config.openrouter_api_key_env, "").strip()
        if not key and self.config.openrouter_api_key_file is not None:
            key_path = self.config.openrouter_api_key_file
            try:
                if key_path.stat().st_mode & 0o077:
                    raise RuntimeError("FRONTIER_OPENROUTER_KEY_PERMISSIONS")
                key = key_path.read_text().strip()
            except OSError as error:
                raise RuntimeError("FRONTIER_OPENROUTER_AUTH_ERROR") from error
        if not key:
            raise RuntimeError("FRONTIER_OPENROUTER_AUTH_ERROR")
        fallback_config = self.config.model_copy(
            update={"max_evidence_characters": self.config.openrouter_max_evidence_characters}
        )
        if mode == "executor":
            executor_request = redact(evidence.get("executor_request", {}))
            if not isinstance(executor_request, dict):
                raise RuntimeError("FRONTIER_OPENROUTER_FAILURE")
            body = {
                key: value
                for key, value in executor_request.items()
                if key
                in {
                    "messages",
                    "tools",
                    "tool_choice",
                    "parallel_tool_calls",
                    "max_tokens",
                    "temperature",
                    "top_p",
                    "stop",
                }
            }
            messages = body.get("messages")
            if not isinstance(messages, list):
                raise RuntimeError("FRONTIER_OPENROUTER_FAILURE")
            body.update(
                {
                    "model": self.config.openrouter_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are the remote Executor fallback. Reason privately in "
                                "English, answer in the last user's language, and use only "
                                "supplied tool definitions. Never claim a tool result before "
                                "the client returns it."
                            ),
                        },
                        *messages,
                    ],
                    "stream": False,
                    "reasoning": {"effort": "high", "exclude": True},
                    "provider": {"require_parameters": True},
                }
            )
            bounded = {"executor_request": True}
        else:
            bounded, evidence_json = bounded_external_evidence(evidence, fallback_config)
            body = {
                "model": self.config.openrouter_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Return only the requested {mode} JSON. Use only the supplied "
                            "redacted evidence. Do not use tools, expose hidden reasoning, or "
                            "invent facts."
                        ),
                    },
                    {"role": "user", "content": evidence_json},
                ],
                "stream": False,
                "temperature": 0,
                "max_tokens": 4_096,
                "reasoning": {"effort": "high", "exclude": True},
                "provider": {"require_parameters": True},
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": f"frontier_{mode}",
                        "strict": True,
                        "schema": openrouter_response_schema(schema_model),
                    },
                },
            }
        try:
            with httpx.Client(timeout=self.config.openrouter_timeout_seconds) as client:
                response = client.post(
                    f"{self.config.openrouter_endpoint.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "DGX MoA Frontier Fallback",
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            if mode == "executor":
                result = schema_model.model_validate(
                    {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": message.get("tool_calls") or [],
                        "finish_reason": choice.get(
                            "finish_reason", "tool_calls" if message.get("tool_calls") else "stop"
                        ),
                    }
                ).model_dump()
            else:
                result = schema_model.model_validate_json(message["content"]).model_dump()
            usage = payload.get("usage", {})
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            prompt = prompt if isinstance(prompt, int) and not isinstance(prompt, bool) else None
            completion = (
                completion
                if isinstance(completion, int) and not isinstance(completion, bool)
                else None
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            self._failed()
            raise RuntimeError("FRONTIER_OPENROUTER_FAILURE") from error
        self.failures = 0
        self.opened_at = None
        cost = (
            round(
                prompt * self.config.openrouter_input_cost_per_million / 1_000_000
                + completion * self.config.openrouter_output_cost_per_million / 1_000_000,
                8,
            )
            if prompt is not None and completion is not None
            else None
        )
        return FrontierCollaborationResult(
            mode=mode,
            output=result,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=(
                prompt + completion if prompt is not None and completion is not None else None
            ),
            cost_usd=cost,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
            transmitted_categories=sorted(bounded),
            profile=f"openrouter:{self.config.openrouter_model}",
        )

    def _failed(self) -> None:
        self.failures += 1
        if self.failures >= self.config.circuit_failure_limit:
            self.opened_at = time.monotonic()

    async def collaborate(
        self,
        mode: Literal["architecture", "code_review", "disagreement"],
        evidence: dict[str, Any],
        correlation_id: str,
    ) -> FrontierCollaborationResult:
        return await asyncio.to_thread(self._run, mode, evidence, correlation_id)

    async def execute(
        self,
        request: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Run one remote logical-Executor turn without granting host tool authority."""
        workspace_root = request.get("_client_workspace_path")
        result = await asyncio.to_thread(
            self._run,
            "executor",
            {
                "executor_request": {
                    key: value
                    for key, value in request.items()
                    if key not in {"metadata", "stream", "_client_workspace_path"}
                },
                "_paid_fallback_required": True,
            },
            correlation_id,
        )
        message, sanitized_paths = sanitize_executor_tool_paths(
            FrontierExecutorResult.model_validate(result.output),
            workspace_root,
        )
        usage = {
            key: value
            for key, value in {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
            }.items()
            if value is not None
        }
        return {
            "id": f"chatcmpl-frontier-{correlation_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": (
                self.config.openrouter_model
                if result.profile.startswith("openrouter:")
                else self.config.model
            ),
            "choices": [
                {
                    "index": 0,
                    "message": message.model_dump(exclude={"finish_reason"}),
                    "finish_reason": message.finish_reason,
                }
            ],
            "usage": usage,
            "provider_provenance": {
                "provider": result.profile,
                "latency_ms": result.latency_ms,
                "cost_usd": result.cost_usd,
                "sanitized_absolute_workdirs": sanitized_paths,
            },
        }


class FrontierProvider(Protocol):
    def command(
        self,
        task_path: Path,
        worktree: Path,
        model: str,
        reasoning_effort: str,
        result_schema: Path,
    ) -> list[str]: ...

    def environment(self) -> dict[str, str]: ...


class CodexOAuthProvider:
    def __init__(self, profile: str, profile_root: str | Path | None = None):
        self.profile = validate_profile_name(profile)
        self.profile_root = Path(profile_root) if profile_root is not None else None

    def command(
        self,
        task_path: Path,
        worktree: Path,
        model: str,
        reasoning_effort: str,
        result_schema: Path,
    ) -> list[str]:
        return codex_command(
            self.profile, task_path, worktree, model, reasoning_effort, result_schema
        )

    def environment(self) -> dict[str, str]:
        environment = {
            key: value for key, value in os.environ.items() if key in CODEX_ENVIRONMENT_ALLOWLIST
        }
        if self.profile_root is not None:
            environment["CODEX_HOME"] = str(profile_home(self.profile, self.profile_root))
        else:
            environment.pop("CODEX_HOME", None)
        return environment


class OpenAIAPIProvider:
    """Reserved provider shape; API-key execution stays disabled by default."""

    def command(
        self,
        task_path: Path,
        worktree: Path,
        model: str,
        reasoning_effort: str,
        result_schema: Path,
    ) -> list[str]:
        raise RuntimeError("OpenAI API frontier provider is disabled")

    def environment(self) -> dict[str, str]:
        raise RuntimeError("OpenAI API frontier provider is disabled")


def validate_profile_name(profile: str) -> str:
    if not PROFILE_NAME.fullmatch(profile):
        raise ValueError("profile name must be lowercase letters, digits, or hyphens")
    return profile


def profile_home(profile: str, root: str | Path = DEFAULT_PROFILE_ROOT) -> Path:
    return Path(root) / validate_profile_name(profile)


def profile_status(profile: str, root: str | Path = DEFAULT_PROFILE_ROOT) -> dict[str, str]:
    home = profile_home(profile, root)
    auth = home / "auth.json"
    return {
        "profile": profile,
        "authenticated": "yes" if auth.is_file() else "no",
        "authentication_mode": "oauth",
        "state": "available" if home.is_dir() else "not_configured",
    }


def load_frontier_config(path: str | Path = "config/codex-frontier.yaml") -> FrontierConfig:
    with Path(path).open() as stream:
        loaded = yaml.safe_load(stream) or {}
    return FrontierConfig.model_validate(loaded)


@contextmanager
def profile_lock(profile: str, run_dir: str | Path) -> Iterator[None]:
    validate_profile_name(profile)
    lock_path = Path(run_dir) / "frontier-locks" / f"{profile}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("frontier profile already active") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def frontier_eligible(state: SessionState, metadata: dict[str, Any]) -> tuple[bool, str]:
    if int(metadata.get("frontier_invocations", 0)) >= 1:
        return False, "frontier_invocation_limit"
    if metadata.get("frontier_requested"):
        return True, "explicit_request"
    if state.phase.value == "replanning" and metadata.get("validated_replan_failed"):
        return True, "validated_replan_failed"
    if state.review_status == "rejected" and metadata.get("correction_attempted"):
        return True, "reviewer_rejected_after_correction"
    if state.judge_status == "blocked":
        return True, "heavy_judge_blocked"
    if int(metadata.get("modules_changed", 0)) > int(metadata.get("frontier_module_limit", 8)):
        return True, "module_threshold"
    return False, "local_moa_sufficient"


def select_frontier_profile(
    *,
    explicit_profile: str | None,
    primary_profile: str | None,
    primary_auth_failed: bool = False,
    allow_failover: bool = False,
    failover_profile: str | None = None,
) -> str | None:
    if explicit_profile:
        return validate_profile_name(explicit_profile)
    if primary_profile and not primary_auth_failed:
        return validate_profile_name(primary_profile)
    if primary_auth_failed and allow_failover and failover_profile:
        return validate_profile_name(failover_profile)
    return None


def build_frontier_task(state: SessionState, metadata: dict[str, Any]) -> FrontierTask:
    return FrontierTask(
        task_id=str(metadata["task_id"]),
        objective=state.objective,
        repository_identity=state.repository,
        base_commit=str(metadata["base_commit"]),
        allowed_paths=[str(path) for path in metadata.get("allowed_paths", state.approved_scope)],
        acceptance_criteria=state.acceptance_criteria,
        verified_facts=state.verified_facts[-8:],
        failure_summary=str(metadata.get("failure_summary", ""))[:4000],
        planner_conclusion=json.dumps(state.plan, ensure_ascii=False)[:4000],
        reviewer_conclusion=state.review_status,
        judge_verdict={"status": state.judge_status}
        if state.judge_status != "not_requested"
        else None,
        relevant_diff=str(metadata.get("relevant_diff", ""))[:8000],
        validation_commands=[str(command) for command in metadata.get("validation_commands", [])],
    )


def validate_scope(changes: list[str], allowed_paths: list[str]) -> None:
    for path in changes:
        if path.startswith(FORBIDDEN_PATHS) or not any(
            path == allowed or path.startswith(f"{allowed.rstrip('/')}/")
            for allowed in allowed_paths
        ):
            raise ValueError(f"FRONTIER_SCOPE_VIOLATION: {path}")


def validate_isolated_worktree(task: FrontierTask, worktree: Path) -> None:
    workspace = task.repository_identity.get("workspace_path")
    if not workspace:
        raise ValueError("frontier task lacks production workspace identity")
    production = Path(workspace).resolve()
    target = worktree.resolve()
    if target == production:
        raise ValueError("frontier worktree must not be production working tree")
    listing = subprocess.run(
        ["git", "-C", str(production), "worktree", "list", "--porcelain"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    if f"worktree {target}\n" not in listing:
        raise ValueError("frontier worktree is not registered by production repository")
    branch = subprocess.run(
        ["git", "-C", str(target), "branch", "--show-current"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    if not (branch.startswith("frontier/") or branch.startswith("auto/frontier/")):
        raise ValueError("frontier worktree branch is not isolated")


def evaluate_frontier_candidate(
    result: FrontierResult,
    *,
    changed_paths: list[str],
    task: FrontierTask,
    focused_tests_passed: bool,
    benchmark_passed: bool,
    secret_scan_passed: bool,
    local_review_passed: bool,
    prior_stable_evaluation: bool = False,
) -> dict[str, Any]:
    validate_scope(changed_paths, task.allowed_paths)
    if (
        any(path.startswith(IMMUTABLE_EVALUATOR_PATHS) for path in changed_paths)
        and not prior_stable_evaluation
    ):
        raise ValueError("immutable baseline changes require prior stable evaluation")
    accepted = (
        result.status == "completed"
        and focused_tests_passed
        and benchmark_passed
        and secret_scan_passed
        and local_review_passed
    )
    return {
        "accepted_for_human_review": accepted,
        "automatic_merge": False,
        "automatic_deploy": False,
        "human_approval_required": True,
        "reason": "all deterministic gates passed" if accepted else "candidate gate failed",
    }


def codex_command(
    profile: str,
    task_path: Path,
    worktree: Path,
    model: str,
    reasoning_effort: str,
    result_schema: Path,
) -> list[str]:
    if not model.strip():
        raise ValueError("verified Codex model identifier is required")
    return [
        "codex",
        "exec",
        "--json",
        "--sandbox",
        "workspace-write",
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(result_schema),
        "--output-last-message",
        str(task_path.with_suffix(".result.json")),
        "--model",
        model,
        "--cd",
        str(worktree),
        "Read frontier-task-v1 JSON from "
        + str(task_path)
        + ". Follow allowed_paths and forbidden_actions. Return frontier-result-v1 JSON only.",
    ]


def classify_frontier_failure(output: str) -> str:
    normalized = output.lower()
    if any(
        marker in normalized
        for marker in (
            "context window",
            "context length",
            "input is too long",
            "maximum context",
            "too many tokens",
        )
    ):
        return "FRONTIER_CONTEXT_LIMIT"
    if any(
        marker in normalized
        for marker in (
            "unauthorized",
            "authentication",
            "login required",
            "not logged in",
            "token_invalidated",
            "refresh_token",
        )
    ):
        return "FRONTIER_AUTH_ERROR"
    if any(marker in normalized for marker in ("rate limit", "too many requests", "429")):
        return "FRONTIER_RATE_LIMIT"
    if "usage limit" in normalized:
        return "FRONTIER_USAGE_LIMIT"
    if any(marker in normalized for marker in ("unavailable", "connection refused", "503")):
        return "FRONTIER_PROVIDER_UNAVAILABLE"
    return "FRONTIER_PROTOCOL_ERROR"


def record_frontier_run(
    run_dir: Path,
    task: FrontierTask,
    *,
    profile: str,
    model: str,
    reasoning_effort: str,
    result: FrontierResult,
    failure_class: str | None = None,
) -> Path:
    destination = run_dir / "frontier-runs" / f"{task.task_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "task_id": task.task_id,
                "profile": validate_profile_name(profile),
                "model": model,
                "reasoning_effort": reasoning_effort,
                "starting_commit": task.base_commit,
                "worktree": task.repository_identity.get("workspace_path", ""),
                "result": result.model_dump(),
                "failure_class": failure_class,
            },
            sort_keys=True,
        )
        + "\n"
    )
    return destination


def run_task(
    profile: str,
    task_path: Path,
    worktree: Path,
    model: str,
    reasoning_effort: str,
    timeout: int,
    run_dir: Path,
) -> int:
    task = FrontierTask.model_validate_json(task_path.read_text())
    validate_isolated_worktree(task, worktree)
    result_schema = Path(__file__).parents[3] / "schemas" / "frontier-result-v1.json"
    provider: FrontierProvider = CodexOAuthProvider(profile)
    with profile_lock(profile, run_dir):
        try:
            completed = subprocess.run(
                provider.command(task_path, worktree, model, reasoning_effort, result_schema),
                cwd=worktree,
                env=provider.environment(),
                timeout=timeout,
                check=False,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("FRONTIER_TIMEOUT") from error
    print(redact(completed.stdout), end="")
    print(redact(completed.stderr), end="", file=sys.stderr)
    if completed.returncode:
        failure = classify_frontier_failure(completed.stdout + completed.stderr)
        result = FrontierResult(
            status="blocked" if failure == "FRONTIER_USAGE_LIMIT" else "failed",
            summary=failure,
            root_cause=failure,
            recommended_next_action="return to local MoA or select an authorized profile",
        )
        task_path.with_suffix(".result.json").write_text(result.model_dump_json(indent=2))
        record_frontier_run(
            run_dir,
            task,
            profile=profile,
            model=model,
            reasoning_effort=reasoning_effort,
            result=result,
            failure_class=failure,
        )
        raise RuntimeError(failure)
    result_path = task_path.with_suffix(".result.json")
    if not result_path.is_file():
        raise RuntimeError("FRONTIER_PROTOCOL_ERROR")
    result = FrontierResult.model_validate_json(result_path.read_text())
    record_frontier_run(
        run_dir,
        task,
        profile=profile,
        model=model,
        reasoning_effort=reasoning_effort,
        result=result,
        failure_class="FRONTIER_VALIDATION_FAILURE" if result.status != "completed" else None,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    status = subcommands.add_parser("status")
    status.add_argument("profile")
    status.add_argument("--root", default=str(DEFAULT_PROFILE_ROOT))
    run = subcommands.add_parser("run")
    run.add_argument("--profile", required=True)
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--worktree", type=Path, required=True)
    run.add_argument("--model")
    run.add_argument("--reasoning-effort")
    run.add_argument("--config", type=Path, default=Path("config/codex-frontier.yaml"))
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--run-dir", type=Path, default=Path("data/run"))
    arguments = parser.parse_args()
    if arguments.command == "status":
        print(json.dumps(redact(profile_status(arguments.profile, arguments.root)), sort_keys=True))
        return
    config = load_frontier_config(arguments.config)
    raise SystemExit(
        run_task(
            arguments.profile,
            arguments.task,
            arguments.worktree,
            arguments.model or config.model,
            arguments.reasoning_effort or config.reasoning_effort,
            arguments.timeout,
            arguments.run_dir,
        )
    )


if __name__ == "__main__":
    main()
