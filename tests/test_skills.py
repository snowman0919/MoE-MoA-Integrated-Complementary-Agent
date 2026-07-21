from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.config import Settings
from dgx_moa.controller import Controller
from dgx_moa.skills import (
    RuntimeSkill,
    SkillCandidateEvaluation,
    SkillPattern,
    SkillProvenance,
    SkillQuery,
    SkillRegistry,
    SkillValidation,
)
from dgx_moa.state import SessionState, StateStore
from pydantic import ValidationError


def skill(**overrides: object) -> RuntimeSkill:
    payload: dict[str, object] = {
        "skill_id": "python-test-debugging",
        "version": "1.0.0",
        "name": "python-test-debugging",
        "description": "Diagnose deterministic Python pytest failures",
        "state": "experimental",
        "store": "generated",
        "domains": ["testing", "debugging"],
        "task_types": ["debugging"],
        "languages": ["python"],
        "frameworks": ["pytest"],
        "failure_fingerprints": ["TEST_FAILURE:assertion"],
        "inputs": ["failure output"],
        "outputs": ["verified patch"],
        "procedure": ["Reproduce the smallest failing test", "Apply one bounded correction"],
        "allowed_tools": ["shell", "apply_patch"],
        "recommended_agents": ["reviewer"],
        "provenance": {
            "source": "runtime",
            "created_by": "executor",
            "source_trace_ids": ["trace-1"],
        },
    }
    payload.update(overrides)
    return RuntimeSkill.model_validate(payload)


def test_runtime_skill_must_start_experimental() -> None:
    with pytest.raises(ValidationError, match="must start experimental"):
        skill(state="active", store="core")


def test_passed_validation_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="requires evidence"):
        SkillValidation(status="passed")


