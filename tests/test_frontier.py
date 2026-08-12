from __future__ import annotations

import asyncio
import errno
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from dgx_moa.frontier import (
    COLLABORATION_MODE_INSTRUCTIONS,
    COLLABORATION_SCHEMAS,
    CodexAppServerTurn,
    CodexOAuthCollaboration,
    CodexOAuthProvider,
    FrontierCollaborationResult,
    FrontierConfig,
    FrontierExecutorResult,
    FrontierResult,
    FrontierTask,
    bounded_external_evidence,
    build_frontier_task,
    classify_frontier_failure,
    codex_command,
    codex_usage,
    evaluate_frontier_candidate,
    frontier_eligible,
    load_frontier_config,
    normalize_openrouter_tool_calls,
    openrouter_compatible_schema,
    openrouter_response_schema,
    profile_lock,
    profile_status,
    record_frontier_run,
    run_codex_app_server,
    run_codex_exec,
    sanitize_executor_tool_paths,
    select_frontier_profile,
    validate_isolated_worktree,
    validate_profile_name,
    validate_scope,
)
from dgx_moa.state import Phase, SessionState
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_codex_exec_transports_large_prompt_over_stdin(tmp_path: Path) -> None:
    prompt = "x" * 300_000
    command = [
        sys.executable,
        "-c",
        "import sys; data=sys.stdin.read(); print(len(data)); print('stderr-ok', file=sys.stderr)",
    ]

    result = await run_codex_exec(
        command,
        prompt=prompt,
        cwd=tmp_path,
        environment=dict(os.environ),
        timeout=10,
    )

    assert result.stdout.strip() == str(len(prompt))
    assert result.stderr.strip() == "stderr-ok"
    assert prompt not in result.args


@pytest.mark.asyncio
async def test_codex_app_server_uses_ephemeral_read_only_turn(tmp_path: Path) -> None:
    fake_server = """
import json
import sys
def send(value):
    print(json.dumps(value), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    if message.get("id") == 1:
        send({"id": 1, "result": {"userAgent": "fake"}})
    elif message.get("id") == 2:
        params = message["params"]
        assert params["ephemeral"] is True
        assert params["approvalPolicy"] == "never"
        assert params["sandbox"] == "read-only"
        send({"id": 2, "result": {"thread": {"id": "thread-1"}}})
    elif message.get("id") == 3:
        params = message["params"]
        assert params["sandboxPolicy"]["type"] == "readOnly"
        assert params["input"][0]["text"] == "private prompt"
        send({"id": 3, "result": {"turn": {"id": "turn-1"}}})
        send({
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "tokenUsage": {"last": {"inputTokens": 7, "outputTokens": 3}},
            },
        })
        send({
            "method": "item/completed",
            "params": {"item": {"type": "reasoning", "content": ["discard"]}},
        })
        send({
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": "{\\\"answer\\\":\\\"ok\\\"}",
                }
            },
        })
        send({
            "method": "turn/completed",
            "params": {"turn": {"id": "turn-1", "status": "completed"}},
        })
"""
    command = [sys.executable, "-u", "-c", fake_server]

    result = await run_codex_app_server(
        command,
        prompt="private prompt",
        output_schema={"type": "object"},
        model="gpt-5.6-sol",
        effort="high",
        cwd=tmp_path,
        environment=dict(os.environ),
        timeout=10,
    )

    assert result.output == {"answer": "ok"}
    assert (result.prompt_tokens, result.completion_tokens) == (7, 3)
    assert "private prompt" not in command


@pytest.mark.asyncio
async def test_codex_app_server_normalizes_closed_stdin(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-c",
        "import os, time; os.close(0); os.close(1); time.sleep(0.1)",
    ]

    with pytest.raises(RuntimeError, match="^FRONTIER_APP_SERVER_UNAVAILABLE$"):
        await run_codex_app_server(
            command,
            prompt="bounded",
            output_schema={"type": "object"},
            model="gpt-5.6-sol",
            effort="high",
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout=10,
        )


