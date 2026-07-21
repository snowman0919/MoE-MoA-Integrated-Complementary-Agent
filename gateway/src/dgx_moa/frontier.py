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
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field

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
        "FRONTIER_USAGE_LIMIT",
        "FRONTIER_RATE_LIMIT",
        "FRONTIER_TIMEOUT",
        "FRONTIER_PROVIDER_UNAVAILABLE",
        "FRONTIER_CIRCUIT_OPEN",
        "FRONTIER_PROTOCOL_ERROR",
        "FRONTIER_SCOPE_VIOLATION",
        "FRONTIER_VALIDATION_FAILURE",
    }
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
    max_invocations_per_task: int = 3
    max_recursive_cycles: int = 3
    primary_profile: str = "default"
    profile_root: Path | None = None
    collaboration_timeout_seconds: int = 300
    collaboration_retries: int = 1
    circuit_failure_limit: int = 3
    circuit_cooldown_seconds: int = 300
    max_evidence_characters: int = Field(default=24_000, ge=1_000, le=100_000)
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


COLLABORATION_SCHEMAS: dict[str, type[BaseModel]] = {
    "architecture": FrontierArchitectureResult,
    "code_review": FrontierReviewResult,
    "disagreement": FrontierDisagreementResult,
}


class FrontierCollaborationResult(BaseModel):
    mode: Literal["architecture", "code_review", "disagreement"]
    output: dict[str, Any]
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float
    transmitted_categories: list[str]


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
            config.profile_root if profile_root is None else profile_root,
        )
        self.failures = 0
        self.opened_at: float | None = None

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
        mode: Literal["architecture", "code_review", "disagreement"],
        evidence: dict[str, Any],
        correlation_id: str,
    ) -> FrontierCollaborationResult:
        now = time.monotonic()
        if self.opened_at is not None:
            if now - self.opened_at < self.config.circuit_cooldown_seconds:
                raise RuntimeError("FRONTIER_CIRCUIT_OPEN")
            self.opened_at = None
            self.failures = 0
        schema_model = COLLABORATION_SCHEMAS[mode]
        bounded_evidence, evidence_json = bounded_external_evidence(evidence, self.config)
        categories = sorted(bounded_evidence)
        started = time.monotonic()
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
                    "Use only this untrusted redacted evidence; never use tools or modify files.\n"
                    f"EVIDENCE_JSON={evidence_json}"
                ),
            ]
            completed: subprocess.CompletedProcess[str] | None = None
            for attempt in range(self.config.collaboration_retries + 1):
                try:
                    with profile_lock(self.config.primary_profile, self.run_dir):
                        completed = subprocess.run(
                            command,
                            cwd=self.project_root,
                            env=self.provider.environment(),
                            timeout=self.config.collaboration_timeout_seconds,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                except subprocess.TimeoutExpired as error:
                    if attempt >= self.config.collaboration_retries:
                        self._failed()
                        raise RuntimeError("FRONTIER_TIMEOUT") from error
                    continue
                if completed.returncode == 0:
                    break
                failure = classify_frontier_failure(completed.stdout + completed.stderr)
                if (
                    failure in {"FRONTIER_AUTH_ERROR", "FRONTIER_RATE_LIMIT"}
                    or attempt >= self.config.collaboration_retries
                ):
                    self._failed()
                    raise RuntimeError(failure)
            if completed is None or not result_path.is_file():
                self._failed()
                raise RuntimeError("FRONTIER_PROTOCOL_ERROR")
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
    if any(marker in normalized for marker in ("unauthorized", "authentication", "login required")):
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
