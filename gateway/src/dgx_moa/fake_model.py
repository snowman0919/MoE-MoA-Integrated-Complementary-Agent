from __future__ import annotations

import argparse
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse


def create_fake(role: str) -> FastAPI:
    app = FastAPI()

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {"object": "list", "data": [{"id": role, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(body: dict[str, Any]):  # type: ignore[no-untyped-def]
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        if role == "planner":
            content = json.dumps(
                {
                    "plan": [{"step": "execute requested change"}],
                    "acceptance_criteria": ["tests pass"],
                }
            )
        elif role == "reviewer":
            content = json.dumps({"status": "approved", "findings": []})
        elif role == "judge":
            content = json.dumps({"verdict": "approved", "findings": []})
        else:
            content = "executor response"
        base = {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": role,
        }
        if body.get("stream"):

            async def events() -> AsyncIterator[str]:
                chunk = base | {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                done = base | {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        return base | {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    uvicorn.run(create_fake(arguments.role), host="127.0.0.1", port=arguments.port)


if __name__ == "__main__":
    main()
