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
    seen: set[str] = set()
    retained = messages[-limits.max_retained_observations :]
    tool_count = sum(message.get("role") == "tool" for message in retained)
    tool_budget = limits.max_tool_output_characters // max(1, tool_count)
    for message in retained:
        item = redact(message.copy())
        if item.get("role") == "tool":
            content = item.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, default=str)
            item["content"] = compress_text(content, limits)[:tool_budget]
        fingerprint = json.dumps(item, sort_keys=True, default=str)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        compressed.append(item)
    return compressed
