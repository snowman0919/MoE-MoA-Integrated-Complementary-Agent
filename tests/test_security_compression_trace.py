from __future__ import annotations

import json

import pytest
from dgx_moa.compression import compress_messages, compress_text
from dgx_moa.config import Limits, ModelConfig
from dgx_moa.security import redact
from dgx_moa.state import SessionState
from dgx_moa.trace import TRACE_FIELDS, export_trace, trace_record, validate_trace


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


def test_repeated_messages_are_deduplicated() -> None:
    limits = Limits(max_retained_observations=3)
    messages = [{"role": "tool", "content": "same"}] * 2
    assert len(compress_messages(messages, limits)) == 1


def test_trace_contains_model_revision_and_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    model = ModelConfig(
        repository="test/executor",
        revision="abc",
        classification="official",
        base_url="http://127.0.0.1:8101",
        served_name="executor",
        destination=tmp_path / "executor",
        context_length=1024,
    )
    trace = trace_record(SessionState(session_id="trace"), models={"executor": model})
    assert trace["model_revisions"] == {
        "executor": {"repository": "test/executor", "revision": "abc"}
    }
    assert trace["context_configuration"]["executor"]["context_length"] == 1024


def test_trace_schema_rejects_wrong_version() -> None:
    trace = {field: None for field in TRACE_FIELDS}
    trace["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="unsupported trace schema version"):
        validate_trace(trace)
