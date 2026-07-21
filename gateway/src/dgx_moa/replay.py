from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evidence import validate_evidence_graph

ReplayMode = Literal[
    "audit",
    "regression",
    "skill_evaluation",
    "routing_policy_comparison",
    "training_candidate_validation",
]


class ReplaySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["execution-replay-v1"] = "execution-replay-v1"
    replay_id: str = Field(default_factory=lambda: f"replay_{uuid.uuid4().hex}")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    task_state: dict[str, Any]
    evidence_snapshot: dict[str, list[dict[str, Any]]]
    skill_versions: list[str]
    policy_version: str
    policy_hash: str | None = None
    model_role_configuration: dict[str, dict[str, Any]]
    invoked_roles: list[str]
    mocked_provider_outputs: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    original_outcome: dict[str, Any]
    nondeterminism_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph_snapshot(self) -> ReplaySnapshot:
        validate_evidence_graph(
            self.evidence_snapshot.get("nodes", []), self.evidence_snapshot.get("edges", [])
        )
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"replay_id", "created_at"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class ReplayResult(BaseModel):
    replay_id: str
    mode: ReplayMode
    exact: bool
    deterministic_claim: bool
    snapshot_hash: str
    outputs: dict[str, list[dict[str, Any]]]
    evaluation: dict[str, Any]
    nondeterminism_sources: list[str]


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: ReplaySnapshot
    mode: ReplayMode
    exact: bool


def snapshot_from_trace(
    trace: dict[str, Any],
    *,
    mocked_provider_outputs: dict[str, list[dict[str, Any]]] | None = None,
) -> ReplaySnapshot:
    metrics = trace.get("metrics", {})
    invocations = trace.get("agent_invocations", [])
    roles = list(dict.fromkeys(str(item.get("role", "unknown")) for item in invocations))
    nondeterminism = []
    if any(role == "frontier" for role in roles):
        nondeterminism.append("remote_frontier_provider")
    if trace.get("tool_executions"):
        nondeterminism.append("external_tool_or_filesystem_state")
    if any(
        configuration.get("temperature") not in {None, 0}
        for configuration in trace.get("model_revisions", {}).values()
    ):
        nondeterminism.append("stochastic_model_sampling")
    return ReplaySnapshot(
        task_state={
            "session_id": trace.get("session_id"),
            "task_id": trace.get("task_id"),
            "objective": trace.get("objective"),
            "selected_route": trace.get("selected_route"),
            "verified_state": trace.get("verified_state", []),
            "acceptance_evidence": trace.get("completion_evidence", {}),
            "runtime_mode": metrics.get("runtime_mode"),
            "request_class": metrics.get("request_class"),
        },
        evidence_snapshot=trace.get("evidence_graph", {"nodes": [], "edges": []}),
        skill_versions=list(metrics.get("skill_versions", [])),
        policy_version=str(metrics.get("policy_version", "none")),
        policy_hash=metrics.get("policy_hash"),
        model_role_configuration=trace.get("model_revisions", {}),
        invoked_roles=roles,
        mocked_provider_outputs=mocked_provider_outputs or {},
        original_outcome={
            "final_status": trace.get("final_status"),
            "review_outcome": trace.get("review_outcome"),
            "derived_confidence": trace.get("derived_confidence"),
        },
        nondeterminism_sources=nondeterminism,
    )


def save_snapshot(path: str | Path, snapshot: ReplaySnapshot) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content_hash = snapshot.content_hash()
    payload = {
        "snapshot": snapshot.model_dump(mode="json"),
        "content_sha256": content_hash,
    }
    descriptor, temporary = tempfile.mkstemp(
        dir=destination.parent, prefix=".replay-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return content_hash


def load_snapshot(path: str | Path) -> ReplaySnapshot:
    payload = json.loads(Path(path).read_text())
    snapshot = ReplaySnapshot.model_validate(payload["snapshot"])
    if snapshot.content_hash() != payload.get("content_sha256"):
        raise ValueError("execution replay snapshot hash mismatch")
    return snapshot


class ReplayEngine:
    async def run(
        self,
        snapshot: ReplaySnapshot,
        *,
        mode: ReplayMode,
        exact: bool,
        live_provider: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        evaluator: Callable[[ReplaySnapshot, dict[str, list[dict[str, Any]]]], dict[str, Any]]
        | None = None,
    ) -> ReplayResult:
        if exact and live_provider is not None:
            raise ValueError("exact replay cannot call live providers")
        outputs: dict[str, list[dict[str, Any]]] = {}
        nondeterminism = list(snapshot.nondeterminism_sources)
        if exact:
            missing = [
                role
                for role in snapshot.invoked_roles
                if role not in snapshot.mocked_provider_outputs
            ]
            if missing:
                raise ValueError(f"exact replay missing mocked provider output: {missing[0]}")
            outputs = snapshot.mocked_provider_outputs
        elif live_provider is not None:
            nondeterminism.append("live_provider_outputs")
            for role in snapshot.invoked_roles:
                outputs.setdefault(role, []).append(
                    await live_provider(
                        role,
                        {
                            "task_state": snapshot.task_state,
                            "evidence_snapshot": snapshot.evidence_snapshot,
                            "skill_versions": snapshot.skill_versions,
                            "policy_version": snapshot.policy_version,
                            "model_configuration": snapshot.model_role_configuration.get(role, {}),
                        },
                    )
                )
        elif mode != "audit":
            raise ValueError("comparative replay requires a live provider or exact mocks")
        evaluation = (
            evaluator(snapshot, outputs)
            if evaluator is not None
            else {"original_outcome": snapshot.original_outcome}
        )
        deterministic = exact and not nondeterminism
        return ReplayResult(
            replay_id=snapshot.replay_id,
            mode=mode,
            exact=exact,
            deterministic_claim=deterministic,
            snapshot_hash=snapshot.content_hash(),
            outputs=outputs,
            evaluation=evaluation,
            nondeterminism_sources=list(dict.fromkeys(nondeterminism)),
        )
