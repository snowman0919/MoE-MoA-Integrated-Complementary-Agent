from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from dgx_moa.state import StateStore
from dgx_moa.training import (
    ContentStore,
    TrainingCandidate,
    TrainingCollector,
    TrainingEvent,
    TrainingStore,
    assess_candidate,
    candidate_from_trace,
    candidates_from_trace,
    near_duplicate,
    sanitize,
)
from pydantic import ValidationError


def eligible_trace() -> dict:  # type: ignore[type-arg]
    return {
        "session_id": "request-1",
        "training_eligibility": "eligible",
        "objective": "Fix the bounded test",
        "verified_state": ["pytest passed"],
        "assistant_tool_call": {"name": "apply_patch"},
        "completion_evidence": {"tests": "evidence-1"},
        "final_status": "completed",
        "review_outcome": {"status": "approved"},
        "agent_invocations": [],
        "failure_classification": {},
        "metrics": {},
    }


def test_content_store_is_addressed_deduplicated_and_verified(tmp_path: Path) -> None:
    store = ContentStore(tmp_path / "objects")
    first = store.put({"hello": "world"})
    second = store.put({"hello": "world"})

    assert first == second
    assert store.get(first) == {"hello": "world"}
    with pytest.raises(KeyError, match="invalid content"):
        store.get("../escape")
    with pytest.raises(ValueError, match="size limit"):
        ContentStore(tmp_path / "bounded", maximum_bytes=2).put({"too": "large"})


def test_sanitizer_handles_synthetic_secrets_entropy_email_and_phone() -> None:
    result = sanitize(
        {
            "authorization": "Bearer synthetic-value",
            "body": "api_key=syntheticSecret1234567890 user@example.test +82 10-1234-5678",
        }
    )

    serialized = str(result.value)
    assert "syntheticSecret" not in serialized
    assert "user@example" not in serialized
    assert "1234-5678" not in serialized
    assert result.secret_redactions >= 1
    assert result.pii_redactions == 2


def test_unknown_repository_optout_and_external_license_fail_closed() -> None:
    trace = eligible_trace()
    trace["agent_invocations"] = [{"role": "frontier"}]

    candidate = candidate_from_trace(
        trace,
        repository_policy="unknown",
        request_opt_out=True,
        external_output_permitted=False,
    )

    assert candidate.training_eligible is False
    assert candidate.quality_tier == "rejected"
    assert "training_opt_out" in candidate.transformations
    assert "external_output_license_unverified" in candidate.transformations
    assert candidate.messages[0]["content"] == "[EXCLUDED]"


def test_evidence_grounded_success_becomes_role_specific_gold_candidate() -> None:
    candidate = candidate_from_trace(
        eligible_trace(), repository_policy="training_allowed", external_output_permitted=False
    )

    assert candidate.role_target == "executor"
    assert candidate.candidate_type == "sft"
    assert candidate.quality_tier == "gold"
    assert candidate.training_eligible is True
    assert candidate.evidence_summary == ["evidence-1"]


def test_trace_material_produces_separate_role_routing_tool_and_skill_candidates() -> None:
    trace = eligible_trace() | {
        "reasoner_contributions": [{"conclusion": "bounded"}],
        "planner_output": [{"step": "test"}],
        "agent_artifacts": [{"role": "reviewer", "output": {"status": "approved"}}],
        "orchestration_decisions": [{"required_agents": ["reviewer"]}],
        "tool_executions": [{"tool_name": "pytest", "exit_code": 0}],
        "evidence_graph": {
            "nodes": [{"node_type": "skill_selection", "payload": {"skill_id": "python-test"}}]
        },
    }

    candidates = candidates_from_trace(trace, repository_policy="training_allowed")

    assert {(item.role_target, item.candidate_type) for item in candidates} == {
        ("executor", "sft"),
        ("reasoner", "sft"),
        ("planner", "sft"),
        ("reviewer", "review"),
        ("executor", "routing"),
        ("executor", "tool_use"),
        ("executor", "skill"),
    }


def test_preference_candidate_requires_observable_grounding() -> None:
    with pytest.raises(ValidationError, match="grounding evidence"):
        TrainingCandidate(
            candidate_type="preference",
            source_request_ids=["request-1"],
            role_target="executor",
            accepted_answer="good",
            rejected_answers=["bad"],
        )


