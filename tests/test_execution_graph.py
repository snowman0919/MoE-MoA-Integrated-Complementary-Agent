from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from dgx_moa.config import Limits
from dgx_moa.execution_graph import (
    EdgeType,
    ExecutionGraph,
    ExecutionGraphRuntime,
    ExecutionGraphStore,
    GraphCheckpointIncompatible,
    GraphCompileInput,
    NodeState,
    NodeType,
    SchedulingSnapshot,
    _graph_hash,
    compact_session_active_state,
    compile_execution_graph,
    execution_graph_parity,
    validate_execution_graph,
)
from dgx_moa.state import SessionState, StateStore


def request(complexity: str = "engineering", **overrides: Any) -> GraphCompileInput:
    values: dict[str, Any] = {
        "request_id": "request-1",
        "api_key_id": "key-id-1",
        "objective": "implement and verify",
        "request_class": "native_agent_turn",
        "complexity": complexity,
        "risk": "critical" if complexity == "critical" else "medium",
        "policy_version": "policy-1",
        "policy_hash": "0" * 64,
        "deadline": "2099-01-01T00:00:00+00:00",
        "scheduling": SchedulingSnapshot(
            selected_executor="local_primary",
            fallback_executor="remote_overflow",
        ),
        "tools_requested": True,
        "validation_required": True,
        "reasoner_enabled": True,
    }
    values.update(overrides)
    return GraphCompileInput.model_validate(values)


def find_node(
    runtime: ExecutionGraphRuntime, node_type: NodeType, purpose: str | None = None
) -> str:
    return next(
        node.node_id
        for node in runtime.graph.nodes
        if node.node_type == node_type and (purpose is None or node.purpose == purpose)
    )


def finish_ready_until(runtime: ExecutionGraphRuntime, stop: str) -> None:
    while stop not in runtime.ready_node_ids():
        ready = runtime.ready_node_ids()
        assert ready
        for node_id in ready:
            attempt = runtime.start_attempt(node_id)
            node = runtime._nodes[node_id]
            runtime.finish_attempt(
                attempt.attempt_id,
                outcome=(
                    EdgeType.ON_CHECKPOINT
                    if node.node_type == NodeType.CHECKPOINT
                    else EdgeType.ON_SUCCESS
                ),
                artifact_hash=("a" * 64 if node.purpose == "primary" else None),
            )


def test_compiler_is_deterministic_and_rejects_unallowlisted_or_cyclic_graphs() -> None:
    first = compile_execution_graph(request(), created_at="2026-08-08T00:00:00+00:00")
    second = compile_execution_graph(request(), created_at="2026-08-09T00:00:00+00:00")

    assert first.graph_hash == second.graph_hash
    assert first.graph_id == second.graph_id
    assert first.input_hash == second.input_hash
    assert all(not node.mutation_allowed or node.role == "executor" for node in first.nodes)

    raw = first.model_dump(mode="json")
    raw["nodes"][0]["node_type"] = "MODEL_CHOSEN_NODE"
    with pytest.raises(ValueError):
        ExecutionGraph.model_validate(raw)

    historical = first.model_dump(mode="json")
    historical.pop("scheduling")
    historical["graph_hash"] = _graph_hash(historical)
    historical["graph_id"] = f"graph_{historical['graph_hash'][:24]}"
    loaded = validate_execution_graph(ExecutionGraph.model_validate(historical))
    assert loaded.scheduling is None

    raw = first.model_dump(mode="json")
    raw["edges"].append(
        {
            "edge_id": f"e{len(raw['edges']):03d}",
            "from_node": first.terminal_nodes[0],
            "to_node": first.entry_nodes[0],
            "edge_type": "ON_SUCCESS",
            "max_traversals": 0,
        }
    )
    with pytest.raises(ValueError, match="undeclared cycle"):
        ExecutionGraph.model_validate(raw)
    with pytest.raises(ValueError):
        request(tools_requested="false")

    complex_graph = compile_execution_graph(request("complex"))
    checkpoint = next(node for node in complex_graph.nodes if node.node_type == NodeType.CHECKPOINT)
    assert any(
        edge.from_node == checkpoint.node_id
        and edge.edge_type == EdgeType.ON_CHECKPOINT
        and edge.to_node in complex_graph.terminal_nodes
        for edge in complex_graph.edges
    )
    checkpointed = ExecutionGraphRuntime(complex_graph)
    finish_ready_until(checkpointed, complex_graph.terminal_nodes[0])
    checkpoint_attempt = next(
        attempt for attempt in checkpointed.attempts if attempt.node_type == NodeType.CHECKPOINT
    )
    assert checkpoint_attempt.checkpoint_id == "cp_000001"


