from __future__ import annotations

import json

import pytest
from dgx_moa.adapters import register
from dgx_moa.benchmark import TASKS, summarize
from dgx_moa.dataset import build
from dgx_moa.improvement import compare, mine, statistics


def test_benchmark_shape_and_improvement_tools(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert len(TASKS) == 10
    benchmark = tmp_path / "baseline.json"
    tasks = [
        {
            "task_success": True,
            "wall_clock_seconds": 1.0,
            "tool_calls": 1,
            "failure_classes": ["REPEATED_ACTION"],
            "expected_route": "fast",
            "reviewer_rejections": 0,
            "judge_invocations": 0,
        }
    ]
    benchmark.write_text(
        json.dumps(
            {
                "summary": summarize(tasks),
                "tasks": tasks,
            }
        )
    )
    proposal = mine(benchmark, tmp_path / "proposal.json")
    assert proposal["proposal_id"] == "IMP-2026-0001"
    assert proposal["statistics"]["failure_frequency"] == {"REPEATED_ACTION": 1}
    assert statistics({"tasks": []})["replan_rate"] == 0
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"summary": summarize([])}))
    verdict = compare(benchmark, candidate, tmp_path / "comparison.json")
    assert verdict["automatic_merge"] is False


def test_dataset_and_adapter_promotion_guard(tmp_path) -> None:  # type: ignore[no-untyped-def]
    traces = tmp_path / "traces"
    traces.mkdir()
    trace = json.dumps(
        {
            "session_id": "one",
            "objective": "x",
            "final_status": "completed",
            "review_outcome": {"status": "approved"},
            "verified_state": [],
            "tool_observation": {},
            "assistant_tool_call": {},
        }
    )
    (traces / "one.jsonl").write_text(trace + "\n" + trace + "\n")
    assert build(traces, tmp_path / "set.jsonl", tmp_path / "manifest.json")["count"] == 1
    metadata = {
        "adapter_id": "executor-v1",
        "status": "approved",
        "base_model_repository": "x",
        "base_model_revision": "x",
        "dataset_revision": "x",
        "dataset_hash": "x",
        "training_backend": "manual",
        "training_config_hash": "x",
        "created_at": "x",
        "benchmark": {},
    }
    path = tmp_path / "adapter.json"
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="human approval"):
        register(path, tmp_path / "adapters")