@pytest.mark.asyncio
async def test_codex_app_server_resumes_and_compacts_persistent_thread(
    tmp_path: Path,
) -> None:
    fake_server = """
import json
import sys
def send(value):
    print(json.dumps(value), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if message.get("id") == 1:
        send({"id": 1, "result": {"userAgent": "fake"}})
    elif method == "thread/resume":
        assert message["params"]["threadId"] == "thread-existing"
        assert "ephemeral" not in message["params"]
        send({"id": 2, "result": {"thread": {"id": "thread-existing"}}})
    elif method == "thread/compact/start":
        send({"id": 3, "result": {}})
        send({"method": "turn/started", "params": {"turn": {"id": "compact-1"}}})
        send({
            "method": "turn/completed",
            "params": {"turn": {"id": "compact-1", "status": "completed"}},
        })
    elif method == "turn/start":
        send({"id": 4, "result": {"turn": {"id": "turn-2"}}})
        send({
            "method": "item/completed",
            "params": {"item": {"type": "agentMessage", "text": "{\\"answer\\":\\"ok\\"}"}},
        })
        send({
            "method": "turn/completed",
            "params": {"turn": {"id": "turn-2", "status": "completed"}},
        })
"""

    result = await run_codex_app_server(
        [sys.executable, "-u", "-c", fake_server],
        prompt="bounded follow-up",
        output_schema={"type": "object"},
        model="gpt-5.6-sol",
        effort="high",
        cwd=tmp_path,
        environment=dict(os.environ),
        timeout=10,
        thread_id="thread-existing",
        persistent=True,
        compact_before_turn=True,
    )

    assert result.output == {"answer": "ok"}
    assert result.thread_id == "thread-existing"
    assert result.compacted is True


