from __future__ import annotations

import json
import sqlite3

import pytest
from dgx_moa.controller import Controller
from dgx_moa.dataset import build
from dgx_moa.improvement import cooldown_active, mine, proposal_fingerprint
from dgx_moa.runtime_status import report, state_counts
from dgx_moa.state import Phase, SessionState, StateStore, validate_failure_record
from dgx_moa.trace import (
    TraceRecorder,
    audit_traces,
    trace_record,
    training_default,
    validate_provenance,
)

from .conftest import StubProvider


def complete_state() -> SessionState:
    state = SessionState(
        session_id="complete",
        task_id="task",
        objective="ship",
        repository={
            "workspace_identifier": "repo",
            "current_branch": "main",
            "current_commit": "abc",
            "dirty_status": "clean",
        },
        ending_repository={
            "current_branch": "main",
            "current_commit": "def",
            "dirty_status": "clean",
        },
        runtime_channel="main",
        trace_origin="production",
        route_reasons=["production request"],
        training_eligibility="requires_review",
        phase=Phase.COMPLETED,
        final_status="completed",
        completion_evidence={"tests": "exit 0"},
        controller_commit="abc",
        vllm_version="0.22.1",
    )
    state.decisions = [
        {
            "decision_id": "decision",
            "session_id": "complete",
            "task_id": "task",
            "role": "executor",
            "model_repository": "test/executor",
            "model_revision": "abc",
            "controller_commit": "abc",
            "timestamp": state.created_at,
            "state_before": {"phase": "completed"},
            "context_manifest": {"context_builder_name": "controller", "version": "2"},
            "structured_decision": {"type": "tool_call"},
            "outcome": {"status": "success"},
        }
    ]
    state.tool_executions = [
        {
            "tool_execution_id": "execution",
            "tool_call_id": "call",
            "decision_id": "decision",
            "session_id": "complete",
            "tool_name": "write",
            "normalized_arguments": {"path": "x"},
            "argument_fingerprint": "fingerprint",
            "started_at": state.created_at,
            "ended_at": state.created_at,
            "duration_ms": 1,
            "exit_code": 0,
            "stdout_bytes": 2,
            "stderr_bytes": 0,
            "stdout_summary": "ok",
            "stderr_summary": "",
            "truncated": False,
            "failure_class": None,
            "filesystem_effect": {"changed_paths": ["x"]},
        }
    ]
    state.evaluations = [
        {
            "evaluation_id": "evaluation",
            "target_type": "task",
            "target_id": "complete",
            "evaluator_type": "deterministic",
            "result": "passed",
        }
    ]
    state.failures = [
        {
            "failure_class": "TIMEOUT",
            "suspected_layer": "harness",
            "resolution_status": "resolved",
            "root_cause_summary": "wrong fixture",
        }
    ]
    return state


def test_v2_provenance_training_and_schema() -> None:
    validate_provenance("main", "production")
    validate_provenance("candidate", "candidate_evaluation")
    with pytest.raises(ValueError, match="production"):
        validate_provenance("dev", "production")
    assert training_default("main", "production") == "requires_review"
    assert training_default("dev", "benchmark") == "eligible"
    assert training_default("dev", "diagnostic") == "excluded"
    trace = trace_record(complete_state())
    assert trace["schema_version"] == "agent-trace-v2"
    assert trace["agent_decisions"][0]["context_manifest"]
    assert trace["tool_executions"][0]["decision_id"] == "decision"
    assert trace["evaluations"][0]["target_id"] == "complete"
    assert trace["vllm_version"] == "0.22.1"


def test_failure_record_values_are_strict() -> None:
    validate_failure_record({"suspected_layer": "harness", "resolution_status": "resolved"})
    with pytest.raises(ValueError, match="suspected_layer"):
        validate_failure_record({"suspected_layer": "model", "resolution_status": "active"})
    with pytest.raises(ValueError, match="resolution_status"):
        validate_failure_record({"suspected_layer": "executor", "resolution_status": "gone"})


