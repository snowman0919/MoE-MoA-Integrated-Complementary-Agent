from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.controller import Controller
from dgx_moa.knowledge import (
    KnowledgeConfidence,
    KnowledgeContent,
    KnowledgeEvidence,
    KnowledgeLifecycle,
    KnowledgeProvenance,
    KnowledgeQuery,
    KnowledgeRegistry,
    KnowledgeValidation,
    RuntimeKnowledge,
)
from dgx_moa.state import SessionState, StateStore


def entry(
    *,
    knowledge_id: str = "knowledge.mcp.unsupported-tool",
    version: int = 1,
    state: str = "candidate",
    summary: str = "Unsupported MCP tools must produce a typed recovery action.",
    validation_evidence: list[str] | None = None,
    supersedes: list[str] | None = None,
) -> RuntimeKnowledge:
    return RuntimeKnowledge.model_validate(
        {
            "knowledge_id": knowledge_id,
            "version": version,
            "title": "Unsupported MCP tool handling",
            "state": state,
            "category": "tool_limitation",
            "domains": ["mcp", "tools"],
            "repository_scope": [],
            "content": KnowledgeContent(summary=summary),
            "evidence": KnowledgeEvidence(source_task_ids=["task-1"]),
            "provenance": KnowledgeProvenance(source_type="human", created_by="tester"),
            "confidence": KnowledgeConfidence(**{"class": "medium", "basis": "observed"}),
            "lifecycle": KnowledgeLifecycle(supersedes=supersedes or []),
            "validation_evidence": validation_evidence or [],
        }
    )


def validation() -> KnowledgeValidation:
    return KnowledgeValidation(
        source_verified=True,
        duplicate_checked=True,
        contradiction_checked=True,
        repository_scope_checked=True,
        privacy_checked=True,
        license_checked=True,
        reviewer_approved=True,
        evidence_ids=["review-1"],
    )


def test_knowledge_is_immutable_searchable_versioned_and_reversible(tmp_path: Path) -> None:
    registry = KnowledgeRegistry(tmp_path / "knowledge.db")
    registry.put(entry())
    validated = registry.validate_candidate("knowledge.mcp.unsupported-tool", 1, validation())
    promoted = registry.promote(
        validated.knowledge_id,
        validated.version,
        approval_id="approval-1",
        created_by="operator",
    )

    matches = registry.search(KnowledgeQuery(text="unsupported MCP tool"))

    assert matches[0].knowledge.version == promoted.version
    assert "lexical_overlap" in matches[0].reasons[0]
    with pytest.raises(KeyError, match="not found"):
        registry.get("knowledge.missing", 1)
    with pytest.raises(ValueError, match="immutable"):
        registry.put(entry(summary="silently changed"))
    rolled_back = registry.rollback(
        promoted.knowledge_id,
        promoted.version,
        validated.version,
        approval_id="rollback-1",
        created_by="operator",
    )
    assert rolled_back.version == promoted.version + 1
    assert f"{validated.knowledge_id}@{validated.version}" in rolled_back.lifecycle.supersedes
    assert registry.integrity_check()


def test_knowledge_conflicts_are_retained_until_approved_supersession(tmp_path: Path) -> None:
    registry = KnowledgeRegistry(tmp_path / "knowledge.db")
    left = entry(validation_evidence=["left-test"], state="active")
    right = entry(
        knowledge_id="knowledge.mcp.tool-retry",
        state="active",
        summary="Unsupported MCP tools should be retried unchanged.",
        validation_evidence=["right-test"],
    )
    registry.put(left)
    registry.put(right)
    conflict_id = registry.add_conflict(
        (left.knowledge_id, left.version),
        (right.knowledge_id, right.version),
        evidence_ids=["contradiction-test"],
    )

    match = registry.search(KnowledgeQuery(text="unsupported MCP tools"))[0]
    assert conflict_id in match.contradiction_ids
    resolution = entry(
        version=2,
        state="active",
        summary="Verify MCP capability once, then choose a different recovery action.",
        validation_evidence=["resolution-test"],
        supersedes=[f"{left.knowledge_id}@1", f"{right.knowledge_id}@1"],
    )
    registry.resolve_conflict(conflict_id, resolution, approval_id="approval-2")
    assert (
        conflict_id
        not in registry.search(KnowledgeQuery(text="unsupported MCP tools"))[0].contradiction_ids
    )


def test_executor_retrieves_bounded_knowledge_into_evidence(settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    registry = KnowledgeRegistry(tmp_path / "knowledge.db")
    registry.put(entry(state="active", validation_evidence=["verified"]))
    settings.runtime_knowledge.enabled = True
    settings.runtime_knowledge.retrieval_limit = 1
    controller = Controller(
        settings,
        StateStore(settings.state_db),
        object(),  # type: ignore[arg-type]
        knowledge=registry,
    )
    state = SessionState(session_id="knowledge", objective="Handle unsupported MCP tool")

    controller.select_executor_knowledge(state, {"framework": "mcp"})

    assert state.knowledge_selections[0]["knowledge_id"] == "knowledge.mcp.unsupported-tool"
    assert any(
        event["event_type"] == "knowledge_retrieved"
        for event in controller.store.events(state.session_id)
    )