@pytest.mark.asyncio
async def test_codex_app_server_interrupts_cancelled_turn(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    interrupted = tmp_path / "interrupted"
    fake_server = f"""
import json
import pathlib
import sys
def send(value):
    print(json.dumps(value), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if message.get("id") == 1:
        send({{"id": 1, "result": {{"userAgent": "fake"}}}})
    elif method == "thread/start":
        send({{"id": 2, "result": {{"thread": {{"id": "thread-cancel"}}}}}})
    elif method == "turn/start":
        send({{"id": 3, "result": {{"turn": {{"id": "turn-cancel"}}}}}})
        pathlib.Path({str(ready)!r}).touch()
    elif method == "turn/interrupt":
        assert message["params"] == {{"threadId": "thread-cancel", "turnId": "turn-cancel"}}
        pathlib.Path({str(interrupted)!r}).touch()
        send({{"id": 5, "result": {{}}}})
"""
    task = asyncio.create_task(
        run_codex_app_server(
            [sys.executable, "-u", "-c", fake_server],
            prompt="cancel me",
            output_schema={"type": "object"},
            model="gpt-5.6-sol",
            effort="high",
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout=10,
            persistent=True,
        )
    )
    for _ in range(100):
        if ready.is_file():
            break
        await asyncio.sleep(0.01)
    assert ready.is_file()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert interrupted.is_file()


@pytest.mark.asyncio
async def test_app_server_unavailable_falls_back_once_to_stdin_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"app_server": 0, "exec": 0}

    async def unavailable(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        calls["app_server"] += 1
        raise RuntimeError("FRONTIER_APP_SERVER_UNAVAILABLE")

    async def exec_fallback(command, **_kwargs):  # type: ignore[no-untyped-def]
        calls["exec"] += 1
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "recommended_architecture": "bounded",
                    "design_decisions": [],
                    "tradeoffs": [],
                    "failure_modes": [],
                    "implementation_sequence": [],
                    "review_questions": [],
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_app_server", unavailable)
    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", exec_fallback)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            protocol="codex-app-server-jsonrpc",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    result = await runner.collaborate("architecture", {"objective": "bounded"}, "request")

    assert calls == {"app_server": 1, "exec": 1}
    assert result.transport == "codex_exec_fallback"


@pytest.mark.asyncio
async def test_app_server_auth_failure_does_not_use_cli_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def auth_failure(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("FRONTIER_AUTH_ERROR")

    async def unexpected_exec(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        pytest.fail("CLI fallback must not retry an App Server auth failure")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_app_server", auth_failure)
    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", unexpected_exec)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            protocol="codex-app-server-jsonrpc",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="FRONTIER_AUTH_ERROR"):
        await runner.collaborate("architecture", {"objective": "bounded"}, "request")


@pytest.mark.asyncio
async def test_collaboration_persists_bounded_daemon_thread_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_app_server(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"command": command, **kwargs})
        return CodexAppServerTurn(
            output={
                "recommended_architecture": "bounded",
                "design_decisions": [],
                "tradeoffs": [],
                "failure_modes": [],
                "implementation_sequence": [],
                "review_questions": [],
            },
            prompt_tokens=7,
            completion_tokens=3,
            thread_id=kwargs.get("thread_id") or "thread-persisted",
            compacted=bool(kwargs["compact_before_turn"]),
        )

    monkeypatch.setattr("dgx_moa.frontier.run_codex_app_server", fake_app_server)
    config = FrontierConfig(
        enabled=True,
        protocol="codex-app-server-jsonrpc",
        collaboration_retries=0,
        app_server_compact_after_turns=1,
        app_server_max_threads=1,
    )
    run_dir = tmp_path / "run"
    first = CodexOAuthCollaboration(config, run_dir, tmp_path)
    await first.collaborate("architecture", {"objective": "one"}, "task:frontier:1")

    restarted = CodexOAuthCollaboration(config, run_dir, tmp_path)
    result = await restarted.collaborate("architecture", {"objective": "two"}, "task:frontier:2")

    assert result.transport == "codex_app_server"
    assert calls[0]["command"] == ["codex", "app-server", "proxy"]
    assert calls[0]["thread_id"] is None
    assert calls[1]["thread_id"] == "thread-persisted"
    assert calls[1]["compact_before_turn"] is True
    await restarted.collaborate("architecture", {"objective": "other"}, "other-task:frontier:1")
    assert calls[2]["thread_id"] is None
    state_file = run_dir / "frontier-app-server-sessions.json"
    saved = state_file.read_text()
    assert "task" not in saved
    threads = json.loads(saved)["threads"]
    assert len(threads) == 1
    assert threads.popitem()[1]["turns"] == 1
    assert state_file.stat().st_mode & 0o777 == 0o600
    state_file.chmod(0o644)
    with pytest.raises(ValueError, match="insecure Frontier App Server session state"):
        CodexOAuthCollaboration(config, run_dir, tmp_path)


def test_frontier_profile_and_selection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        FrontierConfig(protocol="unbounded")  # type: ignore[arg-type]
    assert validate_profile_name("primary") == "primary"
    with pytest.raises(ValueError):
        validate_profile_name("../secret")
    assert profile_status("primary", tmp_path)["authenticated"] == "no"
    assert str(tmp_path) not in profile_status("primary", tmp_path).values()
    assert (
        select_frontier_profile(explicit_profile="secondary", primary_profile="primary")
        == "secondary"
    )
    assert select_frontier_profile(explicit_profile=None, primary_profile="primary") == "primary"
    assert (
        select_frontier_profile(
            explicit_profile=None,
            primary_profile="primary",
            primary_auth_failed=True,
            allow_failover=False,
            failover_profile="secondary",
        )
        is None
    )


def test_frontier_lock_and_eligibility(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = SessionState(session_id="frontier", phase=Phase.REPLANNING)
    assert frontier_eligible(state, {"validated_replan_failed": True}) == (
        True,
        "validated_replan_failed",
    )
    assert (
        frontier_eligible(state, {"frontier_requested": True, "frontier_invocations": 1})[0]
        is False
    )
    assert classify_frontier_failure("You've hit your usage limit") == "FRONTIER_USAGE_LIMIT"
    assert classify_frontier_failure("HTTP 429") == "FRONTIER_RATE_LIMIT"
    assert classify_frontier_failure("503 unavailable") == "FRONTIER_PROVIDER_UNAVAILABLE"
    usage_event = '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}'
    assert codex_usage(usage_event) == (
        7,
        3,
    )

    def take_second_lock() -> None:
        with profile_lock("primary", tmp_path):
            pass

    with profile_lock("primary", tmp_path), pytest.raises(RuntimeError, match="already active"):
        take_second_lock()


def test_frontier_task_scope_and_candidate_gate() -> None:
    state = SessionState(session_id="frontier", objective="fix", approved_scope=["gateway/src"])
    task = build_frontier_task(state, {"task_id": "one", "base_commit": "abc"})
    assert json.loads(task.model_dump_json())["schema_version"] == "frontier-task-v1"
    validate_scope(["gateway/src/dgx_moa/frontier.py"], task.allowed_paths)
    with pytest.raises(ValueError, match="FRONTIER_SCOPE_VIOLATION"):
        validate_scope([".env"], task.allowed_paths)
    result = FrontierResult(
        status="completed", summary="done", root_cause="x", recommended_next_action="review"
    )
    evaluation = evaluate_frontier_candidate(
        result,
        changed_paths=["gateway/src/dgx_moa/frontier.py"],
        task=task,
        focused_tests_passed=True,
        benchmark_passed=True,
        secret_scan_passed=True,
        local_review_passed=True,
    )
    assert evaluation == {
        "accepted_for_human_review": True,
        "automatic_merge": False,
        "automatic_deploy": False,
        "human_approval_required": True,
        "reason": "all deterministic gates passed",
    }


def test_frontier_config(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "frontier.yaml"
    config.write_text("model: gpt-5.6-sol\nreasoning_effort: high\n")
    assert load_frontier_config(config).model == "gpt-5.6-sol"
    command = codex_command("primary", config, tmp_path, "gpt-5.6-sol", "high", config)
    assert 'model_reasoning_effort="high"' in command
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert "--ask-for-approval" not in command
    assert CodexOAuthProvider("primary", tmp_path).environment()["CODEX_HOME"] == str(
        tmp_path / "primary"
    )


def test_frontier_code_review_keeps_bounded_tool_executions() -> None:
    evidence, _ = bounded_external_evidence(
        {
            "tool_executions": [{"tool_name": "apply_patch", "exit_code": 0}],
            "private_payload": "drop-me",
        },
        FrontierConfig(),
    )

    assert evidence == {"tool_executions": [{"tool_name": "apply_patch", "exit_code": 0}]}
    assert "CODEX_HOME" not in CodexOAuthProvider("default").environment()


def test_remote_executor_tool_paths_stay_in_client_workspace() -> None:
    message = FrontierExecutorResult.model_validate(
        {
            "role": "assistant",
            "content": None,
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "absolute",
                    "type": "function",
                    "function": {
                        "name": "exec_command",
                        "arguments": json.dumps(
                            {"cmd": "python -m unittest", "workdir": "/gateway/production"}
                        ),
                    },
                },
                {
                    "id": "relative",
                    "type": "function",
                    "function": {
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": "pwd", "cwd": "tests"}),
                    },
                },
                {
                    "id": "patch",
                    "type": "function",
                    "function": {
                        "name": "patch",
                        "arguments": json.dumps(
                            {
                                "patch": (
                                    "*** Begin Patch\n"
                                    "*** Update File: /gateway/production/src/app.py\n"
                                    "@@\n-old\n+new\n"
                                    "*** End Patch\n"
                                )
                            }
                        ),
                    },
                },
            ],
        }
    )

    sanitized, count = sanitize_executor_tool_paths(message, "/gateway/production")

    assert count == 2
    assert json.loads(sanitized.tool_calls[0].function.arguments) == {"cmd": "python -m unittest"}
    assert json.loads(sanitized.tool_calls[1].function.arguments)["cwd"] == "tests"
    patch = json.loads(sanitized.tool_calls[2].function.arguments)["patch"]
    assert "*** Update File: src/app.py" in patch
    assert "/gateway/production" not in patch


def test_openrouter_schema_removes_unsupported_numeric_constraints() -> None:
    schema = openrouter_response_schema(COLLABORATION_SCHEMAS["code_review"])
    encoded = json.dumps(schema)

    assert '"minimum"' not in encoded
    assert '"maximum"' not in encoded
    assert '"confidence"' in encoded


def test_openrouter_compatible_schema_preserves_structure() -> None:
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "schema": {
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 0}},
            }
        },
    }

    compatible = openrouter_compatible_schema(response_format)

    assert compatible["type"] == "json_schema"
    assert compatible["json_schema"]["schema"]["properties"]["count"] == {"type": "integer"}