def test_partition_index_and_completeness(tmp_path, settings) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "state.db")
    state = complete_state()
    store.save(state)
    for event in (
        "session_started",
        "route_selected",
        "assistant_stream_finished",
        "session_ended",
    ):
        store.event(state.session_id, event, {})
    path = TraceRecorder(tmp_path / "traces", store, settings.models).record(state)
    assert path.parts[-4:-2] == ("main", "production")
    report = audit_traces(tmp_path / "traces")
    assert report["mandatory_field_completeness_percent"] == 100.0
    with store._connect() as database:
        assert database.execute("SELECT path FROM trace_index").fetchone()[0] == str(path)


def test_incomplete_and_legacy_traces_are_not_promoted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "legacy.jsonl").write_text('{"schema_version":"agent-trace-v1"}\n')
    report = audit_traces(traces)
    assert report["incomplete_sessions"] == 1
    assert report["legacy_sessions"] == 1
    dataset = build(traces, tmp_path / "set.jsonl", tmp_path / "manifest.json")
    assert dataset["count"] == 0 and dataset["legacy_excluded"] == 1


def test_tool_linkage_and_stricter_training_override(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    controller = Controller(settings, StateStore(settings.state_db), stub_provider)  # type: ignore[arg-type]
    state = SessionState(session_id="tool")
    controller.select_route(
        state,
        {
            "runtime_channel": "dev",
            "trace_origin": "benchmark",
            "training_eligibility": "excluded",
        },
    )
    state.last_decision_id = "decision"
    controller._observe(
        state,
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call",
                        "type": "function",
                        "function": {"name": "write", "arguments": '{"path":"x"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call",
                "content": json.dumps(
                    {
                        "tool_name": "write",
                        "exit_code": 0,
                        "stdout": "ok",
                        "changed_paths": ["x"],
                    }
                ),
            },
        ],
    )
    assert state.training_eligibility == "excluded"
    assert state.tool_executions[0]["decision_id"] == "decision"
    assert state.tool_executions[0]["filesystem_effect"] == {"changed_paths": ["x"]}


def test_proposal_cooldown_changes_with_material_evidence() -> None:
    first = proposal_fingerprint("TIMEOUT", 1, {"tasks": 1})
    same = proposal_fingerprint("TIMEOUT", 1, {"tasks": 1})
    changed = proposal_fingerprint("TIMEOUT", 2, {"tasks": 2})
    assert cooldown_active({"proposal_fingerprint": first}, same)
    assert not cooldown_active({"proposal_fingerprint": first}, changed)


def test_miner_prioritizes_active_production_v2_trace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    traces = tmp_path / "traces"
    traces.mkdir()
    production = {
        "schema_version": "agent-trace-v2",
        "session_id": "production",
        "runtime_channel": "main",
        "trace_origin": "production",
        "final_status": "failed",
        "failures": [{"failure_class": "PROVIDER", "resolution_status": "active"}],
    }
    benchmark = {
        "schema_version": "agent-trace-v2",
        "session_id": "benchmark",
        "runtime_channel": "dev",
        "trace_origin": "benchmark",
        "final_status": "failed",
        "failures": [{"failure_class": "BENCHMARK", "resolution_status": "active"}],
    }
    (traces / "traces.jsonl").write_text(
        json.dumps(benchmark) + "\n" + json.dumps(production) + "\n"
    )
    proposal = mine(traces, tmp_path / "proposal.json")
    assert proposal["evidence"]["failure_class"] == "PROVIDER"


def test_runtime_state_counts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "state.db"
    store = StateStore(path)
    completed = SessionState(session_id="done", final_status="completed")
    blocked = SessionState(session_id="blocked", final_status="blocked")
    store.save(completed)
    store.save(blocked)
    store.event("done", "request_received", {})
    assert state_counts(path) == {"request": 1, "completed": 1, "failed": 0, "blocked": 1}
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT count(*) FROM trace_index").fetchone()[0] == 0


def test_runtime_report_reads_model_journals(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from dgx_moa import runtime_status

    def fake_command(*args: str) -> str:
        if "dgx-moa-reviewer.service" in args and args[0] == "journalctl":
            return "EngineCore failed: CUDA error: out of memory"
        if args[0] == "systemctl":
            return "ActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0"
        return ""

    monkeypatch.setattr(runtime_status, "command", fake_command)
    monkeypatch.setattr(runtime_status, "memory_available", lambda: 1)
    assert report(tmp_path / "missing.db", tmp_path)["model_backend_failures_24h"] == 2
