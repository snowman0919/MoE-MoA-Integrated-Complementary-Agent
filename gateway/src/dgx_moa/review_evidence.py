"""Bounded review evidence assembly shared by Chat and Responses execution."""

from __future__ import annotations

import json
import re
from typing import Any

from .security import redact
from .state import SessionState

REVIEW_CONTRACT_DOCUMENTS = {"agents.md", "readme.md", "requirements.md", "spec.md"}


def changed_paths_evidence(state: SessionState, metadata: dict[str, Any]) -> list[str]:
    return list(
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
    )


def tool_execution_changes_files(execution: dict[str, Any]) -> bool:
    if execution.get("tool_name") in {
        "apply_patch",
        "patch",
        "delete",
        "edit_file",
        "edit",
        "write",
        "write_file",
        "delete_file",
    }:
        return True
    effect = execution.get("filesystem_effect")
    if isinstance(effect, dict) and any(
        effect.get(key) for key in ("changed_paths", "created_paths", "deleted_paths")
    ):
        return True
    arguments = execution.get("normalized_arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    command = (
        arguments.get("cmd") or arguments.get("command") if isinstance(arguments, dict) else None
    )
    if not isinstance(command, str):
        return False
    direct_mutation = re.search(
        r"(?:^|&&|\|\||;|\n)\s*(?:"
        r"(?:cat|echo|printf)\b[^\n;]*(?<![\d>])(?:1?>|>>)|tee\b|"
        r"sed\b[^\n;]*\s-i(?:\s|$)|perl\b[^\n;]*\s-(?:pi|ip)\b|"
        r"apply_patch\b|"
        r"touch\b|cp\b|mv\b|rm\b|truncate\b|install\b|"
        r"git\s+(?:apply|checkout|restore|reset|clean)\b)",
        command,
    )
    python_mutation = re.search(
        r"(?:^|&&|\|\||;|\n)\s*python(?:3(?:\.\d+)?)?\b[\s\S]*"
        r"(?:\.write_(?:text|bytes)\s*\(|"
        r"\bopen\s*\([^,\n]+,\s*[\"'][wax](?:[bt+])?[\"'])",
        command,
    )
    if python_mutation and "TemporaryDirectory" in command:
        python_mutation = None
    return bool(direct_mutation or python_mutation)


def has_review_evidence(state: SessionState, metadata: dict[str, Any]) -> bool:
    completion_evidence = metadata.get("completion_evidence")
    if (
        (isinstance(completion_evidence, dict) and completion_evidence)
        or metadata.get("changed_paths")
        or metadata.get("diff_summary")
        or metadata.get("validation_results")
    ):
        return True
    for execution in reversed(state.tool_executions):
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
        if is_successful_validation_execution(execution) or (
            execution.get("exit_code") == 0
            and isinstance(command, str)
            and re.search(r"(?:^|&&|\|\||;|\n|[\"'])\s*git\s+diff\b", command)
        ):
            return True
        if tool_execution_changes_files(execution):
            break
    return False


def is_successful_validation_execution(execution: dict[str, Any]) -> bool:
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
    return execution.get("exit_code") == 0 and isinstance(command, str) and bool(
        re.search(
            r"(?:^|&&|\|\||;|\n|[\"'])\s*"
            r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+\s+)*"
            r"(?:timeout\s+\d+(?:\.\d+)?[smh]?\s+)?"
            r"(?:uv run )?(?:python -m )?"
            r"(?:unittest|pytest|ruff(?: check| format --check)|mypy)\b",
            command,
        )
    )


def review_tool_results(state: SessionState) -> list[dict[str, Any]]:
    return list(state.tool_results[-4:])


def review_tool_executions(state: SessionState) -> list[dict[str, Any]]:
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
        for execution in state.tool_executions[-6:]
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


def review_observation(
    state: SessionState,
    response: dict[str, Any],
    metadata: dict[str, Any],
    max_characters: int,
) -> str:
    choice = (response.get("choices") or [{}])[0]
    current_completion = metadata.get("completion_evidence")
    evidence = {
        "original_objective": state.resolved_objective or state.objective,
        "acceptance_criteria": state.acceptance_criteria,
        "changed_paths": changed_paths_evidence(state, metadata),
        "diff_summary": metadata.get("diff_summary", ""),
        "contract_evidence": review_contract_evidence(state),
        "implementation_evidence": state.implementation_evidence,
        "tool_results": review_tool_results(state),
        "tool_executions": review_tool_executions(state),
        "validation_results": metadata.get("validation_results", []),
        "scope_evidence": state.approved_scope,
        "completion_evidence": state.completion_evidence
        | (current_completion if isinstance(current_completion, dict) else {}),
        "known_failures": [
            item for item in state.failures if item.get("resolution_status", "active") == "active"
        ][-4:],
        "assistant_message": choice.get("message", {}),
        "finish_reason": choice.get("finish_reason"),
    }
    bounded: dict[str, Any] = redact(evidence)
    serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    marker = "...[truncated]"
    while len(serialized) > max_characters:
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
        keep = max(0, len(source) - (len(serialized) - max_characters) - len(marker) - 2)
        replacement = source[:keep] + marker
        if bounded[key] == replacement:
            raise ValueError("review evidence limit too small")
        bounded[key] = replacement
        serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    return serialized