def test_openrouter_tool_calls_drop_provider_metadata() -> None:
    calls = normalize_openrouter_tool_calls(
        [
            {
                "index": 0,
                "id": "call-1",
                "type": "function",
                "function": {"name": "write_file", "arguments": {"path": "x", "content": "y"}},
            }
        ]
    )

    assert calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "write_file",
                "arguments": '{"path":"x","content":"y"}',
            },
        }
    ]


def test_executor_tool_calls_repair_only_known_freeform_arguments() -> None:
    patch = "*** Begin Patch\n*** Add File: result.txt\n+ok\n*** End Patch"
    calls = normalize_openrouter_tool_calls(
        [
            {
                "id": "patch",
                "type": "function",
                "function": {"name": "apply_patch", "arguments": patch},
            },
            {
                "id": "command",
                "type": "function",
                "function": {
                    "name": "exec_command",
                    "arguments": "python -m unittest",
                },
            },
            {
                "id": "unknown",
                "type": "function",
                "function": {"name": "unknown_tool", "arguments": "not-json"},
            },
        ]
    )

    assert json.loads(calls[0]["function"]["arguments"]) == {"input": patch}
    assert json.loads(calls[1]["function"]["arguments"]) == {"cmd": "python -m unittest"}
    assert calls[2]["function"]["arguments"] == "not-json"
    with pytest.raises(ValidationError):
        FrontierExecutorResult.model_validate(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [calls[2]],
                "finish_reason": "tool_calls",
            }
        )