def test_registry_versions_are_immutable(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    original = skill()
    path = registry.put(original)

    assert registry.put(original) == path
    changed = skill(description="silently overwrite the existing version")
    with pytest.raises(ValueError, match="immutable"):
        registry.put(changed)


def test_registry_rejects_path_traversal_identifiers(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)

    with pytest.raises(KeyError, match="invalid Skill"):
        registry.get("../escape", "1.0.0")


def test_core_successor_requires_approval(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    core = skill(
        state="active",
        store="core",
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-1"),
    )
    registry.put(core)

    with pytest.raises(PermissionError, match="explicit approval"):
        registry.successor(core.skill_id, core.version, created_by="executor")

    successor = registry.successor(
        core.skill_id,
        core.version,
        procedure=["Run the approved replacement procedure"],
        created_by="operator",
        approval_id="a-2",
    )
    assert successor.version == "1.0.1"
    assert successor.state == "experimental"
    assert core.procedure == registry.get(core.skill_id, core.version).procedure


def test_promotion_requires_validation_and_approval(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    registry.put(skill())

    with pytest.raises(ValueError, match="passed validation"):
        registry.promote(
            "python-test-debugging", "1.0.0", approval_id="approval-1", created_by="operator"
        )

    validated = skill(
        version="1.0.1",
        validation=SkillValidation(
            status="passed", evidence_ids=["test-exit-0"], validated_at="2026-07-22T00:00:00Z"
        ),
    )
    registry.put(validated)
    registry.record_canary(
        validated.skill_id,
        validated.version,
        outcome="helpful",
        evidence_ids=["canary-exit-0"],
        activated_by="executor",
    )
    promoted = registry.promote(
        validated.skill_id,
        validated.version,
        approval_id="approval-2",
        created_by="operator",
    )

    assert promoted.state == "active"
    assert promoted.store == "core"
    assert promoted.version == "1.1.1"
    assert promoted.provenance.parent_versions == ["python-test-debugging@1.0.1"]


def test_search_returns_bounded_active_matches_with_reasons(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    active = skill(
        state="active",
        store="core",
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-1"),
        validation=SkillValidation(status="passed", evidence_ids=["e-1"]),
    )
    registry.put(active)
    registry.put(skill(skill_id="unused-experiment", name="unused-experiment"))
    registry.record_outcome(active.skill_id, active.version, "selected")
    registry.record_outcome(
        active.skill_id,
        active.version,
        "succeeded",
        token_delta=-12,
        quality_gain=0.2,
        task_covered=True,
    )
    registry.record_outcome(active.skill_id, active.version, "frontier_correction")
    registry.record_outcome(active.skill_id, active.version, "reviewer_finding")

    matches = registry.search(
        SkillQuery(
            text="debug Python pytest assertion",
            task_type="debugging",
            language="python",
            framework="pytest",
            failure_fingerprints=["TEST_FAILURE:assertion"],
        ),
        limit=1,
    )

    assert [item.skill.skill_id for item in matches] == [active.skill_id]
    assert "task_type_match" in matches[0].reasons
    assert any(reason.startswith("historical_reliability:") for reason in matches[0].reasons)
    assert registry.metrics(active.skill_id, active.version).selected == 1
    assert registry.metrics(active.skill_id, active.version).succeeded == 1
    assert registry.metrics(active.skill_id, active.version).average_token_delta == -12
    assert registry.metrics(active.skill_id, active.version).frontier_corrections == 1
    assert registry.metrics(active.skill_id, active.version).reviewer_findings == 1
    assert registry.metrics(active.skill_id, active.version).task_coverage == 1


def test_search_limit_is_strict(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="between 1 and 10"):
        registry.search(SkillQuery(text="anything"), limit=11)


def test_executor_alone_selects_and_activates_bounded_skills(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path / "skills")
    active = skill(
        state="active",
        store="core",
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-1"),
        validation=SkillValidation(status="passed", evidence_ids=["e-1"]),
    )
    registry.put(active)
    settings = Settings(
        auth_enabled=False,
        state_db=tmp_path / "state.db",
        runtime_skills={
            "enabled": True,
            "root": tmp_path / "skills",
            "retrieval_limit": 1,
            "max_context_characters": 2_000,
        },
    )
    store = StateStore(settings.state_db)
    controller = Controller(settings, store, object(), skills=registry)  # type: ignore[arg-type]
    state = SessionState(
        session_id="skill-session",
        objective="Debug a Python pytest assertion failure",
        request_class="debugging",
    )

    controller.select_executor_skills(
        state, {"task_type": "debugging", "language": "python", "framework": "pytest"}
    )

    assert len(state.skill_selections) == 1
    assert state.skill_selections[0]["activation_authority"] == "executor"
    assert state.skill_selections[0]["skill_version"] == "1.0.0"
    assert state.skill_selections[0]["result"] == "unknown"
    assert state.skill_selections[0]["requested_tool_subset"] == ["shell", "apply_patch"]
    assert "activated_skills" in controller.role_context("executor", state, "")
    assert "activated_skills" not in controller.role_context("reasoner", state, "")
    events = store.events(state.session_id)
    assert events[-1]["event_type"] == "executor_skills_selected"


def test_corrupt_skill_isolated_from_executor_request(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path / "skills")
    corrupt = tmp_path / "skills" / "core" / "bad-skill" / "1.0.0.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not-json")
    settings = Settings(
        auth_enabled=False,
        state_db=tmp_path / "state.db",
        runtime_skills={"enabled": True, "root": tmp_path / "skills"},
    )
    store = StateStore(settings.state_db)
    controller = Controller(settings, store, object(), skills=registry)  # type: ignore[arg-type]
    state = SessionState(session_id="corrupt-skill", objective="bad skill")

    controller.select_executor_skills(state, {})

    assert state.skill_selections == []
    assert state.observability_degraded is True
    assert store.events(state.session_id)[-1]["event_type"] == "skill_selection_failed"


def test_skill_pack_import_is_experimental_and_hash_verified(tmp_path: Path) -> None:
    source = SkillRegistry(tmp_path / "source")
    source.put(skill())
    pack = source.export_pack(
        tmp_path / "pack.zip",
        pack_id="python-pack",
        skill_versions=[("python-test-debugging", "1.0.0")],
        compatibility={"gateway": ">=0.1.0"},
    )
    target = SkillRegistry(tmp_path / "target")

    imported = target.import_pack(pack)

    assert len(imported) == 1
    assert imported[0].source == "imported"
    assert imported[0].state == "experimental"
    assert imported[0].store == "experimental"


def test_skill_pack_invalid_signature_is_blocked(tmp_path: Path) -> None:
    source = SkillRegistry(tmp_path / "source")
    source.put(skill())
    pack = source.export_pack(
        tmp_path / "signed.zip",
        pack_id="signed-pack",
        skill_versions=[("python-test-debugging", "1.0.0")],
        signer=lambda payload: ("operator-key", f"signature-{len(payload)}"),
    )
    target = SkillRegistry(tmp_path / "target")

    with pytest.raises(PermissionError, match="verification failed"):
        target.import_pack(pack, require_signature=True, verifier=lambda key, data, sig: False)


def test_skill_rollback_creates_new_active_version_and_preserves_history(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    prior = skill(
        version="1.0.0",
        state="active",
        store="core",
        validation=SkillValidation(status="passed", evidence_ids=["prior-pass"]),
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-1"),
    )
    current = skill(
        version="1.1.0",
        state="active",
        store="core",
        procedure=["A regressed replacement"],
        validation=SkillValidation(status="passed", evidence_ids=["current-pass"]),
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-2"),
    )
    registry.put(prior)
    registry.put(current)

    rolled_back = registry.rollback(
        prior.skill_id,
        current.version,
        prior.version,
        approval_id="rollback-1",
        created_by="operator",
    )

    assert rolled_back.version == "1.2.0"
    assert rolled_back.procedure == prior.procedure
    assert registry.get(prior.skill_id, current.version).procedure == current.procedure
    assert registry.metrics(current.skill_id, current.version).rollbacks == 1


def test_recurring_pattern_generates_only_an_experimental_immutable_draft(
    tmp_path: Path,
) -> None:
    registry = SkillRegistry(tmp_path)
    pattern = SkillPattern(
        pattern_id="repeat-mcp-fallback",
        kind="failure_fingerprint",
        occurrences=3,
        evidence_ids=["trace-1", "trace-2", "trace-3"],
        description="Use the native filesystem after an unavailable MCP server",
        procedure=["Classify the MCP failure", "Use the bounded native filesystem fallback"],
        failure_fingerprints=["MCP_SERVER_UNAVAILABLE"],
        allowed_tools=["read_file"],
    )

    draft = registry.draft_from_pattern(pattern, created_by="runtime-detector")

    assert draft.state == "experimental"
    assert draft.store == "generated"
    assert draft.validation.status == "unvalidated"
    assert registry.list_skills(states={"active"}) == []
    with pytest.raises(ValueError, match="distinct recurring evidence"):
        SkillPattern(
            pattern_id="not-recurring",
            kind="task_class",
            occurrences=2,
            evidence_ids=["same", "same"],
            description="invalid synthetic pattern",
            procedure=["do nothing"],
        )


def test_generated_skill_evaluation_requires_all_checks_and_frontier_when_high_impact(
    tmp_path: Path,
) -> None:
    registry = SkillRegistry(tmp_path)
    draft = registry.draft_from_pattern(
        SkillPattern(
            pattern_id="repeat-review",
            kind="review_checklist",
            occurrences=2,
            evidence_ids=["trace-a", "trace-b"],
            description="Repeat a verified review checklist",
            procedure=["Run the bounded checklist"],
        ),
        created_by="runtime-detector",
    )
    failed, _ = registry.evaluate_candidate(
        draft.skill_id,
        draft.version,
        evaluator=lambda _: SkillCandidateEvaluation(
            isolated_validation=True,
            historical_replay=True,
            regression_evaluation=True,
            reviewer_inspection=True,
            high_impact=True,
            frontier_review=False,
            evidence_ids=["evaluation-failed"],
        ),
        created_by="isolated-evaluator",
    )
    assert failed.validation.status == "failed"
    with pytest.raises(ValueError, match="passed validation"):
        registry.promote(
            failed.skill_id,
            failed.version,
            approval_id="approval-must-not-help",
            created_by="operator",
        )

    passed, evaluation = registry.evaluate_candidate(
        failed.skill_id,
        failed.version,
        evaluator=lambda _: SkillCandidateEvaluation(
            isolated_validation=True,
            historical_replay=True,
            regression_evaluation=True,
            reviewer_inspection=True,
            high_impact=True,
            frontier_review=True,
            evidence_ids=["isolated", "replay", "regression", "reviewer", "frontier"],
        ),
        created_by="isolated-evaluator",
    )
    assert evaluation.passed is True
    assert passed.validation.status == "passed"
    assert passed.version == "0.1.2"
    assert registry.list_skills(states={"active"}) == []
    with pytest.raises(ValueError, match="helpful canary"):
        registry.promote(
            passed.skill_id,
            passed.version,
            approval_id="approval-before-canary",
            created_by="operator",
        )
    registry.record_canary(
        passed.skill_id,
        passed.version,
        outcome="harmful",
        evidence_ids=["canary-regression"],
        activated_by="executor",
    )
    with pytest.raises(ValueError, match="helpful canary"):
        registry.promote(
            passed.skill_id,
            passed.version,
            approval_id="approval-after-harm",
            created_by="operator",
        )
    registry.record_canary(
        passed.skill_id,
        passed.version,
        outcome="helpful",
        evidence_ids=["canary-success"],
        activated_by="executor",
    )
    promoted = registry.promote(
        passed.skill_id,
        passed.version,
        approval_id="approval-after-canary",
        created_by="operator",
    )
    assert promoted.state == "active"
    assert registry.canary_summary(passed.skill_id, passed.version) == {
        "helpful": 1,
        "neutral": 0,
        "harmful": 1,
    }


def test_skill_lifecycle_is_versioned_and_governed(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    core = skill(
        source="core",
        state="active",
        store="core",
        provenance=SkillProvenance(source="human", created_by="operator", approval_id="a-1"),
    )
    registry.put(core)
    with pytest.raises(PermissionError, match="core Skill"):
        registry.transition_lifecycle(
            core.skill_id, core.version, "deprecated", created_by="runtime"
        )
    deprecated = registry.transition_lifecycle(
        core.skill_id,
        core.version,
        "deprecated",
        created_by="operator",
        approval_id="deprecate-1",
    )
    assert deprecated.version == "1.0.1"
    assert registry.get(core.skill_id, core.version).state == "active"

    generated = skill(skill_id="generated-lifecycle")
    registry.put(generated)
    disabled = registry.transition_lifecycle(
        generated.skill_id,
        generated.version,
        "disabled",
        created_by="weekly-policy",
        policy_permits=True,
    )
    archived = registry.transition_lifecycle(
        disabled.skill_id,
        disabled.version,
        "archived",
        created_by="weekly-policy",
        policy_permits=True,
    )
    assert disabled.state == "disabled"
    assert archived.state == "archived"
