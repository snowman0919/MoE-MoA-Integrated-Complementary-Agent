"""Compatibility adapters: legacy representations become canonical actions.

Adapters may rename a known alias or parse textual markup, but they can never
invent a capability. Every adapter result must still pass preflight validation.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

_TOOL_CALL_PATTERN = re.compile(
    r"\s*<tool_call>\s*<function=(?P<name>[A-Za-z_][A-Za-z0-9_]*)>"
    r"(?P<parameters>.*?)</function>\s*</tool_call>",
    re.DOTALL,
)
_TOOL_PARAMETER_PATTERN = re.compile(
    r"\s*<parameter=(?P<name>[A-Za-z_][A-Za-z0-9_]*)>(?P<value>.*?)</parameter>",
    re.DOTALL,
)

# Verified tool-name aliases only. Fuzzy name guessing is forbidden.
TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "shell": ("bash", "exec_command"),
    "bash": ("exec_command",),
}

# Verified argument aliases only. Unknown keys still fail schema validation.
ARGUMENT_ALIASES: dict[str, dict[str, str]] = {
    "bash": {"cmd": "command"},
    "exec_command": {"command": "cmd"},
    "shell": {"command": "cmd", "cmd": "cmd"},
}

ADAPTER_NAMES = (
    "text_tool_call",
    "tool_alias",
    "argument_alias",
    "local_file",
    "continuation",
)


@dataclass
class AdaptationResult:
    tool_name: str
    arguments: dict[str, Any]
    adapters: tuple[str, ...] = ()
    recovered: bool = False


@dataclass
class AdapterTelemetry:
    counts: dict[str, int] = field(default_factory=dict)

    def record(self, adapter: str) -> None:
        self.counts[adapter] = self.counts.get(adapter, 0) + 1

    def to_dict(self) -> dict[str, int]:
        return dict(self.counts)


def parse_textual_tool_calls(text: str) -> list[tuple[str, dict[str, Any]]] | None:
    calls: list[tuple[str, dict[str, Any]]] = []
    cursor = 0
    for match in _TOOL_CALL_PATTERN.finditer(text):
        if text[cursor : match.start()].strip():
            return None
        parameters = match.group("parameters")
        arguments: dict[str, Any] = {}
        parameter_cursor = 0
        for parameter in _TOOL_PARAMETER_PATTERN.finditer(parameters):
            if parameters[parameter_cursor : parameter.start()].strip():
                return None
            name = parameter.group("name")
            if name in arguments:
                return None
            raw_value = parameter.group("value").strip()
            try:
                arguments[name] = json.loads(raw_value)
            except ValueError:
                arguments[name] = raw_value
            parameter_cursor = parameter.end()
        if parameters[parameter_cursor:].strip():
            return None
        calls.append((match.group("name"), arguments))
        cursor = match.end()
    if not calls or text[cursor:].strip():
        return None
    return calls


def recover_textual_tool_call(
    text: str, available_tool_names: set[str] | None = None
) -> AdaptationResult | None:
    parsed = parse_textual_tool_calls(text)
    if not parsed or len(parsed) != 1:
        return None
    name, arguments = parsed[0]
    tool_name = name
    if tool_name not in (available_tool_names or set()):
        for candidate in TOOL_ALIASES.get(tool_name, ()):
            if candidate in (available_tool_names or set()):
                tool_name = candidate
                break
    return AdaptationResult(
        tool_name=tool_name, arguments=arguments, adapters=("text_tool_call",), recovered=True
    )


def normalize_tool_name(tool_name: str, available_tool_names: set[str]) -> tuple[str, bool]:
    if tool_name in available_tool_names:
        return tool_name, False
    for candidate in TOOL_ALIASES.get(tool_name, ()):
        if candidate in available_tool_names:
            return candidate, True
    return tool_name, False


def normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    aliases = ARGUMENT_ALIASES.get(tool_name, {})
    if not aliases:
        return dict(arguments), False
    normalized = dict(arguments)
    recovered = False
    for legacy, canonical in aliases.items():
        if legacy != canonical and legacy in normalized and canonical not in normalized:
            normalized[canonical] = normalized.pop(legacy)
            recovered = True
    return normalized, recovered


def normalize_legacy_call(
    tool_name: str,
    raw_arguments: str | dict[str, Any],
    available_tool_names: set[str],
    *,
    telemetry: AdapterTelemetry | None = None,
) -> AdaptationResult:
    adapters: list[str] = []
    if isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    else:
        try:
            parsed = json.loads(raw_arguments) if raw_arguments else {}
        except ValueError:
            return AdaptationResult(tool_name=tool_name, arguments={}, adapters=())
        arguments = parsed if isinstance(parsed, dict) else {}
    resolved_name, renamed = normalize_tool_name(tool_name, available_tool_names)
    if renamed:
        adapters.append("tool_alias")
        if telemetry is not None:
            telemetry.record("tool_alias")
    normalized_arguments, aliased = normalize_arguments(resolved_name, arguments)
    if aliased:
        adapters.append("argument_alias")
        if telemetry is not None:
            telemetry.record("argument_alias")
    return AdaptationResult(
        tool_name=resolved_name,
        arguments=normalized_arguments,
        adapters=tuple(adapters),
        recovered=bool(adapters),
    )


def normalize_local_file_compat(
    tool_name: str,
    arguments: dict[str, Any],
    available_tool_names: set[str],
    *,
    telemetry: AdapterTelemetry | None = None,
) -> AdaptationResult | None:
    """Bounded historical compatibility: local read helpers become ``cat``.

    Only applies when the requested helper is unavailable and ``exec_command``
    is actually advertised. ``read_mcp_resource`` URIs are never rewritten here;
    MCP authority stays with preflight resource checks.
    """
    if tool_name not in {"read_file"} or "exec_command" not in available_tool_names:
        return None
    path = arguments.get("path", arguments.get("file", arguments.get("file_path")))
    if not isinstance(path, str) or not path or "\n" in path:
        return None
    if telemetry is not None:
        telemetry.record("local_file")
    import shlex

    return AdaptationResult(
        tool_name="exec_command",
        arguments={"cmd": f"cat -- {shlex.quote(path)}"},
        adapters=("local_file",),
        recovered=True,
    )


def normalize_edit_call(
    name: str, raw_arguments: str, custom_tool_names: set[str] | None
) -> tuple[str, str]:
    if "apply_patch" not in (custom_tool_names or set()):
        return name, raw_arguments
    try:
        arguments = json.loads(raw_arguments)
        if name == "write_stdin" and "chars" not in arguments:
            path = arguments.get("path", arguments.get("file", arguments.get("file_path")))
            content = arguments.get("content")
            if (
                not isinstance(path, str)
                or not path
                or "\n" in path
                or not isinstance(content, str)
            ):
                raise TypeError
            patch = "\n".join(
                (
                    "*** Begin Patch",
                    f"*** Delete File: {path}",
                    f"*** Add File: {path}",
                    *(f"+{line}" for line in content.splitlines()),
                    "*** End Patch",
                )
            )
            return "apply_patch", json.dumps(
                {"input": patch}, ensure_ascii=False, separators=(",", ":")
            )
        if name not in {"edit", "edit_file"}:
            return name, raw_arguments
        path = arguments.get("file", arguments.get("path", arguments.get("file_path")))
        old_text = arguments.get("old_text", arguments.get("old_string", arguments.get("old")))
        new_text = arguments.get("new_text", arguments.get("new_string", arguments.get("new")))
        if (
            not isinstance(path, str)
            or not path
            or "\n" in path
            or not isinstance(old_text, str)
            or not old_text
            or not isinstance(new_text, str)
        ):
            raise TypeError
    except (TypeError, ValueError):
        return name, raw_arguments
    patch = "\n".join(
        (
            "*** Begin Patch",
            f"*** Update File: {path}",
            "@@",
            *(f"-{line}" for line in old_text.splitlines()),
            *(f"+{line}" for line in new_text.splitlines()),
            "*** End Patch",
        )
    )
    return "apply_patch", json.dumps({"input": patch}, ensure_ascii=False, separators=(",", ":"))


def continuation_key(tool_call_id: str) -> str:
    return f"continuation:{tool_call_id}:{uuid.uuid4().hex[:8]}"


def normalize_continuation_result(
    tool_call_id: str,
    content: Any,
    *,
    telemetry: AdapterTelemetry | None = None,
) -> AdaptationResult:
    if telemetry is not None:
        telemetry.record("continuation")
    return AdaptationResult(
        tool_name="__continuation__",
        arguments={"tool_call_id": tool_call_id, "content": content},
        adapters=("continuation",),
        recovered=False,
    )
