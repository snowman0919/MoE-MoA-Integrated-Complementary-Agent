from __future__ import annotations

import json

from dgx_moa.compression import compress_messages, compress_text
from dgx_moa.config import Limits
from dgx_moa.security import redact
from dgx_moa.trace import TRACE_FIELDS, export_trace


def test_redaction_and_compression(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert redact({"api_key": "secret", "text": "token=abc123"}) == {
        "api_key": "[REDACTED]",
        "text": "token=[REDACTED]",
    }
    limits = Limits(max_tool_output_characters=80, max_error_lines=2)
    text = "\n".join(["noise"] * 30 + ["ERROR decisive"] + ["tail"] * 30)
    compressed = compress_text(text, limits)
    assert "ERROR decisive" in compressed and len(compressed) <= 80
    payload = '{"tool_call":{"arguments":{"path":"x"}}}'
    messages = compress_messages([{"role": "tool", "content": payload}], limits)
    assert messages[0]["content"] == payload


def test_trace_schema_and_secret_redaction(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "trace.jsonl"
    export_trace(path, {"objective": "x", "tool_observation": "Authorization: Bearer secret"})
    trace = json.loads(path.read_text())
    assert set(trace) == TRACE_FIELDS
    assert "secret" not in trace["tool_observation"]
