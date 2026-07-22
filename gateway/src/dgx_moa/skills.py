from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SkillStore = Literal[
    "core",
    "generated",
    "experimental",
    "deprecated",
    "disabled",
    "archived",
    "packs",
]
SkillState = Literal["experimental", "active", "deprecated", "disabled", "archived"]
SKILL_STORES: tuple[SkillStore, ...] = (
    "core",
    "generated",
    "experimental",
    "deprecated",
    "disabled",
    "archived",
    "packs",
)
SAFE_NAME = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
TOKEN = re.compile(r"[a-z0-9][a-z0-9_+.-]*", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SkillValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unvalidated", "passed", "failed"] = "unvalidated"
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    required_evidence: list[str] = Field(default_factory=list, max_length=32)
    regression_suite: list[str] = Field(default_factory=list, max_length=32)
    validated_at: str | None = None

    @model_validator(mode="after")
    def require_evidence_for_pass(self) -> SkillValidation:
        if self.status == "passed" and not self.evidence_ids:
            raise ValueError("passed Skill validation requires evidence")
        return self


class SkillProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["human", "runtime", "imported"]
    created_by: str
    created_at: str = Field(default_factory=utc_now)
    parent_versions: list[str] = Field(default_factory=list, max_length=16)
    source_trace_ids: list[str] = Field(default_factory=list, max_length=64)
    approval_id: str | None = None


class RuntimeSkill(BaseModel):
    """Immutable, versioned Executor procedure; models may only recommend it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    version: str
    name: str
    description: str
    source: Literal["core", "generated", "imported"] = "generated"
    state: SkillState = "experimental"
    store: SkillStore = "experimental"
    domains: list[str] = Field(default_factory=list, max_length=32)
    task_types: list[str] = Field(default_factory=list, max_length=32)
    languages: list[str] = Field(default_factory=list, max_length=16)
    frameworks: list[str] = Field(default_factory=list, max_length=16)
    failure_fingerprints: list[str] = Field(default_factory=list, max_length=64)
    inputs: list[str] = Field(default_factory=list, max_length=32)
    outputs: list[str] = Field(default_factory=list, max_length=32)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    procedure: list[str] = Field(min_length=1, max_length=64)
    allowed_tools: list[str] = Field(default_factory=list, max_length=32)
    denied_tools: list[str] = Field(default_factory=list, max_length=32)
    recommended_agents: list[str] = Field(default_factory=list, max_length=8)
    provenance: SkillProvenance
    validation: SkillValidation = Field(default_factory=SkillValidation)

    @field_validator("skill_id")
    @classmethod
    def validate_safe_name(cls, value: str) -> str:
        if len(value) > 64 or not SAFE_NAME.fullmatch(value):
            raise ValueError("Skill IDs must use safe lowercase dot or hyphen segments")
        return value

    @field_validator("name", "description")
    @classmethod
    def validate_display_text(cls, value: str) -> str:
        if not value.strip() or len(value) > 500:
            raise ValueError("Skill display text must be nonempty and bounded")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not SEMVER.fullmatch(value):
            raise ValueError("Skill version must be semantic x.y.z")
        return value

    @model_validator(mode="after")
    def validate_store_state(self) -> RuntimeSkill:
        expected: dict[SkillState, set[SkillStore]] = {
            "experimental": {"generated", "experimental"},
            "active": {"core"},
            "deprecated": {"deprecated"},
            "disabled": {"disabled"},
            "archived": {"archived"},
        }
        if self.store not in expected[self.state]:
            raise ValueError("Skill store does not match lifecycle state")
        if (
            self.provenance.source == "runtime"
            and not self.provenance.parent_versions
            and self.state != "experimental"
        ):
            raise ValueError("runtime-generated Skills must start experimental")
        if set(self.allowed_tools).intersection(self.denied_tools):
            raise ValueError("Skill tool allow and deny lists must not overlap")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class SkillQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    task_type: str = ""
    language: str = ""
    framework: str = ""
    failure_fingerprints: list[str] = Field(default_factory=list, max_length=32)


class SkillMatch(BaseModel):
    skill: RuntimeSkill
    score: float
    reasons: list[str]


class SkillMetrics(BaseModel):
    selected: int = 0
    succeeded: int = 0
    failed: int = 0
    overridden: int = 0
    rollbacks: int = 0
    regressions: int = 0
    average_latency_ms: float | None = None
    average_token_delta: float | None = None
    estimated_quality_gain: float | None = None
    frontier_corrections: int = 0
    reviewer_findings: int = 0
    task_coverage: int = 0
    last_used_at: str | None = None


class SkillPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    kind: Literal[
        "task_class",
        "failure_fingerprint",
        "repair_sequence",
        "review_checklist",
        "tool_workflow",
        "architecture_decision",
    ]
    occurrences: int = Field(ge=2)
    evidence_ids: list[str] = Field(min_length=2, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    procedure: list[str] = Field(min_length=1, max_length=64)
    task_types: list[str] = Field(default_factory=list, max_length=32)
    failure_fingerprints: list[str] = Field(default_factory=list, max_length=64)
    allowed_tools: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("pattern_id")
    @classmethod
    def validate_pattern_id(cls, value: str) -> str:
        if not SAFE_NAME.fullmatch(value):
            raise ValueError("invalid Skill pattern ID")
        return value

    @model_validator(mode="after")
    def distinct_evidence(self) -> SkillPattern:
        if len(set(self.evidence_ids)) < 2:
            raise ValueError("Skill generation requires distinct recurring evidence")
        return self


class SkillCandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isolated_validation: bool
    historical_replay: bool
    regression_evaluation: bool
    reviewer_inspection: bool
    high_impact: bool = False
    judge_validation: bool | None = None
    evidence_ids: list[str] = Field(min_length=1, max_length=64)

    @property
    def passed(self) -> bool:
        required = (
            self.isolated_validation,
            self.historical_replay,
            self.regression_evaluation,
            self.reviewer_inspection,
        )
        return all(required) and (not self.high_impact or self.judge_validation is True)


class SkillPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    pack_id: str
    created_at: str = Field(default_factory=utc_now)
    skills: list[dict[str, str]]
    dependencies: list[str] = Field(default_factory=list)
    compatibility: dict[str, str] = Field(default_factory=dict)
    signature_key_id: str | None = None
    signature: str | None = None

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not SAFE_NAME.fullmatch(value):
            raise ValueError("invalid Skill pack ID")
        return value

    def signing_payload(self) -> bytes:
        data = self.model_dump(exclude={"signature_key_id", "signature"}, mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


class SkillRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for store in SKILL_STORES:
            (self.root / store).mkdir(exist_ok=True)
        self.metrics_db = self.root / "metrics.db"
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS skill_metrics ("
                "skill_id TEXT NOT NULL, version TEXT NOT NULL, "
                "selected INTEGER NOT NULL DEFAULT 0, "
                "succeeded INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, "
                "overridden INTEGER NOT NULL DEFAULT 0, rollbacks INTEGER NOT NULL DEFAULT 0, "
                "regressions INTEGER NOT NULL DEFAULT 0, average_latency_ms REAL, "
                "average_token_delta REAL, estimated_quality_gain REAL, "
                "frontier_corrections INTEGER NOT NULL DEFAULT 0, "
                "reviewer_findings INTEGER NOT NULL DEFAULT 0, "
                "task_coverage INTEGER NOT NULL DEFAULT 0, last_used_at TEXT, "
                "PRIMARY KEY(skill_id, version))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS skill_canary_events ("
                "event_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_id TEXT NOT NULL, "
                "version TEXT NOT NULL, outcome TEXT NOT NULL, evidence_ids TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            columns = {
                row[1] for row in database.execute("PRAGMA table_info(skill_metrics)").fetchall()
            }
            migrations = {
                "overridden": "INTEGER NOT NULL DEFAULT 0",
                "rollbacks": "INTEGER NOT NULL DEFAULT 0",
                "regressions": "INTEGER NOT NULL DEFAULT 0",
                "average_latency_ms": "REAL",
                "average_token_delta": "REAL",
                "estimated_quality_gain": "REAL",
                "frontier_corrections": "INTEGER NOT NULL DEFAULT 0",
                "reviewer_findings": "INTEGER NOT NULL DEFAULT 0",
                "task_coverage": "INTEGER NOT NULL DEFAULT 0",
                "last_used_at": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    database.execute(f"ALTER TABLE skill_metrics ADD COLUMN {column} {definition}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.metrics_db, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _path(self, skill: RuntimeSkill) -> Path:
        return self.root / skill.store / skill.skill_id / f"{skill.version}.json"

    def put(self, skill: RuntimeSkill) -> Path:
        path = self._path(skill)
        payload = skill.model_dump_json(indent=2)
        if path.exists():
            current = RuntimeSkill.model_validate_json(path.read_text())
            if current.content_hash() != skill.content_hash():
                raise ValueError("Skill versions are immutable")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".skill-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def get(self, skill_id: str, version: str) -> RuntimeSkill:
        if not SAFE_NAME.fullmatch(skill_id) or not SEMVER.fullmatch(version):
            raise KeyError("invalid Skill identifier")
        matches = list(self.root.glob(f"*/{skill_id}/{version}.json"))
        if len(matches) != 1:
            raise KeyError(f"unknown Skill version: {skill_id}@{version}")
        return RuntimeSkill.model_validate_json(matches[0].read_text())

    def list_skills(self, *, states: set[SkillState] | None = None) -> list[RuntimeSkill]:
        skills: list[RuntimeSkill] = []
        for store in SKILL_STORES[:-1]:
            for path in sorted((self.root / store).glob("*/*.json")):
                skill = RuntimeSkill.model_validate_json(path.read_text())
                if states is None or skill.state in states:
                    skills.append(skill)
        return skills

    def successor(
        self,
        skill_id: str,
        version: str,
        *,
        procedure: list[str] | None = None,
        validation: SkillValidation | None = None,
        created_by: str,
        approval_id: str | None = None,
    ) -> RuntimeSkill:
        current = self.get(skill_id, version)
        if current.store == "core" and not approval_id:
            raise PermissionError("core Skill changes require explicit approval")
        major, minor, patch = (int(item) for item in current.version.split("."))
        successor = RuntimeSkill.model_validate(
            current.model_dump()
            | {
                "version": f"{major}.{minor}.{patch + 1}",
                "state": "experimental",
                "store": "experimental",
                "procedure": procedure or current.procedure,
                "validation": validation or SkillValidation(),
                "provenance": SkillProvenance(
                    source="human",
                    created_by=created_by,
                    parent_versions=[f"{current.skill_id}@{current.version}"],
                    approval_id=approval_id,
                ),
            }
        )
        self.put(successor)
        return successor

    def draft_from_pattern(self, pattern: SkillPattern, *, created_by: str) -> RuntimeSkill:
        digest = hashlib.sha256(pattern.model_dump_json().encode()).hexdigest()[:10]
        skill = RuntimeSkill(
            skill_id=f"generated.{pattern.kind.replace('_', '-')}.{digest}",
            version="0.1.0",
            name=pattern.pattern_id,
            description=pattern.description,
            source="generated",
            state="experimental",
            store="generated",
            task_types=pattern.task_types,
            failure_fingerprints=pattern.failure_fingerprints,
            procedure=pattern.procedure,
            allowed_tools=pattern.allowed_tools,
            provenance=SkillProvenance(
                source="runtime",
                created_by=created_by,
                source_trace_ids=pattern.evidence_ids,
            ),
            validation=SkillValidation(
                required_evidence=[
                    "isolated_validation",
                    "historical_replay",
                    "regression_evaluation",
                    "reviewer_inspection",
                ]
            ),
        )
        self.put(skill)
        return skill

    def evaluate_candidate(
        self,
        skill_id: str,
        version: str,
        *,
        evaluator: Callable[[RuntimeSkill], SkillCandidateEvaluation],
        created_by: str,
    ) -> tuple[RuntimeSkill, SkillCandidateEvaluation]:
        current = self.get(skill_id, version)
        if current.state != "experimental":
            raise ValueError("only experimental Skills may enter candidate evaluation")
        evaluation = evaluator(current)
        major, minor, patch = (int(item) for item in current.version.split("."))
        evaluated = RuntimeSkill.model_validate(
            current.model_dump()
            | {
                "version": f"{major}.{minor}.{patch + 1}",
                "store": "experimental",
                "validation": SkillValidation(
                    status="passed" if evaluation.passed else "failed",
                    evidence_ids=evaluation.evidence_ids,
                    required_evidence=[
                        "isolated_validation",
                        "historical_replay",
                        "regression_evaluation",
                        "reviewer_inspection",
                        *(["judge_validation"] if evaluation.high_impact else []),
                    ],
                    validated_at=utc_now(),
                ),
                "provenance": SkillProvenance(
                    source="runtime",
                    created_by=created_by,
                    parent_versions=[f"{current.skill_id}@{current.version}"],
                    source_trace_ids=current.provenance.source_trace_ids,
                ),
            }
        )
        self.put(evaluated)
        return evaluated, evaluation

    def promote(
        self,
        skill_id: str,
        version: str,
        *,
        approval_id: str,
        created_by: str,
    ) -> RuntimeSkill:
        current = self.get(skill_id, version)
        if not approval_id:
            raise PermissionError("Skill promotion requires explicit approval")
        if current.validation.status != "passed":
            raise ValueError("Skill promotion requires passed validation evidence")
        if (
            current.provenance.source == "runtime"
            and not self.canary_summary(skill_id, version)["helpful"]
        ):
            raise ValueError("runtime-generated Skill promotion requires a helpful canary")
        major, minor, patch = (int(item) for item in current.version.split("."))
        promoted = RuntimeSkill.model_validate(
            current.model_dump()
            | {
                "version": f"{major}.{minor + 1}.{patch}",
                "state": "active",
                "store": "core",
                "provenance": SkillProvenance(
                    source="human",
                    created_by=created_by,
                    parent_versions=[f"{current.skill_id}@{current.version}"],
                    source_trace_ids=current.provenance.source_trace_ids,
                    approval_id=approval_id,
                ),
            }
        )
        self.put(promoted)
        return promoted

    def record_canary(
        self,
        skill_id: str,
        version: str,
        *,
        outcome: Literal["helpful", "neutral", "harmful"],
        evidence_ids: list[str],
        activated_by: Literal["executor"],
    ) -> None:
        current = self.get(skill_id, version)
        if current.state != "experimental" or current.validation.status != "passed":
            raise ValueError("canary requires a validated experimental Skill")
        if activated_by != "executor" or not evidence_ids:
            raise PermissionError("Skill canary requires Executor evidence")
        with self._connect() as database:
            database.execute(
                "INSERT INTO skill_canary_events "
                "(skill_id, version, outcome, evidence_ids, created_at) VALUES (?, ?, ?, ?, ?)",
                (skill_id, version, outcome, json.dumps(evidence_ids), utc_now()),
            )
        self.record_outcome(skill_id, version, "selected")
        self.record_outcome(
            skill_id,
            version,
            "succeeded"
            if outcome == "helpful"
            else "regression"
            if outcome == "harmful"
            else "failed",
        )

    def canary_summary(self, skill_id: str, version: str) -> dict[str, int]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT outcome, COUNT(*) FROM skill_canary_events "
                "WHERE skill_id = ? AND version = ? GROUP BY outcome",
                (skill_id, version),
            ).fetchall()
        counts = {"helpful": 0, "neutral": 0, "harmful": 0}
        counts.update({str(outcome): int(count) for outcome, count in rows})
        return counts

    def transition_lifecycle(
        self,
        skill_id: str,
        version: str,
        target: Literal["deprecated", "disabled", "archived"],
        *,
        created_by: str,
        approval_id: str | None = None,
        policy_permits: bool = False,
    ) -> RuntimeSkill:
        current = self.get(skill_id, version)
        allowed = {
            "active": {"deprecated"},
            "experimental": {"disabled"},
            "deprecated": {"disabled"},
            "disabled": {"archived"},
        }
        if target not in allowed.get(current.state, set()):
            raise ValueError(f"invalid Skill lifecycle transition: {current.state} -> {target}")
        if current.source == "core" and not approval_id:
            raise PermissionError("core Skill lifecycle changes require explicit approval")
        if current.source != "core" and not (approval_id or policy_permits):
            raise PermissionError("generated Skill lifecycle change requires approval or policy")
        major, minor, patch = (int(item) for item in current.version.split("."))
        transitioned = RuntimeSkill.model_validate(
            current.model_dump()
            | {
                "version": f"{major}.{minor}.{patch + 1}",
                "state": target,
                "store": target,
                "provenance": SkillProvenance(
                    source="human" if approval_id else "runtime",
                    created_by=created_by,
                    parent_versions=[f"{current.skill_id}@{current.version}"],
                    source_trace_ids=current.provenance.source_trace_ids,
                    approval_id=approval_id,
                ),
            }
        )
        self.put(transitioned)
        return transitioned

    def rollback(
        self,
        skill_id: str,
        current_version: str,
        target_version: str,
        *,
        approval_id: str,
        created_by: str,
    ) -> RuntimeSkill:
        current = self.get(skill_id, current_version)
        target = self.get(skill_id, target_version)
        if current.state != "active" or target.validation.status != "passed":
            raise ValueError("rollback requires active current and validated target Skills")
        if not approval_id:
            raise PermissionError("production Skill rollback requires explicit approval")
        major, minor, patch = (int(item) for item in current.version.split("."))
        rolled_back = RuntimeSkill.model_validate(
            target.model_dump()
            | {
                "version": f"{major}.{minor + 1}.{patch}",
                "state": "active",
                "store": "core",
                "provenance": SkillProvenance(
                    source="human",
                    created_by=created_by,
                    parent_versions=[
                        f"{current.skill_id}@{current.version}",
                        f"{target.skill_id}@{target.version}",
                    ],
                    approval_id=approval_id,
                ),
            }
        )
        self.put(rolled_back)
        self.record_outcome(current.skill_id, current.version, "rollback")
        return rolled_back

    def record_outcome(
        self,
        skill_id: str,
        version: str,
        outcome: Literal[
            "selected",
            "succeeded",
            "failed",
            "overridden",
            "rollback",
            "regression",
            "frontier_correction",
            "reviewer_finding",
        ],
        *,
        latency_ms: float | None = None,
        token_delta: float | None = None,
        quality_gain: float | None = None,
        task_covered: bool = False,
    ) -> None:
        column = {
            "selected": "selected",
            "succeeded": "succeeded",
            "failed": "failed",
            "overridden": "overridden",
            "rollback": "rollbacks",
            "regression": "regressions",
            "frontier_correction": "frontier_corrections",
            "reviewer_finding": "reviewer_findings",
        }[outcome]
        with self._connect() as database:
            database.execute(
                "INSERT INTO skill_metrics(skill_id, version) VALUES (?, ?) "
                "ON CONFLICT(skill_id, version) DO NOTHING",
                (skill_id, version),
            )
            database.execute(
                f"UPDATE skill_metrics SET {column} = {column} + 1 "  # noqa: S608
                "WHERE skill_id = ? AND version = ?",
                (skill_id, version),
            )
            if latency_ms is not None:
                database.execute(
                    "UPDATE skill_metrics SET average_latency_ms = CASE "
                    "WHEN average_latency_ms IS NULL THEN ? ELSE (average_latency_ms + ?) / 2 END "
                    "WHERE skill_id = ? AND version = ?",
                    (latency_ms, latency_ms, skill_id, version),
                )
            if quality_gain is not None:
                database.execute(
                    "UPDATE skill_metrics SET estimated_quality_gain = ? "
                    "WHERE skill_id = ? AND version = ?",
                    (quality_gain, skill_id, version),
                )
            if token_delta is not None:
                database.execute(
                    "UPDATE skill_metrics SET average_token_delta = CASE "
                    "WHEN average_token_delta IS NULL THEN ? ELSE "
                    "(average_token_delta + ?) / 2 END WHERE skill_id = ? AND version = ?",
                    (token_delta, token_delta, skill_id, version),
                )
            if task_covered:
                database.execute(
                    "UPDATE skill_metrics SET task_coverage = task_coverage + 1 "
                    "WHERE skill_id = ? AND version = ?",
                    (skill_id, version),
                )
            database.execute(
                "UPDATE skill_metrics SET last_used_at = ? WHERE skill_id = ? AND version = ?",
                (utc_now(), skill_id, version),
            )

    def metrics(self, skill_id: str, version: str) -> SkillMetrics:
        with self._connect() as database:
            row = database.execute(
                "SELECT selected, succeeded, failed, overridden, rollbacks, regressions, "
                "average_latency_ms, average_token_delta, estimated_quality_gain, "
                "frontier_corrections, reviewer_findings, task_coverage, last_used_at "
                "FROM skill_metrics "
                "WHERE skill_id = ? AND version = ?",
                (skill_id, version),
            ).fetchone()
        if row is None:
            return SkillMetrics()
        return SkillMetrics.model_validate(dict(zip(SkillMetrics.model_fields, row, strict=True)))

    def search(self, query: SkillQuery, *, limit: int = 3) -> list[SkillMatch]:
        if limit < 1 or limit > 10:
            raise ValueError("Skill retrieval limit must be between 1 and 10")
        query_tokens = Counter(TOKEN.findall(query.text.lower()))
        failures = set(query.failure_fingerprints)
        matches: list[SkillMatch] = []
        with self._connect() as database:
            metrics = {
                (row[0], row[1]): row[2:]
                for row in database.execute(
                    "SELECT skill_id, version, selected, succeeded, failed, regressions, "
                    "estimated_quality_gain FROM skill_metrics"
                )
            }
        latest: dict[str, RuntimeSkill] = {}
        for skill in self.list_skills(states={"active"}):
            current = latest.get(skill.skill_id)
            if current is None or tuple(map(int, skill.version.split("."))) > tuple(
                map(int, current.version.split("."))
            ):
                latest[skill.skill_id] = skill
        for skill in latest.values():
            reasons: list[str] = []
            skill_tokens = set(
                TOKEN.findall(" ".join([skill.name, skill.description, *skill.domains]).lower())
            )
            lexical = sum(query_tokens[token] for token in skill_tokens)
            score = float(lexical)
            if lexical:
                reasons.append(f"lexical_overlap:{lexical}")
            for label, requested, values, weight in (
                ("task_type", query.task_type, skill.task_types, 4.0),
                ("language", query.language, skill.languages, 3.0),
                ("framework", query.framework, skill.frameworks, 3.0),
            ):
                if requested and requested.lower() in {item.lower() for item in values}:
                    score += weight
                    reasons.append(f"{label}_match")
            fingerprint_matches = failures.intersection(skill.failure_fingerprints)
            if fingerprint_matches:
                score += 6 * len(fingerprint_matches)
                reasons.append(f"failure_fingerprint_match:{len(fingerprint_matches)}")
            selected, succeeded, failed, regressions, quality_gain = metrics.get(
                (skill.skill_id, skill.version), (0, 0, 0, 0, None)
            )
            if selected:
                reliability = (succeeded + 1) / (succeeded + failed + 2)
                score += reliability
                reasons.append(f"historical_reliability:{reliability:.3f}")
            if quality_gain is not None:
                score += max(-2.0, min(2.0, float(quality_gain)))
                reasons.append(f"quality_gain:{float(quality_gain):.3f}")
            if regressions:
                score -= min(5.0, float(regressions))
                reasons.append(f"recent_regressions:{regressions}")
            if score > 0:
                matches.append(SkillMatch(skill=skill, score=score, reasons=reasons))
        return sorted(matches, key=lambda item: (-item.score, item.skill.skill_id))[:limit]

    def export_pack(
        self,
        path: str | Path,
        *,
        pack_id: str,
        skill_versions: list[tuple[str, str]],
        dependencies: list[str] | None = None,
        compatibility: dict[str, str] | None = None,
        signer: Callable[[bytes], tuple[str, str]] | None = None,
    ) -> Path:
        skills = [self.get(skill_id, version) for skill_id, version in skill_versions]
        entries = [
            {
                "skill_id": item.skill_id,
                "version": item.version,
                "content_sha256": item.content_hash(),
            }
            for item in skills
        ]
        manifest = SkillPackManifest(
            pack_id=pack_id,
            skills=entries,
            dependencies=dependencies or [],
            compatibility=compatibility or {},
        )
        if signer is not None:
            key_id, signature = signer(manifest.signing_payload())
            manifest = manifest.model_copy(
                update={"signature_key_id": key_id, "signature": signature}
            )
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=destination.parent, prefix=".skill-pack-", suffix=".tmp"
        )
        os.close(descriptor)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", manifest.model_dump_json(indent=2))
                for item in skills:
                    archive.writestr(
                        f"skills/{item.skill_id}/{item.version}.json",
                        item.model_dump_json(indent=2),
                    )
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination

    def import_pack(
        self,
        path: str | Path,
        *,
        require_signature: bool = False,
        verifier: Callable[[str, bytes, str], bool] | None = None,
    ) -> list[RuntimeSkill]:
        with zipfile.ZipFile(path) as archive:
            manifest = SkillPackManifest.model_validate_json(archive.read("manifest.json"))
            has_signature = bool(manifest.signature_key_id and manifest.signature)
            if require_signature and not has_signature:
                raise PermissionError("Skill pack signature required")
            if has_signature and (
                verifier is None
                or not verifier(
                    manifest.signature_key_id or "",
                    manifest.signing_payload(),
                    manifest.signature or "",
                )
            ):
                raise PermissionError("Skill pack signature verification failed")
            imported: list[RuntimeSkill] = []
            for entry in manifest.skills:
                skill_id = entry.get("skill_id", "")
                version = entry.get("version", "")
                if not SAFE_NAME.fullmatch(skill_id) or not SEMVER.fullmatch(version):
                    raise ValueError("invalid Skill pack entry")
                raw = archive.read(f"skills/{skill_id}/{version}.json")
                source = RuntimeSkill.model_validate_json(raw)
                if source.content_hash() != entry.get("content_sha256"):
                    raise ValueError("Skill pack content hash mismatch")
                candidate = RuntimeSkill.model_validate(
                    source.model_dump()
                    | {
                        "source": "imported",
                        "state": "experimental",
                        "store": "experimental",
                        "provenance": SkillProvenance(
                            source="imported",
                            created_by=f"skill-pack:{manifest.pack_id}",
                            parent_versions=[f"{source.skill_id}@{source.version}"],
                        ),
                    }
                )
                self.put(candidate)
                imported.append(candidate)
        return imported
