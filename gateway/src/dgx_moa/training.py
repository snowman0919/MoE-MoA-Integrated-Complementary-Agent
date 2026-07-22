from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .state import StateStore

RepositoryTrainingPolicy = Literal[
    "training_allowed", "internal_only", "training_denied", "unknown"
]
ReviewState = Literal[
    "collected", "sanitized", "scored", "quarantined", "approved", "rejected", "packaged", "revoked"
]
QualityTier = Literal["gold", "silver", "bronze", "negative", "quarantine", "rejected"]
REVIEW_TRANSITIONS: dict[ReviewState, frozenset[ReviewState]] = {
    "collected": frozenset({"sanitized", "quarantined", "rejected"}),
    "sanitized": frozenset({"scored", "quarantined", "approved", "rejected"}),
    "scored": frozenset({"quarantined", "approved", "rejected"}),
    "quarantined": frozenset({"sanitized", "rejected"}),
    "approved": frozenset({"packaged", "revoked"}),
    "rejected": frozenset({"revoked"}),
    "packaged": frozenset({"revoked"}),
    "revoked": frozenset(),
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)authorization:\s*(?:bearer|basic)\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s]+"),
    re.compile(r"\b(?:sk|hf)_[A-Za-z0-9_-]{12,}\b"),
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")
TOKEN = re.compile(r"[A-Za-z0-9_+-]{24,}")


def now() -> str:
    return datetime.now(UTC).isoformat()


def entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


class SanitizationResult(BaseModel):
    value: Any
    secret_redactions: int = 0
    pii_redactions: int = 0
    excluded: bool = False
    reasons: list[str] = Field(default_factory=list)


def sanitize(value: Any) -> SanitizationResult:
    secrets_found = 0
    pii_found = 0

    def clean(item: Any) -> Any:
        nonlocal secrets_found, pii_found
        if isinstance(item, dict):
            cleaned = {}
            for key, content in item.items():
                if re.search(r"(?i)authorization|cookie|token|secret|password|api.?key", key):
                    cleaned[key] = "[REDACTED]"
                    secrets_found += 1
                else:
                    cleaned[key] = clean(content)
            return cleaned
        if isinstance(item, list):
            return [clean(content) for content in item]
        if not isinstance(item, str):
            return item
        text = item
        for pattern in SECRET_PATTERNS:
            text, count = pattern.subn("[REDACTED_SECRET]", text)
            secrets_found += count
        for candidate in TOKEN.findall(text):
            if entropy(candidate) >= 4.0:
                text = text.replace(candidate, "[REDACTED_SECRET]")
                secrets_found += 1
        text, count = EMAIL.subn("[REDACTED_EMAIL]", text)
        pii_found += count
        text, count = PHONE.subn("[REDACTED_PHONE]", text)
        pii_found += count
        return text

    cleaned = clean(value)
    reasons = []
    if secrets_found:
        reasons.append("secret_redacted")
    if pii_found:
        reasons.append("pii_redacted")
    return SanitizationResult(
        value=cleaned,
        secret_redactions=secrets_found,
        pii_redactions=pii_found,
        reasons=reasons,
    )


class TrainingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    timestamp: str = Field(default_factory=now)
    request_id: str
    task_id: str
    loop_id: str = ""
    iteration: int = 0
    role: str
    event_type: str
    model_provider: str
    model_identifier: str
    model_revision: str
    prompt_template_version: str
    policy_version: str
    skill_versions: list[str] = Field(default_factory=list)
    knowledge_versions: list[str] = Field(default_factory=list)
    input_ref: str | None = None
    output_ref: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    status: str
    privacy_class: Literal["public", "internal", "restricted"] = "internal"
    training_eligibility: Literal["eligible", "excluded", "quarantine"] = "excluded"


class TrainingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex}")
    candidate_type: Literal[
        "sft",
        "preference",
        "tool_use",
        "routing",
        "review",
        "judge",
        "repair",
        "skill",
        "knowledge",
        "policy",
        "prompt",
        "loop",
    ]
    source_request_ids: list[str]
    role_target: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    expected_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    accepted_answer: Any = None
    rejected_answers: list[Any] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    quality_labels: dict[str, Any] = Field(default_factory=dict)
    safety_labels: dict[str, Any] = Field(default_factory=dict)
    privacy_labels: dict[str, Any] = Field(default_factory=dict)
    license_labels: dict[str, Any] = Field(default_factory=dict)
    deduplication: dict[str, Any] = Field(default_factory=dict)
    transformations: list[str] = Field(default_factory=list)
    review_state: ReviewState = "collected"
    quality_tier: QualityTier = "quarantine"
    training_eligible: bool = False

    @model_validator(mode="after")
    def validate_preference_grounding(self) -> TrainingCandidate:
        if self.candidate_type == "preference" and (
            not self.accepted_answer or not self.rejected_answers or not self.evidence_summary
        ):
            raise ValueError("preference candidates require both answers and grounding evidence")
        return self


class CandidateQualityReport(BaseModel):
    language: str
    score: float = Field(ge=0, le=1)
    errors: list[str] = Field(default_factory=list)


def detect_language(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    if re.search(r"[가-힣]", text):
        return "ko"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return "unknown"


def assess_candidate(candidate: TrainingCandidate) -> CandidateQualityReport:
    errors: list[str] = []
    if not candidate.messages or any(
        item.get("role") not in {"system", "user", "assistant", "tool"}
        or not isinstance(item.get("content", ""), str)
        for item in candidate.messages
    ):
        errors.append("conversation_reconstruction_failed")
    call_ids = {
        str(item.get("id") or item.get("tool_call_id"))
        for item in candidate.expected_tool_calls
        if item.get("id") or item.get("tool_call_id")
    }
    result_ids = {
        str(item.get("tool_call_id")) for item in candidate.tool_results if item.get("tool_call_id")
    }
    if call_ids and not call_ids.issubset(result_ids):
        errors.append("tool_call_result_mismatch")
    transitions = candidate.quality_labels.get("loop_transitions", [])
    if isinstance(transitions, list):
        for previous, current in zip(transitions, transitions[1:], strict=False):
            if (
                not isinstance(previous, dict)
                or not isinstance(current, dict)
                or (previous.get("state_after") != current.get("state_before"))
            ):
                errors.append("loop_transition_mismatch")
                break
    if candidate.quality_labels.get("truncated"):
        errors.append("truncated_output")
    if candidate.quality_labels.get("malformed_output"):
        errors.append("malformed_output")
    if candidate.training_eligible and not candidate.evidence_summary:
        errors.append("missing_grounding_evidence")
    return CandidateQualityReport(
        language=detect_language(
            [candidate.messages, candidate.accepted_answer, candidate.rejected_answers]
        ),
        score=max(0.0, 1.0 - 0.2 * len(errors)),
        errors=errors,
    )


class CandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: ReviewState
    reason: str = Field(min_length=1, max_length=500)


class TrainingRequestExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=500)


class TrainingRepositoryExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_identity: dict[str, Any]
    reason: str = Field(min_length=1, max_length=500)


class TrainingUserExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=500)


class TrainingRetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_before: str = Field(min_length=1, max_length=64)
    candidate_before: str = Field(min_length=1, max_length=64)
    apply: bool = False