def test_fanout_runs_independently_and_join_waits_for_every_branch() -> None:
    runtime = ExecutionGraphRuntime(compile_execution_graph(request()))
    classify = runtime.start_attempt(runtime.graph.entry_nodes[0])
    runtime.finish_attempt(classify.attempt_id)
    parallel = runtime.ready_node_ids()

    assert len(parallel) == 3
    assert {runtime._nodes[node_id].parallel_group_id for node_id in parallel} == {"parallel_0"}
    join = find_node(runtime, NodeType.JOIN)
    for node_id in parallel[:-1]:
        attempt = runtime.start_attempt(node_id)
        runtime.finish_attempt(attempt.attempt_id)
    assert join not in runtime.ready_node_ids()

    last = runtime.start_attempt(parallel[-1])
    runtime.finish_attempt(last.attempt_id)
    assert runtime.ready_node_ids() == (join,)


def test_transient_retries_are_bounded_before_separate_fallback_attempt() -> None:
    runtime = ExecutionGraphRuntime(compile_execution_graph(request("simple")))
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY, "primary")
    fallback = find_node(runtime, NodeType.EXECUTOR_FALLBACK, "fallback")
    finish_ready_until(runtime, primary)

    for expected_attempt in range(1, 4):
        if expected_attempt == 2:
            with pytest.raises(ValueError, match="model pin mismatch"):
                runtime.start_attempt(primary, model="changed-model")
        attempt = runtime.start_attempt(primary, model="mistral-small-4")
        assert attempt.attempt_id.endswith(f"a{expected_attempt:03d}")
        runtime.fail_attempt(
            attempt.attempt_id,
            failure_code="FRONTIER_PROVIDER_TIMEOUT",
            failure_fingerprint="1" * 64,
            retryable=True,
        )
    assert primary not in runtime.ready_node_ids()
    assert fallback in runtime.ready_node_ids()
    assert runtime.node_states[primary] == NodeState.DEGRADED
    fallback_attempt = runtime.start_attempt(fallback)
    assert fallback_attempt.provider == "remote_overflow"
    assert fallback_attempt.selected_incoming_edge is not None


def test_explicit_executor_types_and_actual_controller_parity() -> None:
    runtime = ExecutionGraphRuntime(
        compile_execution_graph(
            request(
                "simple",
                tools_requested=False,
                validation_required=False,
                scheduling=SchedulingSnapshot(selected_executor="local_primary"),
            )
        )
    )
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY)
    finish_ready_until(runtime, primary)
    attempt = runtime.start_attempt(primary)
    runtime.finish_attempt(attempt.attempt_id)
    state = SessionState(
        session_id="parity",
        current_request_id="request-2",
        agent_invocations=[
            {"role": "planner", "request_id": "request-1", "status": "completed"},
            {"role": "executor", "request_id": "request-2", "status": "completed"},
        ],
    )

    assert execution_graph_parity(runtime, state)["matches"] is True
    state.agent_invocations.append(
        {"role": "planner", "request_id": "request-2", "status": "completed"}
    )
    assert execution_graph_parity(runtime, state)["authority_eligible"] is False


