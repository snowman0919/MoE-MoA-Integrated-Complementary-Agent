#!/usr/bin/env python3
"""Analyze the frozen sustained-Goal context-retention gate."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

PROTOCOL = "frontier-long-goal-v48"
PHASES = (
    "intake_and_plan",
    "core_implementation",
    "integration_and_tests",
    "independent_review_and_repair",
    "full_validation_and_final",
)
CHECKPOINTS = len(PHASES)
AVATARFORGE_PROTOCOL = "avatarforge-long-goal-v3"
AVATARFORGE_PHASES = (
    "avatarforge_phase_0_contract",
    "avatarforge_phase_1_plugin",
    "avatarforge_phase_2_environment",
    "avatarforge_phase_3_state",
)
PROTOCOL_PHASES = {
    PROTOCOL: PHASES,
    AVATARFORGE_PROTOCOL: AVATARFORGE_PHASES,
}
INTERVAL_SECONDS = 0
MAX_VARIABLE_COST_USD = 10.0
SCHEDULE_TOLERANCE_SECONDS = 60
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "hidden_reasoning",
    "prompt",
    "raw_output",
    "raw_prompt",
    "repository_name",
    "request_id",
}
STABLE_HASHES = (
    "session_sha256",
    "objective_sha256",
    "acceptance_sha256",
    "plan_sha256",
    "repository_sha256",
    "branch_sha256",
    "provider_config_sha256",
)


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {line_number}: invalid JSON") from error
        if not isinstance(event, dict):
            raise ValueError(f"line {line_number}: object required")
        reject_private_fields(event, f"line {line_number}")
        events.append(event)
    if not events:
        raise ValueError("empty evidence")
    return events


def reject_private_fields(value: Any, location: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"{location}: private field forbidden")
            reject_private_fields(item, location)
    elif isinstance(value, list):
        for item in value:
            reject_private_fields(item, location)


def finite_number(
    value: Any,
    field: str,
    failures: list[str],
    *,
    minimum: float = 0,
) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        failures.append(f"invalid_{field}")
        return None
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        failures.append(f"invalid_{field}")
        return None
    return number


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def valid_commit(value: Any) -> bool:
    return isinstance(value, str) and COMMIT.fullmatch(value) is not None


def validate_header(
    header: dict[str, Any], protocol: str, phases: tuple[str, ...], failures: list[str]
) -> None:
    if header.get("type") != "header" or header.get("protocol") != protocol:
        failures.append("invalid_header")
    if header.get("expected_checkpoints") != len(phases):
        failures.append("checkpoint_count_not_preregistered")
    if header.get("checkpoint_interval_seconds") != INTERVAL_SECONDS:
        failures.append("checkpoint_interval_not_preregistered")
    if header.get("client_path") not in {"codex", "opencode", "hermes"}:
        failures.append("invalid_client_path")
    if header.get("gateway_path") != "authenticated_loopback":
        failures.append("invalid_gateway_path")
    variant = header.get("variant")
    if not isinstance(variant, str) or not re.fullmatch(r"V[0-9]+", variant):
        failures.append("variant_not_opaque")
    finite_number(header.get("started_at_epoch"), "started_at_epoch", failures)
    if not valid_commit(header.get("baseline_commit")):
        failures.append("invalid_baseline_commit")
    for field in STABLE_HASHES:
        if not valid_hash(header.get(field)):
            failures.append(f"invalid_{field}")


def validate_checkpoint(
    checkpoint: dict[str, Any],
    header: dict[str, Any],
    expected_index: int,
    phases: tuple[str, ...],
    failures: list[str],
) -> None:
    if checkpoint.get("index") != expected_index:
        failures.append("checkpoint_index_gap")
    if checkpoint.get("phase_index") != expected_index:
        failures.append("phase_drift")
    if checkpoint.get("phase") != phases[expected_index]:
        failures.append("phase_contract_drift")
    for field in STABLE_HASHES:
        if checkpoint.get(field) != header.get(field):
            failures.append(f"{field}_drift")
    for field in ("next_action_sha256", "context_summary_sha256", "evidence_sha256"):
        if not valid_hash(checkpoint.get(field)):
            failures.append(f"invalid_{field}")
    if not valid_commit(checkpoint.get("commit")):
        failures.append("invalid_commit")
    if checkpoint.get("dirty_state") != "clean":
        failures.append("dirty_checkpoint")
    if checkpoint.get("provider_pinned") is not True:
        failures.append("provider_not_pinned")
    provenance = checkpoint.get("provider_provenance")
    if not isinstance(provenance, list) or not provenance:
        failures.append("missing_provider_provenance")
    else:
        for item in provenance:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item[field]
                for field in ("role", "provider", "model")
            ):
                failures.append("invalid_provider_provenance")
                break
    for field in (
        "scheduled_at_epoch",
        "completed_at_epoch",
        "latency_seconds",
        "context_tokens",
        "cached_tokens",
        "tool_calls",
        "retries",
        "provider_errors",
        "unjustified_repeated_reads",
        "peak_memory_bytes",
        "swap_delta_bytes",
        "variable_cost_usd",
    ):
        minimum = 0.000001 if field in {"latency_seconds", "context_tokens"} else 0
        finite_number(checkpoint.get(field), field, failures, minimum=minimum)
    scheduled = checkpoint.get("scheduled_at_epoch")
    completed = checkpoint.get("completed_at_epoch")
    if (
        isinstance(scheduled, int | float)
        and isinstance(completed, int | float)
        and completed < scheduled
    ):
        failures.append("checkpoint_completed_before_schedule")
    if checkpoint.get("provider_errors") != 0:
        failures.append("provider_error")
    if checkpoint.get("unjustified_repeated_reads") != 0:
        failures.append("unjustified_repeated_read")
    if checkpoint.get("premature_completion") is not False:
        failures.append("premature_completion")
    if checkpoint.get("terminal") is not True:
        failures.append("missing_checkpoint_terminal")
    if not isinstance(checkpoint.get("tool_calls"), int) or checkpoint["tool_calls"] < 1:
        failures.append("missing_checkpoint_tool_use")
    context_tokens = checkpoint.get("context_tokens")
    cached_tokens = checkpoint.get("cached_tokens")
    if (
        isinstance(context_tokens, int | float)
        and not isinstance(context_tokens, bool)
        and isinstance(cached_tokens, int | float)
        and not isinstance(cached_tokens, bool)
        and cached_tokens > context_tokens
    ):
        failures.append("cached_tokens_exceed_context")


def validate_final(
    final: dict[str, Any],
    header: dict[str, Any],
    failures: list[str],
) -> None:
    for field in STABLE_HASHES:
        if final.get(field) != header.get(field):
            failures.append(f"final_{field}_drift")
    if final.get("implementation_evidence") is not True:
        failures.append("missing_implementation_evidence")
    if not valid_commit(final.get("implementation_commit")):
        failures.append("invalid_implementation_commit")
    if final.get("implementation_commit") == header.get("baseline_commit"):
        failures.append("implementation_commit_unchanged")
    for field in ("implementation_sha256", "review_sha256", "validation_sha256"):
        if not valid_hash(final.get(field)):
            failures.append(f"invalid_{field}")
    if final.get("review_status") != "approved":
        failures.append("review_not_approved")
    if type(final.get("validation_exit")) is not int or final["validation_exit"] != 0:
        failures.append("validation_failed")
    finite_number(final.get("completed_at_epoch"), "final_completed_at_epoch", failures)
    if final.get("terminal") is not True:
        failures.append("missing_terminal")
    if final.get("unresolved_critical_findings") != 0:
        failures.append("unresolved_critical_findings")
    if final.get("task_outcome") != "completed":
        failures.append("task_not_completed")


def analyze(path: Path) -> dict[str, Any]:
    events = load_events(path)
    header = events[0]
    raw_protocol = header.get("protocol")
    protocol = raw_protocol if isinstance(raw_protocol, str) else ""
    phases = PROTOCOL_PHASES.get(protocol, ())
    checkpoints_expected = len(phases)
    checkpoints = [event for event in events if event.get("type") == "checkpoint"]
    finals = [event for event in events if event.get("type") == "final"]
    failures: list[str] = []
    if not phases:
        failures.append("invalid_protocol")
    validate_header(header, protocol, phases, failures)
    expected_types = ["header", *(["checkpoint"] * checkpoints_expected), "final"]
    if [event.get("type") for event in events] != expected_types:
        failures.append("invalid_event_order")
    if len(checkpoints) != checkpoints_expected:
        failures.append("incomplete_checkpoints")
    for index, checkpoint in enumerate(checkpoints[:checkpoints_expected]):
        validate_checkpoint(checkpoint, header, index, phases, failures)
    if len(finals) != 1:
        failures.append("invalid_final_count")
    else:
        validate_final(finals[0], header, failures)

    scheduled = [
        float(checkpoint["scheduled_at_epoch"])
        for checkpoint in checkpoints
        if isinstance(checkpoint.get("scheduled_at_epoch"), int | float)
    ]
    if checkpoints_expected and len(scheduled) == checkpoints_expected:
        started = header.get("started_at_epoch")
        if (
            isinstance(started, int | float)
            and not isinstance(started, bool)
            and abs(scheduled[0] - float(started)) > SCHEDULE_TOLERANCE_SECONDS
        ):
            failures.append("initial_checkpoint_schedule_drift")
        for previous, current in zip(scheduled, scheduled[1:], strict=False):
            if abs((current - previous) - INTERVAL_SECONDS) > SCHEDULE_TOLERANCE_SECONDS:
                failures.append("checkpoint_schedule_drift")
    else:
        failures.append("missing_checkpoint_schedule")
    reconnects = sum(checkpoint.get("intentional_reconnect") is True for checkpoint in checkpoints)
    if reconnects < 1:
        failures.append("missing_intentional_reconnect")
    if not any(
        isinstance(checkpoint.get("cached_tokens"), int | float) and checkpoint["cached_tokens"] > 0
        for checkpoint in checkpoints
    ):
        failures.append("cache_reuse_not_observed")
    observed_roles = {
        item.get("role")
        for checkpoint in checkpoints
        for item in checkpoint.get("provider_provenance") or []
        if isinstance(item, dict)
    }
    for role in {"reasoner", "executor", "planner", "reviewer"} - observed_roles:
        failures.append(f"missing_{role}_role")
    if protocol == AVATARFORGE_PROTOCOL:
        previous_commit = header.get("baseline_commit")
        for checkpoint in checkpoints:
            if checkpoint.get("commit") == previous_commit:
                failures.append("avatarforge_phase_commit_unchanged")
            previous_commit = checkpoint.get("commit")

    request_cost = sum(
        float(checkpoint.get("variable_cost_usd", 0))
        for checkpoint in checkpoints
        if isinstance(checkpoint.get("variable_cost_usd"), int | float)
        and not isinstance(checkpoint.get("variable_cost_usd"), bool)
    )
    if request_cost > MAX_VARIABLE_COST_USD:
        failures.append("variable_cost_budget_exceeded")
    if len(finals) == 1 and len(checkpoints) == checkpoints_expected:
        final = finals[0]
        if final.get("implementation_commit") != checkpoints[-1].get("commit"):
            failures.append("final_commit_mismatch")
    failures = sorted(set(failures))
    return {
        "protocol": protocol,
        "passed": not failures,
        "failures": failures,
        "checkpoints": len(checkpoints),
        "scheduled_duration_seconds": (
            scheduled[-1] - scheduled[0]
            if len(scheduled) == checkpoints_expected
            else None
        ),
        "intentional_reconnects": reconnects,
        "cache_reuse_observed": "cache_reuse_not_observed" not in failures,
        "provider_pinning_preserved": "provider_not_pinned" not in failures,
        "variable_cost_usd": request_cost,
        "variable_cost_budget_usd": MAX_VARIABLE_COST_USD,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = analyze(args.evidence)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.write_text(rendered)
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
