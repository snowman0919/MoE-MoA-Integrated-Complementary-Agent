from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ModelConfig
from .security import redact
from .state import SessionState, StateStore, validate_failure_record

LEGACY_TRACE_FIELDS = frozenset(
    {
        "schema_version",
        "session_id",
        "task_id",
        "workspace_identity",
        "objective",
        "selected_route",
        "model_revisions",
        "context_configuration",
        "events",
        "final_status",
        "completion_evidence",
        "metrics",
        "verified_state",
        "planner_output",
        "tool_schema",
        "assistant_tool_call",
        "tool_observation",
        "failure_classification",
        "review_outcome",
        "human_correction",
    }
)
MOA_TRACE_FIELDS = frozenset(
    {
        "reasoner_contributions",
        "orchestration_decisions",
        "agent_invocations",
        "agent_artifacts",
        "recommendation_resolutions",
        "evidence_graph",
        "derived_confidence",
        "engineering_loop",
    }
)
TRACE_FIELDS = (
    LEGACY_TRACE_FIELDS
    | MOA_TRACE_FIELDS
    | frozenset(
        {
            "runtime_channel",
            "trace_origin",
            "repository_identity",
            "starting_branch",
            "starting_commit",
            "ending_branch",
            "ending_commit",
            "dirty_state_start",
            "dirty_state_end",
            "controller_commit",
            "gateway_version",
            "vllm_version",
            "adapter_identifiers",
            "started_at",
            "ended_at",
            "training_eligibility",
            "observability_status",
            "observability_degraded",
            "agent_decisions",
            "tool_executions",
            "evaluations",
            "failures",
        }
    )
)
V2_TRACE_FIELDS = TRACE_FIELDS - MOA_TRACE_FIELDS

LIST_FIELDS = {
    "events",
    "agent_decisions",
    "reasoner_contributions",
    "orchestration_decisions",
    "agent_invocations",
    "agent_artifacts",
    "recommendation_resolutions",
    "tool_executions",
    "evaluations",
    "failures",
}
DICT_FIELDS = {
    "workspace_identity",
    "repository_identity",
    "selected_route",
    "model_revisions",
    "context_configuration",
    "adapter_identifiers",
    "completion_evidence",
    "metrics",
    "tool_schema",
    "assistant_tool_call",
    "tool_observation",
    "failure_classification",
    "review_outcome",
    "evidence_graph",
    "engineering_loop",
}


def training_default(runtime_channel: str, trace_origin: str) -> str:
    if trace_origin in {"validation", "diagnostic"}:
        return "excluded"
    if trace_origin == "benchmark":
        return "eligible"
    if trace_origin in {"production", "candidate_evaluation"}:
        return "requires_review"
    return "local_only" if runtime_channel != "main" else "requires_review"


def validate_provenance(runtime_channel: str, trace_origin: str) -> None:
    if runtime_channel not in {"main", "dev", "candidate"}:
        raise ValueError("invalid runtime_channel")
    if trace_origin not in {
        "production",
        "benchmark",
        "validation",
        "diagnostic",
        "candidate_evaluation",
    }:
        raise ValueError("invalid trace_origin")
    if trace_origin == "production" and runtime_channel != "main":
        raise ValueError("production trace requires main runtime")
    if trace_origin == "candidate_evaluation" and runtime_channel != "candidate":
        raise ValueError("candidate_evaluation trace requires candidate runtime")


