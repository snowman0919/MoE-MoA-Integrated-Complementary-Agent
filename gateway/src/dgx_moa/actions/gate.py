"""Deterministic compiler plus preflight validator for external actions."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from typing import Any

from .compat import (
    AdapterTelemetry,
    normalize_arguments,
    normalize_local_file_compat,
    normalize_tool_name,
)
from .ledger import FailureLedger
from .resources import ResourceAuthority
from .types import (
    ActionDecision,
    CandidateAction,
    CapabilitySnapshot,
    canonical_arguments,
    resource_references,
    semantic_fingerprint,
)


@dataclass(frozen=True)
class CompiledAction:
    external_name: str
    arguments_json: str
    capability_id: str
    schema_hash: str


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    code: str
    message: str
    decision: ActionDecision | None = None
    compiled: CompiledAction | None = None
    adapters: tuple[str, ...] = ()
    recovered: bool = False
    semantic_fingerprint: str = ""
    state_revision: str = ""
    sanitized_call: dict[str, Any] | None = None


@dataclass
class PreflightPolicy:
    denied_tools: tuple[str, ...] = ()
    denied_side_effects: tuple[str, ...] = ()


@dataclass
class PreflightContext:
    snapshot: CapabilitySnapshot
    authority: ResourceAuthority
    ledger: FailureLedger
    state_revision: str = ""
    policy: PreflightPolicy | None = None
    telemetry: AdapterTelemetry = field(default_factory=AdapterTelemetry)


def _schema_error(schema: Any, arguments: Any) -> str | None:
    if not isinstance(schema, dict) or not schema:
        return None if isinstance(arguments, dict) else "arguments must be an object"
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        return None
    required = schema.get("required")
    if isinstance(required, list):
        missing = [str(item) for item in required if item not in arguments]
        if missing:
            return f"missing required fields: {', '.join(sorted(missing))}"
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, declaration in properties.items():
            if name not in arguments or not isinstance(declaration, dict):
                continue
            expected = declaration.get("type")
            if expected is None:
                continue
            value = arguments[name]
            if expected == "string" and not isinstance(value, str):
                return f"field '{name}' must be a string"
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return f"field '{name}' must be an integer"
            if expected == "number" and not (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            ):
                return f"field '{name}' must be a number"
            if expected == "boolean" and not isinstance(value, bool):
                return f"field '{name}' must be a boolean"
            if expected == "object" and not isinstance(value, dict):
                return f"field '{name}' must be an object"
            if expected == "array" and not isinstance(value, list):
                return f"field '{name}' must be an array"
    additional = schema.get("additionalProperties")
    if additional is False and isinstance(properties, dict):
        unknown = sorted(name for name in arguments if name not in properties)
        if unknown:
            return f"unknown fields: {', '.join(unknown)}"
    return None


def compile_action(decision: ActionDecision) -> CompiledAction:
    canonical = canonical_arguments(decision.candidate.arguments)
    return CompiledAction(
        external_name=decision.capability.external_name,
        arguments_json=json.dumps(canonical, ensure_ascii=False, separators=(",", ":")),
        capability_id=decision.capability.capability_id,
        schema_hash=decision.capability.schema_hash,
    )


def preflight_action(
    snapshot: CapabilitySnapshot,
    tool_name: str,
    raw_arguments: str | dict[str, Any],
    context: PreflightContext,
) -> PreflightResult:
    available = set(snapshot.names)
    resolved_name, renamed = normalize_tool_name(tool_name, available)
    adapters: list[str] = []
    if renamed:
        adapters.append("tool_alias")
        context.telemetry.record("tool_alias")
    capability_id = snapshot.capability_id_for(resolved_name)
    if capability_id is None:
        parsed_for_compat: dict[str, Any] | None = None
        if isinstance(raw_arguments, dict):
            parsed_for_compat = dict(raw_arguments)
        elif isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                decoded = json.loads(raw_arguments)
            except ValueError:
                decoded = None
            parsed_for_compat = decoded if isinstance(decoded, dict) else None
        local_adapted = (
            normalize_local_file_compat(
                tool_name, parsed_for_compat, available, telemetry=context.telemetry
            )
            if parsed_for_compat is not None
            else None
        )
        if local_adapted is not None:
            adapted = preflight_action(
                snapshot, local_adapted.tool_name, local_adapted.arguments, context
            )
            if adapted.ok:
                return PreflightResult(
                    adapted.ok,
                    adapted.code,
                    adapted.message,
                    decision=adapted.decision,
                    compiled=adapted.compiled,
                    adapters=tuple([*adapters, "local_file", *adapted.adapters]),
                    recovered=True,
                    semantic_fingerprint=adapted.semantic_fingerprint,
                    state_revision=adapted.state_revision,
                )
        return PreflightResult(False, "unknown_tool", f"unknown tool '{tool_name}'")
    capability = snapshot.capabilities[capability_id]
    if isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    elif isinstance(raw_arguments, str):
        if not raw_arguments.strip():
            arguments = {}
        else:
            try:
                parsed = json.loads(raw_arguments)
            except ValueError:
                return PreflightResult(False, "malformed_arguments", "arguments are not valid JSON")
            if not isinstance(parsed, dict):
                return PreflightResult(False, "malformed_arguments", "arguments must be an object")
            arguments = parsed
    else:
        return PreflightResult(False, "malformed_arguments", "arguments must be an object")
    arguments, aliased = normalize_arguments(capability.external_name, arguments)
    if aliased:
        adapters.append("argument_alias")
        context.telemetry.record("argument_alias")
    canonical = canonical_arguments(arguments)
    fingerprint = semantic_fingerprint(capability, canonical)
    schema_problem = _schema_error(capability.schema, arguments)
    if schema_problem is not None:
        return PreflightResult(
            False,
            "schema_mismatch",
            schema_problem,
            semantic_fingerprint=fingerprint,
            state_revision=context.state_revision,
        )
    authority_ok, authority_message = context.authority.check(capability, arguments)
    if not authority_ok:
        code = "workspace_violation" if "workspace" in authority_message else "unknown_resource"
        return PreflightResult(
            False,
            code,
            authority_message,
            semantic_fingerprint=fingerprint,
            state_revision=context.state_revision,
        )
    if context.state_revision and context.ledger.is_blocked(fingerprint, context.state_revision):
        return PreflightResult(
            False,
            "duplicate_failed_action",
            "identical failed action is blocked",
            semantic_fingerprint=fingerprint,
            state_revision=context.state_revision,
        )
    policy = context.policy
    if policy is not None:
        if any(
            fnmatch.fnmatch(capability.external_name, pattern) for pattern in policy.denied_tools
        ):
            return PreflightResult(
                False,
                "permission_denied",
                f"tool '{capability.external_name}' is denied",
                semantic_fingerprint=fingerprint,
                state_revision=context.state_revision,
            )
        if capability.side_effect_class in policy.denied_side_effects:
            return PreflightResult(
                False,
                "permission_denied",
                f"side effect '{capability.side_effect_class}' is denied",
                semantic_fingerprint=fingerprint,
                state_revision=context.state_revision,
            )
    candidate = CandidateAction(capability_id=capability_id, arguments=canonical)
    decision = ActionDecision(
        candidate=candidate,
        capability=capability,
        resources=resource_references(capability, canonical),
        semantic_fingerprint=fingerprint,
    )
    compiled = compile_action(decision)
    recovered = bool(adapters)
    if recovered:
        for adapter in adapters:
            context.telemetry.record(f"recovered:{adapter}")
    return PreflightResult(
        True,
        "ok",
        "ok",
        decision=decision,
        compiled=compiled,
        adapters=tuple(adapters),
        recovered=recovered,
        semantic_fingerprint=fingerprint,
        state_revision=context.state_revision,
        sanitized_call={
            "id": "",
            "type": "function",
            "function": {"name": compiled.external_name, "arguments": compiled.arguments_json},
        },
    )


def preflight_tool_call(
    call: dict[str, Any], snapshot: CapabilitySnapshot, context: PreflightContext
) -> PreflightResult:
    function = call.get("function") if isinstance(call, dict) else None
    name = function.get("name") if isinstance(function, dict) else ""
    raw_arguments = function.get("arguments") if isinstance(function, dict) else ""
    if not isinstance(name, str) or not name:
        return PreflightResult(False, "unknown_tool", "tool call is missing a function name")
    return preflight_action(
        snapshot, name, raw_arguments if raw_arguments is not None else "", context
    )