def test_training_store_is_separate_append_only_and_tombstone_aware(tmp_path: Path) -> None:
    objects = ContentStore(tmp_path / "objects")
    store = TrainingStore(tmp_path / "training.db", objects, minimum_free_bytes=0)
    event = TrainingEvent(
        request_id="request-1",
        task_id="task-1",
        role="executor",
        event_type="agent_output",
        model_provider="local",
        model_identifier="executor",
        model_revision="abc",
        prompt_template_version="1",
        policy_version="1",
        status="success",
        training_eligibility="eligible",
    )
    candidate = candidate_from_trace(eligible_trace(), repository_policy="training_allowed")

    store.append_event(event)
    assert store.append_candidate(candidate) is True
    assert store.append_candidate(candidate) is False
    clone = candidate.model_copy(update={"candidate_id": "cand_different"})
    assert store.append_candidate(clone) is False
    assert len(store.packageable_candidates()) == 1
    assert (
        len(
            store.packageable_candidates(
                created_from="2000-01-01T00:00:00+00:00",
                created_before="9999-01-01T00:00:00+00:00",
            )
        )
        == 1
    )
    assert store.packageable_candidates(created_before="2000-01-01T00:00:00+00:00") == []
    store.tombstone("request-1", "user opt-out")
    assert store.excluded("request-1") is True
    assert store.packageable_candidates() == []
    with pytest.raises(PermissionError, match="tombstoned"):
        store.append_candidate(candidate.model_copy(update={"candidate_id": "cand_new"}))


def test_training_store_integrity_and_atomic_backup_detect_content_corruption(
    tmp_path: Path,
) -> None:
    objects = ContentStore(tmp_path / "objects")
    store = TrainingStore(tmp_path / "training.db", objects, minimum_free_bytes=0)
    candidate = candidate_from_trace(eligible_trace(), repository_policy="training_allowed")
    assert store.append_candidate(candidate) is True

    assert store.verify_integrity() == {"database_ok": True, "verified_objects": 1}
    backup = store.backup(tmp_path / "backups/training.db")
    with sqlite3.connect(backup) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    digest = objects.put(candidate.model_dump(mode="json"))
    object_path = tmp_path / "objects/sha256" / digest[:2] / digest[2:4] / f"{digest}.json.gz"
    object_path.write_bytes(b"synthetic corruption")
    with pytest.raises(ValueError, match="content integrity"):
        store.verify_integrity()


def test_training_candidate_review_is_transactional_audited_and_revocable(
    tmp_path: Path,
) -> None:
    store = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    candidate = candidate_from_trace(eligible_trace(), repository_policy="training_allowed")
    assert store.append_candidate(candidate) is True

    approved = store.transition_candidate(
        candidate.candidate_id,
        "approved",
        actor="synthetic-reviewer",
        reason="synthetic evidence passed",
    )
    assert approved.review_state == "approved"
    assert store.candidate(candidate.candidate_id).review_state == "approved"
    assert store.review_history(candidate.candidate_id)[0]["to_state"] == "approved"
    with pytest.raises(ValueError, match="invalid review transition"):
        store.transition_candidate(
            candidate.candidate_id,
            "sanitized",
            actor="synthetic-reviewer",
            reason="invalid rollback",
        )

    store.transition_candidate(
        candidate.candidate_id,
        "packaged",
        actor="weekly-packager",
        reason="synthetic package",
    )
    store.tombstone("request-1", "synthetic revocation")
    assert store.candidate(candidate.candidate_id).review_state == "revoked"
    assert store.packageable_candidates() == []


def test_ineligible_training_candidate_cannot_be_approved(tmp_path: Path) -> None:
    store = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    candidate = candidate_from_trace(
        eligible_trace(), repository_policy="training_denied"
    ).model_copy(update={"review_state": "sanitized"})
    assert store.append_candidate(candidate) is True
    with pytest.raises(PermissionError, match="ineligible"):
        store.transition_candidate(
            candidate.candidate_id,
            "approved",
            actor="synthetic-reviewer",
            reason="must fail closed",
        )


def test_repository_exclusion_is_hashed_and_collector_fails_closed(tmp_path: Path) -> None:
    operational = StateStore(tmp_path / "operational.db")
    training = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    repository = {"workspace_id": "synthetic-repository", "current_commit": "abc123"}
    identity_hash = training.exclude_repository(repository, "synthetic owner opt-out")
    assert len(identity_hash) == 64
    assert training.repository_excluded(repository) is True

    collector = TrainingCollector(training, operational)
    collector.collect(eligible_trace() | {"repository_identity": repository})

    assert collector.metrics["excluded"] == 1
    assert training.packageable_candidates() == []


def test_persistent_user_exclusion_is_hashed_and_applied_by_collector(tmp_path: Path) -> None:
    operational = StateStore(tmp_path / "operational.db")
    training = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    subject_hash = training.exclude_user("synthetic-user", "synthetic opt-out")
    assert len(subject_hash) == 64
    assert training.user_excluded(subject_hash) is True

    collector = TrainingCollector(training, operational)
    collector.collect(
        eligible_trace()
        | {
            "metrics": {
                "repository_training_policy": "training_allowed",
                "training_subject_hash": subject_hash,
            }
        }
    )

    assert collector.metrics["excluded"] == 1
    assert training.packageable_candidates() == []