def validate_trace(trace: dict[str, Any]) -> None:
    version = trace.get("schema_version")
    required = (
        LEGACY_TRACE_FIELDS
        if version == "agent-trace-v1"
        else V2_TRACE_FIELDS
        if version == "agent-trace-v2"
        else TRACE_FIELDS
    )
    missing = required - trace.keys()
    if missing:
        raise ValueError(f"trace fields missing: {', '.join(sorted(missing))}")
    if version not in {"agent-trace-v1", "agent-trace-v2", "agent-trace-v3"}:
        raise ValueError("unsupported trace schema version")
    if version in {"agent-trace-v2", "agent-trace-v3"}:
        validate_provenance(str(trace["runtime_channel"]), str(trace["trace_origin"]))
        for decision in trace["agent_decisions"]:
            if decision.get("role") not in {
                "planner",
                "executor",
                "reviewer",
                "reasoner",
                "judge",
                "frontier",
            }:
                raise ValueError("invalid decision role")
        for execution in trace["tool_executions"]:
            effect = execution.get("filesystem_effect", {})
            if not set(effect) & {
                "changed_paths",
                "created_paths",
                "deleted_paths",
                "unknown_effect",
            }:
                raise ValueError("invalid filesystem effect")
        for failure in trace["failures"]:
            validate_failure_record(failure)


def final_status(state: SessionState) -> str:
    if state.final_status:
        return state.final_status
    if state.phase.value == "completed":
        return "completed"
    if state.phase.value == "blocked":
        return "blocked"
    return "degraded"


def trace_record(
    state: SessionState,
    *,
    events: list[dict[str, Any]] | None = None,
    task_id: str = "",
    metrics: dict[str, Any] | None = None,
    models: dict[str, ModelConfig] | None = None,
) -> dict[str, Any]:
    """Build bounded trajectory evidence; never source or hidden-reasoning archives."""
    validate_provenance(state.runtime_channel, state.trace_origin)
    latest = state.tool_results[-1] if state.tool_results else {}
    repository = state.repository
    ending = state.ending_repository
    return {
        "schema_version": "agent-trace-v3",
        "session_id": state.session_id,
        "task_id": task_id or state.task_id,
        "runtime_channel": state.runtime_channel,
        "trace_origin": state.trace_origin,
        "workspace_identity": repository,
        "repository_identity": repository,
        "objective": state.objective,
        "starting_branch": repository.get("current_branch", "unknown"),
        "starting_commit": repository.get("current_commit", "unknown"),
        "ending_branch": ending.get("current_branch", "unknown"),
        "ending_commit": ending.get("current_commit", "unknown"),
        "dirty_state_start": repository.get("dirty_status", "unknown"),
        "dirty_state_end": ending.get("dirty_status", "unknown"),
        "controller_commit": state.controller_commit,
        "gateway_version": state.gateway_version,
        "vllm_version": state.vllm_version,
        "selected_route": {"route": state.route, "reasons": state.route_reasons},
        "model_revisions": {
            role: {"repository": model.repository, "revision": model.revision}
            for role, model in (models or {}).items()
        },
        "adapter_identifiers": {
            role: str(model.lora_adapter) if model.lora_adapter else None
            for role, model in (models or {}).items()
        },
        "context_configuration": {
            role: {"context_length": model.context_length, "max_num_seqs": model.max_num_seqs}
            for role, model in (models or {}).items()
        },
        "started_at": state.created_at,
        "ended_at": state.updated_at if final_status(state) != "degraded" else None,
        "events": events or [],
        "agent_decisions": state.decisions,
        "reasoner_contributions": state.reasoner_contributions,
        "orchestration_decisions": state.orchestration_decisions,
        "agent_invocations": state.agent_invocations,
        "agent_artifacts": state.agent_artifacts,
        "recommendation_resolutions": state.recommendation_resolutions,
        "evidence_graph": {"nodes": state.evidence_nodes, "edges": state.evidence_edges},
        "derived_confidence": state.derived_confidence,
        "tool_executions": state.tool_executions,
        "evaluations": state.evaluations,
        "failures": state.failures,
        "engineering_loop": (
            state.engineering_loop.model_dump(mode="json") if state.engineering_loop else {}
        ),
        "final_status": final_status(state),
        "completion_evidence": state.completion_evidence,
        "training_eligibility": state.training_eligibility,
        "observability_status": state.observability_status,
        "observability_degraded": state.observability_degraded,
        "metrics": (metrics or {})
        | {
            "request_timing_ms": state.timings_ms,
            "runtime_mode": state.runtime_mode,
            "request_class": state.request_class,
            "roles_required": state.roles_required,
            "truncated": state.truncated,
            "training_opt_out": state.training_opt_out,
            "user_training_opt_out": state.user_training_opt_out,
            "training_subject_hash": state.training_subject_hash,
            "repository_training_policy": state.repository_training_policy,
            "policy_version": (
                state.policy_decisions[-1].get("policy_version", "none")
                if state.policy_decisions
                else "none"
            ),
            "skill_versions": [
                f"{item.get('skill_id')}@{item.get('skill_version')}"
                for item in state.skill_selections
            ],
            "engineering_loop_id": state.engineering_loop.loop_id if state.engineering_loop else "",
        },
        "verified_state": state.verified_facts[-8:],
        "planner_output": state.plan,
        "tool_schema": {},
        "assistant_tool_call": state.last_tool_call or {},
        "tool_observation": latest,
        "failure_classification": state.failure_families,
        "review_outcome": {"status": state.review_status, "judge": state.judge_status},
        "human_correction": None,
    }


