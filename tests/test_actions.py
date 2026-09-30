"""Focused Action Runtime tests: capability, resource, ledger, compat, convergence."""

from __future__ import annotations

import json

from dgx_moa.actions import (
    AdapterTelemetry,
    FailureLedger,
    PolicyEngine,
    PreflightContext,
    ResourceAuthority,
    build_capability_snapshot,
    build_state_revision,
    candidates_from_tool_calls,
    normalize_legacy_call,
    normalize_local_file_compat,
    parse_textual_tool_calls,
    preflight_action,
    preflight_tool_call,
    recover_textual_tool_call,
)


def _tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "run",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "read",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_mcp_resource",
                "description": "mcp read",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string"},
                        "uri": {"type": "string"},
                    },
                    "required": ["server", "uri"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_mcp_resources",
                "description": "mcp list",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _context(snapshot, workspace_roots=("/work",)) -> PreflightContext:
    return PreflightContext(
        snapshot=snapshot,
        authority=ResourceAuthority(workspace_roots=workspace_roots),
        ledger=FailureLedger(),
        state_revision="rev-1",
    )


def test_request_tools_become_capabilities() -> None:
    snapshot = build_capability_snapshot(_tools())
    assert set(snapshot.names) == {
        "terminal",
        "read_file",
        "read_mcp_resource",
        "list_mcp_resources",
    }
    assert snapshot.capabilities[snapshot.names["terminal"]].external_name == "terminal"


def test_unavailable_tool_cannot_execute() -> None:
    snapshot = build_capability_snapshot(_tools())
    result = preflight_action(snapshot, "nonexistent_tool", "{}", _context(snapshot))
    assert not result.ok and result.code == "unknown_tool"


def test_schema_mismatch_rejected() -> None:
    snapshot = build_capability_snapshot(_tools())
    result = preflight_action(snapshot, "terminal", '{"command": 42}', _context(snapshot))
    assert not result.ok and result.code == "schema_mismatch"


def test_malformed_arguments_rejected() -> None:
    snapshot = build_capability_snapshot(_tools())
    result = preflight_action(snapshot, "terminal", "{broken", _context(snapshot))
    assert not result.ok and result.code == "malformed_arguments"


def test_guessed_mcp_server_rejected() -> None:
    snapshot = build_capability_snapshot(_tools())
    result = preflight_action(
        snapshot,
        "read_mcp_resource",
        {"server": "guessed", "uri": "mcp://x/y"},
        _context(snapshot),
    )
    assert not result.ok and result.code == "unknown_resource"


def test_undiscovered_mcp_uri_rejected() -> None:
    snapshot = build_capability_snapshot(_tools())
    context = _context(snapshot)
    context.authority.note_discovered_server("files")
    result = preflight_action(
        snapshot, "read_mcp_resource", {"server": "files", "uri": "mcp://x/y"}, context
    )
    assert not result.ok and result.code == "unknown_resource"


def test_observed_mcp_resource_accepted() -> None:
    snapshot = build_capability_snapshot(_tools())
    context = _context(snapshot)
    context.authority.note_discovered_server("files")
    context.authority.note_discovered_uri("mcp://files/doc")
    result = preflight_action(
        snapshot, "read_mcp_resource", {"server": "files", "uri": "mcp://files/doc"}, context
    )
    assert result.ok


def test_invented_session_id_rejected() -> None:
    snapshot = build_capability_snapshot(
        [
            {
                "type": "function",
                "function": {
                    "name": "write_stdin",
                    "parameters": {
                        "type": "object",
                        "properties": {"session_id": {"type": "integer"}},
                        "required": ["session_id"],
                    },
                },
            }
        ]
    )
    result = preflight_action(snapshot, "write_stdin", {"session_id": 999}, _context(snapshot))
    assert not result.ok and result.code == "unknown_resource"


def test_workspace_new_file_accepted_and_escape_rejected() -> None:
    snapshot = build_capability_snapshot(_tools())
    ok_result = preflight_action(
        snapshot, "read_file", {"path": "/work/new.py"}, _context(snapshot)
    )
    assert ok_result.ok
    bad_result = preflight_action(
        snapshot, "read_file", {"path": "/etc/passwd"}, _context(snapshot)
    )
    assert not bad_result.ok and bad_result.code == "workspace_violation"


def test_failed_action_blocked_until_state_changes() -> None:
    snapshot = build_capability_snapshot(_tools())
    context = _context(snapshot)
    first = preflight_action(snapshot, "terminal", {"command": "run"}, context)
    assert first.ok and first.decision is not None
    context.ledger.record_failure(first.decision.semantic_fingerprint, "rev-1", "TEST_FAILURE")
    blocked = preflight_action(snapshot, "terminal", {"command": "run"}, context)
    assert not blocked.ok and blocked.code == "duplicate_failed_action"
    context.state_revision = "rev-2"
    assert preflight_action(snapshot, "terminal", {"command": "run"}, context).ok


def test_alternative_action_eligible_after_failure() -> None:
    snapshot = build_capability_snapshot(_tools())
    context = _context(snapshot)
    first = preflight_action(snapshot, "terminal", {"command": "run"}, context)
    assert first.ok and first.decision is not None
    context.ledger.record_failure(first.decision.semantic_fingerprint, "rev-1", "TEST_FAILURE")
    other = preflight_action(snapshot, "terminal", {"command": "run-other"}, context)
    assert other.ok


def test_success_resolves_failure_state() -> None:
    ledger = FailureLedger()
    revision = build_state_revision()
    entry = ledger.record_failure("semantic", revision, "TEST_FAILURE")
    assert ledger.is_blocked("semantic", revision.revision)
    ledger.record_success("semantic")
    assert not ledger.is_blocked("semantic", revision.revision)
    assert entry.semantic_fingerprint == "semantic"


def test_textual_tool_call_normalized_then_validated() -> None:
    snapshot = build_capability_snapshot(_tools())
    text = "<tool_call><function=terminal><parameter=command>run</parameter></function></tool_call>"
    assert parse_textual_tool_calls(text) == [("terminal", {"command": "run"})]
    recovered = recover_textual_tool_call(text, set(snapshot.names))
    assert recovered is not None
    result = preflight_action(
        snapshot, recovered.tool_name, recovered.arguments, _context(snapshot)
    )
    assert result.ok


def test_shell_alias_only_with_advertised_bash() -> None:
    snapshot = build_capability_snapshot(
        [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            }
        ]
    )
    result = preflight_action(snapshot, "shell", {"cmd": "ls"}, _context(snapshot))
    assert result.ok and result.compiled is not None
    assert result.compiled.external_name == "bash"
    assert json.loads(result.compiled.arguments_json) == {"command": "ls"}


