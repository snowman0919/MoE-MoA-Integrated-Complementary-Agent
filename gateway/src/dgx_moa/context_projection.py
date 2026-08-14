"""Immutable canonical evidence snapshots and bounded role context projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .compression import message_fingerprint
from .security import redact

SNAPSHOT_SCHEMA_VERSION: Literal["runtime-evidence-snapshot-v1"] = "runtime-evidence-snapshot-v1"
PROJECTION_SCHEMA_VERSION: Literal["role-context-projection-v1"] = "role-context-projection-v1"
MAX_CONTEXT_BYTES = 1_000_000
ROLE_CONTEXT_TARGET_BYTES: dict[ProjectionRole, int] = {
    "reasoner": 96 * 1024,
    "planner": 80 * 1024,
    "frontier_a": 192 * 1024,
    "executor": 524 * 1024,
    "reviewer": 128 * 1024,
    "judge": 80 * 1024,
    "frontier_b": 128 * 1024,
}

RuntimeEvidenceKind = Literal[
    "tool",
    "diff",
    "test",
    "build",
    "failure",
    "policy",
    "checkpoint",
]
ContributionRole = Literal[
    "reasoner",
    "planner",
    "frontier_a",
    "executor",
    "reviewer",
    "judge",
    "frontier_b",
]
ProjectionRole = ContributionRole
ProjectionStage = Literal["fanout", "fan_in", "review", "adjudication"]


def _canonical(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        redact(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda item: (
            item.model_dump(mode="json") if isinstance(item, BaseModel) else _unsupported_json(item)
        ),
    )


def _unsupported_json(value: Any) -> Any:
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _content_hash(model: BaseModel, id_field: str, hash_field: str) -> str:
    payload = model.model_dump(mode="json")
    payload.pop(id_field, None)
    payload.pop(hash_field, None)
    return _hash(payload)


def _bounded_unique(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if any(not value for value in normalized):
        raise ValueError("provenance IDs cannot be empty")
    if len(normalized) > 512:
        raise ValueError("provenance ID collection is too large")
    return normalized


def _validate_canonical_json(value: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError("context payload must be valid JSON") from error
    if _canonical(parsed) != value:
        raise ValueError("context payload must be canonical redacted JSON")
    return value


def _validate_context_size(value: BaseModel) -> None:
    if len(_canonical(value).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError(f"runtime context exceeds {MAX_CONTEXT_BYTES} bytes")


class CanonicalRequestInput(BaseModel):
    """One immutable original client input, preserving its original sequence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_id: str = Field(min_length=1, max_length=128)
    payload_json: str = Field(min_length=1, max_length=400_000)

    @field_validator("payload_json")
    @classmethod
    def canonical_payload(cls, value: str) -> str:
        return _validate_canonical_json(value)

    def payload(self) -> Any:
        return json.loads(self.payload_json)


class RuntimeEvidenceItem(BaseModel):
    """A runtime-observed fact; model opinions are deliberately not representable here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=256)
    kind: RuntimeEvidenceKind
    payload_json: str = Field(min_length=1, max_length=400_000)
    source_attempt_id: str | None = Field(default=None, min_length=1, max_length=256)
    parent_evidence_ids: tuple[str, ...] = ()

    @field_validator("payload_json")
    @classmethod
    def canonical_payload(cls, value: str) -> str:
        return _validate_canonical_json(value)

    def payload(self) -> Any:
        return json.loads(self.payload_json)


class ModelContribution(BaseModel):
    """A model position kept separate from original input and observed evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contribution_id: str = Field(min_length=1, max_length=256)
    role: ContributionRole
    payload_json: str = Field(min_length=1, max_length=400_000)
    source_attempt_id: str = Field(min_length=1, max_length=256)
    evidence_ids: tuple[str, ...] = ()

    @field_validator("payload_json")
    @classmethod
    def canonical_payload(cls, value: str) -> str:
        return _validate_canonical_json(value)

    def payload(self) -> Any:
        return json.loads(self.payload_json)


