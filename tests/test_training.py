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
from dgx_moa.weekly import candidate_path
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


def test_sanitizer_preserves_routing_cost_measurements() -> None:
    result = sanitize(
        {
            "remote_api_cost_per_million_tokens_usd": 1.25,
            "input_tokens": 42,
            "access_token": "synthetic-secret",
        }
    )

    assert result.value == {
        "remote_api_cost_per_million_tokens_usd": 1.25,
        "input_tokens": 42,
        "access_token": "[REDACTED]",
    }
    assert result.secret_redactions == 1


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
    assert {
        "acceptance_criteria_coverage",
        "test_status",
        "build_status",
        "review_severity",
        "frontier_verdict",
        "judge_verdict",
        "user_feedback",
        "tool_success_rate",
        "repair_count",
        "iteration_count",
        "progress_score",
        "final_confidence_state",
    }.issubset(candidate.quality_labels)


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


def test_permitted_remote_judge_trace_produces_categorical_role_datasets() -> None:
    trace = eligible_trace() | {
        "evaluations": [
            {
                "evaluator_type": "opencode_go",
                "evidence_references": ["test-1"],
                "later_confirmation": "false_approval",
                "result": {
                    "verdict": "approve",
                    "criteria": {"test_consistency": "pass"},
                    "findings": [
                        {
                            "severity": "important",
                            "category": "unsupported_claim",
                            "description": "raw provider prose must not be copied",
                        }
                    ],
                    "required_edits": [
                        {
                            "operation": "replace",
                            "target": "raw target",
                            "instruction": "raw provider instruction",
                        }
                    ],
                },
            }
        ]
    }

    candidates = candidates_from_trace(
        trace,
        repository_policy="training_allowed",
        external_output_permitted=True,
    )
    judge = [item for item in candidates if item.candidate_type == "judge"]

    assert {item.quality_labels["judge_dataset"] for item in judge} == {
        "verdicts",
        "findings",
        "corrections",
        "false-approvals",
    }
    assert all(item.role_target == "judge" and item.training_eligible for item in judge)
    serialized = str([item.accepted_answer for item in judge])
    assert "raw provider prose" not in serialized
    assert "raw provider instruction" not in serialized
    assert "unsupported_claim" in serialized


def test_specialist_routing_trace_projects_to_weekly_routing_datasets() -> None:
    trace = eligible_trace() | {
        "specialist_routing": [
            {
                "specialist_role": "planner",
                "residency_state": "LOADING",
                "queue_state": {"local_queue_delay_seconds": 0},
                "selected_provider": "remote",
                "routing_reason": "local_not_ready",
                "warmup_decision": "started",
                "actual_completion_latency_seconds": 20.8,
                "remote_cost_usd": 0,
                "quality_outcome": "approved",
                "task_outcome": "completed",
            }
        ],
        "specialist_eviction_decisions": [
            {
                "role": "planner",
                "residency_state": "READY",
                "would_unload": False,
                "reason": "minimum_residency",
            }
        ],
    }

    candidates = candidates_from_trace(trace, repository_policy="training_allowed")
    paths = {
        candidate_path(candidate)
        for candidate in candidates
        if candidate.candidate_type == "routing"
    }

    assert paths == {
        "datasets/routing/specialist-residency-routing.jsonl",
        "datasets/routing/local-vs-remote-routing.jsonl",
        "datasets/routing/warmup-decisions.jsonl",
        "datasets/routing/eviction-decisions.jsonl",
        "datasets/routing/latency-prediction.jsonl",
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


def test_successful_repair_produces_loop_and_grounded_preference_candidates() -> None:
    trace = eligible_trace() | {
        "engineering_loop": {
            "loop_id": "loop-1",
            "termination_reason": "SUCCESS",
            "observed_evidence_ids": ["test-evidence"],
        },
        "failures": [
            {
                "failure_class": "TEST_FAILURE",
                "attempted_strategy": "repeat unchanged command",
            }
        ],
    }

    candidates = candidates_from_trace(trace, repository_policy="training_allowed")
    loop = next(item for item in candidates if item.candidate_type == "loop")
    preference = next(item for item in candidates if item.candidate_type == "preference")

    assert loop.evidence_summary == ["test-evidence"]
    assert loop.accepted_answer["termination_reason"] == "SUCCESS"
    assert preference.accepted_answer == {"name": "apply_patch"}
    assert preference.rejected_answers[0][0]["failure_class"] == "TEST_FAILURE"
    assert preference.evidence_summary == ["evidence-1"]
    assert "failed_repair_preference" in preference.transformations


@pytest.mark.parametrize(
    "trace_update",
    [
        {"final_status": "failed"},
        {"completion_evidence": {}, "review_outcome": {"status": "rejected"}},
    ],
)
def test_failed_or_ungrounded_answer_does_not_produce_repair_preference(
    trace_update: dict,  # type: ignore[type-arg]
) -> None:
    trace = (
        eligible_trace()
        | trace_update
        | {
            "failures": [{"failure_class": "TEST_FAILURE"}],
        }
    )

    candidates = candidates_from_trace(trace, repository_policy="training_allowed")

    assert all(item.candidate_type != "preference" for item in candidates)


def test_derived_candidates_preserve_base_privacy_counts() -> None:
    trace = eligible_trace() | {
        "objective": "api_key=syntheticSecret1234567890",
        "engineering_loop": {"loop_id": "loop-privacy"},
        "failures": [{"failure_class": "TEST_FAILURE"}],
    }

    candidates = candidates_from_trace(trace, repository_policy="training_allowed")

    assert candidates[0].privacy_labels["secret_redactions"] >= 1
    assert all(
        item.privacy_labels["secret_redactions"]
        >= candidates[0].privacy_labels["secret_redactions"]
        for item in candidates
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
    object_path = tmp_path / "objects/sha256" / digest[:2] / digest[2:4] / f"{digest}.json.zst"
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


def test_collector_records_exact_provider_classes(tmp_path: Path) -> None:
    operational = StateStore(tmp_path / "operational.db")
    objects = ContentStore(tmp_path / "objects")
    training = TrainingStore(tmp_path / "training.db", objects, minimum_free_bytes=0)
    collector = TrainingCollector(training, operational, external_output_permitted=True)
    trace = eligible_trace() | {
        "model_revisions": {
            role: {"repository": f"test/{role}", "revision": "abc"}
            for role in ("executor", "frontier", "judge")
        },
        "agent_invocations": [
            {"role": "executor", "status": "completed"},
            {"role": "frontier", "status": "completed"},
            {"role": "judge", "provider": "opencode_go", "status": "completed"},
        ],
        "metrics": {"repository_training_policy": "training_allowed"},
    }

    collector.collect(trace)

    with sqlite3.connect(tmp_path / "training.db") as database:
        hashes = [
            row[0]
            for row in database.execute(
                "SELECT payload_hash FROM training_events ORDER BY rowid"
            ).fetchall()
        ]
    assert [objects.get(digest)["model_provider"] for digest in hashes] == [
        "local",
        "frontier",
        "opencode_go",
    ]


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