def test_no_fuzzy_tool_guessing() -> None:
    snapshot = build_capability_snapshot(_tools())
    result = preflight_action(snapshot, "termnal", {"command": "x"}, _context(snapshot))
    assert not result.ok and result.code == "unknown_tool"


def test_alias_cannot_bypass_schema() -> None:
    snapshot = build_capability_snapshot(
        [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            }
        ]
    )
    legacy = normalize_legacy_call("shell", '{"cmd": 42}', set(snapshot.names))
    result = preflight_action(snapshot, legacy.tool_name, legacy.arguments, _context(snapshot))
    assert not result.ok and result.code == "schema_mismatch"


def test_local_file_compat_requires_advertised_exec() -> None:
    assert normalize_local_file_compat("read_file", {"path": "x"}, {"exec_command"}) is not None
    assert normalize_local_file_compat("read_file", {"path": "x"}, {"other"}) is None
    assert normalize_local_file_compat("read_mcp_resource", {"uri": "x"}, {"exec_command"}) is None


def test_policy_selects_finite_candidates_and_shadow_records() -> None:
    snapshot = build_capability_snapshot(_tools())
    calls = [
        {
            "id": "a",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command":"x"}'},
        }
    ]
    candidates = candidates_from_tool_calls(calls, snapshot)
    engine = PolicyEngine()
    decision = engine.decide(snapshot, candidates)
    assert decision is not None and decision.capability.external_name == "terminal"


def test_telemetry_counts_recovery() -> None:
    telemetry = AdapterTelemetry()
    normalize_legacy_call("shell", '{"cmd":"x"}', {"bash"}, telemetry=telemetry)
    assert telemetry.to_dict().get("tool_alias", 0) >= 1


def test_preflight_tool_call_shape() -> None:
    snapshot = build_capability_snapshot(_tools())
    call = {
        "id": "a",
        "type": "function",
        "function": {"name": "terminal", "arguments": '{"command":"x"}'},
    }
    assert preflight_tool_call(call, snapshot, _context(snapshot)).ok
