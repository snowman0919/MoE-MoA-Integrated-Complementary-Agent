from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .security import redact

TRACE_FIELDS = {
    "session_metadata",
    "objective",
    "verified_state",
    "planner_output",
    "tool_schema",
    "assistant_tool_call",
    "tool_observation",
    "failure_classification",
    "review_outcome",
    "completion_evidence",
    "human_correction",
}


def export_trace(path: str | Path, trace: dict[str, Any]) -> None:
    output = {field: redact(trace.get(field)) for field in TRACE_FIELDS}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as stream:
        stream.write(json.dumps(output, ensure_ascii=False) + "\n")
