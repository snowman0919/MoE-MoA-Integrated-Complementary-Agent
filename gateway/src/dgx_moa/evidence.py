from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .loop_engineering import (
    PROGRESS_EVIDENCE_KINDS,
    progress_evidence_fingerprint,
    record_progress,
)
from .state import SessionState, now

EvidenceNodeType = Literal[
    "user_objective",
    "constraint",
    "assumption",
    "reasoner_conclusion",
    "executor_decision",
    "planner_plan",
    "knowledge_entry",
    "skill_selection",
    "skill_output",
    "tool_call",
    "tool_result",
    "file_change",
    "test_result",
    "reviewer_finding",
    "frontier_finding",
    "judge_verdict",
    "judge_finding",
    "acceptance_criterion",
    "failure",
    "policy_decision",
    "final_response",
    "user_feedback",
]
EvidenceRelationship = Literal[
    "supports",
    "contradicts",
    "depends_on",
    "generated_from",
    "supersedes",
    "validated_by",
    "invalidated_by",
    "resolved_by",
    "selected_because",
    "rejected_because",
    "corrected_by",
]
TrustClass = Literal[
    "user_provided_constraint",
    "model_assertion",
    "tool_observed_fact",
    "test_confirmed_fact",
    "review_finding",
    "frontier_finding",
    "judge_finding",
    "policy_decision",
    "unverified_assumption",
]
TRUST_RANK: dict[TrustClass, int] = {
    "unverified_assumption": 0,
    "model_assertion": 1,
    "review_finding": 2,
    "frontier_finding": 2,
    "judge_finding": 2,
    "user_provided_constraint": 3,
    "policy_decision": 4,
    "tool_observed_fact": 5,
    "test_confirmed_fact": 6,
}
REPOSITORY_MUTATION_TOOLS = frozenset(
    {
        "apply_patch",
        "patch",
        "delete",
        "edit_file",
        "edit",
        "write",
        "write_file",
        "delete_file",
    }
)


def argument_paths(arguments: Any) -> set[str]:
    text = arguments if isinstance(arguments, str) else json.dumps(arguments, sort_keys=True)
    paths = {
        match.removeprefix("file://").rstrip(",.);]")
        for match in re.findall(r"(?:file://)?/[^\s\"'\\]+", text)
    }
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            normalized = key.lower().replace("_", "")
            if (
                normalized in {"path", "file", "filepath", "filename", "target", "targetpath"}
                and isinstance(value, str)
                and value
                and "\n" not in value
            ):
                paths.add(value.removeprefix("file://"))
    paths.update(
        match.strip()
        for match in re.findall(
            r"(?<![\w./-])(?:[\w.-]+/)*[\w.-]+\.(?:py|js|ts|json|toml|yaml|yml|md)\b",
            text,
        )
    )
    return paths


def active_failures(state: SessionState) -> list[dict[str, Any]]:
    return [item for item in state.failures if item.get("resolution_status", "active") == "active"]


def effective_objective(state: SessionState) -> str:
    objective = state.resolved_objective or state.objective
    if state.active_user_instruction and state.active_user_instruction != state.objective:
        return objective + "\n\nCURRENT USER INSTRUCTION\n" + state.active_user_instruction
    return objective


def current_turn_executions(state: SessionState) -> list[dict[str, Any]]:
    marker = state.active_turn_after_tool_execution_id
    if not marker:
        return state.tool_executions
    for index, execution in enumerate(state.tool_executions):
        if execution.get("tool_execution_id") == marker:
            return state.tool_executions[index + 1 :]
    return state.tool_executions


