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
    structured = [{"type": "text", "text": "x" * 200}]
    messages = compress_messages([{"role": "tool", "content": structured}], limits)
    assert isinstance(messages[0]["content"], str)
    assert len(messages[0]["content"]) <= 80


def test_redaction_covers_http_credential_keys() -> None:
    assert redact(
        {
            "authorization": "Bearer synthetic-secret",
            "Cookie": "session=synthetic-secret",
        }
    ) == {"authorization": "[REDACTED]", "Cookie": "[REDACTED]"}


def test_redaction_preserves_token_and_cost_measurements() -> None:
    assert redact(
        {
            "remote_api_cost_per_million_tokens_usd": 1.25,
            "input_tokens": 42,
            "secret_redactions": 0,
            "access_token": "synthetic-secret",
            "clientSecret": "synthetic-secret",
        }
    ) == {
        "remote_api_cost_per_million_tokens_usd": 1.25,
        "input_tokens": 42,
        "secret_redactions": 0,
        "access_token": "[REDACTED]",
        "clientSecret": "[REDACTED]",
    }


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


def test_tool_outputs_share_the_compression_budget() -> None:
    limits = Limits(max_tool_output_characters=80)
    messages = [{"role": "tool", "content": character * 100} for character in ("a", "b", "c", "d")]
    compressed = compress_messages(messages, limits)
    assert sum(len(message["content"]) for message in compressed) <= 80


def test_default_tool_output_budget_preserves_small_source_files() -> None:
    limits = Limits()
    source = "x" * 1_038
    assert limits.max_tool_output_characters == 16_000
    assert compress_text(source, limits) == source


def test_trace_contains_model_revision_and_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    model = ModelConfig(
        repository="test/executor",
        revision="abc",
        classification="official",
        base_url="http://127.0.0.1:8101",
        served_name="executor",
        destination=tmp_path / "executor",
        context_length=65536,
    )
    trace = trace_record(SessionState(session_id="trace"), models={"executor": model})
    assert trace["model_revisions"] == {
        "executor": {"repository": "test/executor", "revision": "abc"}
    }
    assert trace["context_configuration"]["executor"]["context_length"] == 65536


def test_trace_schema_rejects_wrong_version() -> None:
    trace = {field: None for field in TRACE_FIELDS}
    trace["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="unsupported trace schema version"):
        validate_trace(trace)