def test_runtime_owns_observed_attempt_metrics_and_failure_fingerprint() -> None:
    graph = compile_execution_graph(request("simple"))
    primary = next(
        node.node_id for node in graph.nodes if node.node_type == NodeType.EXECUTOR_PRIMARY
    )
    runtime = ExecutionGraphRuntime(graph)
    finish_ready_until(runtime, primary)

    attempt = runtime.start_node_type(NodeType.EXECUTOR_PRIMARY)
    assert attempt is not None
    finished = runtime.finish_observed_attempt(
        attempt.attempt_id,
        {
            "total_tokens": 7,
            "cached_tokens": 3,
            "cost_usd": 0.25,
            "latency_ms": 12,
        },
        generated_evidence_ids=("executor-evidence",),
    )
    assert (finished.token_usage, finished.cached_tokens) == (7, 3)
    assert (finished.cost_usd, finished.latency_ms) == (0.25, 12.0)

    failed_runtime = ExecutionGraphRuntime(graph)
    finish_ready_until(failed_runtime, primary)
    failed = failed_runtime.start_node_type(NodeType.EXECUTOR_PRIMARY)
    assert failed is not None
    failed_runtime.fail_role_attempt(failed.attempt_id, "executor", TimeoutError())
    assert failed.failure_code == "EXECUTOR_TIMEOUTERROR"
    assert failed.failure_fingerprint == hashlib.sha256(b"EXECUTOR_TIMEOUTERROR").hexdigest()


def test_repair_cycle_requires_new_evidence_and_stops_at_bound() -> None:
    runtime = ExecutionGraphRuntime(
        compile_execution_graph(
            request(
                "critical",
                scheduling=SchedulingSnapshot(selected_executor="local_primary"),
            )
        )
    )
    reviewer = find_node(runtime, NodeType.REVIEWER)
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY, "primary")

    finish_ready_until(runtime, reviewer)
    for traversal in range(2):
        review = runtime.start_attempt(reviewer)
        runtime.finish_attempt(
            review.attempt_id,
            outcome=EdgeType.ON_FINDING,
            progress_evidence_ids=(f"test-evidence-{traversal}",),
            validated_evidence_ids=(f"test-evidence-{traversal}",),
        )
        assert primary in runtime.ready_node_ids()
        finish_ready_until(runtime, reviewer)

    review = runtime.start_attempt(reviewer)
    runtime.finish_attempt(
        review.attempt_id,
        outcome=EdgeType.ON_FINDING,
        progress_evidence_ids=("test-evidence-2",),
        validated_evidence_ids=("test-evidence-2",),
    )
    assert primary not in runtime.ready_node_ids()
    assert find_node(runtime, NodeType.FINALIZE) in runtime.ready_node_ids()
    assert max(runtime.traversal_counts.values()) == 2

    duplicate = ExecutionGraphRuntime(runtime.graph)
    finish_ready_until(duplicate, reviewer)
    first_review = duplicate.start_attempt(reviewer)
    duplicate.finish_attempt(
        first_review.attempt_id,
        outcome=EdgeType.ON_FINDING,
        progress_evidence_ids=("same-evidence",),
        validated_evidence_ids=("same-evidence",),
    )
    finish_ready_until(duplicate, reviewer)
    second_review = duplicate.start_attempt(reviewer)
    duplicate.finish_attempt(
        second_review.attempt_id,
        outcome=EdgeType.ON_FINDING,
        progress_evidence_ids=("same-evidence",),
        validated_evidence_ids=("same-evidence",),
    )
    assert primary not in duplicate.ready_node_ids()
    assert find_node(duplicate, NodeType.FINALIZE) in duplicate.ready_node_ids()