class RuntimeEvidenceSnapshot(BaseModel):
    """Versioned source of truth from which every role context is independently projected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["runtime-evidence-snapshot-v1"] = SNAPSHOT_SCHEMA_VERSION
    snapshot_id: str = Field(pattern=r"^snapshot_[0-9a-f]{24}$")
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(min_length=1, max_length=256)
    graph_id: str | None = Field(default=None, min_length=1, max_length=256)
    objective: str = Field(max_length=200_000)
    request_inputs: tuple[CanonicalRequestInput, ...] = ()
    request_constraints_json: tuple[str, ...] = ()
    acceptance_criteria_json: tuple[str, ...] = ()
    runtime_evidence: tuple[RuntimeEvidenceItem, ...] = ()
    model_contributions: tuple[ModelContribution, ...] = ()

    @field_validator("request_constraints_json", "acceptance_criteria_json")
    @classmethod
    def canonical_payloads(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_canonical_json(value) for value in values)

    @model_validator(mode="after")
    def valid_identity_and_provenance(self) -> RuntimeEvidenceSnapshot:
        expected_hash = _content_hash(self, "snapshot_id", "snapshot_hash")
        if self.snapshot_hash != expected_hash:
            raise ValueError("runtime evidence snapshot hash mismatch")
        if self.snapshot_id != f"snapshot_{expected_hash[:24]}":
            raise ValueError("runtime evidence snapshot ID mismatch")
        input_ids = [item.input_id for item in self.request_inputs]
        evidence_ids = [item.evidence_id for item in self.runtime_evidence]
        contribution_ids = [item.contribution_id for item in self.model_contributions]
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("duplicate original input ID")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate runtime Evidence ID")
        if len(contribution_ids) != len(set(contribution_ids)):
            raise ValueError("duplicate model contribution ID")
        known_evidence = set(evidence_ids)
        for item in self.runtime_evidence:
            if item.evidence_id in item.parent_evidence_ids:
                raise ValueError("runtime Evidence cannot be its own parent")
            if not set(item.parent_evidence_ids).issubset(known_evidence):
                raise ValueError("runtime Evidence references an unknown parent")
        parents = {
            item.evidence_id: set(item.parent_evidence_ids) for item in self.runtime_evidence
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(evidence_id: str) -> None:
            if evidence_id in visiting:
                raise ValueError("runtime Evidence provenance contains a cycle")
            if evidence_id in visited:
                return
            visiting.add(evidence_id)
            for parent_id in parents[evidence_id]:
                visit(parent_id)
            visiting.remove(evidence_id)
            visited.add(evidence_id)

        for evidence_id in parents:
            visit(evidence_id)
        for contribution in self.model_contributions:
            if not set(contribution.evidence_ids).issubset(known_evidence):
                raise ValueError("model contribution references unknown runtime Evidence")
        _validate_context_size(self)
        return self


class ProjectionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(pattern=r"^snapshot_[0-9a-f]{24}$")
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_id: str | None = Field(default=None, min_length=1, max_length=256)
    target_node_id: str | None = Field(default=None, min_length=1, max_length=256)
    target_attempt_id: str | None = Field(default=None, min_length=1, max_length=256)
    causal_parent_attempt_ids: tuple[str, ...] = ()
    join_node_id: str | None = Field(default=None, min_length=1, max_length=256)
    source_attempt_ids: tuple[str, ...] = ()
    included_evidence_ids: tuple[str, ...] = ()
    included_contribution_ids: tuple[str, ...] = ()
    excluded_evidence_ids: tuple[str, ...] = ()
    excluded_contribution_ids: tuple[str, ...] = ()
    included_categories: tuple[str, ...] = ()
    excluded_contribution_roles: tuple[ContributionRole, ...] = ()
    target_bytes: int = Field(gt=0, le=MAX_CONTEXT_BYTES)


class RoleContextProjection(BaseModel):
    """A role-specific view that retains a verifiable link to one canonical snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["role-context-projection-v1"] = PROJECTION_SCHEMA_VERSION
    projection_id: str = Field(pattern=r"^projection_[0-9a-f]{24}$")
    projection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: ProjectionRole
    stage: ProjectionStage
    request_id: str = Field(min_length=1, max_length=256)
    objective: str = Field(max_length=200_000)
    request_inputs: tuple[CanonicalRequestInput, ...] = ()
    request_constraints_json: tuple[str, ...] = ()
    acceptance_criteria_json: tuple[str, ...] = ()
    runtime_evidence: tuple[RuntimeEvidenceItem, ...] = ()
    model_contributions: tuple[ModelContribution, ...] = ()
    provenance: ProjectionProvenance

    @model_validator(mode="after")
    def valid_identity_and_policy(self) -> RoleContextProjection:
        expected_hash = _content_hash(self, "projection_id", "projection_hash")
        if self.projection_hash != expected_hash:
            raise ValueError("role context projection hash mismatch")
        if self.projection_id != f"projection_{expected_hash[:24]}":
            raise ValueError("role context projection ID mismatch")
        policy = ROLE_PROJECTION_POLICIES[(self.role, self.stage)]
        if self.provenance.policy_id != policy.policy_id:
            raise ValueError("role projection policy mismatch")
        if any(
            item.role not in policy.allowed_contribution_roles for item in self.model_contributions
        ):
            raise ValueError("role projection contains a disallowed model contribution")
        if any(item.kind not in policy.allowed_runtime_kinds for item in self.runtime_evidence):
            raise ValueError("role projection contains a disallowed runtime Evidence kind")
        if self.provenance.included_evidence_ids != tuple(
            item.evidence_id for item in self.runtime_evidence
        ):
            raise ValueError("role projection Evidence provenance mismatch")
        if self.provenance.included_contribution_ids != tuple(
            item.contribution_id for item in self.model_contributions
        ):
            raise ValueError("role projection contribution provenance mismatch")
        expected_categories = _projection_categories(
            self.request_inputs,
            self.request_constraints_json,
            self.acceptance_criteria_json,
            self.runtime_evidence,
            self.model_contributions,
        )
        if self.provenance.included_categories != expected_categories:
            raise ValueError("role projection category provenance mismatch")
        _validate_context_size(self)
        return self


class RoleProjectionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    role: ProjectionRole
    stage: ProjectionStage
    allowed_runtime_kinds: tuple[RuntimeEvidenceKind, ...]
    allowed_contribution_roles: tuple[ContributionRole, ...]


_ALL_RUNTIME_KINDS: tuple[RuntimeEvidenceKind, ...] = (
    "tool",
    "diff",
    "test",
    "build",
    "failure",
    "policy",
    "checkpoint",
)

ROLE_PROJECTION_POLICIES: dict[tuple[ProjectionRole, ProjectionStage], RoleProjectionPolicy] = {
    ("reasoner", "fanout"): RoleProjectionPolicy(
        policy_id="reasoner-fanout-v1",
        role="reasoner",
        stage="fanout",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=(),
    ),
    ("planner", "fanout"): RoleProjectionPolicy(
        policy_id="planner-fanout-v1",
        role="planner",
        stage="fanout",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=(),
    ),
    ("frontier_a", "fanout"): RoleProjectionPolicy(
        policy_id="frontier-a-fanout-v1",
        role="frontier_a",
        stage="fanout",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=(),
    ),
    ("executor", "fanout"): RoleProjectionPolicy(
        policy_id="executor-evidence-fanout-v1",
        role="executor",
        stage="fanout",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=(),
    ),
    ("executor", "fan_in"): RoleProjectionPolicy(
        policy_id="executor-fan-in-v1",
        role="executor",
        stage="fan_in",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=(
            "reasoner",
            "planner",
            "frontier_a",
            "reviewer",
            "judge",
            "frontier_b",
        ),
    ),
    ("reviewer", "review"): RoleProjectionPolicy(
        policy_id="reviewer-evidence-v1",
        role="reviewer",
        stage="review",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=("executor",),
    ),
    ("judge", "review"): RoleProjectionPolicy(
        policy_id="judge-evidence-v1",
        role="judge",
        stage="review",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=("frontier_a", "executor", "reviewer"),
    ),
    ("frontier_b", "adjudication"): RoleProjectionPolicy(
        policy_id="frontier-b-evidence-v1",
        role="frontier_b",
        stage="adjudication",
        allowed_runtime_kinds=_ALL_RUNTIME_KINDS,
        allowed_contribution_roles=("frontier_a", "executor", "reviewer", "judge"),
    ),
}

