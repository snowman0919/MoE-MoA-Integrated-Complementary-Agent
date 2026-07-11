from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ModelConfig
from .security import redact
from .state import SessionState, StateStore

TRACE_FIELDS = frozenset(
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


def validate_trace(trace: dict[str, Any]) -> None:
    missing = TRACE_FIELDS - trace.keys()
    if missing:
        raise ValueError(f"trace fields missing: {', '.join(sorted(missing))}")
    if trace["schema_version"] != "agent-trace-v1":
        raise ValueError("unsupported trace schema version")


def trace_record(
    state: SessionState,
    *,
    events: list[dict[str, Any]] | None = None,
    task_id: str = "",
    metrics: dict[str, Any] | None = None,
    models: dict[str, ModelConfig] | None = None,
) -> dict[str, Any]:
    """Build bounded decision-point trace, never a source or transcript archive."""
    latest = state.tool_results[-1] if state.tool_results else {}
    return {
        "schema_version": "agent-trace-v1",
        "session_id": state.session_id,
        "task_id": task_id,
        "workspace_identity": state.repository,
        "objective": state.objective,
        "selected_route": {"route": state.route, "reasons": state.route_reasons},
        "model_revisions": {
            role: {"repository": model.repository, "revision": model.revision}
            for role, model in (models or {}).items()
        },
        "context_configuration": {
            role: {"context_length": model.context_length, "max_num_seqs": model.max_num_seqs}
            for role, model in (models or {}).items()
        },
        "events": events or [],
        "final_status": state.phase,
        "completion_evidence": state.completion_evidence,
        "metrics": metrics or {},
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
    output = {
        field: redact(trace.get(field, "agent-trace-v1" if field == "schema_version" else None))
        for field in TRACE_FIELDS
    }
    validate_trace(output)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as stream:
        stream.write(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")


class TraceRecorder:
    def __init__(
        self, directory: str | Path, store: StateStore, models: dict[str, ModelConfig] | None = None
    ):
        self.directory = Path(directory)
        self.store = store
        self.models = models or {}

    def record(
        self, state: SessionState, *, task_id: str = "", metrics: dict[str, Any] | None = None
    ) -> Path:
        path = self.directory / f"{state.session_id}.jsonl"
        export_trace(
            path,
            trace_record(
                state,
                events=self.store.events(state.session_id),
                task_id=task_id,
                metrics=metrics,
                models=self.models,
            ),
        )
        return path
