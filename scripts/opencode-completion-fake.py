#!/usr/bin/env python3
"""Loopback fake for OpenCode's tool-call completion lifecycle."""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def chunk(delta: dict, finish_reason: str | None = None) -> bytes:
    payload = {
        "id": "fake-completion",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "fake-agent",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def handler(run_dir: Path) -> type[BaseHTTPRequestHandler]:
    class CompletionHandler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"object":"list","data":[]}')

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            continued = any(message.get("role") == "tool" for message in body["messages"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if continued:
                events = (chunk({"content": "WORKER_DONE"}), chunk({}, "stop"))
            else:
                arguments = json.dumps(
                    {"filePath": str(run_dir / "COMPLETION.txt"), "content": "DONE"},
                    separators=(",", ":"),
                )
                events = (
                    chunk(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_fake",
                                    "type": "function",
                                    "function": {"name": "write", "arguments": arguments},
                                }
                            ],
                        }
                    ),
                    chunk({}, "tool_calls"),
                )
            for event in (*events, b"data: [DONE]\n\n"):
                self.wfile.write(event)
                self.wfile.flush()

    return CompletionHandler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), handler(args.run_dir)).serve_forever()


if __name__ == "__main__":
    main()
