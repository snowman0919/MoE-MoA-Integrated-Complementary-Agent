from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .state import now

ArtifactKind = Literal["prompt", "policy", "routing", "failure_handling", "judge_prompt"]
ArtifactState = Literal["candidate", "evaluated", "canary", "active", "deprecated", "rejected"]
PROMPT_ROLES = frozenset(
    {
        "reasoner",
        "executor",
        "planner",
        "reviewer",
        "frontier",
        "judge",
        "skill_generation",
        "knowledge_generation",
        "dataset_transformation",
    }
)


class EvolutionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    kind: ArtifactKind
    version: int = Field(ge=1)
    state: ArtifactState
    payload: dict[str, Any]
    high_impact: bool = False
    source_evidence_ids: list[str]
    evaluation_evidence_ids: list[str] = Field(default_factory=list)
    parent_versions: list[str] = Field(default_factory=list)
    rollback_target: str | None = None
    approval_id: str | None = None
    created_by: str
    created_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def validate_prompt_role(self) -> EvolutionArtifact:
        if self.kind in {"prompt", "judge_prompt"}:
            role = self.payload.get("role")
            if role not in PROMPT_ROLES or not isinstance(self.payload.get("template"), str):
                raise ValueError("Prompt artifact requires a supported role and template")
        if self.state == "active" and (not self.approval_id or not self.rollback_target):
            raise ValueError("active evolution artifact requires approval and rollback target")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"state", "created_at", "approval_id"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class EvolutionEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_valid: bool
    historical_replay: bool
    regression_thresholds_passed: bool
    reviewer_approved: bool
    judge_approved: bool = False
    evidence_ids: list[str]
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    candidate_metrics: dict[str, float] = Field(default_factory=dict)

    def passed(self, *, high_impact: bool) -> bool:
        return (
            self.schema_valid
            and self.historical_replay
            and self.regression_thresholds_passed
            and self.reviewer_approved
            and (not high_impact or self.judge_approved)
            and bool(self.evidence_ids)
        )


class EvolutionRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                "CREATE TABLE IF NOT EXISTS evolution_artifacts ("
                "artifact_id TEXT NOT NULL, version INTEGER NOT NULL, kind TEXT NOT NULL, "
                "state TEXT NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL, "
                "created_at TEXT NOT NULL, PRIMARY KEY(artifact_id, version));"
                "CREATE TABLE IF NOT EXISTS evolution_canaries ("
                "artifact_id TEXT NOT NULL, version INTEGER NOT NULL, outcome TEXT NOT NULL, "
                "evidence_ids TEXT NOT NULL, created_at TEXT NOT NULL, "
                "FOREIGN KEY(artifact_id, version) "
                "REFERENCES evolution_artifacts(artifact_id, version));"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def put(self, artifact: EvolutionArtifact) -> None:
        payload = artifact.model_dump_json()
        digest = artifact.content_hash()
        with self._connect() as database:
            existing = database.execute(
                "SELECT content_hash, payload FROM evolution_artifacts "
                "WHERE artifact_id = ? AND version = ?",
                (artifact.artifact_id, artifact.version),
            ).fetchone()
            if existing:
                if existing != (digest, payload):
                    raise ValueError("evolution artifact versions are immutable")
                return
            database.execute(
                "INSERT INTO evolution_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.artifact_id,
                    artifact.version,
                    artifact.kind,
                    artifact.state,
                    digest,
                    payload,
                    artifact.created_at,
                ),
            )

    def get(self, artifact_id: str, version: int) -> EvolutionArtifact:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM evolution_artifacts WHERE artifact_id = ? AND version = ?",
                (artifact_id, version),
            ).fetchone()
        if row is None:
            raise KeyError(f"evolution artifact not found: {artifact_id}@{version}")
        return EvolutionArtifact.model_validate_json(row[0])

    def list_artifacts(
        self, *, kind: ArtifactKind | None = None, state: ArtifactState | None = None
    ) -> list[EvolutionArtifact]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload FROM evolution_artifacts ORDER BY artifact_id, version"
            ).fetchall()
        artifacts = [EvolutionArtifact.model_validate_json(row[0]) for row in rows]
        return [
            item
            for item in artifacts
            if (kind is None or item.kind == kind) and (state is None or item.state == state)
        ]

    def evaluate(
        self,
        artifact_id: str,
        version: int,
        evaluation: EvolutionEvaluation,
        *,
        created_by: str,
    ) -> EvolutionArtifact:
        current = self.get(artifact_id, version)
        if current.state != "candidate":
            raise ValueError("only candidate evolution artifacts may be evaluated")
        evaluated = current.model_copy(
            update={
                "version": version + 1,
                "state": (
                    "evaluated"
                    if evaluation.passed(high_impact=current.high_impact)
                    else "rejected"
                ),
                "evaluation_evidence_ids": evaluation.evidence_ids,
                "parent_versions": [f"{artifact_id}@{version}"],
                "created_by": created_by,
                "created_at": now(),
            }
        )
        self.put(evaluated)
        return evaluated

    def start_canary(
        self,
        artifact_id: str,
        version: int,
        *,
        rollback_target: str,
        approval_id: str,
        created_by: str,
    ) -> EvolutionArtifact:
        current = self.get(artifact_id, version)
        if current.state != "evaluated" or not current.evaluation_evidence_ids:
            raise ValueError("canary requires a passed evaluated artifact")
        if not approval_id or not rollback_target:
            raise PermissionError("canary requires approval and rollback target")
        canary = current.model_copy(
            update={
                "version": version + 1,
                "state": "canary",
                "parent_versions": [f"{artifact_id}@{version}"],
                "rollback_target": rollback_target,
                "approval_id": approval_id,
                "created_by": created_by,
                "created_at": now(),
            }
        )
        self.put(canary)
        return canary

    def record_canary(
        self,
        artifact_id: str,
        version: int,
        *,
        outcome: Literal["helpful", "neutral", "harmful"],
        evidence_ids: list[str],
    ) -> None:
        current = self.get(artifact_id, version)
        if current.state != "canary" or not evidence_ids:
            raise ValueError("canary outcome requires a canary and evidence")
        with self._connect() as database:
            database.execute(
                "INSERT INTO evolution_canaries VALUES (?, ?, ?, ?, ?)",
                (artifact_id, version, outcome, json.dumps(evidence_ids), now()),
            )

    def promote(
        self,
        artifact_id: str,
        version: int,
        *,
        approval_id: str,
        created_by: str,
    ) -> EvolutionArtifact:
        current = self.get(artifact_id, version)
        with self._connect() as database:
            helpful = database.execute(
                "SELECT COUNT(*) FROM evolution_canaries WHERE artifact_id = ? AND version = ? "
                "AND outcome = 'helpful'",
                (artifact_id, version),
            ).fetchone()[0]
        if (
            current.state != "canary"
            or not helpful
            or not approval_id
            or not current.rollback_target
        ):
            raise PermissionError(
                "promotion requires helpful canary, approval, and rollback target"
            )
        promoted = current.model_copy(
            update={
                "version": version + 1,
                "state": "active",
                "parent_versions": [f"{artifact_id}@{version}"],
                "approval_id": approval_id,
                "created_by": created_by,
                "created_at": now(),
            }
        )
        self.put(promoted)
        return promoted

    def rollback(
        self,
        artifact_id: str,
        current_version: int,
        target_version: int,
        *,
        approval_id: str,
        created_by: str,
    ) -> EvolutionArtifact:
        current = self.get(artifact_id, current_version)
        target = self.get(artifact_id, target_version)
        if current.state != "active" or not approval_id:
            raise PermissionError("rollback requires active current and approval")
        rolled_back = target.model_copy(
            update={
                "version": current_version + 1,
                "state": "active",
                "parent_versions": [
                    f"{artifact_id}@{current_version}",
                    f"{artifact_id}@{target_version}",
                ],
                "rollback_target": f"{artifact_id}@{current_version}",
                "approval_id": approval_id,
                "created_by": created_by,
                "created_at": now(),
            }
        )
        self.put(rolled_back)
        return rolled_back

    def active(self, artifact_id: str) -> EvolutionArtifact | None:
        candidates = [
            item for item in self.list_artifacts(state="active") if item.artifact_id == artifact_id
        ]
        return max(candidates, key=lambda item: item.version, default=None)


class PromptRegistry:
    def __init__(self, path: str | Path):
        self.registry = EvolutionRegistry(path)

    def active_template(self, role: str) -> str | None:
        if role not in PROMPT_ROLES:
            raise ValueError("unsupported prompt role")
        artifact = self.registry.active(f"prompt.{role}")
        return str(artifact.payload["template"]) if artifact else None
