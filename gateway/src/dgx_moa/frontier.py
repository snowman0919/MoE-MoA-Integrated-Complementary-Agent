"""Bounded Codex frontier runs; no credential handling or automatic failover."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .security import redact
from .state import SessionState

PROFILE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
DEFAULT_PROFILE_ROOT = Path("/home/kotori9/.local/share/dgx-moa/codex-profiles")
FORBIDDEN_PATHS = (".env", ".env.local", "systemd/", "config/tailscale")
FRONTIER_FAILURES = frozenset(
    {
        "FRONTIER_AUTH_ERROR",
        "FRONTIER_USAGE_LIMIT",
        "FRONTIER_TIMEOUT",
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
    protocol: str = "codex-exec-jsonl"
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "high"
    max_invocations_per_task: int = 1
    max_recursive_cycles: int = 3


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


def evaluate_frontier_candidate(
    result: FrontierResult,
    *,
    changed_paths: list[str],
    task: FrontierTask,
    focused_tests_passed: bool,
    benchmark_passed: bool,
    secret_scan_passed: bool,
    local_review_passed: bool,
) -> dict[str, Any]:
    validate_scope(changed_paths, task.allowed_paths)
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
        "--ask-for-approval",
        "never",
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


def run_task(
    profile: str,
    task_path: Path,
    worktree: Path,
    model: str,
    reasoning_effort: str,
    timeout: int,
    run_dir: Path,
) -> int:
    FrontierTask.model_validate_json(task_path.read_text())
    if worktree.resolve() == Path.cwd().resolve():
        raise ValueError("frontier worktree must not be production working tree")
    result_schema = Path(__file__).parents[3] / "schemas" / "frontier-result-v1.json"
    environment = os.environ | {"CODEX_HOME": str(profile_home(profile))}
    with profile_lock(profile, run_dir):
        try:
            completed = subprocess.run(
                codex_command(profile, task_path, worktree, model, reasoning_effort, result_schema),
                cwd=worktree,
                env=environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("FRONTIER_TIMEOUT") from error
    return completed.returncode


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