def test_retention_is_dry_run_first_and_respects_holds_and_deletion_workflow(
    tmp_path: Path,
) -> None:
    store = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    event = TrainingEvent(
        request_id="request-retention",
        task_id="task-retention",
        role="executor",
        event_type="agent_output",
        model_provider="local",
        model_identifier="executor",
        model_revision="abc",
        prompt_template_version="1",
        policy_version="1",
        status="success",
        training_eligibility="eligible",
    )
    candidate = candidate_from_trace(
        eligible_trace() | {"session_id": "request-retention"},
        repository_policy="training_allowed",
    )
    store.append_event(event)
    assert store.append_candidate(candidate) is True
    store.tombstone("request-retention", "synthetic deletion request")

    held = store.purge_retention(
        event_before="9999-01-01T00:00:00+00:00",
        candidate_before="9999-01-01T00:00:00+00:00",
    )
    assert held == {"apply": False, "event_count": 0, "candidate_count": 0, "held_count": 2}

    store.resolve_deletion_request("request-retention")
    hold_id = store.place_hold(
        "candidate",
        candidate.candidate_id,
        kind="legal",
        reason="synthetic legal hold",
    )
    partially_held = store.purge_retention(
        event_before="9999-01-01T00:00:00+00:00",
        candidate_before="9999-01-01T00:00:00+00:00",
    )
    assert partially_held["event_count"] == 1
    assert partially_held["candidate_count"] == 0
    store.release_hold(hold_id)

    dry_run = store.purge_retention(
        event_before="9999-01-01T00:00:00+00:00",
        candidate_before="9999-01-01T00:00:00+00:00",
    )
    assert dry_run["event_count"] == 1
    assert dry_run["candidate_count"] == 1
    assert store.candidate(candidate.candidate_id).review_state == "revoked"

    applied = store.purge_retention(
        event_before="9999-01-01T00:00:00+00:00",
        candidate_before="9999-01-01T00:00:00+00:00",
        apply=True,
    )
    assert applied | {"apply": False} == dry_run
    with pytest.raises(KeyError, match="unknown training candidate"):
        store.candidate(candidate.candidate_id)


def test_near_duplicate_uses_normalized_content() -> None:
    assert near_duplicate("Fix TEST 123 now", "fix test 123 now!") is True
    assert near_duplicate("python api", "fpga timing") is False


def test_candidate_quality_detects_tool_loop_and_conversation_inconsistency() -> None:
    candidate = TrainingCandidate(
        candidate_type="tool_use",
        source_request_ids=["synthetic-quality"],
        role_target="executor",
        messages=[{"role": "user", "content": "도구를 실행해"}],
        expected_tool_calls=[{"id": "call-1"}],
        tool_results=[{"tool_call_id": "call-other"}],
        evidence_summary=["synthetic evidence"],
        quality_labels={
            "loop_transitions": [
                {"state_before": "start", "state_after": "testing"},
                {"state_before": "editing", "state_after": "done"},
            ]
        },
        review_state="approved",
        quality_tier="silver",
        training_eligible=True,
    )

    report = assess_candidate(candidate)

    assert report.language == "ko"
    assert "tool_call_result_mismatch" in report.errors
    assert "loop_transition_mismatch" in report.errors


def test_collector_creates_separate_events_and_candidate_without_raw_duplication(
    tmp_path: Path,
) -> None:
    operational = StateStore(tmp_path / "operational.db")
    training = TrainingStore(
        tmp_path / "training.db", ContentStore(tmp_path / "objects"), minimum_free_bytes=0
    )
    collector = TrainingCollector(training, operational)
    trace = eligible_trace() | {
        "task_id": "task-1",
        "model_revisions": {"executor": {"repository": "test/executor", "revision": "abc"}},
        "agent_invocations": [{"role": "executor", "status": "completed", "latency_ms": 2}],
        "evidence_graph": {"nodes": [{"node_id": "evidence-1"}]},
        "metrics": {"repository_training_policy": "training_allowed"},
    }

    collector.collect(trace)

    assert collector.metrics == {
        "events": 1,
        "candidates": 1,
        "excluded": 0,
        "failures": 0,
        "secret_redactions": 0,
        "privacy_exclusions": 0,
        "license_exclusions": 0,
    }
    assert len(training.packageable_candidates()) == 1


def test_training_capacity_failure_does_not_escape_to_request_runtime(tmp_path: Path) -> None:
    operational = StateStore(tmp_path / "operational.db")
    training = TrainingStore(
        tmp_path / "training.db",
        ContentStore(tmp_path / "objects"),
        minimum_free_bytes=10**30,
    )
    collector = TrainingCollector(training, operational)

    collector.collect(eligible_trace())

    assert collector.metrics["failures"] == 1
    assert operational.events("request-1")[-1]["event_type"] == "training_collection_failed"
