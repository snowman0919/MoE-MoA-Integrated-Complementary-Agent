#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dgx_moa.config import load_settings
from dgx_moa.context_projection import (
    build_runtime_evidence_snapshot,
    canonical_request_input,
    project_role_context,
    runtime_evidence_item,
)
from dgx_moa.frontier import CodexOAuthCollaboration, load_frontier_config
from dgx_moa.providers import parse_json_content
from dgx_moa.schemas import PlannerPlan, ReviewResult
from dgx_moa.specialists import RemotePlannerProvider, RemoteReviewerProvider

MARKERS = ("compare_digest", "token exchange")


def request(schema: type[PlannerPlan] | type[ReviewResult], content: str) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": content}],
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


def usage(response: dict[str, Any]) -> dict[str, int]:
    raw = response.get("usage", {})
    return {
        key: int(raw.get(key, 0) or 0)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


async def validate(config: Path, frontier_config: Path, output: Path) -> None:
    settings = load_settings(config)
    specialist = settings.specialist_routing
    planner = RemotePlannerProvider(
        endpoint=specialist.endpoint,
        api_key_env=specialist.api_key_env,
        model=specialist.models["planner"],
    )
    reviewer = RemoteReviewerProvider(
        endpoint=specialist.endpoint,
        api_key_env=specialist.api_key_env,
        model=specialist.models["reviewer"],
    )
    snapshot = build_runtime_evidence_snapshot(
        request_id="role-context-ab-auth-callback",
        objective="Review and plan a security-sensitive authentication callback correction.",
        request_inputs=(
            canonical_request_input(
                "original-request",
                {
                    "role": "user",
                    "content": (
                        "The callback must compare CSRF state with hmac.compare_digest and reject "
                        "a mismatch before token exchange. Review the proposed implementation."
                    ),
                },
            ),
        ),
        request_constraints=("Do not weaken authentication or expose credentials.",),
        acceptance_criteria=(
            "Use hmac.compare_digest for state comparison.",
            "Reject mismatched state before token exchange.",
            "The failing security test must pass before approval.",
        ),
        runtime_evidence=(
            runtime_evidence_item(
                "actual-diff",
                "diff",
                {
                    "path": "auth/callback.py",
                    "added": "if supplied_state != expected_state: reject()",
                },
                source_attempt_id="executor-a001",
            ),
            runtime_evidence_item(
                "security-test",
                "test",
                {
                    "status": "failed",
                    "summary": "timing-safe state comparison missing before token exchange",
                },
                source_attempt_id="test-a001",
                parent_evidence_ids=("actual-diff",),
            ),
        ),
        graph_id="graph-role-context-ab",
    )
    legacy = {
        "objective": snapshot.objective,
        "executor_summary": "The callback refactor is complete and all tests pass.",
        "executor_completion_claim": "ready for approval",
    }
    direct_planner = project_role_context(snapshot, "planner", stage="fanout")
    direct_reviewer = project_role_context(
        snapshot,
        "reviewer",
        stage="review",
        target_attempt_id="reviewer-a001",
        causal_parent_attempt_ids=("executor-a001", "test-a001"),
    )
    cases: dict[str, dict[str, Any]] = {}

    async def specialist_case(
        label: str,
        provider: RemotePlannerProvider | RemoteReviewerProvider,
        schema: type[PlannerPlan] | type[ReviewResult],
        package: Any,
    ) -> Any:
        started = time.monotonic()
        totals = {key: 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        for attempt in (1, 2):
            response = await provider.complete(
                request(schema, json.dumps(package, ensure_ascii=False, sort_keys=True)),
                timeout_seconds=specialist.timeout_seconds,
            )
            for key, value in usage(response).items():
                totals[key] += value
            try:
                parsed = schema.model_validate(parse_json_content(response))
                break
            except (TypeError, ValueError):
                if attempt == 2:
                    raise
        serialized = parsed.model_dump(mode="json")
        text = json.dumps(serialized, ensure_ascii=False).lower()
        cases[label] = {
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "package_bytes": len(json.dumps(package, ensure_ascii=False).encode()),
            "output_sha256": digest(serialized),
            "marker_recall": {marker: marker in text for marker in MARKERS},
            "attempts": attempt,
            **totals,
        }
        if isinstance(parsed, ReviewResult):
            cases[label]["status"] = parsed.status
            cases[label]["false_approval"] = parsed.status == "approved"
            cases[label]["critical_finding_recall"] = any(
                finding.severity in {"important", "critical"}
                and any(marker in json.dumps(finding.model_dump()).lower() for marker in MARKERS)
                for finding in parsed.findings
            )
        return parsed

    await specialist_case("planner_legacy", planner, PlannerPlan, legacy)
    await specialist_case(
        "planner_direct", planner, PlannerPlan, direct_planner.model_dump(mode="json")
    )
    await specialist_case("reviewer_legacy", reviewer, ReviewResult, legacy)
    await specialist_case(
        "reviewer_direct", reviewer, ReviewResult, direct_reviewer.model_dump(mode="json")
    )

    frontier = CodexOAuthCollaboration(
        load_frontier_config(frontier_config), output.parent / "frontier", Path.cwd()
    )
    for variant, package in (
        ("legacy", legacy),
        ("direct", direct_reviewer.model_dump(mode="json")),
    ):
        result = await frontier.collaborate(
            "code_review",
            {
                "objective": snapshot.objective,
                "constraints": list(snapshot.acceptance_criteria_json),
                "relevant_evidence": package,
                "specific_questions": ["Identify any security-blocking defect."],
            },
            f"role-context-ab-{variant}-{uuid.uuid4().hex}",
        )
        text = json.dumps(result.output, ensure_ascii=False).lower()
        cases[f"frontier_{variant}"] = {
            "latency_ms": result.latency_ms,
            "package_bytes": len(json.dumps(package, ensure_ascii=False).encode()),
            "output_sha256": digest(result.output),
            "marker_recall": {marker: marker in text for marker in MARKERS},
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "profile": result.profile,
            "transport": result.transport,
        }

    def missed(name: str) -> int:
        return sum(not found for found in cases[name]["marker_recall"].values())

    payload = {
        "schema_version": "role-context-ab-v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "provider_models": {
            "planner": specialist.models["planner"],
            "reviewer": specialist.models["reviewer"],
            "frontier_a": load_frontier_config(frontier_config).model,
        },
        "cases": cases,
        "comparison": {
            "planner_plan_correction": {
                variant: 2 - missed(f"planner_{variant}") for variant in ("legacy", "direct")
            },
            "frontier_recommendation_acceptance": {
                variant: 2 - missed(f"frontier_{variant}") for variant in ("legacy", "direct")
            },
            "reviewer_critical_finding_recall": {
                variant: cases[f"reviewer_{variant}"]["critical_finding_recall"]
                for variant in ("legacy", "direct")
            },
            "false_approval": {
                variant: cases[f"reviewer_{variant}"]["false_approval"]
                for variant in ("legacy", "direct")
            },
            "missed_acceptance_criteria": {
                variant: sum(
                    missed(f"{role}_{variant}") for role in ("planner", "reviewer", "frontier")
                )
                for variant in ("legacy", "direct")
            },
            "repair_iterations": "not_measured_in_specialist_only_pair",
            "verified_completion": "not_measured_in_specialist_only_pair",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frontier-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    asyncio.run(validate(arguments.config, arguments.frontier_config, arguments.output.resolve()))


if __name__ == "__main__":
    main()
