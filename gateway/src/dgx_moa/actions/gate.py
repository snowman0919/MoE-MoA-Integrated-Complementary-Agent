"""Deterministic compiler plus preflight validator for external actions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .compat import AdapterTelemetry, normalize_arguments, normalize_tool_name
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


@dataclass
class PreflightContext:
    snapshot: CapabilitySnapshot
    authority: ResourceAuthority
    ledger: FailureLedger
    state_revision: str = ""
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
    schema_problem = _schema_error(capability.schema, arguments)
    if schema_problem is not None:
        return PreflightResult(False, "schema_mismatch", schema_problem)
    authority_ok, authority_message = context.authority.check(capability, arguments)
    if not authority_ok:
        code = "workspace_violation" if "workspace" in authority_message else "unknown_resource"
        return PreflightResult(False, code, authority_message)
    canonical = canonical_arguments(arguments)
    fingerprint = semantic_fingerprint(capability, canonical)
    if context.state_revision and context.ledger.is_blocked(fingerprint, context.state_revision):
        return PreflightResult(
            False, "duplicate_failed_action", "identical failed action is blocked"
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