_ALL_CONTRIBUTION_ROLES: tuple[ContributionRole, ...] = (
    "reasoner",
    "planner",
    "frontier_a",
    "executor",
    "reviewer",
    "judge",
    "frontier_b",
)


def _projection_categories(
    request_inputs: Sequence[CanonicalRequestInput],
    request_constraints_json: Sequence[str],
    acceptance_criteria_json: Sequence[str],
    runtime_evidence: Sequence[RuntimeEvidenceItem],
    model_contributions: Sequence[ModelContribution],
) -> tuple[str, ...]:
    categories: list[str] = ["objective"]
    if request_inputs:
        categories.append("original_inputs")
    if request_constraints_json:
        categories.append("request_constraints")
    if acceptance_criteria_json:
        categories.append("acceptance_criteria")
    categories.extend(
        f"runtime_evidence:{kind}" for kind in sorted({i.kind for i in runtime_evidence})
    )
    categories.extend(
        f"model_contribution:{role}" for role in sorted({item.role for item in model_contributions})
    )
    return tuple(categories)


def canonical_request_input(input_id: str, payload: Any) -> CanonicalRequestInput:
    return CanonicalRequestInput(input_id=input_id, payload_json=_canonical(payload))


def runtime_evidence_item(
    evidence_id: str,
    kind: RuntimeEvidenceKind,
    payload: Any,
    *,
    source_attempt_id: str | None = None,
    parent_evidence_ids: Iterable[str] = (),
) -> RuntimeEvidenceItem:
    return RuntimeEvidenceItem(
        evidence_id=evidence_id,
        kind=kind,
        payload_json=_canonical(payload),
        source_attempt_id=source_attempt_id,
        parent_evidence_ids=_bounded_unique(parent_evidence_ids),
    )


def model_contribution(
    contribution_id: str,
    role: ContributionRole,
    payload: Any,
    *,
    source_attempt_id: str,
    evidence_ids: Iterable[str] = (),
) -> ModelContribution:
    return ModelContribution(
        contribution_id=contribution_id,
        role=role,
        payload_json=_canonical(payload),
        source_attempt_id=source_attempt_id,
        evidence_ids=_bounded_unique(evidence_ids),
    )


def build_runtime_evidence_snapshot(
    *,
    request_id: str,
    objective: str,
    request_inputs: Sequence[CanonicalRequestInput] = (),
    request_constraints: Iterable[Any] = (),
    acceptance_criteria: Iterable[Any] = (),
    runtime_evidence: Iterable[RuntimeEvidenceItem] = (),
    model_contributions: Iterable[ModelContribution] = (),
    graph_id: str | None = None,
) -> RuntimeEvidenceSnapshot:
    raw: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "request_id": request_id,
        "graph_id": graph_id,
        "objective": str(redact(objective)),
        "request_inputs": [item.model_dump(mode="json") for item in request_inputs],
        "request_constraints_json": [_canonical(item) for item in request_constraints],
        "acceptance_criteria_json": [_canonical(item) for item in acceptance_criteria],
        "runtime_evidence": [
            item.model_dump(mode="json")
            for item in sorted(runtime_evidence, key=lambda item: item.evidence_id)
        ],
        "model_contributions": [
            item.model_dump(mode="json")
            for item in sorted(model_contributions, key=lambda item: item.contribution_id)
        ],
    }
    raw["snapshot_hash"] = _hash(raw)
    raw["snapshot_id"] = f"snapshot_{raw['snapshot_hash'][:24]}"
    return RuntimeEvidenceSnapshot.model_validate(raw)