@pytest.mark.asyncio
async def test_remote_executor_repairs_known_freeform_tool_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch = "*** Begin Patch\n*** Add File: result.txt\n+ok\n*** End Patch"
    runner = CodexOAuthCollaboration(FrontierConfig(), tmp_path / "run", tmp_path)
    collaboration = FrontierCollaborationResult(
        mode="executor",
        output={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "patch",
                    "type": "function",
                    "function": {"name": "apply_patch", "arguments": patch},
                }
            ],
            "finish_reason": "tool_calls",
        },
        latency_ms=1,
        transmitted_categories=["executor_request"],
        profile="primary",
    )

    async def fake_run(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return collaboration

    monkeypatch.setattr(runner, "_run", fake_run)

    result = await runner.execute({"_client_workspace_path": str(tmp_path)}, "request")

    call = result["choices"][0]["message"]["tool_calls"][0]
    assert json.loads(call["function"]["arguments"]) == {"input": patch}
    assert result["choices"][0]["finish_reason"] == "tool_calls"


@pytest.mark.asyncio
async def test_remote_executor_recovers_nested_assistant_tool_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CodexOAuthCollaboration(FrontierConfig(), tmp_path / "run", tmp_path)
    collaboration = FrontierCollaborationResult(
        mode="executor",
        output={
            "role": "assistant",
            "content": json.dumps(
                {
                    "role": "assistant",
                    "content": "Inspecting the repository.",
                    "tool_calls": [
                        {
                            "id": "inspect",
                            "type": "function",
                            "function": {
                                "name": "terminal",
                                "arguments": {"command": "pwd"},
                            },
                        }
                    ],
                }
            ),
            "tool_calls": [],
            "finish_reason": "stop",
        },
        latency_ms=1,
        transmitted_categories=["executor_request"],
        profile="primary",
    )

    async def fake_run(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return collaboration

    monkeypatch.setattr(runner, "_run", fake_run)

    result = await runner.execute({"_client_workspace_path": str(tmp_path)}, "request")

    choice = result["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] == "Inspecting the repository."
    assert choice["message"]["tool_calls"][0]["function"] == {
        "name": "terminal",
        "arguments": '{"command":"pwd"}',
    }


@pytest.mark.asyncio
async def test_codex_oauth_executor_repairs_freeform_before_schema_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch = "*** Begin Patch\n*** Add File: result.txt\n+ok\n*** End Patch"

    async def fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "patch",
                            "type": "function",
                            "function": {
                                "name": "apply_patch",
                                "arguments": patch,
                            },
                        }
                    ],
                    "finish_reason": "tool_calls",
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(enabled=True, collaboration_retries=0),
        tmp_path / "run",
        tmp_path,
    )

    result = await runner._run("executor", {"executor_request": {}}, "correlation")

    arguments = result.output["tool_calls"][0]["function"]["arguments"]
    assert json.loads(arguments) == {"input": patch}


@pytest.mark.asyncio
async def test_codex_oauth_executor_rejects_unknown_freeform_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "unknown",
                            "type": "function",
                            "function": {
                                "name": "unknown_tool",
                                "arguments": "not-json",
                            },
                        }
                    ],
                    "finish_reason": "tool_calls",
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(enabled=True, collaboration_retries=0),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(ValidationError):
        await runner._run("executor", {"executor_request": {}}, "correlation")


def test_frontier_review_requires_finite_arithmetic_parameters() -> None:
    prompt = COLLABORATION_MODE_INSTRUCTIONS["code_review"]

    assert "even when supplied tests omit those cases" in prompt
    assert "timestamp, duration, window, size, or capacity arithmetic" in prompt
    assert "allow_nan=False" in prompt
    assert "expected_version" in prompt
    assert "fully merged object" in prompt
    assert "when missing_tests is non-empty, use revise" in prompt


