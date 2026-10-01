"""Canonical Action Runtime: capability-gated tool execution.

The Executor reasons in terms of :class:`ActionIntent`; only this package may
map a stable internal capability ID back to an external harness tool name.
Model output (native tool calls, textual ``<tool_call>`` markup, legacy
aliases) is normalized into canonical actions and must pass
:func:`preflight_action` before reaching any client harness.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

ACTION_METRICS = (
    "invalid_action_rejected",
    "unknown_tool_rejected",
    "unknown_resource_rejected",
    "duplicate_failed_action_rejected",
    "compatibility_action_recovered",
    "laya_shadow_agreement",
    "laya_shadow_disagreement",
)

ResourcePolicy = Literal["DISCOVERED_ONLY", "OBSERVED_ONLY", "WORKSPACE_BOUNDED"]
SideEffectClass = Literal["read", "write", "execute", "discover", "control"]

_MCP_DISCOVERY_TOOLS = frozenset({"list_mcp_resources", "list_mcp_resource_templates"})
_MCP_READ_TOOLS = frozenset({"read_mcp_resource"})
_MCP_TOOLS = _MCP_DISCOVERY_TOOLS | _MCP_READ_TOOLS
_READ_TOOL_HINTS = ("read", "get", "list", "cat", "inspect", "describe", "status", "check")
_WRITE_TOOL_HINTS = ("write", "edit", "patch", "apply", "create", "update", "delete", "put")
_EXECUTE_TOOL_HINTS = ("exec", "shell", "bash", "terminal", "command", "run", "stdin")
_DISCOVER_TOOL_HINTS = ("discover", "list", "template")
_KNOWN_SESSION_ARGUMENTS = frozenset(
    {"session_id", "process_id", "continuation_id", "container_id", "handle", "run_id"}
)
_PATH_ARGUMENT_KEYS = frozenset(
    {"path", "file", "filepath", "filename", "target", "targetpath", "uri", "workdir", "cwd"}
)


def _tool_external_name(tool: dict[str, Any]) -> str:
    function = tool.get("function")
    if isinstance(function, dict) and function.get("name"):
        return str(function["name"])
    if isinstance(tool.get("name"), str) and tool["name"]:
        return str(tool["name"])
    return ""


def _tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool.get("function")
    parameters: Any = None
    if isinstance(function, dict):
        parameters = function.get("parameters")
    if parameters is None:
        parameters = tool.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def _schema_hash(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _tool_family(name: str, schema: dict[str, Any]) -> str:
    lowered = name.lower()
    if lowered in _MCP_TOOLS or lowered.startswith("mcp"):
        return "mcp"
    for hint in _DISCOVER_TOOL_HINTS:
        if hint in lowered and ("mcp" in lowered or "resource" in lowered):
            return "mcp"
    for hint in _EXECUTE_TOOL_HINTS:
        if hint in lowered:
            return "execute"
    for hint in _WRITE_TOOL_HINTS:
        if hint in lowered:
            return "write"
    for hint in _READ_TOOL_HINTS:
        if hint in lowered:
            return "read"
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if isinstance(properties, dict):
        keys = {str(key).lower() for key in properties}
        if "command" in keys or "cmd" in keys:
            return "execute"
        if "content" in keys or "input" in keys or "patch" in keys:
            return "write"
        if "path" in keys or "uri" in keys:
            return "read"
    return "execute"


def _side_effect(name: str, family: str) -> SideEffectClass:
    lowered = name.lower()
    if lowered in _MCP_DISCOVERY_TOOLS or "discover" in lowered:
        return "discover"
    if family == "read":
        return "read"
    if family == "write":
        return "write"
    if lowered.startswith(("update_plan", "create_goal", "get_goal")):
        return "control"
    return "execute"


def _resource_policy(name: str, family: str) -> ResourcePolicy:
    lowered = name.lower()
    if lowered in _MCP_TOOLS or "mcp" in lowered:
        return "DISCOVERED_ONLY"
    if family in {"read", "write", "execute"}:
        return "WORKSPACE_BOUNDED"
    return "OBSERVED_ONLY"


@dataclass(frozen=True)
class ToolCapability:
    capability_id: str
    external_name: str
    tool_family: str
    schema: dict[str, Any]
    schema_hash: str
    resource_policy: ResourcePolicy
    side_effect_class: SideEffectClass

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "external_name": self.external_name,
            "tool_family": self.tool_family,
            "schema_hash": self.schema_hash,
            "resource_policy": self.resource_policy,
            "side_effect_class": self.side_effect_class,
        }


@dataclass
class CapabilitySnapshot:
    revision: str
    capabilities: dict[str, ToolCapability] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def capability(self, capability_id: str) -> ToolCapability | None:
        return self.capabilities.get(capability_id)

    def capability_id_for(self, external_name: str) -> str | None:
        return self.names.get(external_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "capabilities": [item.to_dict() for item in self.capabilities.values()],
        }


def build_capability_snapshot(tools: list[dict[str, Any]] | None) -> CapabilitySnapshot:
    """Build tool truth from the tools advertised on the current request."""
    capabilities: dict[str, ToolCapability] = {}
    names: dict[str, str] = {}
    for index, tool in enumerate(tools or []):
        if not isinstance(tool, dict):
            continue
        external_name = _tool_external_name(tool)
        if not external_name or external_name in names:
            continue
        schema = _tool_schema(tool)
        family = _tool_family(external_name, schema)
        capability_id = f"CAPABILITY_T{index}"
        capabilities[capability_id] = ToolCapability(
            capability_id=capability_id,
            external_name=external_name,
            tool_family=family,
            schema=schema,
            schema_hash=_schema_hash(schema),
            resource_policy=_resource_policy(external_name, family),
            side_effect_class=_side_effect(external_name, family),
        )
        names[external_name] = capability_id
    digest = json.dumps(
        sorted(
            (item.capability_id, item.external_name, item.schema_hash)
            for item in capabilities.values()
        ),
        separators=(",", ":"),
    )
    revision = hashlib.sha256(digest.encode()).hexdigest()[:16]
    return CapabilitySnapshot(revision=revision, capabilities=capabilities, names=names)


@dataclass(frozen=True)
class ActionIntent:
    operation: str
    target: str = ""
    reason: str = ""
    expected_postcondition: str = ""
    argument_hints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateAction:
    capability_id: str
    arguments: dict[str, Any]
    intent: ActionIntent | None = None
    source: str = "executor"


@dataclass(frozen=True)
class ResourceRef:
    kind: str
    value: str
    policy: ResourcePolicy


@dataclass(frozen=True)
class ActionDecision:
    candidate: CandidateAction
    capability: ToolCapability
    resources: tuple[ResourceRef, ...]
    semantic_fingerprint: str
    source: str = "deterministic"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def canonical_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key in sorted(arguments):
        value = arguments[key]
        if isinstance(value, dict):
            canonical[key] = canonical_arguments(value)
        elif isinstance(value, list):
            canonical[key] = [
                canonical_arguments(item) if isinstance(item, dict) else item for item in value
            ]
        elif isinstance(value, str):
            canonical[key] = value.strip()
        else:
            canonical[key] = value
    return canonical


def resource_references(
    capability: ToolCapability, arguments: dict[str, Any]
) -> tuple[ResourceRef, ...]:
    references: list[ResourceRef] = []
    lowered_name = capability.external_name.lower()
    if lowered_name in _MCP_TOOLS or "mcp" in lowered_name:
        server = arguments.get("server", arguments.get("server_id", arguments.get("name")))
        if isinstance(server, str) and server.strip():
            references.append(ResourceRef("mcp_server", server.strip(), "DISCOVERED_ONLY"))
        uri = arguments.get("uri", arguments.get("resource_uri"))
        if isinstance(uri, str) and uri.strip():
            references.append(ResourceRef("mcp_uri", uri.strip(), "DISCOVERED_ONLY"))
    for key, value in arguments.items():
        normalized = str(key).lower().replace("_", "")
        if normalized in {
            "sessionid",
            "processid",
            "continuationid",
            "containerid",
            "handle",
            "runid",
        } or (str(key) in _KNOWN_SESSION_ARGUMENTS and isinstance(value, (str, int))):
            text = str(value).strip()
            if text:
                references.append(ResourceRef("runtime_id", text, "OBSERVED_ONLY"))
    for key, value in arguments.items():
        normalized_key = str(key).lower().replace("_", "")
        if normalized_key in _PATH_ARGUMENT_KEYS and isinstance(value, str) and value.strip():
            references.append(ResourceRef("filesystem_path", value.strip(), "WORKSPACE_BOUNDED"))
    seen: set[tuple[str, str, str]] = set()
    unique: list[ResourceRef] = []
    for reference in references:
        marker = (reference.kind, reference.value, reference.policy)
        if marker not in seen:
            seen.add(marker)
            unique.append(reference)
    return tuple(sorted(unique, key=lambda item: (item.kind, item.value)))


def semantic_fingerprint(
    capability: ToolCapability, arguments: dict[str, Any], schema_hash: str | None = None
) -> str:
    payload = {
        "capability": capability.external_name,
        "schema": schema_hash or capability.schema_hash,
        "arguments": canonical_arguments(arguments),
        "resources": [
            {"kind": item.kind, "value": item.value, "policy": item.policy}
            for item in resource_references(capability, arguments)
        ],
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def execution_fingerprint(semantic: str, state_revision: str) -> str:
    payload = {"semantic": semantic, "state_revision": state_revision}
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
