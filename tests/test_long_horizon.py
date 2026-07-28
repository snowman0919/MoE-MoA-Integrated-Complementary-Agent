from __future__ import annotations

import json
from pathlib import Path

import pytest
from dgx_moa import long_horizon_analysis as MODULE

HASH = "a" * 64


def write_evidence(
    path: Path,
    *,
    protocol: str = MODULE.PROTOCOL,
    phases: tuple[str, ...] = MODULE.PHASES,
) -> None:
    header = {
        "type": "header",
        "protocol": protocol,
        "variant": "V1",
        "started_at_epoch": 1_000_000,
        "expected_checkpoints": len(phases),
        "checkpoint_interval_seconds": 0,
        "client_path": "codex",
        "gateway_path": "authenticated_loopback",
        "baseline_commit": "a" * 40,
        **{field: HASH for field in MODULE.STABLE_HASHES},
    }
    checkpoints = []
    for index in range(len(phases)):
        checkpoints.append(
            {
                "type": "checkpoint",
                "index": index,
                "phase_index": index,
                "phase": phases[index],
                "scheduled_at_epoch": 1_000_000,
                "completed_at_epoch": 1_000_030 + index * 30,
                "latency_seconds": 30,
                "next_action_sha256": HASH,
                "context_summary_sha256": HASH,
                "evidence_sha256": HASH,
                "commit": f"{index + 1:040x}",
                "dirty_state": "clean",
                "provider_pinned": True,
                "provider_provenance": [
                    {"role": role, "provider": "local", "model": "candidate"}
                    for role in ("reasoner", "executor", "planner", "reviewer")
                ],
                "context_tokens": 10_000,
                "cached_tokens": 1_000 if index else 0,
                "tool_calls": 3,
                "retries": 0,
                "provider_errors": 0,
                "unjustified_repeated_reads": 0,
                "peak_memory_bytes": 64_000_000_000,
                "swap_delta_bytes": 0,
                "variable_cost_usd": 0,
                "intentional_reconnect": index == len(phases) // 2,
                "premature_completion": False,
                "terminal": True,
                **{field: HASH for field in MODULE.STABLE_HASHES},
            }
        )
    final = {
        "type": "final",
        "completed_at_epoch": 1_000_630,
        "implementation_evidence": True,
        "implementation_commit": f"{len(phases):040x}",
        "implementation_sha256": HASH,
        "review_sha256": HASH,
        "validation_sha256": HASH,
        "review_status": "approved",
        "validation_exit": 0,
        "terminal": True,
        "unresolved_critical_findings": 0,
        "task_outcome": "completed",
        **{field: HASH for field in MODULE.STABLE_HASHES},
    }
    path.write_text("\n".join(json.dumps(item) for item in [header, *checkpoints, final]) + "\n")


def test_long_horizon_analyzer_accepts_complete_pinned_sustained_goal(tmp_path: Path) -> None:
    evidence = tmp_path / "long.jsonl"
    write_evidence(evidence)

    result = MODULE.analyze(evidence)

    assert result["passed"] is True
    assert result["checkpoints"] == MODULE.CHECKPOINTS
    assert result["scheduled_duration_seconds"] == 0
    assert result["intentional_reconnects"] == 1
    assert result["variable_cost_usd"] == 0


def test_long_horizon_analyzer_accepts_avatarforge_profile(tmp_path: Path) -> None:
    evidence = tmp_path / "avatarforge.jsonl"
    write_evidence(
        evidence,
        protocol=MODULE.AVATARFORGE_PROTOCOL,
        phases=MODULE.AVATARFORGE_PHASES,
    )

    result = MODULE.analyze(evidence)

    assert result["passed"] is True
    assert result["protocol"] == MODULE.AVATARFORGE_PROTOCOL
    assert result["checkpoints"] == len(MODULE.AVATARFORGE_PHASES)


def test_long_horizon_analyzer_accepts_bounded_variable_cost(tmp_path: Path) -> None:
    evidence = tmp_path / "long.jsonl"
    write_evidence(evidence)
    rows = [json.loads(line) for line in evidence.read_text().splitlines()]
    rows[1]["variable_cost_usd"] = 1.25
    evidence.write_text("\n".join(map(json.dumps, rows)) + "\n")

    result = MODULE.analyze(evidence)

    assert result["passed"] is True
    assert result["variable_cost_usd"] == 1.25
    assert result["variable_cost_budget_usd"] == 10


@pytest.mark.parametrize(
    ("mutation", "failure"),
    (
        (lambda rows: rows.pop(5), "incomplete_checkpoints"),
        (
            lambda rows: rows[2].update(session_sha256="c" * 64),
            "session_sha256_drift",
        ),
        (
            lambda rows: rows[3].update(provider_pinned=False),
            "provider_not_pinned",
        ),
        (
            lambda rows: rows[4].update(unjustified_repeated_reads=1),
            "unjustified_repeated_read",
        ),
        (
            lambda rows: rows[-1].update(terminal=False),
            "missing_terminal",
        ),
        (
            lambda rows: rows[5].update(variable_cost_usd=10.01),
            "variable_cost_budget_exceeded",
        ),
        (lambda rows: rows[5].update(tool_calls=0), "missing_checkpoint_tool_use"),
        (lambda rows: rows[4].update(terminal=False), "missing_checkpoint_terminal"),
        (lambda rows: rows[3].update(phase="wrong"), "phase_contract_drift"),
        (
            lambda rows: [
                row.update(
                    provider_provenance=[
                        item
                        for item in row["provider_provenance"]
                        if item["role"] != "reviewer"
                    ]
                )
                for row in rows[1:-1]
            ],
            "missing_reviewer_role",
        ),
        (
            lambda rows: rows[-1].update(implementation_commit="a" * 40),
            "implementation_commit_unchanged",
        ),
    ),
)
def test_long_horizon_analyzer_fails_closed(
    tmp_path: Path,
    mutation,
    failure: str,
) -> None:
    evidence = tmp_path / "long.jsonl"
    write_evidence(evidence)
    rows = [json.loads(line) for line in evidence.read_text().splitlines()]
    mutation(rows)
    evidence.write_text("\n".join(map(json.dumps, rows)) + "\n")

    result = MODULE.analyze(evidence)

    assert result["passed"] is False
    assert failure in result["failures"]


def test_long_horizon_analyzer_rejects_private_payload_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "long.jsonl"
    write_evidence(evidence)
    rows = [json.loads(line) for line in evidence.read_text().splitlines()]
    rows[1]["raw_prompt"] = "private"
    evidence.write_text("\n".join(map(json.dumps, rows)) + "\n")

    with pytest.raises(ValueError, match="private field"):
        MODULE.analyze(evidence)
