#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dgx_moa.config import load_settings
from dgx_moa.frontier import CodexOAuthCollaboration, load_frontier_config
from dgx_moa.remote_judge import JudgeEvidencePackage, OpenCodeGoJudgeProvider
from dgx_moa.specialists import RemotePlannerProvider, RemoteReviewerProvider


async def validate(config: Path, frontier_config: Path, output: Path) -> None:
    settings = load_settings(config)
    frontier = load_frontier_config(frontier_config)
    measured_at = datetime.now(UTC).isoformat()
    records: dict[str, dict[str, Any]] = {}

    async def record(role: str, model: str, probe: Any) -> None:
        try:
            await probe
        except Exception as error:
            records[role] = {
                "model": model,
                "available": False,
                "basis": "structured_inference_probe",
                "failure_class": type(error).__name__,
                "measured_at": measured_at,
            }
        else:
            records[role] = {
                "model": model,
                "available": True,
                "basis": "structured_inference_probe",
                "measured_at": measured_at,
            }

    specialist = settings.specialist_routing
    request = {
        "messages": [{"role": "user", "content": "Return one JSON object with ok=true."}],
        "max_tokens": 64,
        "response_format": {"type": "json_object"},
    }

    async def planner() -> None:
        result = await RemotePlannerProvider(
            endpoint=specialist.endpoint,
            api_key_env=specialist.api_key_env,
            model=specialist.models["planner"],
        ).complete(request, timeout_seconds=120)
        assert result.get("choices")

    async def reviewer() -> None:
        result = await RemoteReviewerProvider(
            endpoint=specialist.endpoint,
            api_key_env=specialist.api_key_env,
            model=specialist.models["reviewer"],
        ).complete(request, timeout_seconds=120)
        assert result.get("choices")

    async def judge() -> None:
        remote = settings.remote_judge
        if not remote.endpoint:
            raise RuntimeError("remote Judge endpoint is not configured")
        verdict = await OpenCodeGoJudgeProvider(
            endpoint=remote.endpoint,
            api_key_env=remote.api_key_env,
            model=remote.model,
            timeout_seconds=remote.timeout_seconds,
            max_retries=remote.max_retries,
            max_calls_per_request=remote.max_calls_per_request,
        ).judge(
            JudgeEvidencePackage(
                request_id="runtime-role-" + uuid.uuid4().hex,
                objective="Verify one bounded runtime role probe.",
                acceptance_criteria=["A structured verdict is returned."],
                executor_draft="The bounded probe completed.",
                test_evidence=[{"id": "probe", "status": "passed"}],
            )
        )
        assert verdict.verdict

    collaboration = CodexOAuthCollaboration(frontier, output.parent, Path.cwd())

    async def frontier_a() -> None:
        result = await collaboration.collaborate(
            "architecture",
            {
                "objective": "Validate a bounded static skeleton and request subgraph.",
                "constraints": ["No host mutation."],
                "specific_questions": ["Is the immutable request graph coherent?"],
            },
            "runtime-frontier-a-" + uuid.uuid4().hex,
        )
        assert result.output

    async def frontier_b() -> None:
        result = await collaboration.collaborate_openrouter(
            "disagreement",
            {
                "objective": "Resolve a bounded graph-policy disagreement.",
                "constraints": ["No host mutation."],
                "relevant_evidence": ["Runtime mutation is forbidden."],
                "specific_questions": ["Should the graph remain immutable?"],
            },
            "runtime-frontier-b-" + uuid.uuid4().hex,
        )
        assert result.output

    await asyncio.gather(
        record("Planner", specialist.models["planner"], planner()),
        record("Reviewer", specialist.models["reviewer"], reviewer()),
        record("Judge", settings.remote_judge.model, judge()),
        record("Frontier A", frontier.model, frontier_a()),
        record("Frontier B", frontier.openrouter_model, frontier_b()),
    )
    payload = {
        "schema_version": "role-validation-v1",
        "measured_at": measured_at,
        "roles": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    if not all(record["available"] for record in records.values()):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frontier-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    asyncio.run(validate(arguments.config, arguments.frontier_config, arguments.output))


if __name__ == "__main__":
    main()
