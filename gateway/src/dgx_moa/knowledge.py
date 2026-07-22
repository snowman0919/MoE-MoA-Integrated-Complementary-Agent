from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .state import now

KnowledgeState = Literal["candidate", "active", "conflicted", "deprecated", "disabled", "archived"]
KnowledgeCategory = Literal[
    "framework_behavior",
    "api_behavior",
    "repository_convention",
    "failure_pattern",
    "successful_repair_pattern",
    "deployment_constraint",
    "provider_limitation",
    "model_behavior",
    "tool_limitation",
    "performance_observation",
    "security_pattern",
    "domain_fact",
]
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
TOKEN = re.compile(r"[a-z0-9_+-]+")


class KnowledgeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=8_000)
    conditions: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class KnowledgeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_task_ids: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    verified_by_tests: bool = False
    last_verified_at: str | None = None


class KnowledgeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["operational", "human", "documentation", "generated"]
    created_at: str = Field(default_factory=now)
    created_by: str


class KnowledgeConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_: Literal["low", "medium", "high"] = Field(alias="class")
    basis: Literal["observed", "tested", "reviewed", "judged"]


class KnowledgeLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supersedes: list[str] = Field(default_factory=list)
    deprecated_by: str | None = None
    approval_id: str | None = None


class RuntimeKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    knowledge_id: str
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=256)
    state: KnowledgeState
    category: KnowledgeCategory
    domains: list[str] = Field(default_factory=list)
    repository_scope: list[str] = Field(default_factory=list)
    content: KnowledgeContent
    evidence: KnowledgeEvidence
    provenance: KnowledgeProvenance
    confidence: KnowledgeConfidence
    lifecycle: KnowledgeLifecycle = Field(default_factory=KnowledgeLifecycle)
    validation_evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_identity(self) -> RuntimeKnowledge:
        if not SAFE_ID.fullmatch(self.knowledge_id):
            raise ValueError("invalid Knowledge ID")
        if self.state == "active" and not self.validation_evidence:
            raise ValueError("active Knowledge requires validation evidence")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        payload.pop("state", None)
        payload.pop("validation_evidence", None)
        payload["lifecycle"] = {"supersedes": payload["lifecycle"]["supersedes"]}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class KnowledgeValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_verified: bool
    duplicate_checked: bool
    contradiction_checked: bool
    repository_scope_checked: bool
    privacy_checked: bool
    license_checked: bool
    historical_replay: bool = False
    reviewer_approved: bool = False
    judge_approved: bool = False
    high_impact: bool = False
    evidence_ids: list[str]

    @property
    def passed(self) -> bool:
        base = all(
            (
                self.source_verified,
                self.duplicate_checked,
                self.contradiction_checked,
                self.repository_scope_checked,
                self.privacy_checked,
                self.license_checked,
                bool(self.evidence_ids),
            )
        )
        return base and (not self.high_impact or self.reviewer_approved or self.judge_approved)


class KnowledgeQuery(BaseModel):
    text: str
    domains: list[str] = Field(default_factory=list)
    category: KnowledgeCategory | None = None
    repository: str | None = None


class KnowledgeMatch(BaseModel):
    knowledge: RuntimeKnowledge
    score: float
    reasons: list[str]
    contradiction_ids: list[str] = Field(default_factory=list)


class KnowledgeRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                "CREATE TABLE IF NOT EXISTS knowledge_entries ("
                "knowledge_id TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, "
                "content_hash TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY(knowledge_id, version));"
                "CREATE TABLE IF NOT EXISTS knowledge_conflicts ("
                "conflict_id TEXT PRIMARY KEY, left_id TEXT NOT NULL, "
                "left_version INTEGER NOT NULL, "
                "right_id TEXT NOT NULL, right_version INTEGER NOT NULL, evidence TEXT NOT NULL, "
                "status TEXT NOT NULL, resolved_by TEXT, created_at TEXT NOT NULL);"
                "CREATE TABLE IF NOT EXISTS knowledge_metrics ("
                "knowledge_id TEXT NOT NULL, version INTEGER NOT NULL, "
                "retrieved INTEGER NOT NULL DEFAULT 0, "
                "helpful INTEGER NOT NULL DEFAULT 0, harmful INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY(knowledge_id, version), "
                "FOREIGN KEY(knowledge_id, version) "
                "REFERENCES knowledge_entries(knowledge_id, version));"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def put(self, entry: RuntimeKnowledge) -> None:
        payload = entry.model_dump_json(by_alias=True)
        digest = entry.content_hash()
        with self._connect() as database:
            existing = database.execute(
                "SELECT content_hash, payload FROM knowledge_entries "
                "WHERE knowledge_id = ? AND version = ?",
                (entry.knowledge_id, entry.version),
            ).fetchone()
            if existing:
                if existing != (digest, payload):
                    raise ValueError("Knowledge versions are immutable")
                return
            database.execute(
                "INSERT INTO knowledge_entries VALUES (?, ?, ?, ?, ?, ?)",
                (entry.knowledge_id, entry.version, entry.state, digest, payload, now()),
            )
            database.execute(
                "INSERT INTO knowledge_metrics(knowledge_id, version) VALUES (?, ?)",
                (entry.knowledge_id, entry.version),
            )

    def get(self, knowledge_id: str, version: int) -> RuntimeKnowledge:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM knowledge_entries WHERE knowledge_id = ? AND version = ?",
                (knowledge_id, version),
            ).fetchone()
        if row is None:
            raise KeyError(f"Knowledge not found: {knowledge_id}@{version}")
        return RuntimeKnowledge.model_validate_json(row[0])

    def list_entries(self, *, states: set[KnowledgeState] | None = None) -> list[RuntimeKnowledge]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload FROM knowledge_entries ORDER BY knowledge_id, version"
            ).fetchall()
        entries = [RuntimeKnowledge.model_validate_json(row[0]) for row in rows]
        return [entry for entry in entries if states is None or entry.state in states]

    def validate_candidate(
        self, knowledge_id: str, version: int, validation: KnowledgeValidation
    ) -> RuntimeKnowledge:
        current = self.get(knowledge_id, version)
        if current.state != "candidate":
            raise ValueError("only candidate Knowledge may be validated")
        if not validation.passed:
            raise ValueError("Knowledge validation gates failed")
        validated = current.model_copy(
            update={
                "version": version + 1,
                "validation_evidence": validation.evidence_ids,
                "confidence": KnowledgeConfidence.model_validate(
                    {
                        "class": "high" if validation.judge_approved else "medium",
                        "basis": "judged" if validation.judge_approved else "reviewed",
                    }
                ),
                "lifecycle": KnowledgeLifecycle(supersedes=[f"{knowledge_id}@{version}"]),
            }
        )
        self.put(validated)
        return validated

    def promote(
        self, knowledge_id: str, version: int, *, approval_id: str, created_by: str
    ) -> RuntimeKnowledge:
        current = self.get(knowledge_id, version)
        if current.state != "candidate" or not current.validation_evidence:
            raise ValueError("Knowledge promotion requires a validated candidate")
        if not approval_id:
            raise PermissionError("Knowledge promotion requires explicit approval")
        promoted = current.model_copy(
            update={
                "version": version + 1,
                "state": "active",
                "provenance": KnowledgeProvenance(source_type="human", created_by=created_by),
                "lifecycle": KnowledgeLifecycle(
                    supersedes=[f"{knowledge_id}@{version}"], approval_id=approval_id
                ),
            }
        )
        self.put(promoted)
        return promoted

    def add_conflict(
        self,
        left: tuple[str, int],
        right: tuple[str, int],
        *,
        evidence_ids: list[str],
    ) -> str:
        self.get(*left)
        self.get(*right)
        ordered = sorted((f"{left[0]}@{left[1]}", f"{right[0]}@{right[1]}"))
        conflict_id = "conflict_" + hashlib.sha256("|".join(ordered).encode()).hexdigest()[:16]
        with self._connect() as database:
            database.execute(
                "INSERT OR IGNORE INTO knowledge_conflicts "
                "VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, ?)",
                (
                    conflict_id,
                    left[0],
                    left[1],
                    right[0],
                    right[1],
                    json.dumps(evidence_ids),
                    now(),
                ),
            )
        return conflict_id

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution: RuntimeKnowledge,
        *,
        approval_id: str,
    ) -> RuntimeKnowledge:
        if not approval_id or not resolution.lifecycle.supersedes:
            raise PermissionError("Knowledge conflict resolution requires approval and supersedes")
        with self._connect() as database:
            row = database.execute(
                "SELECT status FROM knowledge_conflicts WHERE conflict_id = ?", (conflict_id,)
            ).fetchone()
            if row is None or row[0] != "open":
                raise ValueError("Knowledge conflict is not open")
        resolution = resolution.model_copy(
            update={
                "lifecycle": resolution.lifecycle.model_copy(update={"approval_id": approval_id})
            }
        )
        self.put(resolution)
        with self._connect() as database:
            database.execute(
                "UPDATE knowledge_conflicts SET status = 'resolved', resolved_by = ? "
                "WHERE conflict_id = ?",
                (f"{resolution.knowledge_id}@{resolution.version}", conflict_id),
            )
        return resolution

    def _conflicts(self, knowledge_id: str, version: int) -> list[str]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT conflict_id FROM knowledge_conflicts WHERE status = 'open' AND "
                "((left_id = ? AND left_version = ?) OR (right_id = ? AND right_version = ?))",
                (knowledge_id, version, knowledge_id, version),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def search(self, query: KnowledgeQuery, *, limit: int = 3) -> list[KnowledgeMatch]:
        if not 1 <= limit <= 10:
            raise ValueError("Knowledge retrieval limit must be between 1 and 10")
        query_tokens = Counter(TOKEN.findall(query.text.lower()))
        latest: dict[str, RuntimeKnowledge] = {}
        for entry in self.list_entries(states={"active"}):
            if (
                entry.knowledge_id not in latest
                or entry.version > latest[entry.knowledge_id].version
            ):
                latest[entry.knowledge_id] = entry
        matches: list[KnowledgeMatch] = []
        for entry in latest.values():
            if query.category and entry.category != query.category:
                continue
            if (
                query.repository
                and entry.repository_scope
                and query.repository not in entry.repository_scope
            ):
                continue
            text = " ".join(
                [entry.title, entry.content.summary, *entry.domains, *entry.content.conditions]
            ).lower()
            score = float(sum(query_tokens[token] for token in set(TOKEN.findall(text))))
            reasons = [f"lexical_overlap:{int(score)}"] if score else []
            overlap = set(map(str.lower, query.domains)).intersection(map(str.lower, entry.domains))
            if overlap:
                score += 3 * len(overlap)
                reasons.append(f"domain_match:{len(overlap)}")
            if score:
                matches.append(
                    KnowledgeMatch(
                        knowledge=entry,
                        score=score,
                        reasons=reasons,
                        contradiction_ids=self._conflicts(entry.knowledge_id, entry.version),
                    )
                )
        selected = sorted(matches, key=lambda item: (-item.score, item.knowledge.knowledge_id))[
            :limit
        ]
        with self._connect() as database:
            for match in selected:
                database.execute(
                    "UPDATE knowledge_metrics SET retrieved = retrieved + 1 "
                    "WHERE knowledge_id = ? AND version = ?",
                    (match.knowledge.knowledge_id, match.knowledge.version),
                )
        return selected

    def record_outcome(
        self, knowledge_id: str, version: int, outcome: Literal["helpful", "harmful"]
    ) -> None:
        with self._connect() as database:
            database.execute(
                f"UPDATE knowledge_metrics SET {outcome} = {outcome} + 1 "  # noqa: S608
                "WHERE knowledge_id = ? AND version = ?",
                (knowledge_id, version),
            )

    def transition_lifecycle(
        self,
        knowledge_id: str,
        version: int,
        target: Literal["deprecated", "disabled", "archived"],
        *,
        approval_id: str,
        created_by: str,
    ) -> RuntimeKnowledge:
        current = self.get(knowledge_id, version)
        allowed = {
            "active": {"deprecated"},
            "deprecated": {"disabled"},
            "disabled": {"archived"},
        }
        if target not in allowed.get(current.state, set()):
            raise ValueError(f"invalid Knowledge lifecycle transition: {current.state} -> {target}")
        if not approval_id:
            raise PermissionError("Knowledge lifecycle change requires explicit approval")
        transitioned = current.model_copy(
            update={
                "version": version + 1,
                "state": target,
                "provenance": KnowledgeProvenance(source_type="human", created_by=created_by),
                "lifecycle": KnowledgeLifecycle(
                    supersedes=[f"{knowledge_id}@{version}"], approval_id=approval_id
                ),
            }
        )
        self.put(transitioned)
        return transitioned

    def rollback(
        self,
        knowledge_id: str,
        current_version: int,
        target_version: int,
        *,
        approval_id: str,
        created_by: str,
    ) -> RuntimeKnowledge:
        current = self.get(knowledge_id, current_version)
        target = self.get(knowledge_id, target_version)
        if not approval_id or current.state != "active" or not target.validation_evidence:
            raise PermissionError(
                "Knowledge rollback requires active current, validated target, and approval"
            )
        rolled_back = target.model_copy(
            update={
                "version": current_version + 1,
                "state": "active",
                "provenance": KnowledgeProvenance(source_type="human", created_by=created_by),
                "lifecycle": KnowledgeLifecycle(
                    supersedes=[
                        f"{knowledge_id}@{current_version}",
                        f"{knowledge_id}@{target_version}",
                    ],
                    approval_id=approval_id,
                ),
            }
        )
        self.put(rolled_back)
        return rolled_back

    def integrity_check(self) -> bool:
        with self._connect() as database:
            result = database.execute("PRAGMA integrity_check").fetchone()
        return bool(result == ("ok",))
