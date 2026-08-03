from __future__ import annotations

import json
import re
from typing import Any

from .loop_engineering import completion_ready as loop_completion_ready
from .state import SessionState


def validation_execution(execution: dict[str, Any]) -> bool:
    arguments = execution.get("validation_arguments", execution.get("normalized_arguments"))
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
    return isinstance(command, str) and bool(
        re.search(
            r"(?:^|&&|\|\||;|\n|[\"'])\s*(?:timeout\s+\S+\s+)?"
            r"(?:uv run )?(?:python -m )?"
            r"(?:unittest|pytest|ruff(?: check| format --check)|mypy)\b",
            command,
        )
    )


def successful_validation_execution(execution: dict[str, Any]) -> bool:
    return (
        execution.get("exit_code") == 0
        and execution.get("failure_class") is None
        and validation_execution(execution)
    )


def filtered_validation_execution(execution: dict[str, Any]) -> bool:
    arguments = execution.get("validation_arguments", execution.get("normalized_arguments"))
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
    return (
        validation_execution(execution)
        and isinstance(command, str)
        and bool(re.search(r"(?<!\|)\|(?!\|)|(?:^|\s)(?:\d*>>?|&>)", command))
    )


def validation_verdict_present(execution: dict[str, Any], output: str) -> bool:
    arguments = execution.get("validation_arguments", execution.get("normalized_arguments"))
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    command = (
        arguments.get("cmd") or arguments.get("command")
        if isinstance(arguments, dict)
        else ""
    )
    if not isinstance(command, str):
        return False
    if re.search(r"(?:python -m )?pytest\b", command):
        return bool(re.search(r"\b[1-9]\d* passed\b", output))
    if re.search(r"(?:python -m )?unittest\b", command):
        return bool(
            re.search(r"\bRan [1-9]\d* tests?\b", output)
            and re.search(r"(?m)^OK\b", output)
        )
    return True


def completion_ready(state: SessionState) -> bool:
    if state.engineering_loop is not None:
        return state.review_status == "approved" and loop_completion_ready(state.engineering_loop)
    return (
        state.review_status == "approved"
        and bool(state.acceptance_criteria)
        and all(criterion in state.completion_evidence for criterion in state.acceptance_criteria)
    )


def missing_evidence(state: SessionState) -> list[str]:
    return [
        criterion
        for criterion in state.acceptance_criteria
        if criterion not in state.completion_evidence
    ]