def project_role_context(
    snapshot: RuntimeEvidenceSnapshot,
    role: ProjectionRole,
    *,
    stage: ProjectionStage,
    target_node_id: str | None = None,
    target_attempt_id: str | None = None,
    causal_parent_attempt_ids: Iterable[str] = (),
    join_node_id: str | None = None,
) -> RoleContextProjection:
    try:
        policy = ROLE_PROJECTION_POLICIES[(role, stage)]
    except KeyError as error:
        raise ValueError(f"unsupported role projection stage: {role}:{stage}") from error
    evidence = tuple(
        item for item in snapshot.runtime_evidence if item.kind in policy.allowed_runtime_kinds
    )
    causal_parents = _bounded_unique(causal_parent_attempt_ids)
    contributions = tuple(
        item
        for item in snapshot.model_contributions
        if item.role in policy.allowed_contribution_roles
        and (not causal_parents or item.source_attempt_id in causal_parents)
    )
    request_inputs_reversed: list[CanonicalRequestInput] = []
    seen_inputs: set[str] = set()
    for item in reversed(snapshot.request_inputs):
        payload = item.payload()
        fingerprint = (
            message_fingerprint(payload)
            if isinstance(payload, dict) and payload.get("role") in {"developer", "system", "user"}
            else item.payload_json
        )
        if fingerprint in seen_inputs:
            continue
        seen_inputs.add(fingerprint)
        request_inputs_reversed.append(item)
    request_inputs = tuple(reversed(request_inputs_reversed))
    target_bytes = ROLE_CONTEXT_TARGET_BYTES[role]

    def build() -> RoleContextProjection:
        source_attempt_values = [
            item.source_attempt_id for item in evidence if item.source_attempt_id is not None
        ]
        source_attempt_values.extend(item.source_attempt_id for item in contributions)
        included_roles = {item.role for item in contributions}
        provenance = ProjectionProvenance(
            policy_id=policy.policy_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            graph_id=snapshot.graph_id,
            target_node_id=target_node_id,
            target_attempt_id=target_attempt_id,
            causal_parent_attempt_ids=causal_parents,
            join_node_id=join_node_id,
            source_attempt_ids=_bounded_unique(source_attempt_values),
            included_evidence_ids=tuple(item.evidence_id for item in evidence),
            included_contribution_ids=tuple(item.contribution_id for item in contributions),
            excluded_evidence_ids=tuple(
                item.evidence_id for item in snapshot.runtime_evidence if item not in evidence
            ),
            excluded_contribution_ids=tuple(
                item.contribution_id
                for item in snapshot.model_contributions
                if item.role in policy.allowed_contribution_roles and item not in contributions
            ),
            included_categories=_projection_categories(
                request_inputs,
                snapshot.request_constraints_json,
                snapshot.acceptance_criteria_json,
                evidence,
                contributions,
            ),
            excluded_contribution_roles=tuple(
                role_name
                for role_name in _ALL_CONTRIBUTION_ROLES
                if role_name not in included_roles
            ),
            target_bytes=target_bytes,
        )
        raw: dict[str, Any] = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "role": role,
            "stage": stage,
            "request_id": snapshot.request_id,
            "objective": snapshot.objective,
            "request_inputs": [item.model_dump(mode="json") for item in request_inputs],
            "request_constraints_json": list(snapshot.request_constraints_json),
            "acceptance_criteria_json": list(snapshot.acceptance_criteria_json),
            "runtime_evidence": [item.model_dump(mode="json") for item in evidence],
            "model_contributions": [item.model_dump(mode="json") for item in contributions],
            "provenance": provenance.model_dump(mode="json"),
        }
        raw["projection_hash"] = _hash(raw)
        raw["projection_id"] = f"projection_{raw['projection_hash'][:24]}"
        return RoleContextProjection.model_validate(raw)

    projection = build()
    # ponytail: at most 512 bounded items; replace with cumulative sizing if this becomes hot.
    while len(_canonical(projection).encode()) > target_bytes and evidence:
        evidence = evidence[:-1]
        projection = build()
    while len(_canonical(projection).encode()) > target_bytes and contributions:
        contributions = contributions[:-1]
        projection = build()
    while len(_canonical(projection).encode()) > target_bytes and request_inputs:
        request_inputs = request_inputs[1:]
        projection = build()
    return projection
