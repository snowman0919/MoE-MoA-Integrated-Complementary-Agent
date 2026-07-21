from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dgx_moa.skills import RuntimeSkill, SkillProvenance, SkillRegistry, SkillValidation
from dgx_moa.training import TrainingCandidate
from dgx_moa.weekly import (
    ArchiveRegistry,
    CronSchedule,
    WeeklyPackager,
    prepare_candidates,
    previous_complete_week,
    sha256,
    weekly_skill_report,
)


def candidate() -> TrainingCandidate:
    return TrainingCandidate(
        candidate_type="sft",
        source_request_ids=["request-1"],
        role_target="executor",
        messages=[{"role": "user", "content": "synthetic task"}],
        accepted_answer="synthetic answer",
        evidence_summary=["test-1"],
        review_state="approved",
        quality_tier="gold",
        training_eligible=True,
    )


def runtime_skill(skill_id: str, procedure: list[str]) -> RuntimeSkill:
    return RuntimeSkill(
        skill_id=skill_id,
        version="1.0.0",
        name=skill_id,
        description="Synthetic weekly Skill",
        source="core",
        state="active",
        store="core",
        procedure=procedure,
        provenance=SkillProvenance(source="human", created_by="test", approval_id="a-1"),
        validation=SkillValidation(status="passed", evidence_ids=["test-1"]),
    )


def fake_7z(path: Path, *, fail_test: bool = False) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "command = sys.argv[1]\n"
        "archive = next(pathlib.Path(x) for x in sys.argv[2:] "
        "if x.endswith(('.tmp', '.7z')))\n"
        "if command == 'a': archive.write_bytes(b'synthetic-7z')\n"
        f"if command == 't' and {fail_test!r}: raise SystemExit(2)\n"
        "raise SystemExit(0 if archive.exists() else 3)\n"
    )
    path.chmod(0o700)
    return path


def test_previous_week_is_complete_monday_to_monday_in_seoul() -> None:
    window = previous_complete_week(datetime(2026, 7, 22, 12, tzinfo=UTC))

    assert window.week == "2026-W29"
    assert window.local_start.isoformat() == "2026-07-13T00:00:00+09:00"
    assert window.local_end.isoformat() == "2026-07-20T00:00:00+09:00"
    assert window.utc_start.isoformat() == "2026-07-12T15:00:00+00:00"
    assert window.utc_end.isoformat() == "2026-07-19T15:00:00+00:00"


def test_weekly_cron_uses_configured_seoul_calendar_and_rejects_unsupported_syntax() -> None:
    current = datetime(2026, 7, 22, 12, tzinfo=UTC)

    assert CronSchedule.parse("0 3 * * 0").next_after(current, "Asia/Seoul").isoformat() == (
        "2026-07-26T03:00:00+09:00"
    )
    assert CronSchedule.parse("0 2 * * 1").next_after(current, "Asia/Seoul").isoformat() == (
        "2026-07-27T02:00:00+09:00"
    )
    with pytest.raises(ValueError, match="one bounded integer"):
        CronSchedule.parse("0 25 * * 1")


def test_package_tree_contains_manifest_reports_checksums_and_role_data(tmp_path: Path) -> None:
    packager = WeeklyPackager(tmp_path / "final", ArchiveRegistry(tmp_path / "registry.db"))
    directory = tmp_path / "package"
    window = previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC))

    packager._write_package(
        directory, [candidate()], window, "abcdef1", "policy-1", "skills-1", {}, {}
    )

    manifest = json.loads((directory / "MANIFEST.json").read_text())
    assert manifest["window"]["timezone"] == "Asia/Seoul"
    assert manifest["dataset_counts"] == {"datasets/sft/executor.jsonl": 1}
    assert (directory / "datasets/sft/executor.jsonl").read_text().count("candidate_id") == 1
    assert (directory / "quarantine/metadata-only.jsonl").read_text() == ""
    assert "candidate_id" in (directory / "indices/candidate-index.jsonl").read_text()
    assert "request-1" in (directory / "indices/request-index.jsonl").read_text()
    assert json.loads((directory / "reports/data-quality.json").read_text())["candidate_count"] == 1
    assert "MANIFEST.json" in (directory / "CHECKSUMS.sha256").read_text()


