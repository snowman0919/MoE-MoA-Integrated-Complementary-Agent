from __future__ import annotations

import json
from pathlib import Path

import pytest
from dgx_moa.replay import ReplayEngine, load_snapshot, save_snapshot, snapshot_from_trace


def trace() -> dict:  # type: ignore[type-arg]
    return {
        "session_id": "request-1",
        "task_id": "task-1",
        "objective": "bounded task",
        "selected_route": {"route": "standard"},
        "verified_state": ["test passed"],
        "completion_evidence": {"tests": "evidence-1"},
        "evidence_graph": {
            "nodes": [
                {
                    "node_id": "evidence-1",
                    "node_type": "test_result",
                    "kind": "test_result",
                    "trust_class": "test_confirmed_fact",
                    "source": "pytest",
                    "payload": {"status": "passed"},
                    "created_at": "2026-07-22T00:00:00Z",
                }
            ],
            "edges": [],
        },
        "metrics": {
            "runtime_mode": "moa",
            "request_class": "native_agent_turn",
            "skill_versions": ["python-test@1.0.0"],
            "policy_version": "policy-1",
        },
        "model_revisions": {
            "reasoner": {"repository": "test/reasoner", "revision": "abc"},
            "executor": {"repository": "test/executor", "revision": "def"},
        },
        "agent_invocations": [{"role": "reasoner"}, {"role": "executor"}],
        "tool_executions": [],
        "final_status": "completed",
        "review_outcome": {"status": "approved"},
        "derived_confidence": "high",
        "engineering_loop": {
            "loop_id": "loop-1",
            "termination_reason": "SUCCESS",
            "observed_evidence_ids": ["evidence-1"],
        },
    }


def mocks() -> dict[str, list[dict]]:  # type: ignore[type-arg]
    return {"reasoner": [{"conclusion": "bounded"}], "executor": [{"answer": "done"}]}


def test_snapshot_roundtrip_hash_covers_state_evidence_skills_policy_and_models(
    tmp_path: Path,
) -> None:
    snapshot = snapshot_from_trace(trace(), mocked_provider_outputs=mocks())
    path = tmp_path / "replay.json"
    digest = save_snapshot(path, snapshot)
    restored = load_snapshot(path)

    assert restored.content_hash() == digest
    assert restored.skill_versions == ["python-test@1.0.0"]
    assert restored.policy_version == "policy-1"
    assert set(restored.model_role_configuration) == {"reasoner", "executor"}
    assert restored.task_state["engineering_loop"]["termination_reason"] == "SUCCESS"
    payload = json.loads(path.read_text())
    payload["snapshot"]["task_state"]["objective"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_snapshot(path)


@pytest.mark.asyncio
async def test_exact_replay_requires_and_uses_only_mocked_outputs() -> None:
    snapshot = snapshot_from_trace(trace(), mocked_provider_outputs=mocks())

    result = await ReplayEngine().run(snapshot, mode="regression", exact=True)

    assert result.outputs == mocks()
    assert result.exact is True
    assert result.nondeterminism_sources == []
    assert result.deterministic_claim is True


@pytest.mark.asyncio
async def test_exact_replay_rejects_missing_mock_or_live_provider() -> None:
    snapshot = snapshot_from_trace(trace(), mocked_provider_outputs={"reasoner": []})

    with pytest.raises(ValueError, match="missing mocked"):
        await ReplayEngine().run(snapshot, mode="regression", exact=True)
    with pytest.raises(ValueError, match="cannot call live"):
        await ReplayEngine().run(
            snapshot,
            mode="regression",
            exact=True,
            live_provider=lambda role, request: None,  # type: ignore[arg-type,return-value]
        )


@pytest.mark.asyncio
async def test_live_comparative_replay_records_nondeterminism_and_evaluation() -> None:
    snapshot = snapshot_from_trace(trace())

    async def provider(role: str, request: dict) -> dict:  # type: ignore[type-arg]
        return {"role": role, "policy": request["policy_version"]}

    result = await ReplayEngine().run(
        snapshot,
        mode="routing_policy_comparison",
        exact=False,
        live_provider=provider,
        evaluator=lambda saved, outputs: {"roles_compared": sorted(outputs)},
    )

    assert result.deterministic_claim is False
    assert "live_provider_outputs" in result.nondeterminism_sources
    assert result.evaluation == {"roles_compared": ["executor", "reasoner"]}


@pytest.mark.asyncio
async def test_audit_replay_needs_no_provider_and_preserves_outcome() -> None:
    snapshot = snapshot_from_trace(trace())

    result = await ReplayEngine().run(snapshot, mode="audit", exact=False)

    assert result.outputs == {}
    assert result.evaluation["original_outcome"]["final_status"] == "completed"
