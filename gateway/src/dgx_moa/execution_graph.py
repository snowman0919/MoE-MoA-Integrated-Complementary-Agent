"""Deterministic, policy-owned execution graphs with durable bounded replay."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from .compression import compress_text
from .config import Limits, Settings
from .security import redact
from .state import SessionState, StateStore

GRAPH_SCHEMA_VERSION: Final = "execution-graph-v1"
GRAPH_COMPILER_VERSION: Final = "stdlib-v1"
TRANSIENT_RETRY_LIMIT: Final = 2
VALIDATION_COMMAND: Final = re.compile(
    r"\b(?:pytest|unittest|ruff|mypy|cargo test|go test|npm test)\b"
)
GraphEventListener = Callable[[str, str, str, str, dict[str, Any], str], None]


def record_shadow_failure(store: StateStore, session_id: str, stage: str, error: Exception) -> None:
    store.event(
        session_id,
        "execution_graph_shadow_failed",
        {"failure_code": type(error).__name__, "stage": stage},
    )


class NodeType(StrEnum):
    CLASSIFY = "CLASSIFY"
    REASONER = "REASONER"
    PLANNER = "PLANNER"
    FRONTIER_A = "FRONTIER_A"
    EXECUTOR_SELECT = "EXECUTOR_SELECT"
    EXECUTOR = "EXECUTOR"
    TOOL = "TOOL"
    TEST = "TEST"
    REVIEWER = "REVIEWER"
    JUDGE = "JUDGE"
    FRONTIER_B = "FRONTIER_B"
    JOIN = "JOIN"
    POLICY_GATE = "POLICY_GATE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    CHECKPOINT = "CHECKPOINT"
    FINALIZE = "FINALIZE"


class EdgeType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    ON_SUCCESS = "ON_SUCCESS"
    ON_FAILURE = "ON_FAILURE"
    ON_RETRYABLE_FAILURE = "ON_RETRYABLE_FAILURE"
    ON_FINDING = "ON_FINDING"
    ON_APPROVAL = "ON_APPROVAL"
    ON_REJECTION = "ON_REJECTION"
    ON_BUDGET = "ON_BUDGET"
    ON_PROGRESS = "ON_PROGRESS"
    ON_NO_PROGRESS = "ON_NO_PROGRESS"
    ON_FALLBACK = "ON_FALLBACK"
    ON_CHECKPOINT = "ON_CHECKPOINT"


class NodeState(StrEnum):
    QUEUED = "QUEUED"
    DISPATCHING = "DISPATCHING"
    RUNNING = "RUNNING"
    STREAMING = "STREAMING"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class GraphBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tokens: int = Field(default=5_000_000, ge=0, strict=True)
    tool_calls: int = Field(default=500, ge=0, strict=True)
    wall_clock_seconds: int = Field(default=43_200, gt=0, strict=True)


class SchedulingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_executor: Literal[
        "local_mistral", "opencode_go", "legacy_local_qwen", "codex_frontier"
    ]
    fallback_executor: (
        Literal["local_mistral", "opencode_go", "legacy_local_qwen", "codex_frontier"] | None
    ) = None
    lease_owner_api_key_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    queue_position: int = Field(default=0, ge=0, strict=True)
    round_robin_epoch: int = Field(default=0, ge=0, strict=True)
    readiness: dict[str, StrictBool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def different_fallback(self) -> SchedulingSnapshot:
        if self.fallback_executor == self.selected_executor:
            raise ValueError("fallback executor must differ from selected executor")
        return self


class GraphCompileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=256)
    api_key_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    objective: str = Field(min_length=1, max_length=200_000)
    request_class: str = Field(min_length=1, max_length=64)
    complexity: Literal["simple", "engineering", "complex", "critical"]
    risk: Literal["low", "medium", "high", "critical"]
    policy_version: str = Field(min_length=1, max_length=128)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline: str
    scheduling: SchedulingSnapshot
    budgets: GraphBudget = Field(default_factory=GraphBudget)
    allowed_mutation_paths: tuple[str, ...] = ()
    tools_requested: bool = Field(default=False, strict=True)
    validation_required: bool = Field(default=False, strict=True)
    reasoner_enabled: bool = Field(default=False, strict=True)
    planner_enabled: bool = Field(default=True, strict=True)
    frontier_enabled: bool = Field(default=True, strict=True)
    reviewer_enabled: bool = Field(default=True, strict=True)
    judge_enabled: bool = Field(default=True, strict=True)
    human_approval_required: bool = Field(default=False, strict=True)

    @field_validator("deadline")
    @classmethod
    def aware_deadline(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("deadline must include a timezone")
        return value

    @field_validator("allowed_mutation_paths")
    @classmethod
    def bounded_relative_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 256 or any(
            not path or Path(path).is_absolute() or ".." in Path(path).parts for path in value
        ):
            raise ValueError("mutation paths must be bounded relative paths")
        return tuple(sorted(set(value)))


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=r"^n\d{2}_[a-z0-9_]+$")
    node_type: NodeType
    role: str | None = None
    purpose: Literal["control", "primary", "evidence", "fallback"] = "control"
    parallel_group_id: str | None = None
    provider: str | None = None
    mutation_allowed: bool = False
    allowed_mutation_paths: tuple[str, ...] = ()
    join_all: bool = False

    @model_validator(mode="after")
    def mutation_is_executor_owned(self) -> GraphNode:
        if self.mutation_allowed and (
            self.node_type not in {NodeType.EXECUTOR, NodeType.TOOL} or self.role != "executor"
        ):
            raise ValueError("only Executor-owned EXECUTOR/TOOL nodes may mutate")
        if not self.mutation_allowed and self.allowed_mutation_paths:
            raise ValueError("read-only nodes cannot carry mutation paths")
        if self.join_all != (self.node_type == NodeType.JOIN):
            raise ValueError("only JOIN nodes use join_all")
        return self


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(pattern=r"^e\d{3}$")
    from_node: str
    to_node: str
    edge_type: EdgeType
    max_traversals: int = Field(default=0, ge=0, le=TRANSIENT_RETRY_LIMIT, strict=True)


class ExecutionGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str = Field(pattern=r"^graph_[0-9a-f]{24}$")
    graph_schema_version: Literal["execution-graph-v1"] = GRAPH_SCHEMA_VERSION
    compiler_version: Literal["stdlib-v1"] = GRAPH_COMPILER_VERSION
    policy_version: str
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str
    api_key_id: str
    template_id: Literal["simple-v1", "engineering-v1", "complex-v1", "critical-v1"]
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    deadline: str
    budgets: GraphBudget
    scheduling: SchedulingSnapshot | None = None
    entry_nodes: tuple[str, ...]
    terminal_nodes: tuple[str, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @field_validator("created_at", "deadline")
    @classmethod
    def aware_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("graph timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def structurally_valid(self) -> ExecutionGraph:
        node_ids = [node.node_id for node in self.nodes]
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)):
            raise ValueError("duplicate execution graph ID")
        known = set(node_ids)
        if not self.entry_nodes or not self.terminal_nodes:
            raise ValueError("execution graph requires entry and terminal nodes")
        if not set(self.entry_nodes + self.terminal_nodes).issubset(known):
            raise ValueError("invalid entry or terminal reference")
        if any(edge.from_node not in known or edge.to_node not in known for edge in self.edges):
            raise ValueError("invalid execution edge reference")
        by_id = {node.node_id: node for node in self.nodes}
        for edge in self.edges:
            if edge.edge_type == EdgeType.ON_RETRYABLE_FAILURE:
                if edge.from_node != edge.to_node or edge.max_traversals != TRANSIENT_RETRY_LIMIT:
                    raise ValueError("retry edges must be bounded self-edges")
            elif edge.edge_type == EdgeType.ON_FINDING and edge.max_traversals:
                if (
                    by_id[edge.from_node].node_type
                    not in {
                        NodeType.REVIEWER,
                        NodeType.JUDGE,
                        NodeType.FRONTIER_B,
                        NodeType.TOOL,
                        NodeType.TEST,
                    }
                    or by_id[edge.to_node].node_type != NodeType.EXECUTOR
                ):
                    raise ValueError(
                        "repair edges must be bounded evidence/tool/test-to-executor edges"
                    )
            elif edge.edge_type == EdgeType.ON_FALLBACK and edge.max_traversals:
                if (
                    by_id[edge.from_node].node_type != NodeType.TOOL
                    or by_id[edge.to_node].node_type != NodeType.EXECUTOR
                ):
                    raise ValueError("bounded fallback edges must be tool-to-executor edges")
            elif edge.max_traversals:
                raise ValueError("only retry and repair edges may traverse repeatedly")
            elif edge.from_node == edge.to_node:
                raise ValueError("unbounded self-edge")
        _require_acyclic_base(self.nodes, self.edges)
        reachable = set(self.entry_nodes)
        queue = deque(self.entry_nodes)
        while queue:
            source = queue.popleft()
            for edge in self.edges:
                if edge.from_node == source and edge.to_node not in reachable:
                    reachable.add(edge.to_node)
                    queue.append(edge.to_node)
        if reachable != known:
            raise ValueError("execution graph contains unreachable nodes")
        if any(by_id[node_id].node_type != NodeType.CLASSIFY for node_id in self.entry_nodes):
            raise ValueError("execution graph entry must classify")
        if any(by_id[node_id].node_type != NodeType.FINALIZE for node_id in self.terminal_nodes):
            raise ValueError("execution graph terminal must finalize")
        return self


class NodeAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    node_id: str
    attempt_id: str
    node_type: NodeType
    role: str | None = None
    provider: str | None = None
    model: str | None = None
    state: NodeState
    parent_node_ids: tuple[str, ...] = ()
    parallel_group_id: str | None = None
    selected_incoming_edge: str | None = None
    available_outgoing_edges: tuple[str, ...] = ()
    selected_outgoing_edges: tuple[str, ...] = ()
    started_at: str
    ended_at: str | None = None
    deadline: str
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    token_usage: int = Field(default=0, ge=0, strict=True)
    cached_tokens: int | None = Field(default=None, ge=0, strict=True)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    failure_code: str | None = None
    failure_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    progress_evidence_ids: tuple[str, ...] = ()
    generated_evidence_ids: tuple[str, ...] = ()
    validated_evidence_ids: tuple[str, ...] = ()
    contradicted_evidence_ids: tuple[str, ...] = ()
    public_output_ref: str | None = None
    artifact_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checkpoint_id: str | None = None


class GraphCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str = Field(pattern=r"^cp_\d{6}$")
    graph_id: str
    graph_hash: str
    graph_schema_version: str
    compiler_version: str
    policy_version: str
    parent_checkpoint_id: str | None = None
    completed_node_ids: tuple[str, ...]
    active_node_ids: tuple[str, ...]
    pending_node_ids: tuple[str, ...]
    selected_edges: tuple[str, ...]
    available_edges: tuple[str, ...]
    provider_pins: dict[str, str]
    model_pins: dict[str, str]
    artifact_hashes: dict[str, str]
    remaining_budgets: dict[str, int]
    failure_fingerprints: tuple[str, ...]
    progress_evidence_ids: tuple[str, ...]
    active_state_object_ref: str
    event_cursor: int = Field(ge=0, strict=True)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_before: int = Field(ge=0, strict=True)
    size_after: int = Field(ge=0, strict=True)
    reason: str
    created_at: str
    node_states: dict[str, NodeState]
    traversal_counts: dict[str, int]
    attempt_counts: dict[str, int]
    token_usage: int = Field(ge=0, strict=True)
    tool_calls: int = Field(ge=0, strict=True)
    final_emitted: bool
    terminal_status: Literal["completed", "failed", "cancelled", "degraded"] | None = None


class GraphDeadlineExceeded(RuntimeError):
    pass


class GraphCheckpointIncompatible(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda item: (
            item.model_dump(mode="json") if isinstance(item, BaseModel) else _unsupported_json(item)
        ),
    )


def _unsupported_json(value: Any) -> Any:
    raise TypeError(f"unsupported strict JSON value: {type(value).__name__}")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _graph_hash(graph: ExecutionGraph | dict[str, Any]) -> str:
    payload = graph.model_dump(mode="json") if isinstance(graph, ExecutionGraph) else dict(graph)
    for field in ("graph_id", "graph_hash", "created_at"):
        payload.pop(field, None)
    if payload.get("scheduling") is None:
        payload.pop("scheduling", None)
    return _sha256(payload)


def _checkpoint_hash(checkpoint: GraphCheckpoint | dict[str, Any]) -> str:
    payload = (
        checkpoint.model_dump(mode="json")
        if isinstance(checkpoint, GraphCheckpoint)
        else dict(checkpoint)
    )
    payload.pop("snapshot_hash", None)
    return _sha256(payload)


def _require_acyclic_base(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> None:
    indegree = {node.node_id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for edge in edges:
        if edge.edge_type == EdgeType.ON_RETRYABLE_FAILURE or edge.max_traversals:
            continue
        outgoing[edge.from_node].append(edge.to_node)
        indegree[edge.to_node] += 1
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        node_id = queue.popleft()
        visited += 1
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(nodes):
        raise ValueError("execution graph contains an undeclared cycle")


def validate_execution_graph(graph: ExecutionGraph) -> ExecutionGraph:
    if graph.graph_hash != _graph_hash(graph):
        raise ValueError("execution graph hash mismatch")
    if graph.graph_id != f"graph_{graph.graph_hash[:24]}":
        raise ValueError("execution graph ID mismatch")
    return graph


def compile_execution_graph(
    request: GraphCompileInput, *, created_at: str | None = None
) -> ExecutionGraph:
    """Compile one of four allowlisted templates; model output is never graph authority."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    def node(
        node_type: NodeType,
        *,
        role: str | None = None,
        purpose: Literal["control", "primary", "evidence", "fallback"] = "control",
        parallel_group_id: str | None = None,
        provider: str | None = None,
        mutation_allowed: bool = False,
    ) -> str:
        node_id = f"n{len(nodes):02d}_{node_type.value.lower()}"
        if purpose != "primary" or any(item.node_id == node_id for item in nodes):
            suffix = f"_{purpose}" if purpose != "control" else ""
            node_id += suffix
        nodes.append(
            GraphNode(
                node_id=node_id,
                node_type=node_type,
                role=role,
                purpose=purpose,
                parallel_group_id=parallel_group_id,
                provider=provider,
                mutation_allowed=mutation_allowed,
                allowed_mutation_paths=(request.allowed_mutation_paths if mutation_allowed else ()),
                join_all=node_type == NodeType.JOIN,
            )
        )
        return node_id

    def edge(
        source: str,
        target: str,
        edge_type: EdgeType = EdgeType.ON_SUCCESS,
        *,
        max_traversals: int = 0,
    ) -> None:
        edges.append(
            GraphEdge(
                edge_id=f"e{len(edges):03d}",
                from_node=source,
                to_node=target,
                edge_type=edge_type,
                max_traversals=max_traversals,
            )
        )

    classify = node(NodeType.CLASSIFY)
    finalize = ""
    provider_nodes: list[str] = []
    parallel: list[str] = []
    template_id = f"{request.complexity}-v1"
    after_classify = classify
    approval = None

    collaborators_enabled = any(
        (
            request.reasoner_enabled and request.complexity in {"complex", "critical"},
            request.planner_enabled,
            request.frontier_enabled,
        )
    )
    if request.complexity != "simple" and collaborators_enabled:
        group = "parallel_0"
        if request.reasoner_enabled and request.complexity in {"complex", "critical"}:
            parallel.append(
                node(
                    NodeType.REASONER,
                    role="reasoner",
                    purpose="evidence",
                    parallel_group_id=group,
                    provider="local_qwythos",
                )
            )
        if request.planner_enabled:
            parallel.append(
                node(
                    NodeType.PLANNER,
                    role="planner",
                    purpose="evidence",
                    parallel_group_id=group,
                    provider="opencode_go",
                )
            )
        if request.frontier_enabled:
            parallel.append(
                node(
                    NodeType.FRONTIER_A,
                    role="frontier",
                    purpose="evidence",
                    parallel_group_id=group,
                    provider="codex_oauth",
                )
            )
        parallel.append(
            node(
                NodeType.EXECUTOR,
                role="executor",
                purpose="evidence",
                parallel_group_id=group,
                provider=request.scheduling.selected_executor,
            )
        )
        join = node(NodeType.JOIN)
        for branch in parallel:
            edge(classify, branch)
            edge(branch, join)
        after_classify = join
        provider_nodes.extend(parallel)

    if request.human_approval_required:
        policy_gate = node(NodeType.POLICY_GATE)
        approval = node(NodeType.HUMAN_APPROVAL)
        edge(after_classify, policy_gate)
        edge(policy_gate, approval)
        after_classify = approval

    select = node(NodeType.EXECUTOR_SELECT)
    edge(
        after_classify,
        select,
        EdgeType.ON_APPROVAL if approval else EdgeType.ON_SUCCESS,
    )
    primary = node(
        NodeType.EXECUTOR,
        role="executor",
        purpose="primary",
        provider=request.scheduling.selected_executor,
        mutation_allowed=True,
    )
    provider_nodes.append(primary)
    edge(select, primary)
    executors = [primary]
    if request.scheduling.fallback_executor:
        fallback = node(
            NodeType.EXECUTOR,
            role="executor",
            purpose="fallback",
            provider=request.scheduling.fallback_executor,
            mutation_allowed=True,
        )
        provider_nodes.append(fallback)
        edge(primary, fallback, EdgeType.ON_FALLBACK)
        executors.append(fallback)

    next_nodes = executors
    tool = None
    if request.tools_requested:
        tool = node(NodeType.TOOL, role="executor", mutation_allowed=True)
        for executor in next_nodes:
            edge(executor, tool, EdgeType.ON_FINDING)
        edge(tool, primary, EdgeType.ON_FINDING, max_traversals=TRANSIENT_RETRY_LIMIT)
        edge(tool, primary, EdgeType.ON_FALLBACK, max_traversals=TRANSIENT_RETRY_LIMIT)
    test = None
    if request.validation_required:
        test = node(NodeType.TEST, role="executor")
        if tool:
            edge(tool, test)
            edge(test, primary, EdgeType.ON_FINDING, max_traversals=TRANSIENT_RETRY_LIMIT)
        else:
            for previous in next_nodes:
                edge(previous, test)
            next_nodes = [test]

    reviewer = None
    if request.reviewer_enabled and request.complexity in {"engineering", "complex", "critical"}:
        reviewer = node(
            NodeType.REVIEWER,
            role="reviewer",
            purpose="evidence",
            provider="opencode_go",
        )
        provider_nodes.append(reviewer)
        for previous in next_nodes:
            edge(previous, reviewer)
        next_nodes = [reviewer]

    judge = None
    frontier_b = None
    if request.complexity == "critical" and request.judge_enabled:
        judge = node(
            NodeType.JUDGE,
            role="judge",
            purpose="evidence",
            provider="opencode_go",
        )
        provider_nodes.append(judge)
        for previous in next_nodes:
            edge(previous, judge)
        next_nodes = [judge]
        if request.frontier_enabled:
            frontier_b = node(
                NodeType.FRONTIER_B,
                role="frontier",
                purpose="evidence",
                provider="openrouter",
            )
            provider_nodes.append(frontier_b)
            edge(judge, frontier_b, EdgeType.ON_FINDING)

    checkpoint_node = None
    if request.complexity in {"complex", "critical"}:
        checkpoint_node = node(NodeType.CHECKPOINT)
        for previous in next_nodes:
            edge(previous, checkpoint_node)
        if frontier_b:
            edge(frontier_b, checkpoint_node)
        next_nodes = [checkpoint_node]

    finalize = node(NodeType.FINALIZE, role="executor")
    for previous in next_nodes:
        edge(
            previous,
            finalize,
            EdgeType.ON_CHECKPOINT if previous == checkpoint_node else EdgeType.ON_SUCCESS,
        )
    if approval:
        edge(approval, finalize, EdgeType.ON_REJECTION)
    if judge:
        edge(judge, finalize, EdgeType.ON_REJECTION)
    if tool:
        edge(tool, finalize, EdgeType.ON_BUDGET)
    if tool and test:
        edge(test, finalize, EdgeType.ON_BUDGET)

    if reviewer and request.complexity == "critical":
        edge(
            reviewer,
            primary,
            EdgeType.ON_FINDING,
            max_traversals=TRANSIENT_RETRY_LIMIT,
        )
        edge(reviewer, finalize, EdgeType.ON_NO_PROGRESS)
        edge(reviewer, finalize, EdgeType.ON_BUDGET)
        if checkpoint_node and judge:
            edge(reviewer, checkpoint_node, EdgeType.ON_APPROVAL)
    if judge and not frontier_b:
        edge(
            judge,
            primary,
            EdgeType.ON_FINDING,
            max_traversals=TRANSIENT_RETRY_LIMIT,
        )
    if frontier_b:
        edge(
            frontier_b,
            primary,
            EdgeType.ON_FINDING,
            max_traversals=TRANSIENT_RETRY_LIMIT,
        )

    for provider_node in dict.fromkeys(provider_nodes):
        edge(
            provider_node,
            provider_node,
            EdgeType.ON_RETRYABLE_FAILURE,
            max_traversals=TRANSIENT_RETRY_LIMIT,
        )
    for item in nodes:
        if item.node_id != finalize and not any(
            candidate.from_node == item.node_id and candidate.edge_type == EdgeType.ON_FAILURE
            for candidate in edges
        ):
            edge(item.node_id, finalize, EdgeType.ON_FAILURE)

    input_hash = _sha256(request.model_dump(mode="json"))
    raw: dict[str, Any] = {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "compiler_version": GRAPH_COMPILER_VERSION,
        "policy_version": request.policy_version,
        "policy_hash": request.policy_hash,
        "request_id": request.request_id,
        "api_key_id": request.api_key_id,
        "template_id": template_id,
        "input_hash": input_hash,
        "created_at": created_at or _utc_now(),
        "deadline": request.deadline,
        "budgets": request.budgets.model_dump(mode="json"),
        "scheduling": request.scheduling.model_dump(mode="json"),
        "entry_nodes": (classify,),
        "terminal_nodes": (finalize,),
        "nodes": tuple(nodes),
        "edges": tuple(edges),
    }
    raw["graph_hash"] = _graph_hash(raw)
    raw["graph_id"] = f"graph_{raw['graph_hash'][:24]}"
    return validate_execution_graph(ExecutionGraph.model_validate(raw))


