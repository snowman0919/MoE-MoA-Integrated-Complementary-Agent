"""State revisions and canonical failure ledger for action retries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from .types import _canonical_json, canonical_arguments

RELEVANT_STATE_DOMAINS = (
    "filesystem",
    "repository",
    "capabilities",
    "mcp_discovery",
    "sessions",
    "providers",
    "continuation",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class StateRevision:
    revision: str
    domains: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"revision": self.revision, "domains": dict(self.domains)}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return []


def _executions_digest(executions: Any) -> str:
    items: list[Any] = []
    if isinstance(executions, list):
        for execution in executions[-32:]:
            if not isinstance(execution, dict):
                continue
            paths: list[str] = []
            for key in ("changed_paths", "created_paths", "deleted_paths"):
                effect = execution.get("filesystem_effect")
                values: Any = None
                if isinstance(effect, dict):
                    values = effect.get(key)
                if values is None:
                    values = execution.get(key)
                if isinstance(values, list):
                    paths.extend(str(item) for item in values)
            items.append(
                {
                    "tool": str(execution.get("tool_name", "")),
                    "exit": execution.get("exit_code"),
                    "paths": sorted(set(paths)),
                }
            )
    return _digest(items)


def build_state_revision(
    *,
    tool_executions: Any = None,
    changed_paths: Any = None,
    implementation_evidence: Any = None,
    capability_revision: str = "",
    discovered_mcp_servers: Any = None,
    discovered_mcp_uris: Any = None,
    observed_runtime_ids: Any = None,
    provider_generation: Any = None,
    continuation_state: Any = None,
    repository_state: Any = None,
) -> StateRevision:
    domains = {
        "filesystem": _digest(
            {
                "changed": _string_list(changed_paths),
                "evidence": _string_list(
                    [
                        item.get("tool_name") if isinstance(item, dict) else item
                        for item in (implementation_evidence or [])
                    ]
                ),
                "executions": _executions_digest(tool_executions),
            }
        ),
        "repository": _digest(repository_state if repository_state is not None else {}),
        "capabilities": _digest(capability_revision or ""),
        "mcp_discovery": _digest(
            {
                "servers": _string_list(discovered_mcp_servers),
                "uris": _string_list(discovered_mcp_uris),
            }
        ),
        "sessions": _digest(_string_list(observed_runtime_ids)),
        "providers": _digest(provider_generation if provider_generation is not None else ""),
        "continuation": _digest(continuation_state if continuation_state is not None else ""),
    }
    revision = _digest({name: domains[name] for name in RELEVANT_STATE_DOMAINS})
    return StateRevision(revision=revision, domains=domains)


def _session_value(session: Any, name: str) -> Any:
    if isinstance(session, dict):
        return session.get(name)
    return getattr(session, name, None)


def state_revision_from_session(
    session: Any,
    *,
    capability_revision: str = "",
    discovered_mcp_servers: Any = None,
    discovered_mcp_uris: Any = None,
    observed_runtime_ids: Any = None,
    provider_generation: Any = None,
) -> StateRevision:
    executions = _session_value(session, "tool_executions")
    changed: list[str] = []
    if isinstance(executions, list):
        for execution in executions[-32:]:
            if not isinstance(execution, dict):
                continue
            effect = execution.get("filesystem_effect")
            if isinstance(effect, dict):
                for key in ("changed_paths", "created_paths", "deleted_paths"):
                    values = effect.get(key)
                    if isinstance(values, list):
                        changed.extend(str(item) for item in values)
    repository = _session_value(session, "repository")
    if not isinstance(repository, dict):
        repository = {}
    continuation = {
        "pending": _session_value(session, "pending_tool_call_ids"),
        "last": _session_value(session, "last_tool_call"),
        "phase": str(_session_value(session, "phase") or ""),
    }
    return build_state_revision(
        tool_executions=executions,
        changed_paths=changed,
        implementation_evidence=_session_value(session, "implementation_evidence"),
        capability_revision=capability_revision,
        discovered_mcp_servers=discovered_mcp_servers,
        discovered_mcp_uris=discovered_mcp_uris,
        observed_runtime_ids=observed_runtime_ids,
        provider_generation=provider_generation,
        continuation_state=continuation,
        repository_state=repository,
    )


FailureOutcome = Literal["failed", "blocked", "succeeded"]


@dataclass
class FailureEntry:
    semantic_fingerprint: str
    execution_fingerprint: str
    state_revision: str
    failure_class: str
    outcome: FailureOutcome = "failed"


@dataclass
class FailureLedger:
    """Canonical retry gate: unchanged failed executions stay blocked."""

    entries: dict[str, FailureEntry] = field(default_factory=dict)

    def record_failure(
        self,
        semantic: str,
        revision: StateRevision | str,
        failure_class: str,
        *,
        outcome: FailureOutcome = "failed",
    ) -> FailureEntry:
        revision_id = revision.revision if isinstance(revision, StateRevision) else str(revision)
        entry = FailureEntry(
            semantic_fingerprint=semantic,
            execution_fingerprint=_execution(semantic, revision_id),
            state_revision=revision_id,
            failure_class=failure_class,
            outcome=outcome,
        )
        self.entries[semantic] = entry
        return entry

    def record_success(self, semantic: str) -> None:
        self.entries.pop(semantic, None)

    def is_blocked(self, semantic: str, revision: StateRevision | str) -> bool:
        entry = self.entries.get(semantic)
        if entry is None or entry.outcome == "succeeded":
            return False
        revision_id = revision.revision if isinstance(revision, StateRevision) else str(revision)
        return entry.state_revision == revision_id

    def to_dict(self) -> dict[str, Any]:
        return {
            semantic: {
                "execution_fingerprint": entry.execution_fingerprint,
                "state_revision": entry.state_revision,
                "failure_class": entry.failure_class,
                "outcome": entry.outcome,
            }
            for semantic, entry in self.entries.items()
        }

    @classmethod
    def from_dict(cls, payload: Any) -> FailureLedger:
        ledger = cls()
        if isinstance(payload, dict):
            for semantic, item in payload.items():
                if not isinstance(item, dict):
                    continue
                raw_outcome = item.get("outcome", "failed")
                outcome: FailureOutcome = (
                    raw_outcome if raw_outcome in ("failed", "blocked", "succeeded") else "failed"
                )
                ledger.entries[str(semantic)] = FailureEntry(
                    semantic_fingerprint=str(semantic),
                    execution_fingerprint=str(item.get("execution_fingerprint", "")),
                    state_revision=str(item.get("state_revision", "")),
                    failure_class=str(item.get("failure_class", "TOOL_EXECUTION_FAILURE")),
                    outcome=outcome,
                )
        return ledger


def _execution(semantic: str, revision: str) -> str:
    payload = json.dumps({"semantic": semantic, "revision": revision}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def legacy_failure_key(tool_name: str, arguments: Any) -> str:
    normalized = arguments if isinstance(arguments, dict) else {"raw": str(arguments)}
    payload = {"call": _digest({"function": {"name": tool_name, "arguments": normalized}})}
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def canonical_semantic_key(tool_name: str, arguments: dict[str, Any], state: Any = None) -> str:
    from .types import ToolCapability, semantic_fingerprint

    capability = ToolCapability(
        capability_id="legacy",
        external_name=tool_name,
        tool_family="execute",
        schema={},
        schema_hash="legacy",
        resource_policy="WORKSPACE_BOUNDED",
        side_effect_class="execute",
    )
    canonical = canonical_arguments(arguments if isinstance(arguments, dict) else {})
    return semantic_fingerprint(capability, canonical)
