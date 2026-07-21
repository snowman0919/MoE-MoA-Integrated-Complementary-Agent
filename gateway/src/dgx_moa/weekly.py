from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from .skills import RuntimeSkill, SkillMetrics, SkillRegistry
from .training import TrainingCandidate, assess_candidate, near_duplicate, sanitize

DATASET_PATHS = (
    "datasets/sft/executor.jsonl",
    "datasets/sft/reasoner.jsonl",
    "datasets/sft/planner.jsonl",
    "datasets/sft/reviewer.jsonl",
    "datasets/preference/executor-preferences.jsonl",
    "datasets/preference/review-preferences.jsonl",
    "datasets/preference/repair-preferences.jsonl",
    "datasets/tool_use/tool-selection.jsonl",
    "datasets/tool_use/tool-calls.jsonl",
    "datasets/tool_use/tool-result-interpretation.jsonl",
    "datasets/routing/agent-routing.jsonl",
    "datasets/routing/frontier-routing.jsonl",
    "datasets/routing/skill-routing.jsonl",
    "datasets/loops/state-transitions.jsonl",
    "datasets/loops/repair-trajectories.jsonl",
    "datasets/loops/termination-decisions.jsonl",
    "datasets/skills/retrieval.jsonl",
    "datasets/skills/usefulness.jsonl",
    "datasets/skills/generation-candidates.jsonl",
    "datasets/skills/revision-candidates.jsonl",
    "datasets/negatives/invalid-structured-output.jsonl",
    "datasets/negatives/failed-tools.jsonl",
    "datasets/negatives/duplicate-repairs.jsonl",
    "datasets/negatives/unsupported-claims.jsonl",
    "indices/request-index.jsonl",
    "indices/candidate-index.jsonl",
    "indices/object-index.jsonl",
    "quarantine/metadata-only.jsonl",
)
REPORTS = (
    "data-quality.json",
    "privacy-report.json",
    "dedup-report.json",
    "skill-usage.json",
    "routing-analysis.json",
    "failure-analysis.json",
)


class WeeklyPackageKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")


class WeeklyPackageRevocationRequest(WeeklyPackageKeyRequest):
    reason: str = Field(min_length=1, max_length=500)


class WeeklyRetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: str = Field(min_length=1, max_length=64)
    apply: bool = False


@dataclass(frozen=True)
class CronSchedule:
    minute: int | None
    hour: int | None
    day: int | None
    month: int | None
    weekday: int | None

    @classmethod
    def parse(cls, value: str) -> CronSchedule:
        fields = value.split()
        if len(fields) != 5:
            raise ValueError("weekly schedule must be a five-field cron expression")
        bounds = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
        parsed: list[int | None] = []
        for field, (minimum, maximum) in zip(fields, bounds, strict=True):
            if field == "*":
                parsed.append(None)
                continue
            if not field.isdigit() or not minimum <= int(field) <= maximum:
                raise ValueError("weekly schedule supports only '*' or one bounded integer")
            parsed.append(int(field))
        return cls(*parsed)

    def next_after(self, current: datetime, timezone: str) -> datetime:
        zone = ZoneInfo(timezone)
        candidate = current.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
        # ponytail: bounded minute scan is fine for two weekly jobs; replace past 370-day schedules.
        for _ in range(370 * 24 * 60):
            cron_weekday = (candidate.weekday() + 1) % 7
            if all(
                expected is None or actual == expected
                for expected, actual in (
                    (self.minute, candidate.minute),
                    (self.hour, candidate.hour),
                    (self.day, candidate.day),
                    (self.month, candidate.month),
                    (self.weekday, cron_weekday),
                )
            ):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError("weekly schedule has no occurrence within 370 days")