class ExecutionGraphRuntime:
    def __init__(self, graph: ExecutionGraph, store: ExecutionGraphStore | None = None):
        self.graph = validate_execution_graph(graph)
        self.store = store
        self.node_states = {
            node.node_id: (
                NodeState.QUEUED
                if node.node_id in graph.entry_nodes
                else NodeState.WAITING_DEPENDENCY
            )
            for node in graph.nodes
        }
        self.selected_edge_ids: list[str] = []
        self.traversal_counts: dict[str, int] = {}
        self.attempt_counts: dict[str, int] = {}
        self.attempts: list[NodeAttempt] = []
        self.provider_pins: dict[str, str] = {}
        self.model_pins: dict[str, str] = {}
        self.artifact_hashes: dict[str, str] = {}
        self.failure_fingerprints: list[str] = []
        self.progress_evidence_ids: list[str] = []
        self.token_usage = 0
        self.tool_calls = 0
        self.final_emitted = False
        self.terminal_status: Literal["completed", "failed", "cancelled", "degraded"] | None = None
        self.last_checkpoint_id: str | None = None
        self.checkpoint_count = 0
        self.active_state_object_ref = ""
        self.event_cursor = 0
        self.checkpoint_size_before = 0
        self.checkpoint_size_after = 0
        if self.store:
            self.store.save_graph(graph)

    @property
    def _nodes(self) -> dict[str, GraphNode]:
        return {node.node_id: node for node in self.graph.nodes}

    @property
    def _edges(self) -> dict[str, GraphEdge]:
        return {edge.edge_id: edge for edge in self.graph.edges}

    def _incoming(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.graph.edges if edge.to_node == node_id]

    def _outgoing(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.graph.edges if edge.from_node == node_id]

    def _is_ready(self, node: GraphNode) -> bool:
        state = self.node_states[node.node_id]
        if state not in {
            NodeState.QUEUED,
            NodeState.WAITING_DEPENDENCY,
            NodeState.RETRYING,
            NodeState.FALLBACK,
        }:
            return False
        incoming = self._incoming(node.node_id)
        if not incoming:
            return node.node_id in self.graph.entry_nodes
        selected = set(self.selected_edge_ids)
        if node.join_all:
            required = [
                edge.edge_id
                for edge in incoming
                if edge.edge_type not in {EdgeType.ON_FAILURE, EdgeType.ON_RETRYABLE_FAILURE}
            ]
            return bool(required) and all(edge_id in selected for edge_id in required)
        return any(edge.edge_id in selected for edge in incoming)

    def ready_node_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.graph.nodes if self._is_ready(node))

    def _check_deadline(self) -> None:
        deadline = datetime.fromisoformat(self.graph.deadline.replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(self.graph.created_at.replace("Z", "+00:00"))
        budget_deadline = created_at + timedelta(seconds=self.graph.budgets.wall_clock_seconds)
        if datetime.now(UTC) >= min(deadline, budget_deadline):
            raise GraphDeadlineExceeded("GRAPH_DEADLINE_EXCEEDED")

    def start_attempt(self, node_id: str, *, model: str | None = None) -> NodeAttempt:
        self._check_deadline()
        if node_id not in self.ready_node_ids():
            raise ValueError("execution node is not ready")
        node = self._nodes[node_id]
        provider = node.provider
        if provider:
            pinned = self.provider_pins.setdefault(node_id, provider)
            if pinned != provider:
                raise ValueError("provider pin mismatch")
        if model is not None and not model:
            raise ValueError("model pin cannot be empty")
        if model:
            pinned_model = self.model_pins.setdefault(node_id, model)
            if pinned_model != model:
                raise ValueError("model pin mismatch")
        count = self.attempt_counts.get(node_id, 0) + 1
        self.attempt_counts[node_id] = count
        incoming = [
            edge.edge_id
            for edge in self._incoming(node_id)
            if edge.edge_id in self.selected_edge_ids
        ]
        attempt_state = (
            NodeState.WAITING_APPROVAL
            if node.node_type == NodeType.HUMAN_APPROVAL
            else NodeState.WAITING_TOOL
            if node.node_type == NodeType.TOOL
            else NodeState.RUNNING
        )
        attempt = NodeAttempt(
            node_id=node_id,
            attempt_id=f"{node_id}_a{count:03d}",
            node_type=node.node_type,
            role=node.role,
            provider=provider,
            model=self.model_pins.get(node_id),
            state=attempt_state,
            parent_node_ids=tuple(
                edge.from_node
                for edge in self._incoming(node_id)
                if edge.edge_id in self.selected_edge_ids
            ),
            parallel_group_id=node.parallel_group_id,
            selected_incoming_edge=incoming[-1] if incoming else None,
            available_outgoing_edges=tuple(edge.edge_id for edge in self._outgoing(node_id)),
            started_at=_utc_now(),
            deadline=self.graph.deadline,
        )
        self.node_states[node_id] = attempt_state
        self.attempts.append(attempt)
        self._persist(attempt, "attempt_started")
        return attempt

    def start_node_type(
        self,
        node_type: NodeType,
        *,
        purpose: str | None = None,
        model: str | None = None,
    ) -> NodeAttempt | None:
        node = next(
            (
                item
                for item in self.graph.nodes
                if item.node_type == node_type and (purpose is None or item.purpose == purpose)
            ),
            None,
        )
        return None if node is None else self.start_attempt(node.node_id, model=model)

    def finish_observed_attempt(
        self,
        attempt_id: str,
        invocation: dict[str, Any],
        *,
        outcome: EdgeType = EdgeType.ON_SUCCESS,
        generated_evidence_ids: tuple[str, ...] = (),
        progress_evidence_ids: tuple[str, ...] = (),
        validated_evidence_ids: tuple[str, ...] = (),
        contradicted_evidence_ids: tuple[str, ...] = (),
    ) -> NodeAttempt:
        total_tokens = invocation.get("total_tokens")
        total_tokens = total_tokens if type(total_tokens) is int and total_tokens >= 0 else 0
        cached_tokens = invocation.get("cached_tokens")
        cached_tokens = (
            cached_tokens
            if type(cached_tokens) is int and 0 <= cached_tokens <= total_tokens
            else None
        )

        def metric(name: str) -> float | None:
            value = invocation.get(name)
            return (
                float(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else None
            )

        return self.finish_attempt(
            attempt_id,
            outcome=outcome,
            token_usage=total_tokens,
            cached_tokens=cached_tokens,
            cost_usd=metric("cost_usd"),
            latency_ms=metric("latency_ms"),
            generated_evidence_ids=generated_evidence_ids,
            progress_evidence_ids=progress_evidence_ids,
            validated_evidence_ids=validated_evidence_ids,
            contradicted_evidence_ids=contradicted_evidence_ids,
        )

    def fail_role_attempt(
        self,
        attempt_id: str,
        role: str,
        error: Exception,
        *,
        generated_evidence_ids: tuple[str, ...] = (),
    ) -> NodeAttempt:
        failure_code = f"{role.upper()}_{type(error).__name__.upper()}"
        return self.fail_attempt(
            attempt_id,
            failure_code=failure_code,
            failure_fingerprint=hashlib.sha256(failure_code.encode()).hexdigest(),
            retryable=False,
            generated_evidence_ids=generated_evidence_ids,
        )

    def _attempt(self, node_type: NodeType, state: NodeState) -> NodeAttempt | None:
        return next(
            (
                item
                for item in reversed(self.attempts)
                if (item.node_type, item.state) == (node_type, state)
            ),
            None,
        )

    def resume_tool_result(self, evidence_id: str, execution: dict[str, Any]) -> bool:
        attempt = self._attempt(NodeType.TOOL, NodeState.WAITING_TOOL)
        if attempt is None:
            return False
        if execution.get("exit_code") != 0:
            failure_code = str(execution.get("failure_class") or "TOOL_EXECUTION_FAILED")
            self.fail_attempt(
                attempt.attempt_id,
                failure_code=failure_code,
                failure_fingerprint=hashlib.sha256(failure_code.encode()).hexdigest(),
                retryable=False,
                generated_evidence_ids=(evidence_id,),
            )
            return True
        test_node = next(
            (node for node in self.graph.nodes if node.node_type == NodeType.TEST), None
        )
        arguments = json.dumps(
            execution.get("normalized_arguments", {}),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        validation_observed = bool(test_node is not None and VALIDATION_COMMAND.search(arguments))
        self.finish_attempt(
            attempt.attempt_id,
            outcome=EdgeType.ON_SUCCESS if validation_observed else EdgeType.ON_FINDING,
            progress_evidence_ids=() if validation_observed else (evidence_id,),
            generated_evidence_ids=(evidence_id,),
            validated_evidence_ids=(evidence_id,),
        )
        if validation_observed:
            assert test_node is not None
            test_attempt = self.start_attempt(test_node.node_id)
            self.finish_attempt(
                test_attempt.attempt_id,
                outcome=EdgeType.ON_FINDING,
                progress_evidence_ids=(evidence_id,),
                generated_evidence_ids=(evidence_id,),
                validated_evidence_ids=(evidence_id,),
            )
        return True

    def resume_approval(self, evidence_id: str) -> bool:
        attempt = self._attempt(NodeType.HUMAN_APPROVAL, NodeState.WAITING_APPROVAL)
        if attempt is None:
            return False
        self.finish_attempt(
            attempt.attempt_id,
            outcome=EdgeType.ON_APPROVAL,
            generated_evidence_ids=(evidence_id,),
            validated_evidence_ids=(evidence_id,),
        )
        return True

    def waiting_for_external(self) -> bool:
        return bool(
            self._attempt(NodeType.TOOL, NodeState.WAITING_TOOL)
            or self._attempt(NodeType.HUMAN_APPROVAL, NodeState.WAITING_APPROVAL)
        )

    def approval_continuable(self) -> bool:
        return (
            self._attempt(NodeType.HUMAN_APPROVAL, NodeState.SUCCEEDED) is not None
            and not self.waiting_for_external()
            and not self.final_emitted
            and bool(self.ready_node_ids())
        )

    def finalize_ready(
        self,
        terminal_status: Literal["completed", "failed", "cancelled", "degraded"],
        *,
        generated_evidence_ids: tuple[str, ...] = (),
        validated_evidence_ids: tuple[str, ...] = (),
        contradicted_evidence_ids: tuple[str, ...] = (),
    ) -> None:
        if self.waiting_for_external():
            return
        ready = self.ready_node_ids()
        checkpoint = next(
            (
                node
                for node in self.graph.nodes
                if node.node_type == NodeType.CHECKPOINT and node.node_id in ready
            ),
            None,
        )
        if checkpoint is not None:
            attempt = self.start_attempt(checkpoint.node_id)
            self.finish_attempt(attempt.attempt_id, outcome=EdgeType.ON_CHECKPOINT)
        terminal = self.start_attempt(self.graph.terminal_nodes[0])
        self.finish_attempt(
            terminal.attempt_id,
            terminal_status=terminal_status,
            generated_evidence_ids=generated_evidence_ids,
            validated_evidence_ids=validated_evidence_ids,
            contradicted_evidence_ids=contradicted_evidence_ids,
        )

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        outcome: EdgeType = EdgeType.ON_SUCCESS,
        token_usage: int = 0,
        cached_tokens: int | None = None,
        cost_usd: float | None = None,
        latency_ms: float | None = None,
        progress_evidence_ids: tuple[str, ...] = (),
        generated_evidence_ids: tuple[str, ...] = (),
        validated_evidence_ids: tuple[str, ...] = (),
        contradicted_evidence_ids: tuple[str, ...] = (),
        public_output_ref: str | None = None,
        artifact_hash: str | None = None,
        terminal_status: Literal["completed", "failed", "cancelled", "degraded"] | None = None,
    ) -> NodeAttempt:
        attempt = self._active_attempt(attempt_id)
        if type(token_usage) is not int or token_usage < 0:
            raise ValueError("token usage must be a nonnegative integer")
        if cached_tokens is not None and (
            type(cached_tokens) is not int or not 0 <= cached_tokens <= token_usage
        ):
            raise ValueError("cached tokens must be between zero and token usage")
        if self.token_usage + token_usage > self.graph.budgets.tokens:
            raise ValueError("GRAPH_TOKEN_BUDGET_EXHAUSTED")
        if cost_usd is not None and (
            isinstance(cost_usd, bool)
            or not isinstance(cost_usd, int | float)
            or not math.isfinite(cost_usd)
            or cost_usd < 0
        ):
            raise ValueError("cost must be a finite nonnegative number")
        if latency_ms is not None and (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, int | float)
            or not math.isfinite(latency_ms)
            or latency_ms < 0
        ):
            raise ValueError("latency must be a finite nonnegative number")
        node = self._nodes[attempt.node_id]
        if node.node_type == NodeType.TOOL and self.tool_calls >= self.graph.budgets.tool_calls:
            raise ValueError("GRAPH_TOOL_BUDGET_EXHAUSTED")
        progress_evidence_ids = _bounded_ids(progress_evidence_ids)
        generated_evidence_ids = _bounded_ids(generated_evidence_ids)
        validated_evidence_ids = _bounded_ids(validated_evidence_ids)
        contradicted_evidence_ids = _bounded_ids(contradicted_evidence_ids)
        if artifact_hash is not None and re.fullmatch(r"[0-9a-f]{64}", artifact_hash) is None:
            raise ValueError("artifact hash must be SHA-256")
        new_progress_evidence_ids = tuple(
            evidence_id
            for evidence_id in progress_evidence_ids
            if evidence_id not in self.progress_evidence_ids
        )
        if outcome == EdgeType.ON_FINDING and not set(new_progress_evidence_ids).issubset(
            validated_evidence_ids
        ):
            raise ValueError("repair progress requires validated Evidence node IDs")
        if outcome in {EdgeType.ON_APPROVAL, EdgeType.ON_REJECTION} and not validated_evidence_ids:
            raise ValueError("approval decisions require validated Evidence node IDs")
        if outcome in {
            EdgeType.ON_FAILURE,
            EdgeType.ON_RETRYABLE_FAILURE,
            EdgeType.ON_FALLBACK,
        }:
            raise ValueError("failure and fallback outcomes use fail_attempt")
        if node.node_type == NodeType.FINALIZE:
            if terminal_status is None:
                raise ValueError("FINALIZE requires terminal status")
            if terminal_status == "completed" and not validated_evidence_ids:
                raise ValueError("completed graph requires validated Evidence node IDs")
            if self.final_emitted:
                raise ValueError("graph terminal already emitted")
        elif terminal_status is not None:
            raise ValueError("only FINALIZE accepts terminal status")

        selected = self._select_outcome_edges(
            node,
            outcome,
            bool(new_progress_evidence_ids),
        )
        self.token_usage += token_usage
        if node.node_type == NodeType.TOOL:
            self.tool_calls += 1
        attempt.state = NodeState.SUCCEEDED
        attempt.ended_at = _utc_now()
        attempt.latency_ms = latency_ms
        attempt.token_usage = token_usage
        attempt.cached_tokens = cached_tokens
        attempt.cost_usd = cost_usd
        attempt.progress_evidence_ids = progress_evidence_ids
        attempt.generated_evidence_ids = generated_evidence_ids
        attempt.validated_evidence_ids = validated_evidence_ids
        attempt.contradicted_evidence_ids = contradicted_evidence_ids
        attempt.public_output_ref = public_output_ref
        attempt.artifact_hash = artifact_hash
        attempt.selected_outgoing_edges = tuple(edge.edge_id for edge in selected)
        self.node_states[node.node_id] = NodeState.SUCCEEDED
        for evidence_id in progress_evidence_ids:
            if evidence_id not in self.progress_evidence_ids:
                self.progress_evidence_ids.append(evidence_id)
        if artifact_hash is not None:
            self.artifact_hashes[node.node_id] = artifact_hash
        self._apply_selected_edges(selected, node, new_progress_evidence_ids)
        if node.node_type == NodeType.FINALIZE:
            self.final_emitted = True
            self.terminal_status = terminal_status
        if node.node_type == NodeType.CHECKPOINT:
            checkpoint = self.checkpoint(reason="checkpoint_node")
            attempt.checkpoint_id = checkpoint.checkpoint_id
            if self.store:
                self.store.save_attempt(self.graph.graph_id, attempt)
        else:
            self._persist(attempt, "attempt_finished")
        return attempt

    def fail_attempt(
        self,
        attempt_id: str,
        *,
        failure_code: str,
        failure_fingerprint: str,
        retryable: bool,
        generated_evidence_ids: tuple[str, ...] = (),
    ) -> NodeAttempt:
        attempt = self._active_attempt(attempt_id)
        if not failure_code or re.fullmatch(r"[0-9a-f]{64}", failure_fingerprint) is None:
            raise ValueError("typed failure code and SHA-256 fingerprint are required")
        attempt.state = NodeState.FAILED
        attempt.ended_at = _utc_now()
        attempt.failure_code = failure_code
        attempt.failure_fingerprint = failure_fingerprint
        self.node_states[attempt.node_id] = NodeState.FAILED
        if failure_fingerprint not in self.failure_fingerprints:
            self.failure_fingerprints.append(failure_fingerprint)
        attempt.generated_evidence_ids = _bounded_ids(generated_evidence_ids)

        selected: list[GraphEdge] = []
        retry = next(
            (
                edge
                for edge in self._outgoing(attempt.node_id)
                if edge.edge_type == EdgeType.ON_RETRYABLE_FAILURE
            ),
            None,
        )
        if retryable and retry is not None:
            traversals = self.traversal_counts.get(retry.edge_id, 0)
            if traversals < retry.max_traversals:
                self.traversal_counts[retry.edge_id] = traversals + 1
                selected = [retry]
                self.node_states[attempt.node_id] = NodeState.RETRYING
        if not selected:
            fallback = next(
                (
                    edge
                    for edge in self._outgoing(attempt.node_id)
                    if edge.edge_type == EdgeType.ON_FALLBACK
                ),
                None,
            )
            if fallback and fallback.max_traversals:
                traversals = self.traversal_counts.get(fallback.edge_id, 0)
                if traversals < fallback.max_traversals:
                    self.traversal_counts[fallback.edge_id] = traversals + 1
                else:
                    fallback = None
            if fallback:
                selected = [fallback]
                if fallback.max_traversals:
                    affected = self._descendants(fallback.to_node)
                    self.selected_edge_ids = [
                        edge_id
                        for edge_id in self.selected_edge_ids
                        if self._edges[edge_id].from_node not in affected
                    ]
                    for node_id in affected:
                        self.node_states[node_id] = NodeState.WAITING_DEPENDENCY
                    self.node_states[attempt.node_id] = NodeState.WAITING_DEPENDENCY
                    self.node_states[fallback.to_node] = NodeState.FALLBACK
                else:
                    self.node_states[attempt.node_id] = NodeState.DEGRADED
                    self.node_states[fallback.to_node] = NodeState.FALLBACK
            else:
                selected = [
                    edge
                    for edge in self._outgoing(attempt.node_id)
                    if edge.edge_type == EdgeType.ON_FAILURE
                ]
        attempt.selected_outgoing_edges = tuple(edge.edge_id for edge in selected)
        self._record_edges(selected)
        self._close_unselected_for_terminal(selected, attempt.node_id)
        self._persist(attempt, "attempt_failed")
        return attempt

    def cancel(self) -> None:
        if self.final_emitted:
            return
        active_node_id = next(
            (
                attempt.node_id
                for attempt in reversed(self.attempts)
                if attempt.state
                in {
                    NodeState.DISPATCHING,
                    NodeState.RUNNING,
                    NodeState.STREAMING,
                    NodeState.WAITING_TOOL,
                    NodeState.WAITING_APPROVAL,
                }
            ),
            self.graph.entry_nodes[0],
        )
        if active_node_id in self.graph.terminal_nodes:
            active_node_id = self.graph.entry_nodes[0]
        for attempt in self.attempts:
            if attempt.state in {
                NodeState.DISPATCHING,
                NodeState.RUNNING,
                NodeState.STREAMING,
                NodeState.WAITING_TOOL,
                NodeState.WAITING_APPROVAL,
            }:
                attempt.state = NodeState.CANCELLED
                attempt.ended_at = _utc_now()
                attempt.failure_code = "GRAPH_CANCELLED"
                if self.store:
                    self.store.save_attempt(self.graph.graph_id, attempt)
        terminal = self.graph.terminal_nodes[0]
        for node_id, state in self.node_states.items():
            if node_id == terminal:
                self.node_states[node_id] = NodeState.WAITING_DEPENDENCY
                continue
            if state not in {NodeState.SUCCEEDED, NodeState.FAILED, NodeState.DEGRADED}:
                self.node_states[node_id] = NodeState.CANCELLED
        failure_edge = next(
            (
                edge
                for edge in self._outgoing(active_node_id)
                if edge.edge_type == EdgeType.ON_FAILURE and edge.to_node == terminal
            ),
            None,
        )
        if failure_edge is None:
            raise ValueError("execution graph has no cancellation terminal edge")
        self._record_edges([failure_edge])
        self.terminal_status = None
        self._persist(None, "cancelled")

    def partial_rerun(
        self,
        invalidated_node_ids: set[str],
        *,
        verified_artifact_hashes: dict[str, str] | None = None,
    ) -> tuple[str, ...]:
        if not invalidated_node_ids:
            raise ValueError("partial rerun requires an invalidated node")
        unknown = invalidated_node_ids.difference(self.node_states)
        if unknown:
            raise ValueError(f"unknown invalidated nodes: {sorted(unknown)}")
        incomplete = {
            node_id
            for node_id in invalidated_node_ids
            if self.node_states[node_id]
            not in {NodeState.SUCCEEDED, NodeState.DEGRADED, NodeState.FAILED}
        }
        if incomplete:
            raise ValueError(f"GRAPH_INVALIDATED_NODE_NOT_COMPLETED: {sorted(incomplete)}")
        affected = set(invalidated_node_ids)
        queue = deque(invalidated_node_ids)
        while queue:
            source = queue.popleft()
            for edge in self._outgoing(source):
                if edge.edge_type in {EdgeType.ON_RETRYABLE_FAILURE, EdgeType.ON_FINDING}:
                    continue
                if edge.to_node not in affected:
                    affected.add(edge.to_node)
                    queue.append(edge.to_node)
        preserved = {
            node_id: artifact_hash
            for node_id, artifact_hash in self.artifact_hashes.items()
            if node_id not in affected and self.node_states[node_id] == NodeState.SUCCEEDED
        }
        if preserved and verified_artifact_hashes is None:
            raise ValueError("GRAPH_ARTIFACT_VERIFICATION_REQUIRED")
        if any(
            verified_artifact_hashes is None
            or verified_artifact_hashes.get(node_id) != artifact_hash
            for node_id, artifact_hash in preserved.items()
        ):
            raise ValueError("GRAPH_ARTIFACT_HASH_MISMATCH")
        self.selected_edge_ids = [
            edge_id
            for edge_id in self.selected_edge_ids
            if self._edges[edge_id].from_node not in affected
        ]
        for node_id in affected:
            self.node_states[node_id] = NodeState.WAITING_DEPENDENCY
        for node_id in invalidated_node_ids:
            self.node_states[node_id] = NodeState.QUEUED
        if set(self.graph.terminal_nodes).intersection(affected):
            self.final_emitted = False
            self.terminal_status = None
        ordered = tuple(node.node_id for node in self.graph.nodes if node.node_id in affected)
        self._persist(None, "partial_rerun")
        return ordered

    def checkpoint(
        self,
        *,
        reason: str,
        active_state_object_ref: str | None = None,
        event_cursor: int | None = None,
        size_before: int | None = None,
        size_after: int | None = None,
        persist: bool = True,
    ) -> GraphCheckpoint:
        active_state_object_ref = (
            self.active_state_object_ref
            if active_state_object_ref is None
            else active_state_object_ref
        )
        event_cursor = self.event_cursor if event_cursor is None else event_cursor
        size_before = self.checkpoint_size_before if size_before is None else size_before
        size_after = self.checkpoint_size_after if size_after is None else size_after
        if (
            type(event_cursor) is not int
            or event_cursor < 0
            or type(size_before) is not int
            or size_before < 0
            or type(size_after) is not int
            or size_after < 0
        ):
            raise ValueError("checkpoint counters must be nonnegative integers")
        if not isinstance(reason, str) or not reason:
            raise ValueError("checkpoint reason is required")
        self.active_state_object_ref = active_state_object_ref
        self.event_cursor = event_cursor
        self.checkpoint_size_before = size_before
        self.checkpoint_size_after = size_after
        self.checkpoint_count += 1
        checkpoint_id = f"cp_{self.checkpoint_count:06d}"
        active_states = {
            NodeState.DISPATCHING,
            NodeState.RUNNING,
            NodeState.STREAMING,
            NodeState.WAITING_TOOL,
            NodeState.WAITING_APPROVAL,
        }
        completed_states = {NodeState.SUCCEEDED, NodeState.DEGRADED, NodeState.SKIPPED}
        available_edges = tuple(
            edge.edge_id for node_id in self.ready_node_ids() for edge in self._outgoing(node_id)
        )
        raw: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "graph_id": self.graph.graph_id,
            "graph_hash": self.graph.graph_hash,
            "graph_schema_version": self.graph.graph_schema_version,
            "compiler_version": self.graph.compiler_version,
            "policy_version": self.graph.policy_version,
            "parent_checkpoint_id": self.last_checkpoint_id,
            "completed_node_ids": tuple(
                node_id for node_id, state in self.node_states.items() if state in completed_states
            ),
            "active_node_ids": tuple(
                node_id for node_id, state in self.node_states.items() if state in active_states
            ),
            "pending_node_ids": tuple(
                node_id
                for node_id, state in self.node_states.items()
                if state
                not in active_states | completed_states | {NodeState.CANCELLED, NodeState.FAILED}
            ),
            "selected_edges": tuple(self.selected_edge_ids),
            "available_edges": available_edges,
            "provider_pins": dict(self.provider_pins),
            "model_pins": dict(self.model_pins),
            "artifact_hashes": dict(self.artifact_hashes),
            "remaining_budgets": {
                "tokens": self.graph.budgets.tokens - self.token_usage,
                "tool_calls": self.graph.budgets.tool_calls - self.tool_calls,
                "wall_clock_seconds": max(
                    0,
                    int(
                        (
                            min(
                                datetime.fromisoformat(self.graph.deadline.replace("Z", "+00:00")),
                                datetime.fromisoformat(self.graph.created_at.replace("Z", "+00:00"))
                                + timedelta(seconds=self.graph.budgets.wall_clock_seconds),
                            )
                            - datetime.now(UTC)
                        ).total_seconds()
                    ),
                ),
            },
            "failure_fingerprints": tuple(self.failure_fingerprints),
            "progress_evidence_ids": tuple(self.progress_evidence_ids),
            "active_state_object_ref": active_state_object_ref,
            "event_cursor": event_cursor,
            "size_before": size_before,
            "size_after": size_after,
            "reason": reason,
            "created_at": _utc_now(),
            "node_states": dict(self.node_states),
            "traversal_counts": dict(self.traversal_counts),
            "attempt_counts": dict(self.attempt_counts),
            "token_usage": self.token_usage,
            "tool_calls": self.tool_calls,
            "final_emitted": self.final_emitted,
            "terminal_status": self.terminal_status,
        }
        raw["snapshot_hash"] = _checkpoint_hash(raw)
        checkpoint = GraphCheckpoint.model_validate(raw)
        self.last_checkpoint_id = checkpoint_id
        if persist and self.store:
            self.store.save_checkpoint(checkpoint)
        return checkpoint

    @classmethod
    def resume(
        cls,
        graph: ExecutionGraph,
        checkpoint: GraphCheckpoint,
        *,
        attempts: list[NodeAttempt] | None = None,
        store: ExecutionGraphStore | None = None,
    ) -> ExecutionGraphRuntime:
        validate_execution_graph(graph)
        if (
            checkpoint.graph_id != graph.graph_id
            or checkpoint.graph_hash != graph.graph_hash
            or checkpoint.graph_schema_version != graph.graph_schema_version
            or checkpoint.compiler_version != graph.compiler_version
            or checkpoint.policy_version != graph.policy_version
            or checkpoint.snapshot_hash != _checkpoint_hash(checkpoint)
        ):
            raise GraphCheckpointIncompatible("GRAPH_CHECKPOINT_INCOMPATIBLE")
        runtime = cls(graph, store=None)
        if set(checkpoint.node_states) != {node.node_id for node in graph.nodes}:
            raise GraphCheckpointIncompatible("GRAPH_CHECKPOINT_NODE_SET_MISMATCH")
        runtime.node_states = dict(checkpoint.node_states)
        runtime.selected_edge_ids = list(checkpoint.selected_edges)
        runtime.traversal_counts = dict(checkpoint.traversal_counts)
        runtime.attempt_counts = dict(checkpoint.attempt_counts)
        runtime.provider_pins = dict(checkpoint.provider_pins)
        runtime.model_pins = dict(checkpoint.model_pins)
        runtime.artifact_hashes = dict(checkpoint.artifact_hashes)
        runtime.failure_fingerprints = list(checkpoint.failure_fingerprints)
        runtime.progress_evidence_ids = list(checkpoint.progress_evidence_ids)
        runtime.token_usage = checkpoint.token_usage
        runtime.tool_calls = checkpoint.tool_calls
        runtime.final_emitted = checkpoint.final_emitted
        runtime.terminal_status = checkpoint.terminal_status
        runtime.last_checkpoint_id = checkpoint.checkpoint_id
        runtime.checkpoint_count = int(checkpoint.checkpoint_id.removeprefix("cp_"))
        runtime.active_state_object_ref = checkpoint.active_state_object_ref
        runtime.event_cursor = checkpoint.event_cursor
        runtime.checkpoint_size_before = checkpoint.size_before
        runtime.checkpoint_size_after = checkpoint.size_after
        runtime.attempts = attempts or []
        runtime.store = store
        known_nodes = {node.node_id for node in graph.nodes}
        known_edges = {edge.edge_id for edge in graph.edges}
        repeat_edges = {
            edge.edge_id: edge.max_traversals for edge in graph.edges if edge.max_traversals
        }
        if (
            not set(checkpoint.selected_edges).issubset(known_edges)
            or not set(checkpoint.traversal_counts).issubset(repeat_edges)
            or any(
                count < 0 or count > repeat_edges[edge_id]
                for edge_id, count in checkpoint.traversal_counts.items()
            )
            or not set(checkpoint.attempt_counts).issubset(known_nodes)
            or any(
                type(count) is not int or count < 0 for count in checkpoint.attempt_counts.values()
            )
            or not set(checkpoint.artifact_hashes).issubset(known_nodes)
            or not set(checkpoint.model_pins).issubset(known_nodes)
            or any(not model for model in checkpoint.model_pins.values())
            or any(
                re.fullmatch(r"[0-9a-f]{64}", artifact_hash) is None
                for artifact_hash in checkpoint.artifact_hashes.values()
            )
            or checkpoint.token_usage > graph.budgets.tokens
            or checkpoint.tool_calls > graph.budgets.tool_calls
        ):
            raise GraphCheckpointIncompatible("GRAPH_CHECKPOINT_STATE_INVALID")
        for node_id, provider in checkpoint.provider_pins.items():
            if node_id not in known_nodes or runtime._nodes[node_id].provider != provider:
                raise GraphCheckpointIncompatible("GRAPH_CHECKPOINT_PROVIDER_PIN_MISMATCH")
        interrupted = [
            attempt
            for attempt in runtime.attempts
            if attempt.state
            in {
                NodeState.DISPATCHING,
                NodeState.RUNNING,
                NodeState.STREAMING,
            }
        ]
        restart_fingerprint = hashlib.sha256(b"GRAPH_PROCESS_RESTART").hexdigest()
        for attempt in interrupted:
            if attempt.state in {
                NodeState.DISPATCHING,
                NodeState.RUNNING,
                NodeState.STREAMING,
            }:
                runtime.fail_attempt(
                    attempt.attempt_id,
                    failure_code="GRAPH_PROCESS_RESTART",
                    failure_fingerprint=restart_fingerprint,
                    retryable=True,
                )
        if store:
            store.save_graph(graph)
        runtime._persist(None, "resumed")
        return runtime

    def _active_attempt(self, attempt_id: str) -> NodeAttempt:
        attempt = next(
            (item for item in reversed(self.attempts) if item.attempt_id == attempt_id), None
        )
        if attempt is None or attempt.state not in {
            NodeState.RUNNING,
            NodeState.WAITING_APPROVAL,
            NodeState.WAITING_TOOL,
        }:
            raise ValueError("attempt is not active")
        return attempt

    def _select_outcome_edges(
        self, node: GraphNode, outcome: EdgeType, has_progress: bool
    ) -> list[GraphEdge]:
        if outcome == EdgeType.ON_FINDING:
            repairs = [
                edge
                for edge in self._outgoing(node.node_id)
                if edge.edge_type == EdgeType.ON_FINDING
                and self._nodes[edge.to_node].node_type == NodeType.EXECUTOR
            ]
            if repairs and has_progress:
                edge = repairs[0]
                traversals = self.traversal_counts.get(edge.edge_id, 0)
                if traversals < edge.max_traversals:
                    self.traversal_counts[edge.edge_id] = traversals + 1
                    return [edge]
                outcome = EdgeType.ON_BUDGET
            elif repairs:
                outcome = EdgeType.ON_NO_PROGRESS
        selected = [edge for edge in self._outgoing(node.node_id) if edge.edge_type == outcome]
        if not selected and node.node_type not in {NodeType.FINALIZE}:
            raise ValueError(f"node has no {outcome.value} edge")
        return selected

    def _apply_selected_edges(
        self, selected: list[GraphEdge], node: GraphNode, progress_ids: tuple[str, ...]
    ) -> None:
        self._record_edges(selected)
        self._close_unselected_for_terminal(selected, node.node_id)
        if any(edge.edge_type == EdgeType.ON_SUCCESS for edge in selected):
            for edge in self._outgoing(node.node_id):
                if edge.edge_type == EdgeType.ON_FALLBACK:
                    self.node_states[edge.to_node] = NodeState.SKIPPED
        repair = next((edge for edge in selected if edge.edge_type == EdgeType.ON_FINDING), None)
        if repair and progress_ids:
            affected = self._descendants(repair.to_node)
            self.selected_edge_ids = [
                edge_id
                for edge_id in self.selected_edge_ids
                if self._edges[edge_id].from_node not in affected or edge_id == repair.edge_id
            ]
            for node_id in affected:
                self.node_states[node_id] = NodeState.WAITING_DEPENDENCY
            self.node_states[repair.to_node] = NodeState.RETRYING
            self.node_states[node.node_id] = NodeState.WAITING_DEPENDENCY

    def _close_unselected_for_terminal(
        self, selected: list[GraphEdge], source_node_id: str
    ) -> None:
        terminal = next(
            (
                edge.to_node
                for edge in selected
                if edge.to_node in self.graph.terminal_nodes
                and edge.edge_type != EdgeType.ON_SUCCESS
            ),
            None,
        )
        if terminal is None:
            return
        for attempt in self.attempts:
            if attempt.node_id != source_node_id and attempt.state in {
                NodeState.DISPATCHING,
                NodeState.RUNNING,
                NodeState.STREAMING,
                NodeState.WAITING_TOOL,
                NodeState.WAITING_APPROVAL,
            }:
                attempt.state = NodeState.CANCELLED
                attempt.ended_at = _utc_now()
                attempt.failure_code = "GRAPH_FAIL_CLOSED"
                if self.store:
                    self.store.save_attempt(self.graph.graph_id, attempt)
        for node_id, state in self.node_states.items():
            if node_id in {source_node_id, terminal}:
                continue
            if state not in {NodeState.SUCCEEDED, NodeState.DEGRADED, NodeState.FAILED}:
                self.node_states[node_id] = (
                    NodeState.CANCELLED
                    if state
                    in {
                        NodeState.DISPATCHING,
                        NodeState.RUNNING,
                        NodeState.STREAMING,
                        NodeState.WAITING_TOOL,
                        NodeState.WAITING_APPROVAL,
                    }
                    else NodeState.SKIPPED
                )

    def _record_edges(self, selected: list[GraphEdge]) -> None:
        for edge in selected:
            if edge.edge_id not in self.selected_edge_ids:
                self.selected_edge_ids.append(edge.edge_id)

    def _descendants(self, node_id: str) -> set[str]:
        affected = {node_id}
        queue = deque([node_id])
        while queue:
            source = queue.popleft()
            for edge in self._outgoing(source):
                if edge.edge_type in {EdgeType.ON_RETRYABLE_FAILURE, EdgeType.ON_FINDING}:
                    continue
                if edge.to_node not in affected:
                    affected.add(edge.to_node)
                    queue.append(edge.to_node)
        return affected

    def _persist(self, attempt: NodeAttempt | None, reason: str) -> None:
        if not self.store:
            return
        if attempt:
            self.store.save_attempt(self.graph.graph_id, attempt)
        self.checkpoint(reason=reason)


