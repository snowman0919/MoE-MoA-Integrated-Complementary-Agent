#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
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


def write_status(
    output: Path,
    created_at: str,
    status: str,
    results: dict[str, dict[str, object]],
    *,
    failure_class: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": "live-specialist-routing-validation-v1",
        "created_at": created_at,
        "status": status,
        "provider": "opencode_go",
        "cases": results,
    }
    if failure_class:
        payload["failure_class"] = failure_class
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)


async def validate(output: Path) -> None:
    if not os.getenv("OPENCODE_GO_API_KEY"):
        raise SystemExit("OPENCODE_GO_API_KEY must be set in the environment")
    endpoint = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go")
    created_at = datetime.now(UTC).isoformat()
    results: dict[str, dict[str, object]] = {}
    write_status(output, created_at, "running", results)
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
            "deepseek-v4-pro",
            RemoteReviewerProvider(
                endpoint=endpoint,
                api_key_env="OPENCODE_GO_API_KEY",
                model="deepseek-v4-pro",
            ),
            ReviewResult,
            (
                "Review this concrete evidence: file docs/a.md changed one typo; test evidence "
                "markdown lint passed. Return approved with no findings if sufficient."
            ),
        ),
    )
    for role, model, provider, schema, prompt in cases:
        try:
            started = time.monotonic()
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            for attempt in (1, 2):
                response = await provider.complete(request_for(schema, prompt), timeout_seconds=120)
                raw_usage = response.get("usage", {})
                for key in usage:
                    usage[key] += int(raw_usage.get(key, 0) or 0)
                try:
                    schema.model_validate(parse_json_content(response))
                    break
                except (TypeError, ValueError):
                    if attempt == 1:
                        continue
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
                                "reasoning_characters": len(
                                    str(message.get("reasoning_content") or "")
                                ),
                            },
                            sort_keys=True,
                        )
                    ) from None
            results[role] = {
                "model": model,
                "status": "passed",
                "structured_output": "valid",
                "attempts": attempt,
                "latency_seconds": round(time.monotonic() - started, 3),
                **usage,
            }
        except Exception as error:
            results[role] = {
                "model": model,
                "status": "failed",
                "failure_class": type(error).__name__,
            }
            write_status(
                output,
                created_at,
                "failed",
                results,
                failure_class=type(error).__name__,
            )
            raise
        write_status(output, created_at, "running", results)
    write_status(output, created_at, "passed", results)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    asyncio.run(validate(output))
    print(output.read_text(), end="")


if __name__ == "__main__":
    main()
