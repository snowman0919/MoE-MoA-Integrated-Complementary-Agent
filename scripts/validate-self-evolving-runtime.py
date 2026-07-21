#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dgx_moa.state import StateStore
from dgx_moa.training import (
    ContentStore,
    TrainingCandidate,
    TrainingCollector,
    TrainingStore,
    assess_candidate,
    candidate_from_trace,
    sanitize,
)
from dgx_moa.weekly import ArchiveRegistry, WeeklyPackager, previous_complete_week, sha256


def candidate(candidate_id: str = "cand_physical") -> TrainingCandidate:
    return TrainingCandidate(
        candidate_id=candidate_id,
        candidate_type="sft",
        source_request_ids=["synthetic-physical-request"],
        role_target="executor",
        messages=[{"role": "user", "content": "Run the synthetic bounded validation"}],
        accepted_answer="Synthetic validated answer",
        evidence_summary=["synthetic-test-exit-0"],
        quality_labels={"task_success": True, "iteration_count": 1},
        review_state="approved",
        quality_tier="gold",
        training_eligible=True,
    )


def trace() -> dict[str, object]:
    return {
        "session_id": "synthetic-physical-request",
        "training_eligibility": "eligible",
        "objective": "Synthetic bounded validation",
        "verified_state": ["synthetic test passed"],
        "completion_evidence": {"tests": "synthetic-test-exit-0"},
        "final_status": "completed",
        "review_outcome": {"status": "approved"},
        "agent_invocations": [],
        "metrics": {"repository_training_policy": "training_allowed"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    seven_zip = shutil.which("7zz") or shutil.which("7z")
    if seven_zip is None:
        raise SystemExit("7zz or 7z is required")

    privacy = sanitize(
        {"authorization": "Bearer synthetic-token", "email": "synthetic@example.invalid"}
    )
    assert privacy.secret_redactions >= 1 and privacy.pii_redactions == 1
    quality = assess_candidate(candidate())
    assert quality.errors == []

    objects = ContentStore(root / "training/objects")
    training = TrainingStore(root / "training/training.db", objects, minimum_free_bytes=0)
    base = candidate()
    assert training.append_candidate(base)
    assert not training.append_candidate(base.model_copy(update={"candidate_id": "cand_exact"}))
    assert training.verify_integrity()["database_ok"] is True
    backup = training.backup(root / "backups/training.db")

    closed_window = previous_complete_week(datetime(2026, 7, 22, 12, tzinfo=UTC))
    assert (
        training.packageable_candidates(
            created_from=closed_window.utc_start.isoformat(),
            created_before=closed_window.utc_end.isoformat(),
        )
        == []
    )

    denied = candidate_from_trace(trace(), repository_policy="training_denied")
    opted_out = candidate_from_trace(
        trace(), repository_policy="training_allowed", user_opt_out=True
    )
    external = candidate_from_trace(
        trace()
        | {
            "agent_invocations": [{"role": "frontier"}],
            "model_revisions": {"frontier": {"revision": "synthetic"}},
        },
        repository_policy="training_allowed",
    )
    assert not denied.training_eligible and not opted_out.training_eligible
    assert "external_output_license_unverified" in external.transformations

    operational = StateStore(root / "capacity/operational.db")
    guarded = TrainingStore(
        root / "capacity/training.db",
        ContentStore(root / "capacity/objects"),
        minimum_free_bytes=10**30,
    )
    collector = TrainingCollector(guarded, operational)
    collector.collect(trace())
    assert collector.metrics["failures"] == 1

    notifications: list[tuple[str, dict[str, object]]] = []
    registry = ArchiveRegistry(root / "archive-registry/weekly.db")
    packager = WeeklyPackager(
        root / "weekly-packages",
        registry,
        seven_zip=seven_zip,
        notifier=lambda event, payload: notifications.append((event, payload)),
    )
    near = base.model_copy(
        update={"candidate_id": "cand_near", "accepted_answer": "Synthetic validated answer!"}
    )
    created = packager.package(
        [base, near],
        window=closed_window,
        production_commit="physical-validation",
        policy_version="physical-policy-v1",
        skill_registry_version="physical-skills-v1",
        model_configuration={"executor": {"revision": "synthetic"}},
    )
    verified = packager.verify(created["idempotency_key"])
    replayed = packager.package(
        [base, near],
        window=closed_window,
        production_commit="physical-validation",
        policy_version="physical-policy-v1",
        skill_registry_version="physical-skills-v1",
        model_configuration={"executor": {"revision": "synthetic"}},
    )
    assert replayed["idempotent_replay"] is True
    registry.revoke(created["idempotency_key"], "synthetic physical revocation")
    regenerated = packager.regenerate(created["idempotency_key"], [base])
    assert packager.verify(regenerated["idempotency_key"])["verified"] is True

    empty_window = previous_complete_week(datetime(2026, 7, 22, 12, tzinfo=UTC) - timedelta(days=7))
    empty = packager.package(
        [],
        window=empty_window,
        production_commit="physical-validation",
        policy_version="physical-policy-v1",
        skill_registry_version="physical-skills-v1",
        model_configuration={},
    )
    empty_archive = Path(str(empty["archive_path"]))
    with empty_archive.open("ab") as stream:
        stream.write(b"synthetic-corruption")
    try:
        packager.verify(empty["idempotency_key"])
    except ValueError:
        pass
    else:
        raise AssertionError("archive verification failure was not detected")

    failed_packager = WeeklyPackager(
        root / "failed-packages",
        ArchiveRegistry(root / "archive-registry/failed.db"),
        seven_zip="/bin/false",
    )
    try:
        failed_packager.package(
            [],
            window=closed_window,
            production_commit="expected-failure",
            policy_version="physical-policy-v1",
            skill_registry_version="physical-skills-v1",
            model_configuration={},
        )
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("archive creation failure was not detected")

    result = {
        "status": "passed",
        "created_at": datetime.now(UTC).isoformat(),
        "seven_zip": subprocess.run([seven_zip, "i"], check=True, capture_output=True, text=True)
        .stdout.splitlines()[1]
        .strip(),
        "archive": {
            "path": created["archive_path"],
            "sha256": sha256(Path(str(regenerated["archive_path"]))),
            "verified": verified["verified"],
            "idempotent_replay": replayed["idempotent_replay"],
            "regenerated": regenerated["status"] == "completed",
        },
        "empty_archive_verification_failure": True,
        "archive_creation_failure": True,
        "late_arrival_excluded": True,
        "capacity_guard_isolated": True,
        "privacy_redactions": {
            "secret": privacy.secret_redactions,
            "pii": privacy.pii_redactions,
        },
        "training_backup": str(backup),
        "notifications": notifications,
        "metrics": packager.metrics,
    }
    (root / "physical-validation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