class ExecutionGraphStore:
    """Small SQLite persistence boundary; payloads stay strict JSON and append-only by ID."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._identities: dict[str, tuple[str, str]] = {}
        self._event_listeners: list[GraphEventListener] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS execution_graphs "
                "(graph_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS execution_graph_attempts "
                "(graph_id TEXT NOT NULL, attempt_id TEXT NOT NULL, payload TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, PRIMARY KEY(graph_id, attempt_id))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS execution_graph_checkpoints "
                "(graph_id TEXT NOT NULL, checkpoint_id TEXT NOT NULL, payload TEXT NOT NULL, "
                "created_at TEXT NOT NULL, PRIMARY KEY(graph_id, checkpoint_id))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS execution_graph_active_states "
                "(object_ref TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def subscribe_events(self, listener: GraphEventListener) -> None:
        self._event_listeners.append(listener)

    def _publish(
        self,
        event_type: str,
        graph_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        identity = self._identities.get(graph_id)
        if identity is None:
            try:
                graph = self.load_graph(graph_id)
            except (KeyError, ValueError, sqlite3.Error):
                return
            identity = (graph.api_key_id, graph.request_id)
        for listener in tuple(self._event_listeners):
            try:
                listener(event_type, graph_id, *identity, payload, created_at)
            except Exception:
                continue

    def save_graph(self, graph: ExecutionGraph) -> None:
        payload = _canonical(graph.model_dump(mode="json"))
        with self._connect() as database:
            existing = database.execute(
                "SELECT payload FROM execution_graphs WHERE graph_id = ?", (graph.graph_id,)
            ).fetchone()
            if existing:
                persisted = ExecutionGraph.model_validate(_strict_loads(existing[0]))
                if persisted.graph_hash != graph.graph_hash:
                    raise ValueError("immutable execution graph changed")
            database.execute(
                "INSERT OR IGNORE INTO execution_graphs(graph_id, payload, created_at) "
                "VALUES (?, ?, ?)",
                (graph.graph_id, payload, graph.created_at),
            )
        self._identities[graph.graph_id] = (graph.api_key_id, graph.request_id)
        self._publish(
            "graph_saved",
            graph.graph_id,
            graph.model_dump(mode="json"),
            graph.created_at,
        )

    def save_attempt(self, graph_id: str, attempt: NodeAttempt) -> None:
        updated_at = _utc_now()
        with self._connect() as database:
            database.execute(
                "INSERT INTO execution_graph_attempts(graph_id, attempt_id, payload, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(graph_id, attempt_id) DO UPDATE SET "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (
                    graph_id,
                    attempt.attempt_id,
                    _canonical(attempt.model_dump(mode="json")),
                    updated_at,
                ),
            )
        self._publish(
            "node_attempt",
            graph_id,
            attempt.model_dump(mode="json"),
            updated_at,
        )

    def save_checkpoint(self, checkpoint: GraphCheckpoint) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO execution_graph_checkpoints"
                "(graph_id, checkpoint_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    checkpoint.graph_id,
                    checkpoint.checkpoint_id,
                    _canonical(checkpoint.model_dump(mode="json")),
                    checkpoint.created_at,
                ),
            )
        self._publish(
            "graph_checkpoint",
            checkpoint.graph_id,
            checkpoint.model_dump(mode="json"),
            checkpoint.created_at,
        )

    def save_active_state(self, payload: dict[str, Any]) -> str:
        serialized = _canonical(redact(payload))
        object_ref = f"sha256:{hashlib.sha256(serialized.encode()).hexdigest()}"
        with self._connect() as database:
            existing = database.execute(
                "SELECT payload FROM execution_graph_active_states WHERE object_ref = ?",
                (object_ref,),
            ).fetchone()
            if existing is not None and existing[0] != serialized:
                raise ValueError("immutable active state changed")
            database.execute(
                "INSERT OR IGNORE INTO execution_graph_active_states"
                "(object_ref, payload, created_at) VALUES (?, ?, ?)",
                (object_ref, serialized, _utc_now()),
            )
        return object_ref

    def load_active_state(self, object_ref: str) -> dict[str, Any]:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM execution_graph_active_states WHERE object_ref = ?",
                (object_ref,),
            ).fetchone()
        if row is None:
            raise KeyError(object_ref)
        payload = _strict_loads(row[0])
        if not isinstance(payload, dict):
            raise ValueError("active state must be an object")
        return cast(dict[str, Any], payload)

    def load_graph(self, graph_id: str) -> ExecutionGraph:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM execution_graphs WHERE graph_id = ?", (graph_id,)
            ).fetchone()
        if not row:
            raise KeyError(graph_id)
        graph = validate_execution_graph(ExecutionGraph.model_validate(_strict_loads(row[0])))
        self._identities[graph_id] = (graph.api_key_id, graph.request_id)
        return graph

    def snapshot(self, graph_id: str) -> dict[str, Any]:
        graph = self.load_graph(graph_id)
        attempts = self.load_attempts(graph_id)
        try:
            checkpoint = self.load_latest_checkpoint(graph_id)
        except KeyError:
            checkpoint = None
        active_state = (
            self.load_active_state(checkpoint.active_state_object_ref)
            if checkpoint is not None and checkpoint.active_state_object_ref
            else None
        )
        return cast(
            dict[str, Any],
            redact(
                {
                    "graph": graph.model_dump(mode="json"),
                    "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
                    "checkpoint": (
                        checkpoint.model_dump(mode="json") if checkpoint is not None else None
                    ),
                    "active_state": active_state,
                }
            ),
        )

    def aggregate_snapshot(self) -> dict[str, Any]:
        with self._connect() as database:
            graph_count = int(
                database.execute("SELECT COUNT(*) FROM execution_graphs").fetchone()[0]
            )
            templates = database.execute(
                "SELECT json_extract(payload, '$.template_id'), COUNT(*) "
                "FROM execution_graphs GROUP BY 1 ORDER BY 1"
            ).fetchall()
            checkpoints = database.execute(
                "WITH latest AS (SELECT graph_id, MAX(checkpoint_id) AS checkpoint_id "
                "FROM execution_graph_checkpoints GROUP BY graph_id) "
                "SELECT json_extract(c.payload, '$.terminal_status'), COUNT(*), "
                "COALESCE(SUM(json_array_length(c.payload, '$.active_node_ids')), 0), "
                "COALESCE(SUM(json_array_length(c.payload, '$.pending_node_ids')), 0) "
                "FROM execution_graph_checkpoints c JOIN latest l "
                "ON c.graph_id = l.graph_id AND c.checkpoint_id = l.checkpoint_id GROUP BY 1"
            ).fetchall()
        return {
            "graph_count": graph_count,
            "templates": {str(row[0]): int(row[1]) for row in templates},
            "terminal_statuses": {
                str(row[0] if row[0] is not None else "running"): int(row[1]) for row in checkpoints
            },
            "active_nodes": sum(int(row[2]) for row in checkpoints),
            "pending_nodes": sum(int(row[3]) for row in checkpoints),
        }

    def load_attempts(self, graph_id: str) -> list[NodeAttempt]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload FROM execution_graph_attempts WHERE graph_id = ? ORDER BY rowid",
                (graph_id,),
            ).fetchall()
        return [NodeAttempt.model_validate(_strict_loads(row[0])) for row in rows]

    def load_latest_checkpoint(self, graph_id: str) -> GraphCheckpoint:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM execution_graph_checkpoints WHERE graph_id = ? "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (graph_id,),
            ).fetchone()
        if not row:
            raise KeyError(graph_id)
        return GraphCheckpoint.model_validate(_strict_loads(row[0]))

    def load_checkpoint(self, graph_id: str, checkpoint_id: str) -> GraphCheckpoint:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM execution_graph_checkpoints "
                "WHERE graph_id = ? AND checkpoint_id = ?",
                (graph_id, checkpoint_id),
            ).fetchone()
        if not row:
            raise KeyError((graph_id, checkpoint_id))
        return GraphCheckpoint.model_validate(_strict_loads(row[0]))

    def load_checkpoints(self, graph_id: str) -> list[GraphCheckpoint]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload FROM execution_graph_checkpoints WHERE graph_id = ? "
                "ORDER BY checkpoint_id",
                (graph_id,),
            ).fetchall()
        return [GraphCheckpoint.model_validate(_strict_loads(row[0])) for row in rows]

    def load_runtime(self, graph_id: str) -> ExecutionGraphRuntime:
        graph = self.load_graph(graph_id)
        return ExecutionGraphRuntime.resume(
            graph,
            self.load_latest_checkpoint(graph_id),
            attempts=self.load_attempts(graph_id),
            store=self,
        )


def project_execution_graph(
    settings: Settings,
    state_store: StateStore,
    graph_store: ExecutionGraphStore | None,
    state: SessionState,
    metadata: dict[str, Any],
    *,
    risk: Literal["low", "medium", "high", "critical"],
    executor_provider: Literal[
        "local_mistral", "opencode_go", "legacy_local_qwen", "codex_frontier"
    ],
    scheduling: SchedulingSnapshot | None = None,
    tools_requested: bool,
    validation_required: bool,
    deadline_seconds: float,
) -> ExecutionGraphRuntime | None:
    """Persist a non-authoritative graph projection beside the legacy path."""
    if graph_store is None:
        return None
    complexity: Literal["simple", "engineering", "complex", "critical"] = (
        "critical"
        if state.route == "escalation" or risk == "high"
        else "simple"
        if state.route == "fast"
        else "complex"
        if state.request_class in {"multi_file_task", "recovery_task", "explicit_orchestrated"}
        else "engineering"
    )
    decision = state.policy_decisions[-1] if state.policy_decisions else {}
    policy_set = settings.declarative_policy.policy_set()
    loop_budget = state.engineering_loop.remaining_budget if state.engineering_loop else None
    if (
        isinstance(deadline_seconds, bool)
        or not isinstance(deadline_seconds, int | float)
        or not math.isfinite(deadline_seconds)
        or deadline_seconds <= 0
    ):
        state_store.event(
            state.session_id,
            "execution_graph_shadow_failed",
            {"failure_code": "GRAPH_INVALID_DEADLINE"},
        )
        return None
    wall_seconds = max(
        1,
        int(
            min(
                deadline_seconds,
                loop_budget.wall_clock_seconds if loop_budget else deadline_seconds,
            )
        ),
    )
    effective_scheduling = scheduling or SchedulingSnapshot(
        selected_executor=executor_provider,
        readiness={executor_provider: True},
    )
    try:
        graph = compile_execution_graph(
            GraphCompileInput(
                request_id=state.current_request_id or state.session_id,
                api_key_id=state.api_token_id,
                objective=state.resolved_objective or state.objective,
                request_class=state.request_class,
                complexity=complexity,
                risk=risk,
                policy_version=str(decision.get("policy_version", policy_set.version)),
                policy_hash=str(decision.get("policy_hash", policy_set.content_hash())),
                deadline=(datetime.now(UTC) + timedelta(seconds=wall_seconds)).isoformat(),
                scheduling=effective_scheduling,
                budgets=GraphBudget(
                    tokens=loop_budget.tokens if loop_budget else 5_000_000,
                    tool_calls=loop_budget.tool_calls if loop_budget else 500,
                    wall_clock_seconds=wall_seconds,
                ),
                allowed_mutation_paths=tuple(
                    path
                    for path in state.approved_scope
                    if path and not Path(path).is_absolute() and ".." not in Path(path).parts
                ),
                tools_requested=tools_requested,
                validation_required=validation_required,
                reasoner_enabled="reasoner" in state.roles_required,
                planner_enabled="planner" in state.roles_required,
                frontier_enabled=(settings.frontier_enabled and "frontier" in state.roles_required),
                reviewer_enabled=(
                    "reviewer" in state.roles_required or risk in {"high", "critical"}
                ),
                judge_enabled="judge" in state.roles_required or risk in {"high", "critical"},
                human_approval_required=bool(decision.get("approvals_required")),
            )
        )
        graph_store.save_graph(graph)
        active_state = compact_session_active_state(
            state,
            effective_scheduling,
            settings.limits,
        )
        active_state_ref = graph_store.save_active_state(active_state)
        runtime = ExecutionGraphRuntime(graph, graph_store)
        checkpoint = runtime.checkpoint(
            reason="shadow_projection",
            active_state_object_ref=active_state_ref,
            event_cursor=state_store.event_cursor(state.session_id),
            size_before=len(state.model_dump_json().encode()),
            size_after=len(_canonical(active_state).encode()),
        )
    except (ValueError, sqlite3.Error) as error:
        record_shadow_failure(state_store, state.session_id, "compile", error)
        return None
    state.execution_graph_mode = "shadow"
    state.execution_graph_id = graph.graph_id
    state.execution_graph_hash = graph.graph_hash
    state.execution_graph_template = graph.template_id
    state.execution_checkpoint_id = checkpoint.checkpoint_id
    state.active_state_object_ref = active_state_ref
    state_store.event(
        state.session_id,
        "execution_graph_shadow_compiled",
        {
            "graph_id": graph.graph_id,
            "graph_hash": graph.graph_hash,
            "template_id": graph.template_id,
            "executor_provider": executor_provider,
            "request_id": state.current_request_id,
            "checkpoint_id": checkpoint.checkpoint_id,
            "active_state_object_ref": active_state_ref,
            "event_cursor": checkpoint.event_cursor,
            "size_before": checkpoint.size_before,
            "size_after": checkpoint.size_after,
        },
    )
    state_store.save(state)
    return runtime


def _strict_loads(payload: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(payload, parse_constant=reject_constant)


def _bounded_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) > 256 or any(not value or len(value) > 256 for value in values):
        raise ValueError("Evidence node ID list is invalid")
    return tuple(dict.fromkeys(values))


def compact_session_active_state(
    state: SessionState,
    scheduling: SchedulingSnapshot,
    limits: Limits,
) -> dict[str, Any]:
    """Keep only model-relevant resumable state; durable history stays in StateStore."""
    loop = state.engineering_loop
    recent_limit = max(1, limits.max_retained_observations)
    maximum_bytes = limits.max_tool_output_characters * recent_limit
    field_bytes = max(256, (maximum_bytes - 4_096) // 12)

    def bounded(value: Any) -> Any:
        cleaned = redact(value)
        serialized = _canonical(cleaned)
        if len(serialized.encode()) <= field_bytes:
            return cleaned
        summary_characters = max(16, (field_bytes - 256) // 4)
        summary_limits = limits.model_copy(
            update={"max_tool_output_characters": summary_characters}
        )
        return {
            "content_hash": _sha256(cleaned),
            "compacted_json": compress_text(serialized, summary_limits),
            "truncated": True,
        }

    active_state = cast(
        dict[str, Any],
        redact(
            {
                "schema_version": "session-active-state-v1",
                "session_id": state.session_id,
                "objective": bounded(state.resolved_objective or state.objective),
                "constraints": bounded(state.acceptance_criteria),
                "policy_decisions": bounded(state.policy_decisions[-recent_limit:]),
                "current_plan": bounded(state.plan[-recent_limit:]),
                "current_working_set": bounded(
                    {
                        "approved_scope": state.approved_scope,
                        "repository": state.repository,
                    }
                ),
                "unresolved_acceptance_criteria": bounded(
                    [
                        criterion.model_dump(mode="json")
                        for criterion in loop.acceptance_criteria
                        if criterion.state not in {"passed", "waived"}
                    ]
                    if loop is not None
                    else state.acceptance_criteria
                ),
                "recent_relevant_evidence": bounded(state.evidence_nodes[-recent_limit:]),
                "open_failures": bounded(
                    [failure.model_dump(mode="json") for failure in loop.open_failures]
                    if loop is not None
                    else state.failures[-recent_limit:]
                ),
                "review_findings": bounded(state.agent_artifacts[-recent_limit:]),
                "remaining_budget": bounded(
                    loop.remaining_budget.model_dump(mode="json") if loop is not None else {}
                ),
                "scheduling": bounded(scheduling.model_dump(mode="json")),
                "phase": state.phase,
                "pending_tool_call_ids": bounded(state.pending_tool_call_ids),
            }
        ),
    )
    if len(_canonical(active_state).encode()) > maximum_bytes:
        raise ValueError("compact active state exceeds its byte budget")
    return active_state
