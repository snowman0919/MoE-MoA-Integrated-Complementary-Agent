from __future__ import annotations

from typing import Any

from .state import SessionState


def material_review_issue(result: dict[str, Any]) -> bool:
    if result.get("status") == "rejected":
        return True
    findings = result.get("findings", [])
    if not isinstance(findings, list):
        return False
    for finding in findings:
        if isinstance(finding, dict) and str(finding.get("severity", "")).lower() in {
            "critical",
            "important",
        }:
            return True
        if isinstance(finding, str) and finding.lower().startswith(("critical:", "important:")):
            return True
    return False


def material_frontier_review(result: dict[str, Any]) -> bool:
    return bool(
        result.get("verdict") in {"revise", "reject"}
        or result.get("critical")
        or result.get("important")
        or result.get("missing_tests")
    )


def frontier_correction_questions(state: SessionState) -> list[str]:
    prior_review: dict[str, Any] = next(
        (
            artifact.get("output", {})
            for artifact in reversed(state.agent_artifacts)
            if artifact.get("role") == "frontier"
            and isinstance(artifact.get("output"), dict)
            and artifact["output"].get("verdict") in {"revise", "reject"}
        ),
        {},
    )
    return [
        "Correction verification: report all unresolved prior material findings and all "
        "material regressions introduced by the correction in this one response; never "
        "serialize known findings across later reviews, and keep unrelated new hardening as "
        "suggestions.",
        *prior_review.get("critical", []),
        *prior_review.get("important", []),
        *prior_review.get("missing_tests", []),
    ]
