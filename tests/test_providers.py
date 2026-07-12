from __future__ import annotations

import pytest
from dgx_moa.providers import ModelProvider, parse_json_content


def test_judge_is_read_only(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "judge",
        settings.models["judge"],
        {"messages": [], "tools": [{"type": "function"}], "tool_choice": "required"},
    )
    assert "tools" not in body
    assert "tool_choice" not in body
    assert body["stream"] is False


def test_missing_structured_content_is_controlled_error() -> None:
    with pytest.raises(ValueError, match="structured model response missing content"):
        parse_json_content({"choices": [{"message": {"content": None}}]})
