from __future__ import annotations

from dgx_moa.providers import ModelProvider


def test_judge_is_read_only(settings) -> None:  # type: ignore[no-untyped-def]
    body = ModelProvider.body(
        "judge",
        settings.models["judge"],
        {"messages": [], "tools": [{"type": "function"}], "tool_choice": "required"},
    )
    assert "tools" not in body
    assert "tool_choice" not in body
    assert body["stream"] is False
