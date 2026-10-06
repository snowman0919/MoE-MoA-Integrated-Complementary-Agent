"""Focused Action Runtime tests: capability, resource, ledger, compat, convergence."""

from __future__ import annotations

import json

import pytest
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
    file_path_result = preflight_action(
        snapshot, "read_file", {"file_path": "/etc/passwd"}, _context(snapshot)
    )
    assert not file_path_result.ok
    assert file_path_result.code in {"workspace_violation", "schema_mismatch"}
    target_path_result = preflight_action(
        snapshot, "terminal", {"command": "x", "target_path": "/etc/passwd"}, _context(snapshot)
    )
    assert not target_path_result.ok
    assert target_path_result.code in {"workspace_violation", "schema_mismatch"}


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


def test_denied_tool_and_side_effect_rejected_with_fingerprint() -> None:
    from dgx_moa.actions import PreflightPolicy

    snapshot = build_capability_snapshot(_tools())
    denied = preflight_action(
        snapshot,
        "terminal",
        {"command": "x"},
        PreflightContext(
            snapshot=snapshot,
            authority=ResourceAuthority(workspace_roots=("/work",)),
            ledger=FailureLedger(),
            state_revision="rev-1",
            policy=PreflightPolicy(denied_tools=("terminal",)),
        ),
    )
    assert not denied.ok and denied.code == "permission_denied"
    assert denied.semantic_fingerprint
    capability = snapshot.capabilities[snapshot.names["terminal"]]
    blocked = preflight_action(
        snapshot,
        "terminal",
        {"command": "x"},
        PreflightContext(
            snapshot=snapshot,
            authority=ResourceAuthority(workspace_roots=("/work",)),
            ledger=FailureLedger(),
            state_revision="rev-1",
            policy=PreflightPolicy(denied_side_effects=(capability.side_effect_class,)),
        ),
    )
    assert not blocked.ok and blocked.code == "permission_denied"
    assert blocked.semantic_fingerprint == denied.semantic_fingerprint


def test_laya_endpoint_rejects_non_loopback() -> None:
    from dgx_moa.actions import LayaPolicyAdapter
    from dgx_moa.config import ActionRuntimeConfig

    adapter = LayaPolicyAdapter(endpoint="https://example.com/decide", enabled=True)
    assert adapter.choose(build_capability_snapshot(_tools()), []) is None
    with pytest.raises(ValueError, match="loopback"):
        ActionRuntimeConfig(laya_enabled=True, laya_endpoint="https://example.com/decide")
    allowed = ActionRuntimeConfig(laya_enabled=True, laya_endpoint="http://127.0.0.1:8080/decide")
    assert allowed.laya_endpoint == "http://127.0.0.1:8080/decide"


def test_shell_resource_paths_do_not_treat_git_refs_as_absolute_paths() -> None:
    from dgx_moa.actions.types import _shell_path_tokens

    assert _shell_path_tokens("git diff origin/master refs/heads/dev HEAD~1") == []
    assert _shell_path_tokens("git fetch https://github.com/example/repo.git") == []
    assert _shell_path_tokens("git -C /home/monad/repo diff origin/master") == ["/home/monad/repo"]
    assert _shell_path_tokens("cat /etc/passwd; cat '/tmp/data'; ls --cwd=/root") == [
        "/etc/passwd",
        "/tmp/data",
        "/root",
    ]


def test_null_device_redirections_are_not_workspace_file_access() -> None:
    from dgx_moa.actions.types import _shell_path_tokens

    for command in (
        "git diff origin/master 2>/dev/null",
        "command >/dev/null 2>&1",
        "command >> /dev/null",
        "command < /dev/null",
        'command >"/dev/null"',
        "command 2> '/dev/null'",
        "command &>/dev/null",
        "command >| /dev/null",
    ):
        assert _shell_path_tokens(command) == []
    for command in (
        "rm /dev/null",
        "cat /dev/null",
        "command >/dev/null-file",
        "command >/dev/null.",
        "command >/dev/null/child",
        "command >'/dev/null'other",
        "command << /dev/null",
    ):
        assert _shell_path_tokens(command)
    assert _shell_path_tokens("command 2>/dev/null >/etc/passwd") == ["/etc/passwd"]
    assert _shell_path_tokens("command >/dev/null; rm /dev/null") == ["/dev/null"]
    snapshot = build_capability_snapshot(_tools())
    context = _context(snapshot)
    assert preflight_action(snapshot, "terminal", {"command": "git status 2>/dev/null"}, context).ok
    assert not preflight_action(
        snapshot, "terminal", {"command": "git status >/etc/passwd"}, context
    ).ok


def test_attached_options_and_relative_traversal_remain_workspace_bounded() -> None:
    snapshot = build_capability_snapshot(_tools())
    for command in (
        "tar -C/etc -cf archive.tar passwd",
        "git -C/etc status",
        "cc -I/etc source.c",
        "cat ../etc/passwd",
        "cat subdir/../../etc/passwd",
        "command 2>/dev/null; tar -C/etc -cf archive.tar passwd",
    ):
        result = preflight_action(snapshot, "terminal", {"command": command}, _context(snapshot))
        assert not result.ok and result.code == "workspace_violation"
    for command in (
        "git -C/work status 2>/dev/null",
        "git diff custom-remote/master",
        "git diff refs/remotes/origin/master",
    ):
        assert preflight_action(snapshot, "terminal", {"command": command}, _context(snapshot)).ok


def test_null_redirect_does_not_change_path_ending_in_digits() -> None:
    from dgx_moa.actions.types import _shell_path_tokens

    snapshot = build_capability_snapshot(_tools())
    for command in ("cat /work2>/dev/null", "cat /work123>>/dev/null", "cat /work2</dev/null"):
        result = preflight_action(snapshot, "terminal", {"command": command}, _context(snapshot))
        assert not result.ok and result.code == "workspace_violation"
    assert _shell_path_tokens("cat /work/file2>/dev/null") == ["/work/file2"]
    assert _shell_path_tokens("cat /work/file2 2>/dev/null") == ["/work/file2"]
