from __future__ import annotations

import json
import re
from typing import Any, cast

from .evidence import (
    active_failures,
    current_turn_executions,
    effective_objective,
    tool_execution_changes_files,
)
from .loop_engineering import progress_evidence_fingerprint, register_failure
from .security import redact
from .state import SessionState
from .validation import successful_validation_execution

REVIEW_CONTRACT_DOCUMENTS = {
    "agents.md",
    "readme.md",
    "requirements.md",
    "spec.md",
}


def serialize_review_evidence(evidence: dict[str, Any], limit: int) -> str:
    bounded = cast(dict[str, Any], redact(evidence))
    serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    marker = "...[truncated]"
    while len(serialized) > limit:
        key = max(
            bounded,
            key=lambda name: len(json.dumps(bounded[name], ensure_ascii=False, sort_keys=True)),
        )
        current = bounded[key]
        source = (
            current
            if isinstance(current, str)
            else json.dumps(current, ensure_ascii=False, sort_keys=True)
        )
        keep = max(0, len(source) - (len(serialized) - limit) - len(marker) - 2)
        replacement = source[:keep] + marker
        if bounded[key] == replacement:
            raise ValueError("review evidence limit too small")
        bounded[key] = replacement
        serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    return serialized


def review_observation(
    state: SessionState,
    response: dict[str, Any],
    metadata: dict[str, Any],
    limit: int,
) -> str:
    choice = (response.get("choices") or [{}])[0]
    current_completion = metadata.get("completion_evidence")
    evidence = {
        "original_objective": effective_objective(state),
        "acceptance_criteria": state.acceptance_criteria,
        "changed_paths": list(
            dict.fromkeys(
                [
                    *metadata.get("changed_paths", []),
                    *[
                        path
                        for item in state.implementation_evidence
                        for path in item.get("target_paths", [])
                    ],
                ]
            )
        ),
        "diff_summary": metadata.get("diff_summary", ""),
        "contract_evidence": review_contract_evidence(state),
        "implementation_evidence": state.implementation_evidence,
        "tool_results": review_tool_results(state),
        "tool_executions": review_tool_executions(state),
        "validation_results": metadata.get("validation_results", []),
        "scope_evidence": state.approved_scope,
        "completion_evidence": state.completion_evidence
        | (current_completion if isinstance(current_completion, dict) else {}),
        "known_failures": active_failures(state)[-4:],
        "assistant_message": choice.get("message", {}),
        "finish_reason": choice.get("finish_reason"),
    }
    return serialize_review_evidence(evidence, limit)


def has_review_evidence(state: SessionState, metadata: dict[str, Any]) -> bool:
    completion_evidence = metadata.get("completion_evidence")
    if (
        (isinstance(completion_evidence, dict) and completion_evidence)
        or metadata.get("changed_paths")
        or metadata.get("diff_summary")
        or metadata.get("validation_results")
    ):
        return True
    executions = current_turn_executions(state)
    if (
        state.active_turn_requires_change
        and state.active_turn_targets_repository
        and not any(
            execution.get("exit_code") == 0 and tool_execution_changes_files(execution)
            for execution in executions
        )
    ):
        return False
    for execution in reversed(executions):
        arguments = execution.get("normalized_arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        command = (
            arguments.get("cmd") or arguments.get("command")
            if isinstance(arguments, dict)
            else None
        )
        if successful_validation_execution(execution) or (
            execution.get("exit_code") == 0
            and isinstance(command, str)
            and re.search(r"(?:^|&&|\|\||;|\n|[\"'])\s*git\s+diff\b", command)
        ):
            return True
        if tool_execution_changes_files(execution):
            break
    return False


def review_tool_results(state: SessionState) -> list[dict[str, Any]]:
    results = state.tool_results
    return list(results) if len(results) <= 8 else [*results[:4], *results[-4:]]


def review_tool_executions(state: SessionState) -> list[dict[str, Any]]:
    executions = current_turn_executions(state)
    mutation_indexes = [
        index
        for index, execution in enumerate(executions)
        if tool_execution_changes_files(execution)
    ][-4:]
    selected_indexes = sorted(
        set((*mutation_indexes, *range(max(0, len(executions) - 6), len(executions))))
    )
    return [
        {
            key: execution[key]
            for key in (
                "tool_name",
                "normalized_arguments",
                "exit_code",
                "stdout_summary",
                "stderr_summary",
            )
            if key in execution
        }
        for execution in (executions[index] for index in selected_indexes)
    ]


def review_contract_evidence(state: SessionState) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in reversed(state.evidence_nodes):
        if node.get("kind") != "tool_observed_fact":
            continue
        payload = node.get("payload")
        if not isinstance(payload, dict) or payload.get("exit_code") != 0:
            continue
        stdout = payload.get("stdout")
        paths = payload.get("target_paths")
        if not isinstance(stdout, str) or not isinstance(paths, list):
            continue
        for path in paths:
            name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
            normalized = name.lower()
            if normalized not in REVIEW_CONTRACT_DOCUMENTS or normalized in seen:
                continue
            evidence.append({"document": name, "content": stdout[:4_000]})
            seen.add(normalized)
            if len(evidence) == 4:
                return list(reversed(evidence))
    return list(reversed(evidence))


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


def register_frontier_review_failure(
    state: SessionState, result: dict[str, Any]
) -> bool:
    return _register_review_failure(
        state, progress_evidence_fingerprint("frontier_review", result)
    )


def register_local_review_failure(state: SessionState, result: dict[str, Any]) -> bool:
    findings = [
        {
            key: finding.get(key)
            for key in ("finding_id", "severity", "category", "affected_location")
        }
        | {"required_correction": bool(finding.get("required_correction"))}
        for finding in result.get("findings", [])
        if isinstance(finding, dict)
    ]
    return _register_review_failure(
        state,
        progress_evidence_fingerprint(
            "local_review",
            {
                "status": result.get("status"),
                "findings": sorted(
                    findings,
                    key=lambda finding: json.dumps(finding, sort_keys=True, default=str),
                ),
            },
        ),
    )


def _register_review_failure(state: SessionState, fingerprint: str) -> bool:
    loop = state.engineering_loop
    if loop is None:
        return False
    register_failure(loop, "DUPLICATE_FAILURE", finding_fingerprint=fingerprint)
    return loop.termination_reason == "DUPLICATE_FAILURE_LIMIT"


def rejected_without_findings(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("status") == "rejected"
        and not value.get("findings")
    )


def unresolved_structured_rejection() -> dict[str, Any]:
    return {
        "status": "rejected",
        "findings": [
            {
                "finding_id": "review-structured-rejection",
                "severity": "important",
                "category": "review_integrity",
                "evidence_references": [],
                "affected_location": "bounded implementation evidence",
                "impact": (
                    "The Reviewer detected a defect but omitted its required structured finding; "
                    "a later empty approval cannot establish correctness."
                ),
                "required_correction": (
                    "Re-inspect every written requirement against the bounded implementation, "
                    "identify the concrete defect, correct it, and rerun validation before "
                    "approval."
                ),
                "optional_recommendation": None,
            }
        ],
    }