def export_trace(path: str | Path, trace: dict[str, Any]) -> None:
    version = str(trace.get("schema_version", "agent-trace-v3"))
    fields = (
        LEGACY_TRACE_FIELDS
        if version == "agent-trace-v1"
        else V2_TRACE_FIELDS
        if version == "agent-trace-v2"
        else TRACE_FIELDS
    )
    output = {}
    defaults = {
        "runtime_channel": "dev",
        "trace_origin": "validation",
        "training_eligibility": "excluded",
        "observability_status": "ok",
        "observability_degraded": False,
        "final_status": "degraded",
    }
    for field in fields:
        default: Any = defaults.get(
            field, [] if field in LIST_FIELDS else {} if field in DICT_FIELDS else None
        )
        if field == "schema_version":
            default = version
        output[field] = redact(trace.get(field, default))
    validate_trace(output)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as stream:
        stream.write(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")


class TraceRecorder:
    def __init__(
        self,
        directory: str | Path,
        store: StateStore,
        models: dict[str, ModelConfig] | None = None,
        collector: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.directory = Path(directory)
        self.store = store
        self.models = models or {}
        self.collector = collector

    def record(
        self, state: SessionState, *, task_id: str = "", metrics: dict[str, Any] | None = None
    ) -> Path:
        date = datetime.now(UTC).date().isoformat()
        path = (
            self.directory
            / state.runtime_channel
            / state.trace_origin
            / date
            / f"{state.session_id}.jsonl"
        )
        trace = trace_record(
            state,
            events=self.store.events(state.session_id),
            task_id=task_id,
            metrics=metrics,
            models=self.models,
        )
        export_trace(path, trace)
        if self.collector is not None:
            self.collector(trace)
        self.store.index_trace(state.session_id, path, state.runtime_channel, state.trace_origin)
        return path


def trace_missing(trace: dict[str, Any]) -> list[str]:
    version = trace.get("schema_version")
    if version == "agent-trace-v1":
        return ["legacy_v1"]
    if version not in {"agent-trace-v2", "agent-trace-v3"}:
        return ["unsupported_schema_version"]
    required = (
        V2_TRACE_FIELDS if version == "agent-trace-v2" else TRACE_FIELDS - {"engineering_loop"}
    )
    missing = [field for field in required if field not in trace]
    metrics = trace.get("metrics")
    if version == "agent-trace-v3" and (
        not isinstance(metrics, dict) or not metrics.get("runtime_mode")
    ):
        missing.append("metrics.runtime_mode")
    for field in (
        "session_id",
        "task_id",
        "runtime_channel",
        "trace_origin",
        "workspace_identity",
        "controller_commit",
        "gateway_version",
        "vllm_version",
        "model_revisions",
        "context_configuration",
        "selected_route",
        "agent_decisions",
        "final_status",
        "training_eligibility",
        "observability_status",
    ):
        if not trace.get(field) or trace.get(field) == "unknown":
            missing.append(field)
    route = trace.get("selected_route", {})
    if not route.get("route"):
        missing.append("selected_route.route")
    if not route.get("reasons"):
        missing.append("selected_route.reasons")
    if trace.get("final_status") == "completed" and not trace.get("completion_evidence"):
        missing.append("completion_evidence")
    if trace.get("final_status") == "completed" and not trace.get("evaluations"):
        missing.append("evaluations")
    if trace.get("final_status") in {
        "completed",
        "failed",
        "blocked",
        "cancelled",
    } and not trace.get("ended_at"):
        missing.append("ended_at")
    for index, decision in enumerate(trace.get("agent_decisions", [])):
        for field in (
            "decision_id",
            "session_id",
            "task_id",
            "role",
            "model_repository",
            "model_revision",
            "controller_commit",
            "timestamp",
            "state_before",
            "context_manifest",
            "structured_decision",
            "outcome",
        ):
            if field not in decision or decision[field] in (None, "", "unknown"):
                missing.append(f"agent_decisions[{index}].{field}")
    for index, execution in enumerate(trace.get("tool_executions", [])):
        for field in (
            "tool_execution_id",
            "tool_call_id",
            "decision_id",
            "session_id",
            "tool_name",
            "normalized_arguments",
            "argument_fingerprint",
            "started_at",
            "ended_at",
            "duration_ms",
            "exit_code",
            "stdout_bytes",
            "stderr_bytes",
            "stdout_summary",
            "stderr_summary",
            "truncated",
            "failure_class",
            "filesystem_effect",
        ):
            if field not in execution:
                missing.append(f"tool_executions[{index}].{field}")
    return sorted(set(missing))


def audit_traces(directory: str | Path) -> dict[str, Any]:
    latest: dict[str, tuple[int, int, dict[str, Any]]] = {}
    read_sequence = 0
    for path in sorted(Path(directory).rglob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line:
                read_sequence += 1
                trace = json.loads(line)
                session_id = str(trace.get("session_id") or f"legacy:{read_sequence}")
                candidate = (
                    {"agent-trace-v1": 1, "agent-trace-v2": 2, "agent-trace-v3": 3}.get(
                        str(trace.get("schema_version")), 0
                    ),
                    read_sequence,
                    trace,
                )
                if session_id not in latest or candidate[:2] > latest[session_id][:2]:
                    latest[session_id] = candidate
    traces = [candidate[2] for candidate in latest.values()]
    missing_by_path: dict[str, int] = {}
    missing_events: dict[str, int] = {}
    incomplete = 0
    legacy = 0
    for trace in traces:
        missing = trace_missing(trace)
        legacy += int(missing == ["legacy_v1"])
        trace_incomplete = bool(missing)
        for missing_path in missing:
            missing_by_path[missing_path] = missing_by_path.get(missing_path, 0) + 1
        if trace.get("schema_version") in {"agent-trace-v2", "agent-trace-v3"}:
            event_types = {event.get("event_type") for event in trace.get("events", [])}
            for event_type in ("session_started", "route_selected", "session_ended"):
                if event_type not in event_types:
                    trace_incomplete = True
                    missing_events[event_type] = missing_events.get(event_type, 0) + 1
            if (
                trace.get("final_status") == "completed"
                and "assistant_stream_finished" not in event_types
            ):
                trace_incomplete = True
                missing_events["assistant_stream_finished"] = (
                    missing_events.get("assistant_stream_finished", 0) + 1
                )
        incomplete += int(trace_incomplete)
    total = len(traces)
    complete = total - incomplete
    return {
        "schema_version": "trace-completeness-v2",
        "total_sessions": total,
        "complete_sessions": complete,
        "incomplete_sessions": incomplete,
        "legacy_sessions": legacy,
        "mandatory_field_completeness_percent": round(100 * complete / total, 2) if total else 0.0,
        "missing_fields": dict(sorted(missing_by_path.items())),
        "missing_event_counts_by_type": dict(sorted(missing_events.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    report = audit_traces(args.path)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["incomplete_sessions"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