def test_tool_continuation_cycle_stops_at_bound() -> None:
    runtime = ExecutionGraphRuntime(
        compile_execution_graph(
            request(
                "simple",
                scheduling=SchedulingSnapshot(selected_executor="local_primary"),
                validation_required=False,
                reasoner_enabled=False,
                planner_enabled=False,
                frontier_enabled=False,
                reviewer_enabled=False,
                judge_enabled=False,
            )
        )
    )
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY, "primary")
    tool = find_node(runtime, NodeType.TOOL)
    finalize = find_node(runtime, NodeType.FINALIZE)
    finish_ready_until(runtime, primary)

    for traversal in range(3):
        executor_attempt = runtime.start_attempt(primary)
        runtime.finish_attempt(executor_attempt.attempt_id, outcome=EdgeType.ON_FINDING)
        tool_attempt = runtime.start_attempt(tool)
        evidence_id = f"tool-evidence-{traversal}"
        runtime.finish_attempt(
            tool_attempt.attempt_id,
            outcome=EdgeType.ON_FINDING,
            progress_evidence_ids=(evidence_id,),
            validated_evidence_ids=(evidence_id,),
        )

    assert primary not in runtime.ready_node_ids()
    assert finalize in runtime.ready_node_ids()
    assert runtime.attempt_counts[primary] == 3
    assert max(runtime.traversal_counts.values()) == 2


def test_frontier_b_finding_opens_bounded_executor_repair() -> None:
    runtime = ExecutionGraphRuntime(compile_execution_graph(request("critical")))
    judge = find_node(runtime, NodeType.JUDGE)
    frontier_b = find_node(runtime, NodeType.FRONTIER_B)
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY, "primary")
    finish_ready_until(runtime, judge)

    judge_attempt = runtime.start_attempt(judge)
    runtime.finish_attempt(
        judge_attempt.attempt_id,
        outcome=EdgeType.ON_FINDING,
        progress_evidence_ids=("judge-finding",),
        validated_evidence_ids=("judge-finding",),
    )
    assert frontier_b in runtime.ready_node_ids()

    frontier_attempt = runtime.start_attempt(frontier_b)
    assert frontier_attempt.provider == "openrouter"
    runtime.finish_attempt(
        frontier_attempt.attempt_id,
        outcome=EdgeType.ON_FINDING,
        progress_evidence_ids=("frontier-adjudication",),
        validated_evidence_ids=("frontier-adjudication",),
    )
    assert primary in runtime.ready_node_ids()


def test_failed_tool_fallback_stops_at_bound() -> None:
    runtime = ExecutionGraphRuntime(
        compile_execution_graph(
            request(
                "simple",
                scheduling=SchedulingSnapshot(selected_executor="local_primary"),
                validation_required=False,
                reasoner_enabled=False,
                planner_enabled=False,
                frontier_enabled=False,
                reviewer_enabled=False,
                judge_enabled=False,
            )
        )
    )
    primary = find_node(runtime, NodeType.EXECUTOR_PRIMARY, "primary")
    tool = find_node(runtime, NodeType.TOOL)
    finalize = find_node(runtime, NodeType.FINALIZE)
    finish_ready_until(runtime, primary)

    for traversal in range(3):
        executor_attempt = runtime.start_attempt(primary)
        runtime.finish_attempt(executor_attempt.attempt_id, outcome=EdgeType.ON_FINDING)
        tool_attempt = runtime.start_attempt(tool)
        runtime.fail_attempt(
            tool_attempt.attempt_id,
            failure_code="TOOL_EXIT_NONZERO",
            failure_fingerprint=f"{traversal + 1}" * 64,
            retryable=False,
            generated_evidence_ids=(f"tool-failure-{traversal}",),
        )

    assert primary not in runtime.ready_node_ids()
    assert finalize in runtime.ready_node_ids()
    assert runtime.attempt_counts[primary] == 3
    assert runtime.attempts[-1].generated_evidence_ids == ("tool-failure-2",)
    assert max(runtime.traversal_counts.values()) == 2