def test_codex_oauth_environment_excludes_gateway_secrets(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DGX_MOA_API_KEYS", '{"client":"secret"}')
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    environment = CodexOAuthProvider("primary", tmp_path).environment()

    assert environment["PATH"] == "/usr/bin"
    assert environment["CODEX_HOME"] == str(tmp_path / "primary")
    assert "DGX_MOA_API_KEYS" not in environment
    assert "OPENAI_API_KEY" not in environment


@pytest.mark.parametrize(
    ("mode", "output"),
    [
        (
            "architecture",
            {
                "recommended_architecture": "bounded",
                "design_decisions": [],
                "tradeoffs": [],
                "failure_modes": [],
                "implementation_sequence": [],
                "review_questions": [],
            },
        ),
        (
            "code_review",
            {
                "verdict": "approve",
                "critical": [],
                "important": [],
                "suggestions": [],
                "missing_tests": [],
                "confidence": 0.9,
            },
        ),
        (
            "disagreement",
            {
                "preferred_position": "evidence",
                "evidence": [],
                "rejected_assumptions": [],
                "required_follow_up": [],
                "confidence": 0.8,
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_codex_oauth_collaboration_modes_are_read_only_and_redacted(
    tmp_path, monkeypatch: pytest.MonkeyPatch, mode: str, output: dict[str, object]
) -> None:  # type: ignore[no-untyped-def]
    observed: dict[str, object] = {}

    async def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        observed["command"] = command
        observed["task"] = kwargs["prompt"]
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(json.dumps(output))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed","usage":{"input_tokens":11,"output_tokens":5}}',
            stderr="",
        )

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            model="gpt-5.6-sol",
            primary_profile="default",
            collaboration_retries=0,
            input_cost_per_million=1.0,
            output_cost_per_million=2.0,
        ),
        tmp_path / "run",
        tmp_path,
    )
    result = await runner._run(  # type: ignore[arg-type]
        mode,
        {"objective": "review", "api_key": "sk-secret-value"},
        "correlation",
    )

    command = observed["command"]
    assert isinstance(command, list)
    assert command[-1] == "-"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "sk-secret-value" not in str(observed["task"])
    if mode == "executor":
        assert "Never invoke a tool name as a shell command" in str(observed["task"])
    if mode == "code_review":
        assert "Do not turn optional hardening" in str(observed["task"])
        assert "Use approve when the stated contract is met" in str(observed["task"])
        assert "NaN, and both infinities" in str(observed["task"])
    assert COLLABORATION_SCHEMAS[mode].model_validate(result.output)
    assert result.total_tokens == 16
    assert result.cost_usd == 0.000021


@pytest.mark.asyncio
async def test_codex_oauth_timeout_opens_circuit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    async def timeout(_command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["environment"]["CODEX_HOME"]).name)
        raise RuntimeError("FRONTIER_PROVIDER_TIMEOUT")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", timeout)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
            circuit_failure_limit=1,
            circuit_cooldown_seconds=300,
        ),
        tmp_path / "run",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="FRONTIER_PROVIDER_TIMEOUT"):
        await runner._run("architecture", {"objective": "x"}, "one")
    with pytest.raises(RuntimeError, match="FRONTIER_CIRCUIT_OPEN"):
        await runner._run("architecture", {"objective": "x"}, "two")
    assert profiles == ["primary"]


@pytest.mark.asyncio
async def test_codex_oauth_e2big_is_typed_and_not_retried(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    attempts = 0

    async def e2big(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        raise OSError(errno.E2BIG, "argument list too long")

    monkeypatch.setattr("dgx_moa.frontier.asyncio.create_subprocess_exec", e2big)
    runner = CodexOAuthCollaboration(
        FrontierConfig(enabled=True, collaboration_retries=3),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="FRONTIER_INPUT_TRANSPORT_TOO_LARGE"):
        await runner._run("architecture", {"objective": "x" * 20_000}, "e2big")

    assert attempts == 1


@pytest.mark.parametrize("primary_failure", ["not logged in", "usage limit", "rate limit"])
@pytest.mark.asyncio
async def test_codex_oauth_falls_back_to_secondary_profile(
    tmp_path, monkeypatch: pytest.MonkeyPatch, primary_failure: str
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    async def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profile = Path(kwargs["environment"]["CODEX_HOME"]).name
        profiles.append(profile)
        if profile == "primary":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=primary_failure)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "recommended_architecture": "secondary",
                    "design_decisions": [],
                    "tradeoffs": [],
                    "failure_modes": [],
                    "implementation_sequence": [],
                    "review_questions": [],
                }
            )
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}',
            stderr="",
        )

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    result = await runner._run("architecture", {"objective": "x"}, "fallback")

    assert profiles == ["primary", "secondary"]
    assert result.profile == "secondary"
    assert result.total_tokens == 10


@pytest.mark.asyncio
async def test_codex_oauth_uses_global_default_as_tertiary_profile(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    async def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profile = (
            Path(kwargs["environment"]["CODEX_HOME"]).name
            if "CODEX_HOME" in kwargs["environment"]
            else "default"
        )
        profiles.append(profile)
        if profile != "default":
            failure = "usage limit" if profile == "primary" else "token_invalidated"
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=failure)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "recommended_architecture": "default profile",
                    "design_decisions": [],
                    "tradeoffs": [],
                    "failure_modes": [],
                    "implementation_sequence": [],
                    "review_questions": [],
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            tertiary_profile="default",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    result = await runner._run("architecture", {"objective": "x"}, "tertiary")

    assert profiles == ["primary", "secondary", "default"]
    assert result.profile == "default"