def test_verified_archive_publication_is_atomic_and_idempotent(tmp_path: Path) -> None:
    executable = fake_7z(tmp_path / "7zz")
    registry = ArchiveRegistry(tmp_path / "registry.db")
    notifications: list[tuple[str, dict[str, object]]] = []
    packager = WeeklyPackager(
        tmp_path / "weekly",
        registry,
        seven_zip=str(executable),
        notifier=lambda event, payload: notifications.append((event, payload)),
    )
    window = previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC))
    arguments = {
        "window": window,
        "production_commit": "abcdef123",
        "policy_version": "policy-1",
        "skill_registry_version": "skills-1",
        "model_configuration": {"executor": "abc"},
    }

    first = packager.package([candidate()], **arguments)
    second = packager.package([candidate()], **arguments)
    with pytest.raises(FileExistsError, match="another source snapshot"):
        packager.package(
            [candidate().model_copy(update={"accepted_answer": "different synthetic answer"})],
            **arguments,
        )

    archive = Path(first["archive_path"])
    assert archive.is_file()
    assert sha256(archive) == first["archive_sha256"]
    assert archive.with_suffix(".7z.sha256").is_file()
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert notifications == [
        (
            "weekly_package_completed",
            {
                "package_id": "moa-finetune-2026-W29",
                "candidate_count": 1,
                "storage_location_identifier": archive.relative_to(tmp_path / "weekly").as_posix(),
                "checksum": first["archive_sha256"],
                "verification_status": "verified",
            },
        )
    ]
    assert packager.metrics["packages_created"] == 1
    assert packager.metrics["package_bytes"] == archive.stat().st_size
    external_summary = json.loads((archive.parent / "weekly-summary.json").read_text())
    assert external_summary["archive"]["verified"] is True
    assert external_summary["archive"]["sha256"] == first["archive_sha256"]


def test_weekly_package_verify_revoke_and_explicit_regeneration(tmp_path: Path) -> None:
    executable = fake_7z(tmp_path / "7zz")
    registry = ArchiveRegistry(tmp_path / "registry.db")
    packager = WeeklyPackager(tmp_path / "weekly", registry, seven_zip=str(executable))
    arguments = {
        "window": previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC)),
        "production_commit": "abcdef123",
        "policy_version": "policy-1",
        "skill_registry_version": "skills-1",
        "model_configuration": {},
    }
    created = packager.package([candidate()], **arguments)

    verified = packager.verify(created["idempotency_key"])
    assert verified["verified"] is True
    revoked = registry.revoke(created["idempotency_key"], "synthetic deletion request")
    assert revoked["status"] == "revoked"
    with pytest.raises(PermissionError, match="explicit regeneration"):
        packager.package([candidate()], **arguments)

    regenerated = packager.regenerate(created["idempotency_key"], [candidate()])
    assert regenerated["status"] == "completed"
    assert regenerated["supersedes_idempotency_key"] == created["idempotency_key"]
    assert packager.verify(created["idempotency_key"])["verified"] is True


def test_weekly_archive_retention_is_dry_run_first_and_hold_aware(tmp_path: Path) -> None:
    executable = fake_7z(tmp_path / "7zz")
    registry = ArchiveRegistry(tmp_path / "registry.db")
    packager = WeeklyPackager(tmp_path / "weekly", registry, seven_zip=str(executable))
    created = packager.package(
        [candidate()],
        window=previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC)),
        production_commit="abcdef123",
        policy_version="policy-1",
        skill_registry_version="skills-1",
        model_configuration={},
    )
    hold_id = registry.place_hold(
        created["idempotency_key"], kind="preservation", reason="synthetic hold"
    )

    held = packager.purge_retention("9999-01-01T00:00:00+00:00")
    assert held["package_count"] == 0
    registry.release_hold(hold_id)
    dry_run = packager.purge_retention("9999-01-01T00:00:00+00:00")
    assert dry_run["package_count"] == 1
    assert Path(created["archive_path"]).is_file()

    applied = packager.purge_retention("9999-01-01T00:00:00+00:00", apply=True)
    assert applied | {"apply": False} == dry_run
    assert not Path(created["archive_path"]).exists()
    assert registry.get(created["idempotency_key"])["status"] == "retention_deleted"  # type: ignore[index]