def test_policy_owned_human_approval_pauses_and_resumes_on_explicit_edge() -> None:
    runtime = ExecutionGraphRuntime(
        compile_execution_graph(request("critical", human_approval_required=True))
    )
    approval = find_node(runtime, NodeType.HUMAN_APPROVAL)
    select = find_node(runtime, NodeType.EXECUTOR_SELECT)
    finish_ready_until(runtime, approval)

    waiting = runtime.start_attempt(approval)
    assert waiting.state == NodeState.WAITING_APPROVAL
    assert select not in runtime.ready_node_ids()
    runtime.finish_attempt(
        waiting.attempt_id,
        outcome=EdgeType.ON_APPROVAL,
        validated_evidence_ids=("operator-approval-1",),
    )
    assert runtime.ready_node_ids() == (select,)

    cancelled = ExecutionGraphRuntime(compile_execution_graph(request("simple")))
    running = cancelled.start_attempt(cancelled.graph.entry_nodes[0])
    with pytest.raises(ValueError, match="nonnegative integer"):
        cancelled.finish_attempt(running.attempt_id, token_usage=True)
    assert running.state == NodeState.RUNNING
    cancelled.cancel()
    finalize = find_node(cancelled, NodeType.FINALIZE)
    assert cancelled.ready_node_ids() == (finalize,)
    final_attempt = cancelled.start_attempt(finalize)
    cancelled.finish_attempt(final_attempt.attempt_id, terminal_status="cancelled")
    assert cancelled.terminal_status == "cancelled"


