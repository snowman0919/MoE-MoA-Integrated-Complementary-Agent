#!/usr/bin/env python3
"""Run one bounded OpenAI-compatible tool loop inside an isolated workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 file in the workspace.",
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
            "name": "write_file",
            "description": "Replace a UTF-8 file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Run a shell command in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


def workspace_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path escapes workspace")
    return path


def execute_tool(root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        if name == "read_file":
            output = workspace_path(root, str(arguments["path"])).read_text()[:65_536]
            result = {"output": output, "exit_code": 0}
        elif name == "write_file":
            path = workspace_path(root, str(arguments["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(arguments["content"])
            path.write_text(content)
            result = {"bytes_written": len(content.encode()), "exit_code": 0}
        elif name == "terminal":
            command = str(arguments["command"])
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {"DGX_MOA_API_KEY", "DGX_MOA_OPENCODE_KEY"}
            }
            # ponytail: shell stays inside the locked Docker harness; replace with
            # argv allowlisting only if a broader or externally supplied task set needs it.
            run = subprocess.run(
                command,
                cwd=root,
                env=environment,
                shell=True,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            result = {
                "output": (run.stdout + run.stderr)[:65_536],
                "exit_code": run.returncode,
            }
        else:
            raise ValueError(f"unknown tool: {name}")
    except (KeyError, OSError, subprocess.SubprocessError, ValueError) as error:
        result = {"error": f"{type(error).__name__}: {error}", "exit_code": 1}
    result["duration_seconds"] = round(time.monotonic() - started, 6)
    return result


def completion(
    gateway: str,
    key: str,
    session_id: str,
    workspace: Path,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": "dgx-moa",
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "stream": False,
        }
    ).encode()
    request = urllib.request.Request(
        gateway.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
            "X-Runtime-Channel": "dev",
            "X-Trace-Origin": "validation",
            "X-Task-ID": session_id,
            "X-Workspace-Path": str(workspace),
            "X-Workspace-ID": session_id,
            "X-Repository-Branch": "main",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)


def run(args: argparse.Namespace) -> int:
    root = args.workspace.resolve()
    key = os.environ.get("DGX_MOA_API_KEY")
    if not key:
        raise RuntimeError("DGX_MOA_API_KEY is required")
    messages: list[dict[str, Any]] = [{"role": "user", "content": args.prompt}]
    previous_tools_at: float | None = None
    started = time.monotonic()
    for turn in range(1, args.max_turns + 1):
        request_started = time.monotonic()
        try:
            response = completion(args.gateway, key, args.session_id, root, messages)
        except (TimeoutError, urllib.error.URLError, ValueError) as error:
            emit({"event": "request_error", "turn": turn, "error": type(error).__name__})
            return 1
        choice = response["choices"][0]
        message = choice["message"]
        calls = message.get("tool_calls") or []
        now = time.monotonic()
        emit(
            {
                "event": "response",
                "turn": turn,
                "latency_seconds": round(now - request_started, 6),
                "tool_result_to_next_action_seconds": (
                    round(now - previous_tools_at, 6) if previous_tools_at else None
                ),
                "finish_reason": choice.get("finish_reason"),
                "tool_calls": len(calls),
                "usage": response.get("usage"),
            }
        )
        if not calls:
            content = str(message.get("content") or "")
            emit(
                {
                    "event": "final",
                    "duration_seconds": round(now - started, 6),
                    "content": content,
                }
            )
            return 0 if content.strip() else 1
        messages.append(
            {"role": "assistant", "content": message.get("content"), "tool_calls": calls}
        )
        for call in calls:
            function = call["function"]
            arguments: dict[str, Any] = {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except ValueError as error:
                result = {"error": f"invalid arguments: {error}", "exit_code": 1}
            else:
                result = execute_tool(root, function["name"], arguments)
            emit(
                {
                    "event": "tool",
                    "turn": turn,
                    "name": function["name"],
                    "arguments_sha256": hashlib.sha256(
                        json.dumps(arguments, sort_keys=True).encode()
                    ).hexdigest(),
                    "command": arguments.get("command"),
                    "exit_code": result.get("exit_code"),
                    "duration_seconds": result.get("duration_seconds"),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        previous_tools_at = time.monotonic()
    emit({"event": "turn_limit", "max_turns": args.max_turns})
    return 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-turns", type=int, default=24)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