class ContentStore:
    def __init__(self, root: str | Path, *, maximum_bytes: int = 1_000_000):
        self.root = Path(root)
        self.maximum_bytes = maximum_bytes

    def put(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > self.maximum_bytes:
            raise ValueError("content object exceeds size limit")
        digest = hashlib.sha256(raw).hexdigest()
        path = self.root / "sha256" / digest[:2] / digest[2:4] / f"{digest}.json.gz"
        if path.exists():
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".object-", suffix=".tmp")
        os.close(descriptor)
        try:
            with gzip.open(temporary, "wb") as stream:
                stream.write(raw)
            with open(temporary, "rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return digest

    def get(self, digest: str) -> Any:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KeyError("invalid content digest")
        path = self.root / "sha256" / digest[:2] / digest[2:4] / f"{digest}.json.gz"
        with gzip.open(path, "rb") as stream:
            raw = stream.read()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("content object hash mismatch")
        return json.loads(raw)

    def delete(self, digest: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KeyError("invalid content digest")
        path = self.root / "sha256" / digest[:2] / digest[2:4] / f"{digest}.json.gz"
        path.unlink(missing_ok=True)


class TrainingStore:
    def __init__(
        self, path: str | Path, objects: ContentStore, *, minimum_free_bytes: int = 1_000_000_000
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.objects = objects
        self.minimum_free_bytes = minimum_free_bytes
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_events ("
                "event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, task_id TEXT NOT NULL, "
                "payload_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_candidates ("
                "candidate_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL UNIQUE, "
                "dedup_hash TEXT NOT NULL UNIQUE, review_state TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_tombstones ("
                "request_id TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_repository_exclusions ("
                "identity_hash TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_user_exclusions ("
                "subject_hash TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_candidate_requests ("
                "candidate_id TEXT NOT NULL, request_id TEXT NOT NULL, "
                "PRIMARY KEY(candidate_id, request_id), "
                "FOREIGN KEY(candidate_id) REFERENCES training_candidates(candidate_id))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_review_events ("
                "event_id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, "
                "from_state TEXT NOT NULL, to_state TEXT NOT NULL, actor TEXT NOT NULL, "
                "reason TEXT NOT NULL, created_at TEXT NOT NULL, "
                "FOREIGN KEY(candidate_id) REFERENCES training_candidates(candidate_id))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS training_holds ("
                "hold_id TEXT PRIMARY KEY, scope TEXT NOT NULL, target_id TEXT NOT NULL, "
                "kind TEXT NOT NULL, reason TEXT NOT NULL, expires_at TEXT, "
                "released_at TEXT, created_at TEXT NOT NULL)"
            )
            columns = {
                row[1]
                for row in database.execute("PRAGMA table_info(training_candidates)").fetchall()
            }
            if "dedup_hash" not in columns:
                database.execute(
                    "ALTER TABLE training_candidates ADD COLUMN dedup_hash TEXT NOT NULL DEFAULT ''"
                )
                database.execute(
                    "UPDATE training_candidates SET dedup_hash = payload_hash WHERE dedup_hash = ''"
                )
                database.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS training_candidate_dedup "
                    "ON training_candidates(dedup_hash)"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _guard_capacity(self) -> None:
        if shutil.disk_usage(self.path.parent).free < self.minimum_free_bytes:
            raise OSError("training storage capacity guard")

    def verify_integrity(self) -> dict[str, int | bool]:
        with self._connect() as database:
            result = database.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValueError("training database integrity check failed")
            hashes = {
                str(row[0])
                for row in database.execute(
                    "SELECT payload_hash FROM training_events UNION "
                    "SELECT payload_hash FROM training_candidates"
                )
            }
        try:
            for digest in hashes:
                self.objects.get(digest)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("training content integrity check failed") from error
        return {"database_ok": True, "verified_objects": len(hashes)}

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=target.parent, prefix=".training-backup-", suffix=".db"
        )
        os.close(descriptor)
        try:
            with self._connect() as source, sqlite3.connect(temporary) as backup:
                source.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()
                if result is None or result[0] != "ok":
                    raise ValueError("training backup integrity check failed")
            with open(temporary, "rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    def append_event(self, event: TrainingEvent) -> None:
        self._guard_capacity()
        payload_hash = self.objects.put(event.model_dump(mode="json"))
        with self._connect() as database:
            database.execute(
                "INSERT OR IGNORE INTO training_events "
                "(event_id, request_id, task_id, payload_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (event.event_id, event.request_id, event.task_id, payload_hash, event.timestamp),
            )

    def append_candidate(self, candidate: TrainingCandidate) -> bool:
        self._guard_capacity()
        if any(self.excluded(request_id) for request_id in candidate.source_request_ids):
            raise PermissionError("tombstoned request cannot produce a training candidate")
        payload = candidate.model_dump(mode="json")
        payload_hash = self.objects.put(payload)
        dedup_hash = hashlib.sha256(
            json.dumps(
                payload | {"candidate_id": ""}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        with self._connect() as database:
            cursor = database.execute(
                "INSERT OR IGNORE INTO training_candidates "
                "(candidate_id, payload_hash, dedup_hash, review_state, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (candidate.candidate_id, payload_hash, dedup_hash, candidate.review_state, now()),
            )
            if cursor.rowcount == 1:
                database.executemany(
                    "INSERT INTO training_candidate_requests(candidate_id, request_id) "
                    "VALUES (?, ?)",
                    [
                        (candidate.candidate_id, request_id)
                        for request_id in candidate.source_request_ids
                    ],
                )
        return cursor.rowcount == 1

    def candidate(self, candidate_id: str) -> TrainingCandidate:
        with self._connect() as database:
            row = database.execute(
                "SELECT payload_hash, review_state FROM training_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError("unknown training candidate")
        return TrainingCandidate.model_validate(self.objects.get(row[0])).model_copy(
            update={"review_state": row[1]}
        )

    def transition_candidate(
        self,
        candidate_id: str,
        target: ReviewState,
        *,
        actor: str,
        reason: str,
    ) -> TrainingCandidate:
        if not actor or not reason:
            raise ValueError("review transition requires actor and reason")
        with self._connect() as database:
            row = database.execute(
                "SELECT payload_hash, review_state FROM training_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError("unknown training candidate")
            current = cast(ReviewState, str(row[1]))
            if target == current:
                return TrainingCandidate.model_validate(self.objects.get(row[0])).model_copy(
                    update={"review_state": current}
                )
            if target not in REVIEW_TRANSITIONS[current]:
                raise ValueError(f"invalid review transition: {current} -> {target}")
            candidate = TrainingCandidate.model_validate(self.objects.get(row[0]))
            if target in {"approved", "packaged"} and not candidate.training_eligible:
                raise PermissionError("ineligible candidate cannot be approved or packaged")
            database.execute(
                "UPDATE training_candidates SET review_state = ? WHERE candidate_id = ?",
                (target, candidate_id),
            )
            database.execute(
                "INSERT INTO training_review_events "
                "(candidate_id, from_state, to_state, actor, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (candidate_id, current, target, actor, reason, now()),
            )
        return candidate.model_copy(update={"review_state": target})

    def review_history(self, candidate_id: str) -> list[dict[str, str]]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT from_state, to_state, actor, reason, created_at "
                "FROM training_review_events WHERE candidate_id = ? ORDER BY event_id",
                (candidate_id,),
            ).fetchall()
        keys = ("from_state", "to_state", "actor", "reason", "created_at")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def tombstone(self, request_id: str, reason: str) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO training_tombstones(request_id, reason, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(request_id) DO UPDATE SET reason=excluded.reason, "
                "created_at=excluded.created_at",
                (request_id, reason, now()),
            )
            database.execute(
                "UPDATE training_candidates SET review_state = 'revoked' "
                "WHERE candidate_id IN (SELECT candidate_id FROM training_candidate_requests "
                "WHERE request_id = ?)",
                (request_id,),
            )
            database.execute(
                "INSERT OR IGNORE INTO training_holds "
                "(hold_id, scope, target_id, kind, reason, created_at) "
                "VALUES (?, 'request', ?, 'deletion_request', ?, ?)",
                (f"deletion:{request_id}", request_id, reason, now()),
            )

    def excluded(self, request_id: str) -> bool:
        with self._connect() as database:
            return (
                database.execute(
                    "SELECT 1 FROM training_tombstones WHERE request_id = ?", (request_id,)
                ).fetchone()
                is not None
            )

    @staticmethod
    def repository_identity_hash(repository_identity: dict[str, Any]) -> str:
        if not repository_identity:
            raise ValueError("repository identity is required")
        return hashlib.sha256(
            json.dumps(repository_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def exclude_repository(self, repository_identity: dict[str, Any], reason: str) -> str:
        identity_hash = self.repository_identity_hash(repository_identity)
        with self._connect() as database:
            database.execute(
                "INSERT INTO training_repository_exclusions(identity_hash, reason, created_at) "
                "VALUES (?, ?, ?) ON CONFLICT(identity_hash) DO UPDATE SET "
                "reason=excluded.reason, created_at=excluded.created_at",
                (identity_hash, reason, now()),
            )
        return identity_hash

    def repository_excluded(self, repository_identity: dict[str, Any]) -> bool:
        if not repository_identity:
            return False
        identity_hash = self.repository_identity_hash(repository_identity)
        with self._connect() as database:
            return (
                database.execute(
                    "SELECT 1 FROM training_repository_exclusions WHERE identity_hash = ?",
                    (identity_hash,),
                ).fetchone()
                is not None
            )

    def exclude_user(self, subject_id: str, reason: str) -> str:
        if not subject_id or not reason:
            raise ValueError("user exclusion requires subject and reason")
        subject_hash = hashlib.sha256(subject_id.encode()).hexdigest()
        with self._connect() as database:
            database.execute(
                "INSERT INTO training_user_exclusions(subject_hash, reason, created_at) "
                "VALUES (?, ?, ?) ON CONFLICT(subject_hash) DO UPDATE SET "
                "reason=excluded.reason, created_at=excluded.created_at",
                (subject_hash, reason, now()),
            )
        return subject_hash

    def user_excluded(self, subject_hash: str | None) -> bool:
        if not subject_hash:
            return False
        with self._connect() as database:
            return (
                database.execute(
                    "SELECT 1 FROM training_user_exclusions WHERE subject_hash = ?",
                    (subject_hash,),
                ).fetchone()
                is not None
            )

    def place_hold(
        self,
        scope: Literal["request", "candidate"],
        target_id: str,
        *,
        kind: Literal["legal", "investigation", "preservation"],
        reason: str,
        expires_at: str | None = None,
    ) -> str:
        if not target_id or not reason:
            raise ValueError("retention hold requires target and reason")
        hold_id = f"hold_{uuid.uuid4().hex}"
        with self._connect() as database:
            database.execute(
                "INSERT INTO training_holds "
                "(hold_id, scope, target_id, kind, reason, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (hold_id, scope, target_id, kind, reason, expires_at, now()),
            )
        return hold_id

    def release_hold(self, hold_id: str) -> None:
        with self._connect() as database:
            cursor = database.execute(
                "UPDATE training_holds SET released_at = ? "
                "WHERE hold_id = ? AND released_at IS NULL",
                (now(), hold_id),
            )
        if cursor.rowcount != 1:
            raise KeyError("unknown or released retention hold")

    def resolve_deletion_request(self, request_id: str) -> None:
        with self._connect() as database:
            cursor = database.execute(
                "UPDATE training_holds SET released_at = ? WHERE hold_id = ? "
                "AND kind = 'deletion_request' AND released_at IS NULL",
                (now(), f"deletion:{request_id}"),
            )
        if cursor.rowcount != 1:
            raise KeyError("unknown or resolved deletion request")

    def purge_retention(
        self,
        *,
        event_before: str,
        candidate_before: str,
        apply: bool = False,
        reference_time: str | None = None,
    ) -> dict[str, Any]:
        reference = reference_time or now()
        with self._connect() as database:
            active_holds = {
                (str(row[0]), str(row[1]))
                for row in database.execute(
                    "SELECT scope, target_id FROM training_holds WHERE released_at IS NULL "
                    "AND (expires_at IS NULL OR expires_at > ?)",
                    (reference,),
                )
            }
            event_rows = database.execute(
                "SELECT event_id, request_id, payload_hash FROM training_events "
                "WHERE created_at < ? ORDER BY created_at, event_id",
                (event_before,),
            ).fetchall()
            candidate_rows = database.execute(
                "SELECT candidate_id, payload_hash FROM training_candidates "
                "WHERE created_at < ? AND review_state IN "
                "('quarantined', 'rejected', 'revoked') ORDER BY created_at, candidate_id",
                (candidate_before,),
            ).fetchall()
            candidate_requests = {
                str(candidate_id): [
                    str(row[0])
                    for row in database.execute(
                        "SELECT request_id FROM training_candidate_requests WHERE candidate_id = ?",
                        (candidate_id,),
                    )
                ]
                for candidate_id, _ in candidate_rows
            }
            events = [row for row in event_rows if ("request", str(row[1])) not in active_holds]
            candidates = [
                row
                for row in candidate_rows
                if ("candidate", str(row[0])) not in active_holds
                and not any(
                    ("request", request_id) in active_holds
                    for request_id in candidate_requests[str(row[0])]
                )
            ]
            if apply:
                database.executemany(
                    "DELETE FROM training_events WHERE event_id = ?",
                    [(row[0],) for row in events],
                )
                database.executemany(
                    "DELETE FROM training_candidate_requests WHERE candidate_id = ?",
                    [(row[0],) for row in candidates],
                )
                database.executemany(
                    "DELETE FROM training_review_events WHERE candidate_id = ?",
                    [(row[0],) for row in candidates],
                )
                database.executemany(
                    "DELETE FROM training_candidates WHERE candidate_id = ?",
                    [(row[0],) for row in candidates],
                )
                referenced = {
                    str(row[0])
                    for row in database.execute(
                        "SELECT payload_hash FROM training_events UNION "
                        "SELECT payload_hash FROM training_candidates"
                    )
                }
            else:
                referenced = set()
        if apply:
            for payload_hash in {
                *(str(row[2]) for row in events),
                *(str(row[1]) for row in candidates),
            } - referenced:
                self.objects.delete(payload_hash)
        return {
            "apply": apply,
            "event_count": len(events),
            "candidate_count": len(candidates),
            "held_count": len(event_rows) + len(candidate_rows) - len(events) - len(candidates),
        }

    def packageable_candidates(
        self, *, created_from: str | None = None, created_before: str | None = None
    ) -> list[TrainingCandidate]:
        conditions = ["review_state IN ('approved', 'sanitized', 'scored')"]
        parameters: list[str] = []
        if created_from is not None:
            conditions.append("created_at >= ?")
            parameters.append(created_from)
        if created_before is not None:
            conditions.append("created_at < ?")
            parameters.append(created_before)
        with self._connect() as database:
            rows = database.execute(
                "SELECT payload_hash, review_state FROM training_candidates "
                f"WHERE {' AND '.join(conditions)} ORDER BY rowid",  # noqa: S608
                parameters,
            ).fetchall()
        candidates = [
            TrainingCandidate.model_validate(self.objects.get(row[0])).model_copy(
                update={"review_state": row[1]}
            )
            for row in rows
        ]
        return [
            candidate
            for candidate in candidates
            if candidate.training_eligible
            and not any(self.excluded(item) for item in candidate.source_request_ids)
        ]


def normalized_text(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", json.dumps(value, sort_keys=True).lower()))


def near_duplicate(left: Any, right: Any, threshold: float = 0.9) -> bool:
    # ponytail: O(n²) pair comparison is adequate for weekly batches; use MinHash past 10k items.
    left_tokens = set(normalized_text(left).split())
    right_tokens = set(normalized_text(right).split())
    union = left_tokens | right_tokens
    return bool(union) and len(left_tokens & right_tokens) / len(union) >= threshold


def candidate_from_trace(
    trace: dict[str, Any],
    *,
    repository_policy: RepositoryTrainingPolicy,
    request_opt_out: bool = False,
    user_opt_out: bool = False,
    external_output_permitted: bool = False,
) -> TrainingCandidate:
    request_id = str(trace.get("session_id", ""))
    reasons: list[str] = []
    if trace.get("training_eligibility") != "eligible":
        reasons.append("trace_not_eligible")
    if repository_policy != "training_allowed":
        reasons.append(f"repository_{repository_policy}")
    if request_opt_out or user_opt_out:
        reasons.append("training_opt_out")
    has_external = any(
        invocation.get("role") == "frontier" for invocation in trace.get("agent_invocations", [])
    )
    payload = {
        "objective": trace.get("objective", ""),
        "verified_state": trace.get("verified_state", []),
        "chosen": trace.get("assistant_tool_call") or trace.get("completion_evidence", {}),
    }
    if has_external and not external_output_permitted:
        payload["chosen"] = {"external_output": "excluded", "verdict_only": True}
        reasons.append("external_output_license_unverified")
    content_excluded = any(
        reason in {"training_opt_out", "trace_not_eligible"} or reason.startswith("repository_")
        for reason in reasons
    )
    if content_excluded:
        payload = {
            "objective": "[EXCLUDED]",
            "verified_state": [],
            "chosen": {"content": "excluded_by_policy"},
        }
    sanitized = sanitize(payload)
    successful = trace.get("final_status") == "completed"
    reviewed = trace.get("review_outcome", {}).get("status") == "approved"
    negative = bool(trace.get("failure_classification")) and not successful
    tier: QualityTier = (
        "rejected"
        if reasons
        else "gold"
        if successful and reviewed and trace.get("completion_evidence")
        else "silver"
        if successful
        else "negative"
        if negative
        else "quarantine"
    )
    eligible = not reasons and tier in {"gold", "silver", "negative"}
    return TrainingCandidate(
        candidate_type="repair" if negative else "sft",
        source_request_ids=[request_id],
        role_target="executor",
        messages=[{"role": "user", "content": sanitized.value["objective"]}],
        accepted_answer=sanitized.value["chosen"] if successful else None,
        rejected_answers=[sanitized.value["chosen"]] if negative else [],
        evidence_summary=list(trace.get("completion_evidence", {}).values())
        or list(trace.get("failure_classification", {})),
        quality_labels={
            "task_success": successful,
            "review_status": trace.get("review_outcome", {}).get("status"),
            "iteration_count": trace.get("metrics", {}).get("iteration_count"),
            "failure_classes": sorted(trace.get("failure_classification", {})),
            "unsupported_claim_count": int(
                trace.get("metrics", {}).get("unsupported_claim_count", 0) or 0
            ),
        },
        privacy_labels={
            "secret_redactions": sanitized.secret_redactions,
            "pii_redactions": sanitized.pii_redactions,
        },
        license_labels={"external_output_permitted": external_output_permitted},
        transformations=["sanitized", *reasons],
        review_state="sanitized" if eligible else "rejected",
        quality_tier=tier,
        training_eligible=eligible,
    )


def candidates_from_trace(
    trace: dict[str, Any],
    *,
    repository_policy: RepositoryTrainingPolicy,
    request_opt_out: bool = False,
    user_opt_out: bool = False,
    external_output_permitted: bool = False,
) -> list[TrainingCandidate]:
    base = candidate_from_trace(
        trace,
        repository_policy=repository_policy,
        request_opt_out=request_opt_out,
        user_opt_out=user_opt_out,
        external_output_permitted=external_output_permitted,
    )
    if not base.training_eligible:
        return [base]
    candidates = [base]

    def privacy_labels(cleaned: SanitizationResult) -> dict[str, int]:
        return {
            "secret_redactions": int(base.privacy_labels.get("secret_redactions", 0))
            + cleaned.secret_redactions,
            "pii_redactions": int(base.privacy_labels.get("pii_redactions", 0))
            + cleaned.pii_redactions,
        }

    sources: tuple[tuple[str, str, str, Any], ...] = (
        ("reasoner", "sft", "reasoner_contributions", trace.get("reasoner_contributions", [])),
        ("planner", "sft", "planner_output", trace.get("planner_output", [])),
        (
            "reviewer",
            "review",
            "reviewer_artifacts",
            [item for item in trace.get("agent_artifacts", []) if item.get("role") == "reviewer"],
        ),
        ("executor", "routing", "routing_decisions", trace.get("orchestration_decisions", [])),
        ("executor", "tool_use", "tool_executions", trace.get("tool_executions", [])),
        (
            "executor",
            "skill",
            "skill_selections",
            [
                node.get("payload")
                for node in trace.get("evidence_graph", {}).get("nodes", [])
                if node.get("node_type") == "skill_selection"
            ],
        ),
    )
    for role, candidate_type, transformation, value in sources:
        if not value:
            continue
        cleaned = sanitize(value)
        candidates.append(
            base.model_copy(
                update={
                    "candidate_id": f"cand_{uuid.uuid4().hex}",
                    "candidate_type": candidate_type,
                    "role_target": role,
                    "accepted_answer": cleaned.value,
                    "rejected_answers": [],
                    "privacy_labels": privacy_labels(cleaned),
                    "transformations": [*base.transformations, transformation],
                }
            )
        )
    loop = trace.get("engineering_loop")
    if isinstance(loop, dict) and loop:
        cleaned = sanitize(loop)
        candidates.append(
            base.model_copy(
                update={
                    "candidate_id": f"cand_{uuid.uuid4().hex}",
                    "candidate_type": "loop",
                    "accepted_answer": cleaned.value,
                    "rejected_answers": [],
                    "evidence_summary": list(loop.get("observed_evidence_ids", []))
                    or base.evidence_summary,
                    "privacy_labels": privacy_labels(cleaned),
                    "transformations": [*base.transformations, "loop_state_transition"],
                }
            )
        )
    failures = trace.get("failures", [])
    grounded_success = (
        base.quality_labels.get("task_success") is True
        and bool(trace.get("completion_evidence"))
        and base.accepted_answer is not None
    )
    if grounded_success and isinstance(failures, list) and failures:
        cleaned = sanitize(failures)
        candidates.append(
            base.model_copy(
                update={
                    "candidate_id": f"cand_{uuid.uuid4().hex}",
                    "candidate_type": "preference",
                    "accepted_answer": base.accepted_answer,
                    "rejected_answers": [cleaned.value],
                    "privacy_labels": privacy_labels(cleaned),
                    "transformations": [*base.transformations, "failed_repair_preference"],
                }
            )
        )
    return candidates


class TrainingCollector:
    def __init__(
        self,
        training_store: TrainingStore,
        operational_store: StateStore,
        *,
        external_output_permitted: bool = False,
    ):
        self.training_store = training_store
        self.operational_store = operational_store
        self.external_output_permitted = external_output_permitted
        self.metrics = {
            "events": 0,
            "candidates": 0,
            "excluded": 0,
            "failures": 0,
            "secret_redactions": 0,
            "privacy_exclusions": 0,
            "license_exclusions": 0,
        }

    def collect(self, trace: dict[str, Any]) -> None:
        request_id = str(trace.get("session_id", ""))
        try:
            metrics = trace.get("metrics", {})
            repository_policy: RepositoryTrainingPolicy = trace.get(
                "repository_training_policy", metrics.get("repository_training_policy", "unknown")
            )
            repository_identity = trace.get("repository_identity", {})
            if isinstance(repository_identity, dict) and self.training_store.repository_excluded(
                repository_identity
            ):
                repository_policy = "training_denied"
            subject_hash = metrics.get("training_subject_hash")
            persistent_user_opt_out = self.training_store.user_excluded(
                str(subject_hash) if subject_hash else None
            )
            candidates = candidates_from_trace(
                trace,
                repository_policy=repository_policy,
                request_opt_out=bool(metrics.get("training_opt_out")),
                user_opt_out=bool(metrics.get("user_training_opt_out")) or persistent_user_opt_out,
                external_output_permitted=self.external_output_permitted,
            )
            candidate = candidates[0]
            if self.training_store.excluded(request_id):
                self.metrics["excluded"] += 1
                return
            input_ref = (
                self.training_store.objects.put(candidate.messages)
                if candidate.training_eligible
                else None
            )
            output_ref = (
                self.training_store.objects.put(
                    {
                        "accepted": candidate.accepted_answer,
                        "rejected": candidate.rejected_answers,
                    }
                )
                if candidate.training_eligible
                else None
            )
            for invocation in trace.get("agent_invocations", []):
                role = str(invocation.get("role", "unknown"))
                model = trace.get("model_revisions", {}).get(role, {})
                event = TrainingEvent(
                    request_id=request_id,
                    task_id=str(trace.get("task_id", request_id)),
                    loop_id=str(metrics.get("engineering_loop_id", "")),
                    role=role,
                    event_type="agent_output",
                    model_provider="external" if role == "frontier" else "local",
                    model_identifier=str(model.get("repository", role)),
                    model_revision=str(model.get("revision", "unknown")),
                    prompt_template_version="controller-v2",
                    policy_version=str(metrics.get("policy_version", "none")),
                    skill_versions=list(metrics.get("skill_versions", [])),
                    input_ref=input_ref,
                    output_ref=output_ref,
                    evidence_ids=[
                        str(node.get("node_id"))
                        for node in trace.get("evidence_graph", {}).get("nodes", [])[-32:]
                    ],
                    latency_ms=invocation.get("latency_ms"),
                    input_tokens=invocation.get("prompt_tokens"),
                    output_tokens=invocation.get("completion_tokens"),
                    estimated_cost=invocation.get("cost_usd"),
                    status=str(invocation.get("status", "unknown")),
                    privacy_class="internal",
                    training_eligibility=(
                        "eligible" if candidate.training_eligible else "excluded"
                    ),
                )
                self.training_store.append_event(event)
                self.metrics["events"] += 1
            for item in candidates:
                secret_redactions = int(item.privacy_labels.get("secret_redactions", 0))
                pii_redactions = int(item.privacy_labels.get("pii_redactions", 0))
                self.metrics["secret_redactions"] += secret_redactions
                if not item.training_eligible and (secret_redactions or pii_redactions):
                    self.metrics["privacy_exclusions"] += 1
                if "external_output_license_unverified" in item.transformations:
                    self.metrics["license_exclusions"] += 1
                if self.training_store.append_candidate(item):
                    self.metrics["candidates"] += 1
            if not candidate.training_eligible:
                self.metrics["excluded"] += 1
        except (OSError, ValueError, PermissionError, sqlite3.Error) as error:
            self.metrics["failures"] += 1
            self.operational_store.event(
                request_id,
                "training_collection_failed",
                {"failure_class": type(error).__name__},
            )
