from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def trace_record(
    state: SessionState,
    *,
    events: list[dict[str, Any]] | None = None,
    task_id: str = "",
    metrics: dict[str, Any] | None = None,
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
        "model_revisions": {},
        "context_configuration": {},
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
    output = {field: redact(trace.get(field)) for field in TRACE_FIELDS}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as stream:
        stream.write(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")


class TraceRecorder:
    def __init__(self, directory: str | Path, store: StateStore):
        self.directory = Path(directory)
        self.store = store

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
            ),
        )
        return path
