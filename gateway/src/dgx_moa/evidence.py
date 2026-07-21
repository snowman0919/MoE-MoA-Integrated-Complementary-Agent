from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

EvidenceNodeType = Literal[
    "user_objective",
    "constraint",
    "assumption",
    "reasoner_conclusion",
    "executor_decision",
    "planner_plan",
    "skill_selection",
    "skill_output",
    "tool_call",
    "tool_result",
    "file_change",
    "test_result",
    "reviewer_finding",
    "frontier_finding",
    "judge_verdict",
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
]
TrustClass = Literal[
    "user_provided_constraint",
    "model_assertion",
    "tool_observed_fact",
    "test_confirmed_fact",
    "review_finding",
    "policy_decision",
    "unverified_assumption",
]
TRUST_RANK: dict[TrustClass, int] = {
    "unverified_assumption": 0,
    "model_assertion": 1,
    "review_finding": 2,
    "user_provided_constraint": 3,
    "policy_decision": 4,
    "tool_observed_fact": 5,
    "test_confirmed_fact": 6,
}


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
    elif kind in {"reviewer_finding", "frontier_finding", "judge_verdict"}:
        trust = "review_finding"
    elif kind in {"user_objective", "user_feedback"} or source == "user":
        trust = "user_provided_constraint"
    elif kind in {"model_assertion", "agent_decision", "orchestration_decision"}:
        trust = "model_assertion"
    else:
        trust = "unverified_assumption"
    return node_type, trust


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