class WeeklyScheduler:
    def __init__(
        self,
        *,
        timezone: str,
        skill_schedule: str,
        package_schedule: str,
        skill_job: Callable[[], Awaitable[None]],
        package_job: Callable[[], Awaitable[None]],
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        notifier: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.timezone = timezone
        self.jobs = (
            ("skill", CronSchedule.parse(skill_schedule), skill_job),
            ("package", CronSchedule.parse(package_schedule), package_job),
        )
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleeper = sleeper
        self.notifier = notifier
        self.tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if not self.tasks:
            self.tasks = [
                asyncio.create_task(self._run(name, schedule, job))
                for name, schedule, job in self.jobs
            ]

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def _run(
        self,
        name: str,
        schedule: CronSchedule,
        job: Callable[[], Awaitable[None]],
    ) -> None:
        while True:
            current = self.clock()
            next_run = schedule.next_after(current, self.timezone)
            await self.sleeper(
                max(0.0, (next_run - current.astimezone(next_run.tzinfo)).total_seconds())
            )
            try:
                await job()
            except Exception as error:
                if self.notifier is not None:
                    self.notifier(
                        "weekly_job_failed",
                        {"job": name, "failure_class": type(error).__name__},
                    )


def classify_skill(skill: RuntimeSkill, metrics: SkillMetrics) -> str:
    uses = metrics.selected
    success_rate = metrics.succeeded / uses if uses else 0.0
    if uses == 0:
        return "unused"
    if metrics.regressions or metrics.failed > metrics.succeeded:
        return "deprecation_candidate" if skill.state == "active" else "low_value"
    if uses >= 5 and success_rate >= 0.8 and (metrics.estimated_quality_gain or 0) >= 0:
        return "high_value"
    if success_rate >= 0.6:
        return "useful"
    return "uncertain"


def skill_overlap(left: RuntimeSkill, right: RuntimeSkill) -> float:
    left_tokens = set(" ".join(left.procedure).lower().split())
    right_tokens = set(" ".join(right.procedure).lower().split())
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def weekly_skill_report(
    registry: SkillRegistry,
    output: str | Path,
    *,
    notifier: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    skills = registry.list_skills()
    rows: list[dict[str, Any]] = []
    for skill in skills:
        metrics = registry.metrics(skill.skill_id, skill.version)
        rows.append(
            {
                "skill_id": skill.skill_id,
                "version": skill.version,
                "state": skill.state,
                "classification": classify_skill(skill, metrics),
                "metrics": metrics.model_dump(mode="json"),
            }
        )
    duplicate_groups = [
        [f"{left.skill_id}@{left.version}", f"{right.skill_id}@{right.version}"]
        for index, left in enumerate(skills)
        for right in skills[index + 1 :]
        if skill_overlap(left, right) >= 0.8
    ]
    duplicate_ids = {item for group in duplicate_groups for item in group}
    for row in rows:
        labels = [row["classification"]]
        identity = f"{row['skill_id']}@{row['version']}"
        if identity in duplicate_ids:
            labels.extend(("duplicate_candidate", "merge_candidate"))
        if row["metrics"]["regressions"]:
            labels.append("update_candidate")
        row["classifications"] = labels
    report = {
        "schema_version": "weekly-skill-report-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "skills": rows,
        "highest_value": [row for row in rows if row["classification"] == "high_value"],
        "lowest_value": [
            row for row in rows if row["classification"] in {"low_value", "deprecation_candidate"}
        ],
        "unused": [row for row in rows if row["classification"] == "unused"],
        "duplicate_groups": duplicate_groups,
        "merge_proposals": duplicate_groups,
        "new_candidates": [row for row in rows if row["state"] == "experimental"],
        "candidate_updates": [row for row in rows if "update_candidate" in row["classifications"]],
        "regressions": [row for row in rows if row["metrics"]["regressions"]],
        "recommended_actions": [
            {
                "skill_id": row["skill_id"],
                "action": "review_deprecation",
                "requires_approval": True,
            }
            for row in rows
            if row["classification"] == "deprecation_candidate"
        ],
        "automatically_performed": [],
    }
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "weekly-skill-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    lines = [
        "# Weekly Skill report",
        "",
        f"Skills: {len(rows)}",
        "",
        "| Skill | Class | Uses |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {row['skill_id']}@{row['version']} | {row['classification']} | "
        f"{row['metrics']['selected']} |"
        for row in rows
    )
    (destination / "weekly-skill-report.md").write_text("\n".join(lines) + "\n")
    if notifier is not None:
        notifier(
            "weekly_skill_report_completed",
            {
                "skill_count": len(rows),
                "high_value_count": len(report["highest_value"]),
                "low_value_count": len(report["lowest_value"]),
            },
        )
    return report


@dataclass(frozen=True)
class WeeklyWindow:
    timezone: str
    local_start: datetime
    local_end: datetime
    utc_start: datetime
    utc_end: datetime

    @property
    def week(self) -> str:
        year, week, _ = self.local_start.isocalendar()
        return f"{year}-W{week:02d}"

    def manifest(self) -> dict[str, str]:
        return {
            "timezone": self.timezone,
            "local_start": self.local_start.isoformat(),
            "local_end": self.local_end.isoformat(),
            "utc_start": self.utc_start.isoformat(),
            "utc_end": self.utc_end.isoformat(),
        }


def previous_complete_week(
    reference: datetime | None = None, timezone: str = "Asia/Seoul"
) -> WeeklyWindow:
    zone = ZoneInfo(timezone)
    current = (reference or datetime.now(UTC)).astimezone(zone)
    this_monday = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = this_monday - timedelta(days=7)
    return WeeklyWindow(
        timezone=timezone,
        local_start=start,
        local_end=this_monday,
        utc_start=start.astimezone(UTC),
        utc_end=this_monday.astimezone(UTC),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_path(candidate: TrainingCandidate) -> str:
    if candidate.quality_tier == "negative":
        return "datasets/loops/repair-trajectories.jsonl"
    if candidate.candidate_type == "preference":
        return "datasets/preference/executor-preferences.jsonl"
    if candidate.candidate_type == "tool_use":
        return "datasets/tool_use/tool-calls.jsonl"
    if candidate.candidate_type == "routing":
        return "datasets/routing/agent-routing.jsonl"
    if candidate.candidate_type == "skill":
        return "datasets/skills/retrieval.jsonl"
    return f"datasets/sft/{candidate.role_target}.jsonl"


def prepare_candidates(
    candidates: list[TrainingCandidate],
) -> tuple[list[TrainingCandidate], dict[str, int]]:
    accepted: list[TrainingCandidate] = []
    exact: set[str] = set()
    counts = {"exact_removed": 0, "near_removed": 0}
    for candidate in candidates:
        if not candidate.training_eligible or candidate.review_state not in {
            "sanitized",
            "scored",
            "approved",
        }:
            raise ValueError("weekly package received an ineligible candidate")
        sensitive = sanitize(
            {
                "messages": candidate.messages,
                "accepted_answer": candidate.accepted_answer,
                "rejected_answers": candidate.rejected_answers,
                "tool_results": candidate.tool_results,
            }
        )
        if sensitive.secret_redactions or sensitive.pii_redactions:
            raise ValueError("weekly package candidate failed privacy rescan")
        quality = assess_candidate(candidate)
        if quality.errors:
            raise ValueError("weekly package candidate failed quality gate: " + quality.errors[0])
        candidate = candidate.model_copy(
            update={
                "quality_labels": candidate.quality_labels
                | {"language": quality.language, "quality_score": quality.score}
            }
        )
        content = candidate.model_dump(mode="json") | {"candidate_id": ""}
        fingerprint = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if fingerprint in exact:
            counts["exact_removed"] += 1
            continue
        comparison = {
            "messages": candidate.messages,
            "accepted": candidate.accepted_answer,
            "rejected": candidate.rejected_answers,
        }
        if any(
            near_duplicate(
                comparison,
                {
                    "messages": item.messages,
                    "accepted": item.accepted_answer,
                    "rejected": item.rejected_answers,
                },
            )
            for item in accepted
        ):
            counts["near_removed"] += 1
            continue
        exact.add(fingerprint)
        accepted.append(candidate)
    return accepted, counts


class ArchiveRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS weekly_packages ("
                "idempotency_key TEXT PRIMARY KEY, package_id TEXT NOT NULL, status TEXT NOT NULL, "
                "archive_path TEXT, archive_sha256 TEXT, error_class TEXT, "
                "updated_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS weekly_package_tombstones ("
                "idempotency_key TEXT PRIMARY KEY, package_id TEXT NOT NULL, "
                "reason TEXT NOT NULL, revoked_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS weekly_package_holds ("
                "hold_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL, kind TEXT NOT NULL, "
                "reason TEXT NOT NULL, expires_at TEXT, released_at TEXT, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as database:
            row = database.execute(
                "SELECT package_id, status, archive_path, archive_sha256, error_class, updated_at "
                "FROM weekly_packages WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        keys = (
            "package_id",
            "status",
            "archive_path",
            "archive_sha256",
            "error_class",
            "updated_at",
        )
        return dict(zip(keys, row, strict=True))

    def set(self, key: str, package_id: str, status: str, **values: Any) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO weekly_packages "
                "(idempotency_key, package_id, status, archive_path, archive_sha256, "
                "error_class, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET status=excluded.status, "
                "archive_path=excluded.archive_path, archive_sha256=excluded.archive_sha256, "
                "error_class=excluded.error_class, updated_at=excluded.updated_at",
                (
                    key,
                    package_id,
                    status,
                    values.get("archive_path"),
                    values.get("archive_sha256"),
                    values.get("error_class"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def revoke(self, key: str, reason: str) -> dict[str, Any]:
        if not reason:
            raise ValueError("package revocation requires a reason")
        record = self.get(key)
        if record is None:
            raise KeyError("unknown weekly package")
        with self._connect() as database:
            database.execute(
                "INSERT INTO weekly_package_tombstones "
                "(idempotency_key, package_id, reason, revoked_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET reason=excluded.reason, "
                "revoked_at=excluded.revoked_at",
                (key, record["package_id"], reason, datetime.now(UTC).isoformat()),
            )
            database.execute(
                "UPDATE weekly_packages SET status = 'revoked', updated_at = ? "
                "WHERE idempotency_key = ?",
                (datetime.now(UTC).isoformat(), key),
            )
            database.execute(
                "INSERT OR IGNORE INTO weekly_package_holds "
                "(hold_id, idempotency_key, kind, reason, created_at) "
                "VALUES (?, ?, 'deletion_request', ?, ?)",
                (f"revocation:{key}", key, reason, datetime.now(UTC).isoformat()),
            )
        updated = self.get(key)
        assert updated is not None
        return updated

    def place_hold(
        self,
        key: str,
        *,
        kind: str,
        reason: str,
        expires_at: str | None = None,
    ) -> str:
        if kind not in {"legal", "investigation", "preservation"} or not reason:
            raise ValueError("invalid package retention hold")
        if self.get(key) is None:
            raise KeyError("unknown weekly package")
        hold_id = f"hold_{hashlib.sha256(os.urandom(32)).hexdigest()}"
        with self._connect() as database:
            database.execute(
                "INSERT INTO weekly_package_holds "
                "(hold_id, idempotency_key, kind, reason, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (hold_id, key, kind, reason, expires_at, datetime.now(UTC).isoformat()),
            )
        return hold_id

    def release_hold(self, hold_id: str) -> None:
        with self._connect() as database:
            cursor = database.execute(
                "UPDATE weekly_package_holds SET released_at = ? "
                "WHERE hold_id = ? AND released_at IS NULL",
                (datetime.now(UTC).isoformat(), hold_id),
            )
        if cursor.rowcount != 1:
            raise KeyError("unknown or released package hold")

    def resolve_revocation(self, key: str) -> None:
        with self._connect() as database:
            database.execute(
                "UPDATE weekly_package_holds SET released_at = ? WHERE hold_id = ? "
                "AND released_at IS NULL",
                (datetime.now(UTC).isoformat(), f"revocation:{key}"),
            )

    def retention_candidates(
        self, before: str, *, reference_time: str | None = None
    ) -> list[dict[str, Any]]:
        reference = reference_time or datetime.now(UTC).isoformat()
        with self._connect() as database:
            rows = database.execute(
                "SELECT idempotency_key, package_id, status, archive_path, archive_sha256, "
                "updated_at FROM weekly_packages WHERE updated_at < ? AND status IN "
                "('completed', 'revoked', 'verification_failed') AND idempotency_key NOT IN "
                "(SELECT idempotency_key FROM weekly_package_holds WHERE released_at IS NULL "
                "AND (expires_at IS NULL OR expires_at > ?)) ORDER BY updated_at",
                (before, reference),
            ).fetchall()
        keys = (
            "idempotency_key",
            "package_id",
            "status",
            "archive_path",
            "archive_sha256",
            "updated_at",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def active_archive_paths(self, excluding: frozenset[str]) -> frozenset[str]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT idempotency_key, archive_path FROM weekly_packages "
                "WHERE archive_path IS NOT NULL AND status != 'retention_deleted'"
            ).fetchall()
        return frozenset(
            str(Path(str(path)).resolve()) for key, path in rows if str(key) not in excluding
        )

    def has_revoked_archive_path(self, archive_path: str) -> bool:
        with self._connect() as database:
            return (
                database.execute(
                    "SELECT 1 FROM weekly_packages WHERE archive_path = ? AND status = 'revoked'",
                    (archive_path,),
                ).fetchone()
                is not None
            )


class WeeklyPackager:
    def __init__(
        self,
        root: str | Path,
        registry: ArchiveRegistry,
        *,
        seven_zip: str | None = None,
        notifier: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.root = Path(root)
        self.registry = registry
        self.seven_zip = seven_zip or shutil.which("7zz") or shutil.which("7z")
        self.notifier = notifier
        self.metrics = {
            "packages_created": 0,
            "package_failures": 0,
            "package_bytes": 0,
            "archive_verification_failures": 0,
            "exact_duplicates_removed": 0,
            "near_duplicates_removed": 0,
            "notification_failures": 0,
        }

    def _notify(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.notifier is None:
            return
        try:
            self.notifier(event_type, payload)
        except (OSError, sqlite3.Error):
            self.metrics["notification_failures"] += 1

    def package(
        self,
        candidates: list[TrainingCandidate],
        *,
        window: WeeklyWindow,
        production_commit: str,
        policy_version: str,
        skill_registry_version: str,
        model_configuration: dict[str, Any],
        encrypted: bool = False,
        regenerate: bool = False,
    ) -> dict[str, Any]:
        if encrypted:
            raise ValueError("safe non-command-line 7z password input is unavailable")
        if self.seven_zip is None:
            raise FileNotFoundError("7zz or 7z executable is required")
        candidates, deduplication_counts = prepare_candidates(candidates)
        self.metrics["exact_duplicates_removed"] += deduplication_counts["exact_removed"]
        self.metrics["near_duplicates_removed"] += deduplication_counts["near_removed"]
        source_snapshot = hashlib.sha256(
            json.dumps(
                [
                    candidate.model_dump(mode="json") | {"candidate_id": ""}
                    for candidate in candidates
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        key = hashlib.sha256(
            f"{window.utc_start.isoformat()}|{window.utc_end.isoformat()}|1.0|"
            f"{policy_version}|{source_snapshot}".encode()
        ).hexdigest()
        package_id = f"moa-finetune-{window.week}"
        existing = self.registry.get(key)
        if existing and existing["status"] == "completed":
            archive = Path(str(existing["archive_path"]))
            if archive.is_file() and sha256(archive) == existing["archive_sha256"]:
                return existing | {"idempotency_key": key, "idempotent_replay": True}
        if existing and existing["status"] == "revoked" and not regenerate:
            raise PermissionError("revoked package requires explicit regeneration")
        year, week = window.week.split("-W")
        final_dir = self.root / year / f"W{week}"
        final_dir.mkdir(parents=True, exist_ok=True)

        def stamp(value: datetime) -> str:
            return value.strftime("%Y%m%dT%H%M%SZ")

        short_commit = production_commit[:7] or "unknown"
        name = f"{package_id}_{stamp(window.utc_start)}_{stamp(window.utc_end)}_{short_commit}.7z"
        final_archive = final_dir / name
        if final_archive.exists() and (
            not regenerate or not self.registry.has_revoked_archive_path(str(final_archive))
        ):
            raise FileExistsError(
                "deterministic archive name already belongs to another source snapshot"
            )
        temporary_archive = final_dir / f".{name}.tmp"
        staging = Path(tempfile.mkdtemp(prefix=f".{package_id}-", dir=final_dir))
        package_dir = staging / package_id
        self.registry.set(key, package_id, "staging")
        try:
            self._write_package(
                package_dir,
                candidates,
                window,
                production_commit,
                policy_version,
                skill_registry_version,
                model_configuration,
                deduplication_counts,
            )
            subprocess.run(
                [
                    self.seven_zip,
                    "a",
                    "-t7z",
                    "-m0=lzma2",
                    "-mx=9",
                    "-mmt=on",
                    "-ms=on",
                    str(temporary_archive),
                    str(package_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [self.seven_zip, "t", str(temporary_archive)],
                check=True,
                capture_output=True,
                text=True,
            )
            with temporary_archive.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary_archive, final_archive)
            archive_hash = sha256(final_archive)
            sidecar = final_archive.with_suffix(final_archive.suffix + ".sha256")
            sidecar.write_text(f"{archive_hash}  {final_archive.name}\n")
            manifest = json.loads((package_dir / "MANIFEST.json").read_text())
            manifest["archive"].update(
                sha256=archive_hash,
                size_bytes=final_archive.stat().st_size,
                verified=True,
            )
            (final_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            )
            summary = json.loads((package_dir / "reports/weekly-summary.json").read_text())
            summary["archive"] = {
                "path": str(final_archive.relative_to(self.root)),
                "size_bytes": final_archive.stat().st_size,
                "sha256": archive_hash,
                "verified": True,
            }
            (final_dir / "weekly-summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
            (final_dir / "weekly-summary.md").write_text(
                f"# Weekly summary\n\nCandidates: {summary['eligible_records']}\n"
                f"Archive: {summary['archive']['path']}\n"
                f"SHA-256: {archive_hash}\nVerified: yes\n"
            )
            self.registry.set(
                key,
                package_id,
                "completed",
                archive_path=str(final_archive),
                archive_sha256=archive_hash,
            )
            self.metrics["packages_created"] += 1
            self.metrics["package_bytes"] += final_archive.stat().st_size
            if regenerate:
                self.registry.resolve_revocation(key)
            self._notify(
                "weekly_package_completed",
                {
                    "package_id": package_id,
                    "candidate_count": len(candidates),
                    "storage_location_identifier": str(final_archive.relative_to(self.root)),
                    "checksum": archive_hash,
                    "verification_status": "verified",
                },
            )
            return {
                "package_id": package_id,
                "idempotency_key": key,
                "status": "completed",
                "archive_path": str(final_archive),
                "archive_sha256": archive_hash,
                "idempotent_replay": False,
            }
        except Exception as error:
            temporary_archive.unlink(missing_ok=True)
            self.registry.set(key, package_id, "failed", error_class=type(error).__name__)
            self.metrics["package_failures"] += 1
            if (
                isinstance(error, subprocess.CalledProcessError)
                and len(error.cmd) > 1
                and (error.cmd[1] == "t")
            ):
                self.metrics["archive_verification_failures"] += 1
            self._notify(
                "weekly_package_failed",
                {"package_id": package_id, "failure_class": type(error).__name__},
            )
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def verify(self, idempotency_key: str) -> dict[str, Any]:
        if self.seven_zip is None:
            raise FileNotFoundError("7zz or 7z executable is required")
        record = self.registry.get(idempotency_key)
        if record is None:
            raise KeyError("unknown weekly package")
        if record["status"] != "completed":
            raise ValueError("weekly package is not completed")
        archive = Path(str(record["archive_path"]))
        if not archive.is_file() or sha256(archive) != record["archive_sha256"]:
            self.metrics["archive_verification_failures"] += 1
            self.registry.set(
                idempotency_key,
                str(record["package_id"]),
                "verification_failed",
                archive_path=str(archive),
                archive_sha256=record["archive_sha256"],
                error_class="ChecksumMismatch",
            )
            raise ValueError("weekly package checksum mismatch")
        subprocess.run(
            [self.seven_zip, "t", str(archive)],
            check=True,
            capture_output=True,
            text=True,
        )
        return {
            "package_id": record["package_id"],
            "idempotency_key": idempotency_key,
            "archive_sha256": record["archive_sha256"],
            "verified": True,
        }

    def regenerate(
        self,
        idempotency_key: str,
        candidates: list[TrainingCandidate],
    ) -> dict[str, Any]:
        record = self.registry.get(idempotency_key)
        if record is None:
            raise KeyError("unknown weekly package")
        if record["status"] != "revoked":
            raise ValueError("only a revoked package may be regenerated")
        manifest_path = Path(str(record["archive_path"])).parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        window = self.package_window(idempotency_key)
        regenerated = self.package(
            candidates,
            window=window,
            production_commit=str(manifest["production_commit"]),
            policy_version=str(manifest["policy_version"]),
            skill_registry_version=str(manifest["skill_registry_version"]),
            model_configuration=dict(manifest["model_configuration"]),
            regenerate=True,
        )
        self.registry.resolve_revocation(idempotency_key)
        return regenerated | {"supersedes_idempotency_key": idempotency_key}

    def package_window(self, idempotency_key: str) -> WeeklyWindow:
        record = self.registry.get(idempotency_key)
        if record is None:
            raise KeyError("unknown weekly package")
        manifest_path = Path(str(record["archive_path"])).parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        window_data = manifest["window"]
        return WeeklyWindow(
            timezone=str(window_data["timezone"]),
            local_start=datetime.fromisoformat(window_data["local_start"]),
            local_end=datetime.fromisoformat(window_data["local_end"]),
            utc_start=datetime.fromisoformat(window_data["utc_start"]),
            utc_end=datetime.fromisoformat(window_data["utc_end"]),
        )

    def purge_retention(
        self,
        before: str,
        *,
        apply: bool = False,
        reference_time: str | None = None,
    ) -> dict[str, int | bool]:
        candidates = self.registry.retention_candidates(before, reference_time=reference_time)
        candidate_keys = frozenset(str(item["idempotency_key"]) for item in candidates)
        protected_paths = self.registry.active_archive_paths(candidate_keys)
        removable: list[tuple[dict[str, Any], Path]] = []
        shared_skipped = 0
        root = self.root.resolve()
        for item in candidates:
            archive = Path(str(item["archive_path"])).resolve()
            if not archive.is_relative_to(root):
                raise ValueError("archive registry path escapes package root")
            if str(archive) in protected_paths:
                shared_skipped += 1
                continue
            removable.append((item, archive))
        bytes_total = sum(path.stat().st_size for _, path in removable if path.is_file())
        if apply:
            for item, archive in removable:
                archive.unlink(missing_ok=True)
                archive.with_suffix(archive.suffix + ".sha256").unlink(missing_ok=True)
                self.registry.set(
                    str(item["idempotency_key"]),
                    str(item["package_id"]),
                    "retention_deleted",
                    archive_path=str(archive),
                    archive_sha256=item["archive_sha256"],
                )
        return {
            "apply": apply,
            "package_count": len(removable),
            "bytes": bytes_total,
            "shared_skipped": shared_skipped,
        }

    def _write_package(
        self,
        directory: Path,
        candidates: list[TrainingCandidate],
        window: WeeklyWindow,
        production_commit: str,
        policy_version: str,
        skill_registry_version: str,
        model_configuration: dict[str, Any],
        deduplication_counts: dict[str, int] | None = None,
    ) -> None:
        directory.mkdir(parents=True)
        for relative in DATASET_PATHS:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        for candidate in candidates:
            path = directory / candidate_path(candidate)
            with path.open("a") as stream:
                stream.write(candidate.model_dump_json() + "\n")
        with (directory / "indices/candidate-index.jsonl").open("a") as stream:
            for candidate in candidates:
                stream.write(
                    json.dumps(
                        {
                            "candidate_id": candidate.candidate_id,
                            "candidate_type": candidate.candidate_type,
                            "role_target": candidate.role_target,
                            "quality_tier": candidate.quality_tier,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        with (directory / "indices/request-index.jsonl").open("a") as stream:
            for candidate in candidates:
                for request_id in candidate.source_request_ids:
                    stream.write(
                        json.dumps(
                            {"request_id": request_id, "candidate_id": candidate.candidate_id},
                            sort_keys=True,
                        )
                        + "\n"
                    )
        counts = Counter(candidate_path(candidate) for candidate in candidates)
        tiers = Counter(candidate.quality_tier for candidate in candidates)
        roles = Counter(candidate.role_target for candidate in candidates)
        candidate_types = Counter(candidate.candidate_type for candidate in candidates)
        languages = Counter(
            str(candidate.quality_labels.get("language", "unknown")) for candidate in candidates
        )
        success_count = sum(
            bool(candidate.quality_labels.get("task_success")) for candidate in candidates
        )
        privacy_report = {
            "secret_redactions": sum(
                int(candidate.privacy_labels.get("secret_redactions", 0))
                for candidate in candidates
            ),
            "pii_redactions": sum(
                int(candidate.privacy_labels.get("pii_redactions", 0)) for candidate in candidates
            ),
        }
        manifest = {
            "package_schema_version": "1.0",
            "package_id": f"moa-finetune-{window.week}",
            "window": window.manifest(),
            "created_at": datetime.now(UTC).isoformat(),
            "production_commit": production_commit,
            "policy_version": policy_version,
            "skill_registry_version": skill_registry_version,
            "model_configuration": model_configuration,
            "dataset_counts": dict(counts),
            "quality_tier_counts": dict(tiers),
            "privacy_exclusions": {},
            "license_exclusions": {},
            "deduplication_counts": deduplication_counts or {},
            "source_request_count": len(
                {item for candidate in candidates for item in candidate.source_request_ids}
            ),
            "included_request_count": len(
                {item for candidate in candidates for item in candidate.source_request_ids}
            ),
            "excluded_request_count": 0,
            "archive": {
                "format": "7z",
                "compression": "lzma2",
                "encrypted": False,
                "sha256": None,
                "size_bytes": None,
            },
        }
        (directory / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        (directory / "README.md").write_text(
            f"# {manifest['package_id']}\n\nSanitized role-specific training candidates.\n"
        )
        snapshots = {
            "SCHEMA_VERSIONS.json": {"package": "1.0", "candidate": "current"},
            "POLICY_SNAPSHOT.yaml": {"version": policy_version},
            "SKILL_SNAPSHOT.json": {"version": skill_registry_version},
            "MODEL_SNAPSHOT.json": model_configuration,
        }
        for name, value in snapshots.items():
            (directory / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        reports = directory / "reports"
        reports.mkdir()
        summary = {
            "package_id": manifest["package_id"],
            "request_volume": manifest["source_request_count"],
            "eligible_records": len(candidates),
            "excluded_records": 0,
            "role_distribution": dict(roles),
            "task_type_distribution": dict(candidate_types),
            "language_distribution": dict(languages),
            "agent_participation": dict(roles),
            "skill_participation": candidate_types.get("skill", 0),
            "loop_lengths": [
                candidate.quality_labels.get("iteration_count")
                for candidate in candidates
                if candidate.quality_labels.get("iteration_count") is not None
            ],
            "success_count": success_count,
            "failure_count": len(candidates) - success_count,
            "top_failure_fingerprints": [],
            "repair_success_rate": None,
            "frontier_contribution": roles.get("frontier", 0),
            "reviewer_defect_findings": sum(
                int(candidate.quality_labels.get("reviewer_findings", 0))
                for candidate in candidates
            ),
            "preference_pair_count": candidate_types.get("preference", 0),
            "negative_example_count": tiers.get("negative", 0),
            "quality_tier_distribution": dict(tiers),
            "secret_and_privacy_exclusions": privacy_report,
            "license_exclusions": 0,
            "deduplication": deduplication_counts or {},
            "archive": {"path": None, "size_bytes": None, "sha256": None, "verified": False},
        }
        (reports / "weekly-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        (reports / "weekly-summary.md").write_text(
            f"# Weekly summary\n\nCandidates: {len(candidates)}\n"
        )
        report_payloads = {
            "data-quality.json": {
                "candidate_count": len(candidates),
                "candidate_types": dict(candidate_types),
                "roles": dict(roles),
                "languages": dict(languages),
                "quality_tiers": dict(tiers),
            },
            "privacy-report.json": privacy_report,
            "dedup-report.json": deduplication_counts or {},
            "skill-usage.json": {"candidate_count": candidate_types.get("skill", 0)},
            "routing-analysis.json": {"candidate_count": candidate_types.get("routing", 0)},
            "failure-analysis.json": {"negative_examples": tiers.get("negative", 0)},
        }
        for report in REPORTS:
            (reports / report).write_text(
                json.dumps(report_payloads[report], indent=2, sort_keys=True) + "\n"
            )
        checksum_lines = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "CHECKSUMS.sha256":
                checksum_lines.append(f"{sha256(path)}  {path.relative_to(directory)}")
        (directory / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n")
