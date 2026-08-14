from __future__ import annotations

import json

import pytest
from dgx_moa.context_projection import (
    MAX_CONTEXT_BYTES,
    ROLE_CONTEXT_TARGET_BYTES,
    CanonicalRequestInput,
    ModelContribution,
    RoleContextProjection,
    RuntimeEvidenceItem,
    RuntimeEvidenceSnapshot,
    build_runtime_evidence_snapshot,
    canonical_request_input,
    model_contribution,
    project_role_context,
    runtime_evidence_item,
)
from pydantic import ValidationError


def evidence_space() -> tuple[list[RuntimeEvidenceItem], list[ModelContribution]]:
    evidence = [
        runtime_evidence_item(
            "ev-tool",
            "tool",
            {"exit_code": 0, "stdout": "runtime tool sentinel"},
            source_attempt_id="tool-a001",
        ),
        runtime_evidence_item(
            "ev-diff",
            "diff",
            {"changed_paths": ["gateway.py"], "summary": "runtime diff sentinel"},
            source_attempt_id="executor-a001",
            parent_evidence_ids=("ev-tool",),
        ),
        runtime_evidence_item(
            "ev-test",
            "test",
            {"status": "passed", "summary": "runtime test sentinel"},
            source_attempt_id="test-a001",
            parent_evidence_ids=("ev-diff",),
        ),
        runtime_evidence_item(
            "ev-failure",
            "failure",
            {"status": "resolved", "fingerprint": "runtime failure sentinel"},
            source_attempt_id="executor-a001",
            parent_evidence_ids=("ev-test",),
        ),
    ]
    contributions = [
        model_contribution(
            "contrib-reasoner",
            "reasoner",
            {"position": "reasoner sentinel"},
            source_attempt_id="reasoner-a001",
            evidence_ids=("ev-tool",),
        ),
        model_contribution(
            "contrib-planner",
            "planner",
            {"position": "planner sentinel"},
            source_attempt_id="planner-a001",
            evidence_ids=("ev-diff",),
        ),
        model_contribution(
            "contrib-executor",
            "executor",
            {"position": "executor sentinel"},
            source_attempt_id="executor-a001",
            evidence_ids=("ev-diff", "ev-test"),
        ),
        model_contribution(
            "contrib-frontier-a",
            "frontier_a",
            {"position": "frontier A sentinel"},
            source_attempt_id="frontier-a-a001",
            evidence_ids=("ev-diff",),
        ),
        model_contribution(
            "contrib-reviewer",
            "reviewer",
            {"position": "reviewer sentinel"},
            source_attempt_id="reviewer-a001",
            evidence_ids=("ev-test",),
        ),
        model_contribution(
            "contrib-judge",
            "judge",
            {"position": "judge sentinel"},
            source_attempt_id="judge-a001",
            evidence_ids=("ev-failure",),
        ),
        model_contribution(
            "contrib-frontier-b",
            "frontier_b",
            {"position": "prior Frontier B sentinel"},
            source_attempt_id="frontier-b-a001",
            evidence_ids=("ev-failure",),
        ),
    ]
    return evidence, contributions


def snapshot() -> RuntimeEvidenceSnapshot:
    evidence, contributions = evidence_space()
    return build_runtime_evidence_snapshot(
        request_id="request-1",
        graph_id="graph-test",
        objective="original objective sentinel",
        request_inputs=(
            canonical_request_input(
                "input-001", {"role": "user", "content": "original input sentinel"}
            ),
        ),
        request_constraints=("preserve original constraint sentinel",),
        acceptance_criteria=({"criterion_id": "criterion-1", "required": True},),
        runtime_evidence=reversed(evidence),
        model_contributions=reversed(contributions),
    )


