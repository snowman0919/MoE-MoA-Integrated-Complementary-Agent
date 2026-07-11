#!/usr/bin/env python3
"""Capture bounded OpenAI-compatible SSE sequences without storing credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def capture(
    client: httpx.Client, url: str, token: str, session: str, body: dict[str, Any]
) -> dict[str, Any]:
    events: list[dict[str, Any]] = [{"sequence": 1, "type": "response_started", "at": stamp()}]
    tool_calls: dict[int, dict[str, Any]] = {}
    done = False
    started = time.monotonic()
    with client.stream(
        "POST",
        url,
        headers={"Authorization": f"Bearer {token}", "X-Session-ID": session},
        json=body,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            sequence = len(events) + 1
            if payload == "[DONE]":
                done = True
                events.append({"sequence": sequence, "type": "done", "at": stamp()})
                continue
            chunk = json.loads(payload)
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            event: dict[str, Any] = {
                "sequence": sequence,
                "type": "chunk",
                "choice_index": choice.get("index"),
                "delta_keys": sorted(delta),
                "finish_reason": choice.get("finish_reason"),
            }
            if "usage" in chunk:
                event["usage_position"] = sequence
            for call in delta.get("tool_calls") or []:
                index = int(call.get("index", 0))
                target = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if isinstance(call.get("id"), str):
                    target["id"] += call["id"]
                function = call.get("function") or {}
                if isinstance(function.get("name"), str):
                    target["name"] += function["name"]
                if isinstance(function.get("arguments"), str):
                    target["arguments"] += function["arguments"]
            events.append(event)
    events.append({"sequence": len(events) + 1, "type": "eof", "at": stamp()})
    finish = [event["finish_reason"] for event in events if event.get("finish_reason")]
    if not done or events[-1]["type"] != "eof":
        raise RuntimeError("SSE did not reach DONE then EOF")
    return {
        "session_id": session,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "events": events,
        "finish_reasons": finish,
        "tool_calls": [
            {
                "id": call["id"],
                "name": call["name"],
                "arguments_sha256": hashlib.sha256(call["arguments"].encode()).hexdigest(),
                "arguments": call["arguments"],
            }
            for call in tool_calls.values()
        ],
        "connection_closed_at": stamp(),
    }


def expect(result: dict[str, Any], finish: str) -> None:
    if result["finish_reasons"][-1:] != [finish]:
        raise RuntimeError(f"expected final finish_reason={finish}, got {result['finish_reasons']}")


def completion_events(state_db: Path, session: str) -> list[dict[str, Any]]:
    if not state_db.exists():
        return []
    with sqlite3.connect(state_db) as database:
        rows = database.execute(
            "SELECT event_type, created_at FROM events WHERE session_id = ? "
            "AND event_type IN ('stream_completed', 'stream_aborted') ORDER BY rowid",
            (session,),
        ).fetchall()
    return [{"event_type": event_type, "created_at": created_at} for event_type, created_at in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("DGX_MOA_BASE_URL"))
    parser.add_argument("--output-dir", default="data/diagnostics/opencode-completion")
    parser.add_argument(
        "--state-db",
        type=Path,
        default=Path(os.getenv("DGX_MOA_STATE_DB", "data/state/gateway.db")),
    )
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    token = os.getenv("DGX_MOA_API_KEY")
    if not args.base_url or not token:
        raise SystemExit("DGX_MOA_BASE_URL and DGX_MOA_API_KEY are required")
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    session = f"opencode-sse-{uuid.uuid4()}"
    output = Path(args.output_dir) / f"{session}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=args.timeout) as client:
        normal = capture(
            client,
            url,
            token,
            session,
            {
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "Reply READY."}],
            },
        )
        expect(normal, "stop")
        tool = capture(
            client,
            url,
            token,
            session,
            {
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": "Call read_file once for /tmp/dgx-moa-validation.txt.",
                    }
                ],
                "tools": [TOOL],
                "tool_choice": "required",
            },
        )
        expect(tool, "tool_calls")
        call = tool["tool_calls"][0]
        continuation = capture(
            client,
            url,
            token,
            session,
            {
                "model": "dgx-moa-agent",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": "Call read_file once for /tmp/dgx-moa-validation.txt.",
                    },
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {"name": call["name"], "arguments": call["arguments"]},
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(
                            {
                                "tool_name": call["name"],
                                "arguments": json.loads(call["arguments"]),
                                "stdout": "validation fixture",
                                "stderr": "",
                                "exit_code": 0,
                                "duration_ms": 1,
                                "truncated": False,
                            }
                        ),
                    },
                ],
            },
        )
        expect(continuation, "stop")
    gateway_events = completion_events(args.state_db, session)
    if [event["event_type"] for event in gateway_events] != ["stream_completed"] * 3:
        raise RuntimeError(f"expected three gateway stream completions, got {gateway_events}")
    output.write_text(
        json.dumps(
            {
                "normal": normal,
                "tool": tool,
                "continuation": continuation,
                "gateway_completion_events": gateway_events,
            },
            indent=2,
        )
        + "\n"
    )
    for name, result in (("normal", normal), ("tool", tool), ("continuation", continuation)):
        print(
            name, " ".join(f"{event['sequence']:03}:{event['type']}" for event in result["events"])
        )
    print(output)


if __name__ == "__main__":
    main()
