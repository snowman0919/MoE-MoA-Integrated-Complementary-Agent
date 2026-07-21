from __future__ import annotations

import pytest
from dgx_moa.evidence import (
    EvidenceEdge,
    EvidenceNode,
    classify_evidence,
    contradiction_resolutions,
    stronger_evidence,
    validate_evidence_graph,
)


def node(node_id: str, kind: str, source: str) -> EvidenceNode:
    node_type, trust_class = classify_evidence(kind, source)
    return EvidenceNode(
        node_id=node_id,
        node_type=node_type,
        kind=kind,
        trust_class=trust_class,
        source=source,
        payload={"claim": "same subject"},
        created_at="2026-07-22T00:00:00Z",
    )


def test_tool_and_test_evidence_override_model_assertions() -> None:
    assertion = node("model", "model_assertion", "reasoner")
    tool = node("tool", "tool_result", "shell")
    test = node("test", "test_result", "pytest")

    assert stronger_evidence(assertion, tool) == tool
    assert stronger_evidence(tool, test) == test


def test_unknown_evidence_is_explicit_unverified_assumption() -> None:
    evidence = node("unknown", "new_kind", "runtime")

    assert evidence.node_type == "assumption"
    assert evidence.trust_class == "unverified_assumption"


def test_evidence_edge_uses_supported_relationships() -> None:
    edge = EvidenceEdge(from_node="finding", to_node="test", relationship="validated_by")

    assert edge.relationship == "validated_by"


def test_agent_decision_node_type_tracks_role() -> None:
    planner = node("planner", "agent_decision", "planner")
    reviewer = node("reviewer", "agent_decision", "reviewer")

    assert planner.node_type == "planner_plan"
    assert reviewer.node_type == "reviewer_finding"


def test_graph_consistency_and_contradiction_resolution_use_trust_order() -> None:
    assertion = node("model", "model_assertion", "reasoner")
    test = node("test", "test_result", "pytest")
    nodes = [assertion.model_dump(mode="json"), test.model_dump(mode="json")]
    edges = [
        EvidenceEdge(from_node="model", to_node="test", relationship="contradicts").model_dump(
            mode="json", by_alias=True
        )
    ]

    validated_nodes, validated_edges = validate_evidence_graph(nodes, edges)

    assert len(validated_nodes) == 2
    assert validated_edges[0].relationship == "contradicts"
    assert contradiction_resolutions(nodes, edges) == [
        {"winner": "test", "loser": "model", "basis": "test_confirmed_fact"}
    ]
    with pytest.raises(ValueError, match="invalid edge"):
        validate_evidence_graph(
            nodes, [{"from": "model", "to": "missing", "relationship": "supports"}]
        )
