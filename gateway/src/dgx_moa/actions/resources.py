"""Resource authority: discovered MCP, observed runtime IDs, workspace files."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

from .types import ResourceRef, ToolCapability


def _normalize_path(value: str) -> str:
    text = value.strip().removeprefix("file://")
    if not text.startswith("/"):
        return text
    return posixpath.normpath(text)


@dataclass
class ResourceAuthority:
    discovered_mcp_servers: set[str] = field(default_factory=set)
    discovered_mcp_uris: set[str] = field(default_factory=set)
    observed_runtime_ids: set[str] = field(default_factory=set)
    workspace_roots: tuple[str, ...] = ()
    allow_relative_paths: bool = True

    def note_discovered_server(self, server: str) -> None:
        if server.strip():
            self.discovered_mcp_servers.add(server.strip())

    def note_discovered_uri(self, uri: str) -> None:
        if uri.strip():
            self.discovered_mcp_uris.add(uri.strip())

    def note_observed_id(self, value: str) -> None:
        if str(value).strip():
            self.observed_runtime_ids.add(str(value).strip())

    def _workspace_allows(self, raw_path: str) -> bool:
        text = raw_path.strip().removeprefix("file://")
        if not text or "\n" in text or "\x00" in text:
            return False
        if text.startswith("/"):
            normalized = _normalize_path(text)
            for root in self.workspace_roots:
                cleaned = root.strip().rstrip("/")
                if not cleaned:
                    continue
                if normalized == cleaned or normalized.startswith(cleaned + "/"):
                    return True
            return False
        if text.startswith("~") or ".." in text.split("/"):
            return False
        return self.allow_relative_paths

    def check(self, capability: ToolCapability, arguments: dict[str, Any]) -> tuple[bool, str]:
        from .types import resource_references

        for reference in resource_references(capability, arguments):
            outcome = self.check_reference(reference)
            if not outcome[0]:
                return outcome
        return True, "ok"

    def check_reference(self, reference: ResourceRef) -> tuple[bool, str]:
        if reference.policy == "DISCOVERED_ONLY":
            if reference.kind == "mcp_server":
                if reference.value in self.discovered_mcp_servers:
                    return True, "ok"
                return False, f"unknown mcp server '{reference.value}'"
            if reference.kind == "mcp_uri":
                if reference.value in self.discovered_mcp_uris:
                    return True, "ok"
                if self._file_uri_inside_workspace(reference.value):
                    return True, "ok"
                return False, f"undiscovered mcp uri '{reference.value}'"
            return False, f"undiscovered resource '{reference.kind}:{reference.value}'"
        if reference.policy == "OBSERVED_ONLY":
            if reference.value in self.observed_runtime_ids:
                return True, "ok"
            return False, f"unobserved runtime id '{reference.value}'"
        if reference.policy == "WORKSPACE_BOUNDED":
            if self._workspace_allows(reference.value):
                return True, "ok"
            return False, f"path escapes workspace '{reference.value}'"
        return False, f"unknown resource policy '{reference.policy}'"

    def _file_uri_inside_workspace(self, uri: str) -> bool:
        try:
            parsed = urlsplit(uri)
        except ValueError:
            return False
        if parsed.scheme not in {"", "file"}:
            return False
        if parsed.scheme == "file" and parsed.netloc not in {"", "localhost"}:
            return False
        path = unquote(parsed.path) if parsed.scheme == "file" else uri
        if not path.startswith("/"):
            return False
        return self._workspace_allows(path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "servers": sorted(self.discovered_mcp_servers),
            "uris": sorted(self.discovered_mcp_uris),
            "runtime_ids": sorted(self.observed_runtime_ids),
            "workspace_roots": list(self.workspace_roots),
        }

    @classmethod
    def from_session(
        cls,
        session: Any,
        *,
        workspace_roots: tuple[str, ...] = (),
    ) -> ResourceAuthority:
        authority = cls(workspace_roots=workspace_roots)
        executions: Any = None
        results: Any = None
        if isinstance(session, dict):
            executions = session.get("tool_executions")
            results = session.get("tool_results")
        else:
            executions = getattr(session, "tool_executions", None)
            results = getattr(session, "tool_results", None)
        for collection in (executions, results):
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict):
                    continue
                cls._harvest_item(authority, item)
        return authority

    @staticmethod
    def _harvest_item(authority: ResourceAuthority, item: dict[str, Any]) -> None:
        texts: list[str] = []
        for key in ("stdout", "stderr", "stdout_summary", "stderr_summary", "output"):
            value = item.get(key)
            if isinstance(value, str) and value:
                texts.append(value)
        succeeded = item.get("exit_code", 0) == 0 and "error" not in item
        failure_text = " ".join(texts).lower()
        failed_discovery = any(
            marker in failure_text
            for marker in ("unknown mcp server", "resources/read failed", "not found", "no such")
        )
        arguments = item.get("normalized_arguments", item.get("arguments"))
        if succeeded and not failed_discovery and isinstance(arguments, dict):
            for key in ("server", "server_id"):
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    authority.note_discovered_server(value.strip())
            for key in ("uri", "resource_uri"):
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    authority.note_discovered_uri(value.strip())
        tool_name = str(item.get("tool_name", ""))
        if (
            tool_name in {"list_mcp_resources", "list_mcp_resource_templates"}
            and succeeded
            and not failed_discovery
        ):
            for text in texts:
                for token in text.replace(",", " ").split():
                    token = token.strip().strip("\"'()[]{}")
                    if token.startswith(("file://", "mcp://", "resource://")) or (
                        "/" in token and "." in token and len(token) < 256
                    ):
                        authority.note_discovered_uri(token)
        session_id = item.get("session_id")
        if isinstance(session_id, int) and session_id >= 1:
            authority.note_observed_id(str(session_id))
        call_id = item.get("tool_call_id")
        if isinstance(call_id, str) and call_id.strip():
            authority.note_observed_id(call_id.strip())
