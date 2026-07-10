from __future__ import annotations

import json
from typing import Any

from .config import Limits
from .security import redact


def compress_text(text: str, limits: Limits) -> str:
    if len(text) <= limits.max_tool_output_characters:
        return str(redact(text))
    lines = text.splitlines()
    errors = [
        line
        for line in lines
        if any(word in line.lower() for word in ("error", "failed", "exception", "exit code"))
    ][: limits.max_error_lines]
    head = lines[:20]
    tail = lines[-20:]
    kept = list(dict.fromkeys([*head, *errors, *tail]))
    return str(redact("\n".join(kept)))[: limits.max_tool_output_characters]


def compress_messages(messages: list[dict[str, Any]], limits: Limits) -> list[dict[str, Any]]:
    compressed: list[dict[str, Any]] = []
    for message in messages[-limits.max_retained_observations :]:
        item = redact(message.copy())
        if item.get("role") == "tool" and isinstance(item.get("content"), str):
            content = item["content"]
            try:
                json.loads(content)
            except ValueError:
                item["content"] = compress_text(content, limits)
        compressed.append(item)
    return compressed