@pytest.mark.asyncio
async def test_executor_uses_paid_fallback_only_after_oauth_profiles_fail(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []
    requests: list[dict[str, object]] = []
    key_path = tmp_path / "openrouter_api"
    key_path.write_text("synthetic-openrouter-key")
    key_path.chmod(0o600)

    async def oauth_context_failure(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["environment"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="context window exceeded")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "완료했습니다.",
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            }

    class FakeClient:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args) -> None:  # type: ignore[no-untyped-def]
            return None

        def post(self, _url, **kwargs):  # type: ignore[no-untyped-def]
            requests.append(kwargs)
            return FakeResponse()

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", oauth_context_failure)
    monkeypatch.setattr("dgx_moa.frontier.httpx.Client", FakeClient)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
            openrouter_fallback_enabled=True,
            openrouter_api_key_file=key_path,
        ),
        tmp_path / "run",
        tmp_path,
    )

    result = await runner.execute(
        {
            "messages": [{"role": "user", "content": "한국어로 답해"}],
            "tools": [],
            "parallel_tool_calls": True,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": {
                        "type": "object",
                        "properties": {"confidence": {"type": "number", "minimum": 0}},
                    },
                },
            },
            "stream": True,
        },
        "busy-request",
    )

    assert profiles == ["primary", "secondary"]
    assert result["choices"][0]["message"]["content"] == "완료했습니다."
    assert result["provider_provenance"]["provider"].startswith("openrouter:")
    assert result["provider_provenance"]["cost_usd"] == pytest.approx(0.001)
    assert len(requests) == 1
    sent = requests[0]
    assert sent["headers"]["Authorization"] == "Bearer synthetic-openrouter-key"
    assert sent["json"]["model"] == "anthropic/claude-opus-5"
    assert sent["json"]["reasoning"] == {"effort": "high", "exclude": True}
    assert "parallel_tool_calls" not in sent["json"]
    assert "minimum" not in json.dumps(sent["json"]["response_format"])
    assert "synthetic-openrouter-key" not in json.dumps(sent["json"])


@pytest.mark.asyncio
async def test_executor_preserves_oauth_failure_without_openrouter_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    async def oauth_context_failure(command, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="context window exceeded")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", oauth_context_failure)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            collaboration_retries=0,
            openrouter_fallback_enabled=True,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="FRONTIER_CONTEXT_LIMIT"):
        await runner.execute({"messages": [{"role": "user", "content": "x"}]}, "request")


@pytest.mark.asyncio
async def test_direct_openrouter_collaboration_fails_closed_when_disabled(tmp_path) -> None:
    runner = CodexOAuthCollaboration(FrontierConfig(), tmp_path / "run", tmp_path)

    with pytest.raises(RuntimeError, match="FRONTIER_PROVIDER_UNAVAILABLE"):
        await runner.collaborate_openrouter(
            "disagreement", {"objective": "adjudicate"}, "frontier-b-disabled"
        )


@pytest.mark.asyncio
async def test_required_review_uses_paid_fallback_while_oauth_circuit_is_open(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    key_path = tmp_path / "openrouter_api"
    key_path.write_text("synthetic-openrouter-key")
    requests = 0
    sent_requests: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, valid: bool) -> None:
            self.valid = valid

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                json.dumps(
                                    {
                                        "verdict": "approve",
                                        "critical": [],
                                        "important": [],
                                        "suggestions": [],
                                        "missing_tests": [],
                                        "confidence": 0.9,
                                    }
                                )
                                if self.valid
                                else "{}"
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            }

    class FakeClient:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args) -> None:  # type: ignore[no-untyped-def]
            return None

        def post(self, _url, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal requests
            requests += 1
            sent_requests.append(kwargs)
            return FakeResponse(valid=requests > 1)

    monkeypatch.setattr("dgx_moa.frontier.httpx.Client", FakeClient)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            openrouter_fallback_enabled=True,
            openrouter_api_key_file=key_path,
        ),
        tmp_path / "run",
        tmp_path,
    )
    runner.opened_at = time.monotonic()

    result = await runner._run(
        "code_review",
        {
            "bounded_diff": "bounded",
            "_paid_fallback_required": True,
        },
        "required-review",
    )

    assert result.profile == "openrouter:anthropic/claude-opus-5"
    assert result.output["verdict"] == "approve"
    assert requests == 2
    assert all("temperature" not in request["json"] for request in sent_requests)