def test_failed_archive_verification_never_publishes_final_name(tmp_path: Path) -> None:
    executable = fake_7z(tmp_path / "7zz", fail_test=True)
    registry = ArchiveRegistry(tmp_path / "registry.db")
    packager = WeeklyPackager(tmp_path / "weekly", registry, seven_zip=str(executable))
    window = previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC))

    with pytest.raises(subprocess.CalledProcessError):
        packager.package(
            [],
            window=window,
            production_commit="abcdef123",
            policy_version="policy-1",
            skill_registry_version="skills-1",
            model_configuration={},
        )

    assert list((tmp_path / "weekly").rglob("*.7z")) == []
    assert list((tmp_path / "weekly").rglob("*.tmp")) == []


def test_packager_fails_closed_without_7z_or_safe_encryption(tmp_path: Path) -> None:
    packager = WeeklyPackager(
        tmp_path / "weekly", ArchiveRegistry(tmp_path / "registry.db"), seven_zip=None
    )
    packager.seven_zip = None
    window = previous_complete_week(datetime(2026, 7, 22, tzinfo=UTC))

    with pytest.raises(FileNotFoundError, match="7zz or 7z"):
        packager.package(
            [],
            window=window,
            production_commit="abc",
            policy_version="1",
            skill_registry_version="1",
            model_configuration={},
        )
    packager.seven_zip = "unused"
    with pytest.raises(ValueError, match="password input"):
        packager.package(
            [],
            window=window,
            production_commit="abc",
            policy_version="1",
            skill_registry_version="1",
            model_configuration={},
            encrypted=True,
        )


def test_weekly_skill_report_recommends_without_automatic_deletion(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path / "skills")
    valuable = runtime_skill("valuable-skill", ["run tests", "fix failure"])
    regressed = runtime_skill("regressed-skill", ["run tests", "fix failure"])
    registry.put(valuable)
    registry.put(regressed)
    for _ in range(5):
        registry.record_outcome(valuable.skill_id, valuable.version, "selected")
        registry.record_outcome(valuable.skill_id, valuable.version, "succeeded")
    registry.record_outcome(regressed.skill_id, regressed.version, "selected")
    registry.record_outcome(regressed.skill_id, regressed.version, "regression")

    notifications: list[tuple[str, dict[str, object]]] = []
    report = weekly_skill_report(
        registry,
        tmp_path / "report",
        notifier=lambda event, payload: notifications.append((event, payload)),
    )

    assert report["highest_value"][0]["skill_id"] == "valuable-skill"
    assert report["lowest_value"][0]["skill_id"] == "regressed-skill"
    assert report["automatically_performed"] == []
    assert report["recommended_actions"][0]["requires_approval"] is True
    regressed_row = next(row for row in report["skills"] if row["skill_id"] == "regressed-skill")
    assert {"duplicate_candidate", "merge_candidate", "update_candidate"}.issubset(
        regressed_row["classifications"]
    )
    assert report["candidate_updates"][0]["skill_id"] == "regressed-skill"
    assert (tmp_path / "report/weekly-skill-report.json").is_file()
    assert (tmp_path / "report/weekly-skill-report.md").is_file()
    assert notifications[0][0] == "weekly_skill_report_completed"
    assert notifications[0][1]["skill_count"] == 2


def test_weekly_candidate_gate_rejects_sensitive_or_ineligible_and_deduplicates() -> None:
    first = candidate()
    exact = first.model_copy(update={"candidate_id": "cand_exact"})
    near = first.model_copy(
        update={"candidate_id": "cand_near", "accepted_answer": "synthetic answer!"}
    )

    accepted, counts = prepare_candidates([first, exact, near])

    assert len(accepted) == 1
    assert counts == {"exact_removed": 1, "near_removed": 1}
    with pytest.raises(ValueError, match="ineligible"):
        prepare_candidates([first.model_copy(update={"training_eligible": False})])
    with pytest.raises(ValueError, match="privacy rescan"):
        prepare_candidates(
            [first.model_copy(update={"accepted_answer": "api_key=syntheticSecret1234567890"})]
        )
    with pytest.raises(ValueError, match="tool_call_result_mismatch"):
        prepare_candidates(
            [
                first.model_copy(
                    update={
                        "expected_tool_calls": [{"id": "call-1"}],
                        "tool_results": [{"tool_call_id": "call-2"}],
                    }
                )
            ]
        )