def test_checkpoint_restart_partial_rerun_and_exactly_once_final(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = ExecutionGraphStore(tmp_path / "graph.sqlite")
    assert (tmp_path / "graph.sqlite").stat().st_mode & 0o777 == 0o600
    runtime = ExecutionGraphRuntime(compile_execution_graph(request()), store=store)
    classify = runtime.start_attempt(runtime.graph.entry_nodes[0])
    runtime.finish_attempt(classify.attempt_id)
    interrupted_node = runtime.ready_node_ids()[0]
    interrupted = runtime.start_attempt(interrupted_node)
    active_state_ref = store.save_active_state(
        {"objective": "resume safely", "note": "token=synthetic-secret"}
    )
    duplicate_ref = store.save_active_state(
        {"objective": "resume safely", "note": "token=synthetic-secret"}
    )
    assert duplicate_ref == active_state_ref
    assert store.load_active_state(active_state_ref)["note"] == "token=[REDACTED]"
    runtime.checkpoint(
        reason="compact",
        active_state_object_ref=active_state_ref,
        event_cursor=7,
        size_before=1000,
        size_after=100,
    )

    resumed = store.load_runtime(runtime.graph.graph_id)
    recovered = next(item for item in resumed.attempts if item.attempt_id == interrupted.attempt_id)
    assert recovered.state == NodeState.FAILED
    assert recovered.failure_code == "GRAPH_PROCESS_RESTART"
    assert interrupted_node in resumed.ready_node_ids()
    resumed_checkpoint = store.load_latest_checkpoint(runtime.graph.graph_id)
    assert resumed_checkpoint.active_state_object_ref == active_state_ref
    assert resumed_checkpoint.event_cursor == 7
    assert (resumed_checkpoint.size_before, resumed_checkpoint.size_after) == (1000, 100)

    checkpoint = resumed.checkpoint(reason="manual")
    incompatible = checkpoint.model_copy(update={"policy_version": "changed"})
    with pytest.raises(GraphCheckpointIncompatible):
        ExecutionGraphRuntime.resume(resumed.graph, incompatible)

    clean = ExecutionGraphRuntime(runtime.graph)
    finalize = find_node(clean, NodeType.FINALIZE)
    finish_ready_until(clean, finalize)
    final_attempt = clean.start_attempt(finalize)
    with pytest.raises(ValueError, match="validated Evidence"):
        clean.finish_attempt(final_attempt.attempt_id, terminal_status="completed")
    clean.finish_attempt(
        final_attempt.attempt_id,
        terminal_status="completed",
        validated_evidence_ids=("acceptance-evidence-1",),
    )
    assert clean.final_emitted
    with pytest.raises(ValueError, match="not ready"):
        clean.start_attempt(finalize)

    test_node = find_node(clean, NodeType.TEST)
    reviewer_node = find_node(clean, NodeType.REVIEWER)
    unaffected = find_node(clean, NodeType.PLANNER)
    with pytest.raises(ValueError, match="GRAPH_INVALIDATED_NODE_NOT_COMPLETED"):
        clean.partial_rerun({test_node})
    with pytest.raises(ValueError, match="ARTIFACT_VERIFICATION_REQUIRED"):
        clean.partial_rerun({reviewer_node})
    affected = clean.partial_rerun(
        {reviewer_node},
        verified_artifact_hashes={find_node(clean, NodeType.EXECUTOR_PRIMARY, "primary"): "a" * 64},
    )
    assert reviewer_node in affected and finalize in affected
    assert unaffected not in affected
    assert clean.node_states[unaffected] == NodeState.SUCCEEDED
    assert not clean.final_emitted


def test_long_session_compacts_active_state_without_deleting_durable_history(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    limits = Limits(max_tool_output_characters=16_000, max_retained_observations=12)
    payload = "한" * 20_000
    state = SessionState(
        session_id="long-session",
        objective=payload,
        acceptance_criteria=[payload] * 20,
        plan=[{"step": index, "detail": payload} for index in range(40)],
        policy_decisions=[{"decision": index, "detail": payload} for index in range(40)],
        evidence_nodes=[{"node_id": f"ev-{index}", "payload": payload} for index in range(40)],
        failures=[{"failure_class": "TEST_FAILURE", "detail": payload} for _ in range(40)],
        agent_artifacts=[{"role": "reviewer", "output": payload} for _ in range(40)],
    )
    scheduling = SchedulingSnapshot(selected_executor="local_primary")
    active_state = compact_session_active_state(state, scheduling, limits)
    active_bytes = len(json.dumps(active_state, ensure_ascii=False).encode())

    assert active_bytes <= limits.max_tool_output_characters * limits.max_retained_observations
    assert active_bytes < len(state.model_dump_json().encode())
    assert active_state["objective"]["truncated"] is True
    assert active_state["recent_relevant_evidence"]["truncated"] is True

    state_store = StateStore(tmp_path / "long-session.db")
    state_store.save(state)
    for index in range(2_000):
        state_store.event("long-session", "tool_output", {"index": index, "output": payload[:100]})
    graph_store = ExecutionGraphStore(state_store.path)
    runtime = ExecutionGraphRuntime(compile_execution_graph(request("simple")), graph_store)
    active_state_ref = graph_store.save_active_state(active_state)
    checkpoint = runtime.checkpoint(
        reason="long_session_compaction",
        active_state_object_ref=active_state_ref,
        event_cursor=state_store.event_cursor("long-session"),
        size_before=len(state.model_dump_json().encode()),
        size_after=active_bytes,
    )

    resumed = ExecutionGraphStore(state_store.path).load_runtime(runtime.graph.graph_id)
    checkpoints = graph_store.load_checkpoints(runtime.graph.graph_id)
    assert len(state_store.events("long-session")) == 2_000
    assert resumed.active_state_object_ref == active_state_ref
    assert resumed.event_cursor == 2_000
    assert checkpoint.size_after < checkpoint.size_before
    assert (
        graph_store.load_checkpoint(runtime.graph.graph_id, checkpoint.checkpoint_id) == checkpoint
    )
    assert [item.reason for item in checkpoints] == ["long_session_compaction", "resumed"]
    assert graph_store.load_active_state(active_state_ref) == active_state