@pytest.mark.parametrize(
    ("primary_failure", "failure_class"),
    [
        ("connection refused", "FRONTIER_PROVIDER_UNAVAILABLE"),
        ("malformed response", "FRONTIER_PROTOCOL_ERROR"),
    ],
)
@pytest.mark.asyncio
async def test_codex_oauth_does_not_fail_over_unapproved_failures(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    primary_failure: str,
    failure_class: str,
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    async def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["environment"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=primary_failure)

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match=failure_class):
        await runner._run("architecture", {"objective": "x"}, "no-fallback")

    assert profiles == ["primary"]


@pytest.mark.asyncio
async def test_codex_oauth_does_not_fail_over_validation_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    profiles: list[str] = []

    async def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        profiles.append(Path(kwargs["environment"]["CODEX_HOME"]).name)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text("{}")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("dgx_moa.frontier.run_codex_exec", fake_run)
    runner = CodexOAuthCollaboration(
        FrontierConfig(
            enabled=True,
            primary_profile="primary",
            secondary_profile="secondary",
            allow_profile_failover=True,
            profile_root=tmp_path / "profiles",
            collaboration_retries=0,
        ),
        tmp_path / "run",
        tmp_path,
    )

    with pytest.raises(ValueError):
        await runner._run("architecture", {"objective": "x"}, "invalid-result")

    assert profiles == ["primary"]


def test_frontier_output_schema_uses_strict_property_types() -> None:
    schema = json.loads((Path(__file__).parents[1] / "schemas/frontier-result-v1.json").read_text())
    assert schema["properties"]["schema_version"] == {
        "type": "string",
        "const": "frontier-result-v1",
    }
    assert schema["properties"]["status"]["type"] == "string"
    assert schema["properties"]["changes"]["items"]["required"] == ["path", "purpose"]
    assert schema["properties"]["validation"]["items"]["required"] == [
        "command",
        "exit_code",
        "summary",
    ]


def test_frontier_rejects_production_worktree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    task = FrontierTask(
        task_id="one",
        objective="x",
        repository_identity={"workspace_path": str(tmp_path)},
        base_commit="abc",
        allowed_paths=["gateway"],
        acceptance_criteria=[],
    )
    with pytest.raises(ValueError, match="must not be production"):
        validate_isolated_worktree(task, tmp_path)


def test_frontier_rejects_immutable_evaluator_change() -> None:
    task = FrontierTask(
        task_id="one",
        objective="x",
        base_commit="abc",
        allowed_paths=["data/benchmarks"],
        acceptance_criteria=[],
    )
    result = FrontierResult(
        status="completed", summary="done", root_cause="x", recommended_next_action="review"
    )
    with pytest.raises(ValueError, match="immutable baseline"):
        evaluate_frontier_candidate(
            result,
            changed_paths=["data/benchmarks/mvp-baseline.json"],
            task=task,
            focused_tests_passed=True,
            benchmark_passed=True,
            secret_scan_passed=True,
            local_review_passed=True,
        )


def test_frontier_run_record_excludes_credentials(tmp_path) -> None:  # type: ignore[no-untyped-def]
    task = FrontierTask(
        task_id="record",
        objective="x",
        repository_identity={"workspace_path": "/repo"},
        base_commit="abc",
        allowed_paths=[],
        acceptance_criteria=[],
    )
    path = record_frontier_run(
        tmp_path,
        task,
        profile="secondary",
        model="gpt-5.6-sol",
        reasoning_effort="high",
        result=FrontierResult(
            status="blocked", summary="x", root_cause="x", recommended_next_action="local"
        ),
        failure_class="FRONTIER_VALIDATION_FAILURE",
    )
    assert "auth" not in path.read_text().lower()


def test_frontier_accepts_registered_isolated_worktree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    production = tmp_path / "production"
    worktree = tmp_path / "frontier"
    production.mkdir()
    subprocess.run(["git", "init", "-q", str(production)], check=True)
    (production / "README.md").write_text("fixture\n")
    subprocess.run(["git", "-C", str(production), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(production),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(production), "worktree", "add", "-qb", "frontier/test", str(worktree)],
        check=True,
    )
    task = FrontierTask(
        task_id="one",
        objective="x",
        repository_identity={"workspace_path": str(production)},
        base_commit="abc",
        allowed_paths=["gateway"],
        acceptance_criteria=[],
    )
    validate_isolated_worktree(task, worktree)
