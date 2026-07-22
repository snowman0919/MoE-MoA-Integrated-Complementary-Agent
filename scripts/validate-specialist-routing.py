#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from dgx_moa.providers import parse_json_content
from dgx_moa.schemas import PlannerPlan, ReviewResult
from dgx_moa.specialists import RemotePlannerProvider, RemoteReviewerProvider


def request_for(schema: type[PlannerPlan] | type[ReviewResult], prompt: str) -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "system",
                "content": "Return only the requested JSON object. Do not use tools.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        },
    }


async def main() -> None:
    if not os.getenv("OPENCODE_GO_API_KEY"):
        raise SystemExit("OPENCODE_GO_API_KEY must be set in the environment")
    endpoint = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go")
    cases = (
        (
            "planner",
            "deepseek-v4-pro",
            RemotePlannerProvider(
                endpoint=endpoint,
                api_key_env="OPENCODE_GO_API_KEY",
                model="deepseek-v4-pro",
            ),
            PlannerPlan,
            (
                "Plan a bounded one-file documentation correction. Include scope, assumptions, "
                "one ordered step with step_id/action/dependencies/expected_evidence, "
                "dependencies, risks, validation_plan, rollback_plan, and acceptance_criteria."
            ),
        ),
        (
            "reviewer",
            "deepseek-v4-flash",
            RemoteReviewerProvider(
                endpoint=endpoint,
                api_key_env="OPENCODE_GO_API_KEY",
                model="deepseek-v4-flash",
            ),
            ReviewResult,
            (
                "Review this concrete evidence: file docs/a.md changed one typo; test evidence "
                "markdown lint passed. Return approved with no findings if sufficient."
            ),
        ),
    )
    results = []
    for role, model, provider, schema, prompt in cases:
        started = time.monotonic()
        response = await provider.complete(request_for(schema, prompt), timeout_seconds=120)
        try:
            schema.model_validate(parse_json_content(response))
        except (TypeError, ValueError) as error:
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            raise RuntimeError(
                json.dumps(
                    {
                        "role": role,
                        "model": model,
                        "finish_reason": choice.get("finish_reason"),
                        "message_fields": sorted(message),
                        "content_characters": len(str(message.get("content") or "")),
                        "reasoning_characters": len(str(message.get("reasoning_content") or "")),
                    },
                    sort_keys=True,
                )
            ) from error
        results.append(
            {
                "role": role,
                "model": model,
                "structured_output": "valid",
                "latency_seconds": round(time.monotonic() - started, 3),
                "prompt_tokens": int(response.get("usage", {}).get("prompt_tokens", 0) or 0),
                "completion_tokens": int(
                    response.get("usage", {}).get("completion_tokens", 0) or 0
                ),
                "total_tokens": int(response.get("usage", {}).get("total_tokens", 0) or 0),
            }
        )
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
