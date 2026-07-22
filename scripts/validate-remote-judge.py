#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dgx_moa.remote_judge import (
    JudgeCallLimitExceeded,
    JudgeEvidencePackage,
    NvidiaNimJudgeProvider,
    RemoteJudgeVerdict,
)


def package(request_id: str, **values: object) -> JudgeEvidencePackage:
    return JudgeEvidencePackage.model_validate(
        {
            "request_id": request_id,
            "objective": "Validate an engineering result from bounded evidence.",
            "risk_class": "high",
            "specific_judgment_question": "Is this result ready for final delivery?",
            **values,
        }
    )


async def validate(output: Path) -> None:
    endpoint = os.getenv("NVIDIA_NIM_BASE_URL")
    if not endpoint or not os.getenv("NVIDIA_API_KEY"):
        raise SystemExit("NVIDIA_NIM_BASE_URL and NVIDIA_API_KEY must be set in the environment")
    provider = NvidiaNimJudgeProvider(
        endpoint=endpoint,
        api_key_env="NVIDIA_API_KEY",
        model="z-ai/glm-5.2",
        timeout_seconds=120,
        max_retries=1,
        max_calls_per_request=2,
    )
    if not await provider.available():
        raise RuntimeError("NVIDIA NIM GLM-5.2 model catalog is unavailable")

    results: dict[str, dict[str, object]] = {}

    def write_status(status: str) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(f"{output.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": "live-remote-judge-validation-v1",
                    "status": status,
                    "created_at": datetime.now(UTC).isoformat(),
                    "provider": "nvidia_nim",
                    "model": "z-ai/glm-5.2",
                    "cases": results,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary.replace(output)

    async def run(name: str, evidence: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        verdict = await provider.judge(evidence)
        results[name] = {
            "verdict": verdict.verdict,
            "criteria": verdict.criteria.model_dump(mode="json"),
            "finding_count": len(verdict.findings),
            "required_edit_count": len(verdict.required_edits),
            "recheck_required": verdict.recheck_required,
            "usage": await provider.usage(evidence.request_id),
        }
        write_status("running")
        return verdict

    valid = await run(
        "approve_valid_response",
        package(
            "live-valid",
            acceptance_criteria=["unit tests pass"],
            executor_draft="The unit tests passed. No deployment occurred.",
            test_evidence=[{"id": "test-valid", "status": "passed", "exit_code": 0}],
        ),
    )
    assert valid.verdict in {"approve", "approve_with_edits"}
    assert valid.criteria.test_consistency == "pass"

    unsupported = await run(
        "reject_unsupported_claim",
        package(
            "live-unsupported",
            acceptance_criteria=["production deployment verified"],
            executor_draft="Production deployment succeeded.",
            tool_evidence=[],
            test_evidence=[],
            open_failures=[{"id": "missing-deployment-evidence"}],
        ),
    )
    assert unsupported.verdict not in {"approve", "approve_with_edits"}
    assert unsupported.criteria.evidence_grounding != "pass"

    failed_test = await run(
        "detect_failed_test_reported_success",
        package(
            "live-failed-test",
            acceptance_criteria=["tests pass"],
            executor_draft="All tests passed.",
            test_evidence=[{"id": "test-failed", "status": "failed", "exit_code": 1}],
            open_failures=[{"id": "test-failed"}],
        ),
    )
    assert failed_test.verdict not in {"approve", "approve_with_edits"}
    assert failed_test.criteria.test_consistency in {"partial", "fail"}

    missing = await run(
        "detect_missing_acceptance_criterion",
        package(
            "live-missing-criterion",
            acceptance_criteria=["tests pass", "rollback verified"],
            executor_draft="Tests passed; the result is complete.",
            test_evidence=[{"id": "test-only", "status": "passed", "exit_code": 0}],
        ),
    )
    assert missing.verdict not in {"approve", "approve_with_edits"}
    assert missing.criteria.completeness != "pass"

    correction_package = package(
        "live-correction",
        acceptance_criteria=["report only verified test status"],
        executor_draft="Tests passed and production is healthy.",
        test_evidence=[{"id": "test-correction", "status": "passed", "exit_code": 0}],
        open_failures=[{"id": "production-health-unverified"}],
    )
    correction = await run("require_bounded_correction", correction_package)
    assert correction.verdict in {
        "approve_with_edits",
        "revise",
        "retry_with_evidence",
        "reject",
    }
    assert correction.required_edits

    recheck = await run(
        "approve_corrected_recheck",
        correction_package.model_copy(
            update={
                "executor_draft": "Tests passed.",
                "open_failures": [],
                "specific_judgment_question": "Were the required bounded edits applied?",
            }
        ),
    )
    assert recheck.verdict in {"approve", "approve_with_edits"}
    try:
        await provider.judge(correction_package)
    except JudgeCallLimitExceeded:
        results["maximum_two_call_enforcement"] = {"blocked": True}
        write_status("running")
    else:
        raise AssertionError("third Judge call was not blocked")

    write_status("passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(validate(args.output.resolve()))


if __name__ == "__main__":
    main()
