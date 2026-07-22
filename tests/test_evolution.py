from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.controller import Controller
from dgx_moa.evolution import (
    EvolutionArtifact,
    EvolutionCandidateGenerator,
    EvolutionEvaluation,
    EvolutionRegistry,
    EvolutionSignal,
    PromptRegistry,
)
from dgx_moa.state import SessionState, StateStore


def artifact(*, high_impact: bool = False) -> EvolutionArtifact:
    return EvolutionArtifact(
        artifact_id="prompt.executor",
        kind="prompt",
        version=1,
        state="candidate",
        payload={"role": "executor", "template": "Use verified evidence only."},
        high_impact=high_impact,
        source_evidence_ids=["failure-1"],
        created_by="generator",
    )


def evaluation(*, judge: bool = False) -> EvolutionEvaluation:
    return EvolutionEvaluation(
        schema_valid=True,
        historical_replay=True,
        regression_thresholds_passed=True,
        reviewer_approved=True,
        judge_approved=judge,
        evidence_ids=["schema", "replay", "regression", "reviewer"],
        baseline_metrics={"task_success": 0.8},
        candidate_metrics={"task_success": 0.9},
    )


def test_prompt_candidate_requires_replay_review_canary_approval_and_rollback(
    tmp_path: Path,
) -> None:
    registry = EvolutionRegistry(tmp_path / "evolution.db")
    registry.put(artifact())
    evaluated = registry.evaluate("prompt.executor", 1, evaluation(), created_by="evaluator")
    canary = registry.start_canary(
        evaluated.artifact_id,
        evaluated.version,
        rollback_target="builtin.executor",
        approval_id="canary-approval",
        created_by="operator",
    )
    with pytest.raises(PermissionError, match="helpful canary"):
        registry.promote(
            canary.artifact_id,
            canary.version,
            approval_id="promotion-approval",
            created_by="operator",
        )
    registry.record_canary(
        canary.artifact_id,
        canary.version,
        outcome="helpful",
        evidence_ids=["executor-canary"],
    )
    promoted = registry.promote(
        canary.artifact_id,
        canary.version,
        approval_id="promotion-approval",
        created_by="operator",
    )
    rolled_back = registry.rollback(
        promoted.artifact_id,
        promoted.version,
        1,
        approval_id="rollback-approval",
        created_by="operator",
    )

    assert promoted.state == rolled_back.state == "active"
    assert rolled_back.version == promoted.version + 1
    assert rolled_back.rollback_target == f"prompt.executor@{promoted.version}"


def test_high_impact_evolution_candidate_requires_judge_evidence(tmp_path: Path) -> None:
    registry = EvolutionRegistry(tmp_path / "evolution.db")
    registry.put(artifact(high_impact=True))

    rejected = registry.evaluate(
        "prompt.executor", 1, evaluation(judge=False), created_by="evaluator"
    )

    assert rejected.state == "rejected"


def test_evidence_signals_generate_only_sanitized_idempotent_candidates(tmp_path: Path) -> None:
    registry = EvolutionRegistry(tmp_path / "evolution.db")
    generator = EvolutionCandidateGenerator(registry)
    signals = [
        EvolutionSignal(
            signal_type="invalid_structured_output",
            candidate_kind="prompt",
            scope="executor",
            occurrences=3,
            evidence_ids=["failure-1", "failure-2"],
            proposed_payload={
                "role": "executor",
                "template": "Return the schema; contact alice@example.invalid only if needed.",
            },
        ),
        EvolutionSignal(
            signal_type="repeated_unsafe_action",
            candidate_kind="policy",
            scope="destructive",
            occurrences=2,
            evidence_ids=["unsafe-1", "unsafe-2"],
            proposed_payload={
                "when": {"destructive": True},
                "require": {"approval": True},
            },
        ),
        EvolutionSignal(
            signal_type="latency_cost",
            candidate_kind="routing",
            scope="planner",
            occurrences=5,
            evidence_ids=["latency-1"],
            proposed_payload={"rules": [{"when": "simple", "avoid": "planner"}]},
        ),
    ]

    candidates = generator.generate_many(signals, created_by="weekly-generator")
    replayed = generator.generate(signals[0], created_by="weekly-generator")

    assert [item.kind for item in candidates] == ["prompt", "policy", "routing"]
    assert all(item.state == "candidate" and item.approval_id is None for item in candidates)
    assert candidates[1].high_impact is True
    assert "alice@example.invalid" not in candidates[0].payload["template"]
    assert replayed.artifact_id == candidates[0].artifact_id
    assert replayed.version == candidates[0].version
    assert len(registry.list_artifacts()) == 3


def test_evolution_generator_rejects_mismatched_or_singleton_signals(tmp_path: Path) -> None:
    generator = EvolutionCandidateGenerator(EvolutionRegistry(tmp_path / "evolution.db"))
    with pytest.raises(ValueError, match="greater than or equal to 2"):
        EvolutionSignal(
            signal_type="invalid_structured_output",
            candidate_kind="prompt",
            scope="executor",
            occurrences=1,
            evidence_ids=["one"],
            proposed_payload={"role": "executor", "template": "schema"},
        )
    with pytest.raises(ValueError, match="not valid"):
        generator.generate(
            EvolutionSignal(
                signal_type="repeated_unsafe_action",
                candidate_kind="routing",
                scope="executor",
                occurrences=2,
                evidence_ids=["one", "two"],
                proposed_payload={"rules": [{"when": "unsafe", "route": "reviewer"}]},
            ),
            created_by="generator",
        )


def test_active_prompt_registry_changes_only_role_policy(settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    prompts = PromptRegistry(tmp_path / "prompts.db")
    prompts.registry.put(
        EvolutionArtifact(
            artifact_id="prompt.executor",
            kind="prompt",
            version=1,
            state="active",
            payload={"role": "executor", "template": "Use the registered prompt."},
            source_evidence_ids=["human-source"],
            evaluation_evidence_ids=["human-review"],
            rollback_target="builtin.executor",
            approval_id="human-approval",
            created_by="operator",
        )
    )
    controller = Controller(
        settings,
        StateStore(settings.state_db),
        object(),  # type: ignore[arg-type]
        prompts=prompts,
    )

    rendered = controller.prompt_sandwich(
        "executor", SessionState(session_id="prompt"), "evidence", "act"
    )

    assert "Use the registered prompt." in rendered
    assert "EXACT OUTPUT SCHEMA" in rendered
    assert "No hidden reasoning" in rendered