def test_snapshot_is_immutable_deterministic_and_causally_valid() -> None:
    first = snapshot()
    evidence, contributions = evidence_space()
    second = build_runtime_evidence_snapshot(
        request_id="request-1",
        graph_id="graph-test",
        objective="original objective sentinel",
        request_inputs=(
            canonical_request_input(
                "input-001", {"content": "original input sentinel", "role": "user"}
            ),
        ),
        request_constraints=("preserve original constraint sentinel",),
        acceptance_criteria=({"required": True, "criterion_id": "criterion-1"},),
        runtime_evidence=evidence,
        model_contributions=contributions,
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_hash == second.snapshot_hash
    assert first.runtime_evidence[1].parent_evidence_ids == ("ev-test",)
    assert first.request_inputs[0].payload()["content"] == "original input sentinel"
    with pytest.raises(ValidationError):
        first.objective = "mutated"

    tampered = first.model_dump(mode="json")
    tampered["objective"] = "tampered"
    with pytest.raises(ValidationError, match="snapshot hash mismatch"):
        RuntimeEvidenceSnapshot.model_validate(tampered)


def test_snapshot_hash_is_stable_for_redacted_source_in_tool_evidence() -> None:
    source = build_runtime_evidence_snapshot(
        request_id="redacted-source",
        objective="inspect source",
        runtime_evidence=(
            runtime_evidence_item(
                "tool-source",
                "tool",
                {"stdout": 'self.secret = b"synthetic"\nprint("done")'},
            ),
        ),
    )

    projection = project_role_context(source, "executor", stage="fanout")

    assert RuntimeEvidenceSnapshot.model_validate(source.model_dump(mode="json")) == source
    assert RoleContextProjection.model_validate(projection.model_dump(mode="json")) == projection


def test_role_projections_share_original_runtime_space_without_prompt_contamination() -> None:
    source = snapshot()
    reviewer = project_role_context(
        source,
        "reviewer",
        stage="review",
        target_node_id="n-reviewer",
        target_attempt_id="reviewer-a002",
        causal_parent_attempt_ids=("executor-a001",),
    )
    judge = project_role_context(
        source,
        "judge",
        stage="review",
        target_node_id="n-judge",
        target_attempt_id="judge-a002",
        causal_parent_attempt_ids=("reviewer-a001", "executor-a001"),
        join_node_id="n-review-join",
    )
    frontier_b = project_role_context(
        source,
        "frontier_b",
        stage="adjudication",
        target_node_id="n-frontier-b",
        target_attempt_id="frontier-b-a002",
        causal_parent_attempt_ids=("judge-a001", "reviewer-a001", "executor-a001"),
        join_node_id="n-disagreement-join",
    )

    assert {item.provenance.snapshot_id for item in (reviewer, judge, frontier_b)} == {
        source.snapshot_id
    }
    assert {item.provenance.snapshot_hash for item in (reviewer, judge, frontier_b)} == {
        source.snapshot_hash
    }
    assert all(item.objective == source.objective for item in (reviewer, judge, frontier_b))
    assert all(
        item.runtime_evidence == source.runtime_evidence for item in (reviewer, judge, frontier_b)
    )
    assert [item.role for item in reviewer.model_contributions] == ["executor"]
    assert [item.role for item in judge.model_contributions] == [
        "executor",
        "reviewer",
    ]
    assert [item.role for item in frontier_b.model_contributions] == [
        "executor",
        "judge",
        "reviewer",
    ]

    reviewer_json = reviewer.model_dump_json()
    judge_json = judge.model_dump_json()
    frontier_b_json = frontier_b.model_dump_json()
    assert "reviewer sentinel" not in reviewer_json
    assert "judge sentinel" not in reviewer_json
    assert "prior Frontier B sentinel" not in reviewer_json
    assert "judge sentinel" not in judge_json
    assert "prior Frontier B sentinel" not in judge_json
    assert "prior Frontier B sentinel" not in frontier_b_json
    for serialized in (reviewer_json, judge_json, frontier_b_json):
        assert "original objective sentinel" in serialized
        assert "runtime tool sentinel" in serialized
        assert "runtime diff sentinel" in serialized
        assert "runtime test sentinel" in serialized
        assert "runtime failure sentinel" in serialized


def test_projection_records_graph_fan_in_and_exact_source_provenance() -> None:
    source = snapshot()
    projection = project_role_context(
        source,
        "frontier_b",
        stage="adjudication",
        target_node_id="n12_frontier_b",
        target_attempt_id="n12_frontier_b_a001",
        causal_parent_attempt_ids=("judge-a001", "reviewer-a001", "executor-a001"),
        join_node_id="n11_join",
    )

    assert projection.provenance.graph_id == "graph-test"
    assert projection.provenance.join_node_id == "n11_join"
    assert projection.provenance.causal_parent_attempt_ids == (
        "executor-a001",
        "judge-a001",
        "reviewer-a001",
    )
    assert projection.provenance.source_attempt_ids == (
        "executor-a001",
        "judge-a001",
        "reviewer-a001",
        "test-a001",
        "tool-a001",
    )
    assert projection.provenance.included_evidence_ids == tuple(
        item.evidence_id for item in source.runtime_evidence
    )
    assert projection.provenance.included_contribution_ids == tuple(
        item.contribution_id for item in projection.model_contributions
    )
    assert projection.provenance.included_categories == (
        "objective",
        "original_inputs",
        "request_constraints",
        "acceptance_criteria",
        "runtime_evidence:diff",
        "runtime_evidence:failure",
        "runtime_evidence:test",
        "runtime_evidence:tool",
        "model_contribution:executor",
        "model_contribution:judge",
        "model_contribution:reviewer",
    )
    assert json.loads(projection.acceptance_criteria_json[0]) == {
        "criterion_id": "criterion-1",
        "required": True,
    }


def test_snapshot_rejects_unknown_causal_evidence_reference() -> None:
    with pytest.raises(ValidationError, match="unknown parent"):
        build_runtime_evidence_snapshot(
            request_id="broken",
            objective="broken",
            runtime_evidence=(
                runtime_evidence_item("ev-broken", "test", {}, parent_evidence_ids=("missing",)),
            ),
        )


def test_all_seven_roles_project_directly_from_one_snapshot_with_stage_allowlists() -> None:
    source = snapshot()
    projections = {
        role: project_role_context(source, role, stage="fanout")
        for role in ("reasoner", "planner", "frontier_a", "executor")
    }
    projections["executor_fan_in"] = project_role_context(
        source,
        "executor",
        stage="fan_in",
        causal_parent_attempt_ids=("reasoner-a001", "planner-a001", "frontier-a-a001"),
        join_node_id="n05_join",
    )
    projections["reviewer"] = project_role_context(source, "reviewer", stage="review")
    projections["judge"] = project_role_context(source, "judge", stage="review")
    projections["frontier_b"] = project_role_context(source, "frontier_b", stage="adjudication")

    assert {projection.provenance.snapshot_id for projection in projections.values()} == {
        source.snapshot_id
    }
    for role in ("reasoner", "planner", "frontier_a", "executor"):
        assert projections[role].model_contributions == ()
    assert [item.role for item in projections["executor_fan_in"].model_contributions] == [
        "frontier_a",
        "planner",
        "reasoner",
    ]
    with pytest.raises(ValueError, match="unsupported role projection stage"):
        project_role_context(source, "planner", stage="review")


def test_snapshot_rejects_unknown_model_evidence_and_evidence_cycles() -> None:
    with pytest.raises(ValidationError, match="unknown runtime Evidence"):
        build_runtime_evidence_snapshot(
            request_id="broken-contribution",
            objective="broken",
            model_contributions=(
                model_contribution(
                    "contrib-broken",
                    "executor",
                    {},
                    source_attempt_id="executor-a001",
                    evidence_ids=("missing",),
                ),
            ),
        )


def test_raw_context_payload_must_be_canonical_redacted_json() -> None:
    with pytest.raises(ValidationError, match="valid JSON"):
        CanonicalRequestInput(input_id="bad", payload_json="not-json")
    with pytest.raises(ValidationError, match="canonical redacted JSON"):
        CanonicalRequestInput(input_id="spaced", payload_json='{ "value": 1 }')
    with pytest.raises(ValidationError, match="canonical redacted JSON"):
        CanonicalRequestInput(
            input_id="secret",
            payload_json='{"api_key":"do-not-accept-unredacted"}',
        )

    with pytest.raises(ValidationError, match="contains a cycle"):
        build_runtime_evidence_snapshot(
            request_id="cyclic",
            objective="cyclic",
            runtime_evidence=(
                runtime_evidence_item("ev-a", "tool", {}, parent_evidence_ids=("ev-b",)),
                runtime_evidence_item("ev-b", "test", {}, parent_evidence_ids=("ev-a",)),
            ),
        )


def test_snapshot_rejects_aggregate_context_above_byte_ceiling() -> None:
    payload = "x" * (MAX_CONTEXT_BYTES // 3)
    with pytest.raises(ValidationError, match="runtime context exceeds"):
        build_runtime_evidence_snapshot(
            request_id="oversized",
            objective="bounded",
            request_inputs=tuple(
                canonical_request_input(f"input-{index}", {"content": payload})
                for index in range(3)
            ),
        )


def test_role_targets_bound_discretionary_evidence_without_dropping_original_contract() -> None:
    source = build_runtime_evidence_snapshot(
        request_id="budgeted",
        objective="original objective",
        request_inputs=(canonical_request_input("input", {"content": "original request"}),),
        request_constraints=("hard constraint",),
        acceptance_criteria=("acceptance criterion",),
        runtime_evidence=tuple(
            runtime_evidence_item(f"evidence-{index:03d}", "tool", {"output": "x" * 20_000})
            for index in range(30)
        ),
    )

    planner = project_role_context(source, "planner", stage="fanout")
    executor = project_role_context(source, "executor", stage="fanout")

    assert len(planner.model_dump_json().encode()) <= ROLE_CONTEXT_TARGET_BYTES["planner"]
    assert len(executor.model_dump_json().encode()) <= ROLE_CONTEXT_TARGET_BYTES["executor"]
    assert len(planner.runtime_evidence) < len(executor.runtime_evidence)
    assert planner.request_inputs[0].payload()["content"] == "original request"
    assert json.loads(planner.request_constraints_json[0]) == "hard constraint"
    assert json.loads(planner.acceptance_criteria_json[0]) == "acceptance criterion"
    assert planner.provenance.excluded_evidence_ids


def test_reasoner_target_drops_old_oversized_inputs_and_keeps_current_objective() -> None:
    source = build_runtime_evidence_snapshot(
        request_id="oversized-history",
        objective="current objective",
        request_inputs=tuple(
            canonical_request_input(f"input-{index}", {"content": "x" * 30_000})
            for index in range(8)
        ),
    )

    reasoner = project_role_context(source, "reasoner", stage="fanout")

    assert len(reasoner.model_dump_json().encode()) <= ROLE_CONTEXT_TARGET_BYTES["reasoner"]
    assert reasoner.objective == "current objective"
    assert reasoner.request_inputs[-1].input_id == "input-7"


def test_role_projection_deduplicates_harness_messages_with_new_ids() -> None:
    source = build_runtime_evidence_snapshot(
        request_id="repeated-harness",
        objective="current objective",
        request_inputs=(
            canonical_request_input(
                "old", {"id": "old", "type": "message", "role": "developer", "content": "same"}
            ),
            canonical_request_input(
                "new", {"id": "new", "type": "message", "role": "developer", "content": "same"}
            ),
            canonical_request_input("user", {"role": "user", "content": "current objective"}),
        ),
    )

    projection = project_role_context(source, "executor", stage="fanout")

    assert [item.input_id for item in projection.request_inputs] == ["new", "user"]