def executor_stalled(state: SessionState, *, inspection_limit: int = 6) -> bool:
    """Detect repeated successful inspection since the latest file change."""
    counts: dict[str, int] = {}
    inspections = 0
    for execution in reversed(current_turn_executions(state)):
        if execution.get("exit_code") != 0:
            continue
        if tool_execution_changes_files(execution):
            break
        arguments = execution.get("normalized_arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        tool_name = str(execution.get("tool_name", ""))
        command = (
            arguments.get("cmd") or arguments.get("command")
            if isinstance(arguments, dict)
            else None
        )
        command_inspection = isinstance(command, str) and bool(
            re.search(
                r"(?:^|&&|\|\||;|\n)\s*(?:"
                r"cat|head|tail|ls|find|rg|sed\s+-n|pwd|wc|"
                r"git\s+(?:status|diff|log|show|branch|rev-parse)"
                r")\b",
                command,
            )
        )
        no_progress_tool = tool_name in {
            "read",
            "read_file",
            "view_image",
            "list",
            "glob",
            "grep",
            "search_files",
            "create_goal",
            "get_goal",
            "request_user_input",
            "update_goal",
            "update_plan",
        }
        if command_inspection or no_progress_tool:
            inspections += 1
            if inspections >= inspection_limit:
                return True
        if not command_inspection and not no_progress_tool and tool_name != "write_stdin":
            continue
        targets = argument_paths(arguments)
        if not targets and any(
            marker in str(execution.get("stdout_summary", ""))
            for marker in ("No active process session", "Unknown process id")
        ):
            targets = {"invalid-process-session"}
        for target in targets:
            counts[target] = counts.get(target, 0) + 1
            if counts[target] >= 3:
                return True
    return False


def tool_execution_changes_files(execution: dict[str, Any]) -> bool:
    tool_name = execution.get("tool_name")
    if tool_name in REPOSITORY_MUTATION_TOOLS:
        if tool_name in {"apply_patch", "patch"}:
            arguments = execution.get("normalized_arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {"input": arguments}
            patch = (
                arguments.get("input") or arguments.get("patch") or arguments.get("diff")
                if isinstance(arguments, dict)
                else None
            )
            targets = (
                re.findall(
                    r"^\*\*\* (?:(?:Add|Update|Delete) File: |Move to: )(.+?)\r?$",
                    patch,
                    re.MULTILINE,
                )
                if isinstance(patch, str)
                else []
            )
            if targets and all(
                target in {"/state", "/inputs"} or target.startswith(("/state/", "/inputs/"))
                for target in targets
            ):
                return False
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
        arguments.get("cmd") or arguments.get("command")
        if isinstance(arguments, dict)
        else None
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
    return bool(direct_mutation or python_mutation)


class EvidenceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: EvidenceNodeType
    kind: str
    trust_class: TrustClass
    source: str
    payload: Any
    created_at: str


class EvidenceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(
        validation_alias=AliasChoices("from_node", "from"), serialization_alias="from"
    )
    to_node: str = Field(validation_alias=AliasChoices("to_node", "to"), serialization_alias="to")
    relationship: EvidenceRelationship


KIND_NODE_MAP: dict[str, EvidenceNodeType] = {
    "user_objective": "user_objective",
    "user_feedback": "user_feedback",
    "model_assertion": "reasoner_conclusion",
    "agent_decision": "executor_decision",
    "orchestration_decision": "executor_decision",
    "skill_selection": "skill_selection",
    "skill_output": "skill_output",
    "knowledge_entry": "knowledge_entry",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "file_change": "file_change",
    "test_result": "test_result",
    "reviewer_finding": "reviewer_finding",
    "frontier_finding": "frontier_finding",
    "judge_verdict": "judge_verdict",
    "acceptance_evidence": "acceptance_criterion",
    "failure": "failure",
    "provider_failure": "failure",
    "failure_resolved": "failure",
    "policy_decision": "policy_decision",
    "final_response": "final_response",
}


def classify_evidence(kind: str, source: str) -> tuple[EvidenceNodeType, TrustClass]:
    node_type = KIND_NODE_MAP.get(kind, "assumption")
    if kind == "agent_decision":
        role_node_types: dict[str, EvidenceNodeType] = {
            "reasoner": "reasoner_conclusion",
            "executor": "executor_decision",
            "planner": "planner_plan",
            "reviewer": "reviewer_finding",
            "frontier": "frontier_finding",
            "judge": "judge_verdict",
        }
        node_type = role_node_types.get(source, "assumption")
    if kind in {"test_result", "acceptance_evidence"}:
        trust: TrustClass = "test_confirmed_fact"
    elif kind in {"tool_call", "tool_result", "file_change", "failure_resolved"}:
        trust = "tool_observed_fact"
    elif kind == "policy_decision":
        trust = "policy_decision"
    elif kind == "frontier_finding":
        trust = "frontier_finding"
    elif kind in {"judge_finding", "judge_verdict"}:
        trust = "judge_finding"
    elif kind == "reviewer_finding":
        trust = "review_finding"
    elif kind in {"user_objective", "user_feedback"} or source == "user":
        trust = "user_provided_constraint"
    elif kind in {"model_assertion", "agent_decision", "orchestration_decision"}:
        trust = "model_assertion"
    else:
        trust = "unverified_assumption"
    return node_type, trust


def append_evidence(
    state: SessionState,
    kind: str,
    source: str,
    payload: Any,
    *,
    max_steps: int,
    redactor: Callable[[Any], Any],
    generated_from: str | None = None,
) -> str:
    node_id = str(uuid.uuid4())
    node_type, trust_class = classify_evidence(kind, source)
    safe_payload = redactor(payload)
    node = EvidenceNode(
        node_id=node_id,
        node_type=node_type,
        kind=kind,
        trust_class=trust_class,
        source=source,
        payload=safe_payload,
        created_at=now(),
    )
    state.evidence_nodes.append(node.model_dump(mode="json"))
    state.evidence_nodes = state.evidence_nodes[-max_steps:]
    if state.engineering_loop is not None and kind in PROGRESS_EVIDENCE_KINDS:
        record_progress(
            state.engineering_loop,
            node_id,
            evidence_fingerprint=progress_evidence_fingerprint(kind, safe_payload),
        )
    if generated_from:
        edge = EvidenceEdge(
            from_node=node_id,
            to_node=generated_from,
            relationship="generated_from",
        )
        state.evidence_edges.append(edge.model_dump(mode="json", by_alias=True))
        state.evidence_edges = state.evidence_edges[-max_steps:]
    return node_id


def append_decision(
    state: SessionState,
    role: str,
    structured_decision: dict[str, Any],
    observation: str,
    *,
    model: Any,
    max_steps: int,
    redactor: Callable[[Any], Any],
) -> str:
    decision_id = str(uuid.uuid4())
    facts = state.verified_facts[-8:]
    timestamp = now()
    safe_decision = redactor(structured_decision)
    decision = {
        "decision_id": decision_id,
        "session_id": state.session_id,
        "task_id": state.task_id,
        "role": role,
        "model_repository": model.repository if model else "unknown",
        "model_revision": model.revision if model else "unknown",
        "adapter_id": str(model.lora_adapter) if model and model.lora_adapter else None,
        "controller_commit": state.controller_commit,
        "timestamp": timestamp,
        "state_before": {
            "phase": state.phase,
            "objective_reference": hashlib.sha256(state.objective.encode()).hexdigest(),
            "current_plan_step": state.step_count,
            "acceptance_criterion_ids": [
                hashlib.sha256(item.encode()).hexdigest()[:16]
                for item in state.acceptance_criteria
            ],
            "verified_fact_ids": [
                hashlib.sha256(item.encode()).hexdigest()[:16] for item in facts
            ],
            "working_set": state.approved_scope,
            "active_failure_fingerprints": state.failed_call_fingerprints[-8:],
            "scope_state": state.repository,
            "previous_decision_ids": [item["decision_id"] for item in state.decisions[-4:]],
        },
        "context_manifest": {
            "context_builder_name": "controller.role_context",
            "context_builder_version": "2",
            "configured_context_limit": model.context_length if model else None,
            "input_tokens": None,
            "included_fact_ids": [
                hashlib.sha256(item.encode()).hexdigest()[:16] for item in facts
            ],
            "included_observation_ids": [
                hashlib.sha256(observation.encode()).hexdigest()[:16]
            ],
            "included_plan_ids": [str(index) for index, _ in enumerate(state.plan)],
            "included_file_references": state.approved_scope,
            "included_diff_references": [],
            "included_failure_fingerprints": state.failed_call_fingerprints[-8:],
            "truncated": False,
            "evicted_item_count": 0,
            "evicted_item_categories": [],
            "compression_status": "bounded",
        },
        "structured_decision": safe_decision,
        "outcome": {
            "status": "pending",
            "progress_made": False,
            "state_changed": False,
            "scope_changed": False,
            "validation_triggered": False,
            "next_phase": state.phase,
        },
    }
    state.decisions.append(decision)
    state.decisions = state.decisions[-max_steps:]
    decision_type, trust_class = classify_evidence("agent_decision", role)
    state.evidence_nodes.append(
        EvidenceNode(
            node_id=decision_id,
            node_type=decision_type,
            kind="agent_decision",
            trust_class=trust_class,
            source=role,
            payload=safe_decision,
            created_at=timestamp,
        ).model_dump(mode="json")
    )
    state.evidence_nodes = state.evidence_nodes[-max_steps:]
    state.last_decision_id = decision_id
    return decision_id


def stronger_evidence(left: EvidenceNode, right: EvidenceNode) -> EvidenceNode:
    """Resolve a contradiction by explicit trust rank, preserving deterministic ties."""
    left_rank = TRUST_RANK[left.trust_class]
    right_rank = TRUST_RANK[right.trust_class]
    if left_rank == right_rank:
        return min((left, right), key=lambda item: item.node_id)
    return left if left_rank > right_rank else right


def validate_evidence_graph(
    raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]]
) -> tuple[list[EvidenceNode], list[EvidenceEdge]]:
    nodes = [EvidenceNode.model_validate(item) for item in raw_nodes]
    edges = [EvidenceEdge.model_validate(item) for item in raw_edges]
    identifiers = [node.node_id for node in nodes]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Evidence Graph contains duplicate node IDs")
    known = set(identifiers)
    if any(
        edge.from_node == edge.to_node or edge.from_node not in known or edge.to_node not in known
        for edge in edges
    ):
        raise ValueError("Evidence Graph contains an invalid edge reference")
    return nodes, edges


def contradiction_resolutions(
    raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]]
) -> list[dict[str, str]]:
    nodes, edges = validate_evidence_graph(raw_nodes, raw_edges)
    by_id = {node.node_id: node for node in nodes}
    resolutions = []
    for edge in edges:
        if edge.relationship != "contradicts":
            continue
        winner = stronger_evidence(by_id[edge.from_node], by_id[edge.to_node])
        loser = edge.to_node if winner.node_id == edge.from_node else edge.from_node
        resolutions.append(
            {
                "winner": winner.node_id,
                "loser": loser,
                "basis": winner.trust_class,
            }
        )
    return resolutions
