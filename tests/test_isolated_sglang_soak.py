from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "soak-isolated-sglang.py"
SPEC = importlib.util.spec_from_file_location("isolated_sglang_soak", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def runtime_snapshot() -> dict[str, Any]:
    return {
        "containers": {
            "executor": {
                "available": True,
                "status": "running",
                "oom_killed": False,
                "memory": {"memory_current_bytes": 64_000_000_000},
            },
            "specialist": {
                "available": True,
                "status": "running",
                "oom_killed": False,
                "memory": {"memory_current_bytes": 38_000_000_000},
            },
        },
        "gpu": ["GPU-0, 64000, 122880"],
        "memory": {
            "memavailable_kib": 20_000_000,
            "swaptotal_kib": 16_000_000,
            "swapfree_kib": 15_000_000,
        },
    }


def test_soak_cycle_runs_both_roles_concurrently_without_retaining_payloads(
    monkeypatch,
) -> None:
    def fake_post(
        _url: str, payload: dict[str, Any], _timeout: float
    ) -> tuple[dict[str, Any], float]:
        marker = payload["messages"][0]["content"].rsplit("Reply exactly: ", 1)[1]
        return {
            "choices": [{"message": {"content": marker}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 5,
                "total_tokens": 105,
                "prompt_tokens_details": {"cached_tokens": 80},
            },
        }, 0.25

    monkeypatch.setattr(MODULE.RUNTIME, "post_json", fake_post)
    monkeypatch.setattr(MODULE.RUNTIME, "runtime_snapshot", runtime_snapshot)

    cycle = MODULE.run_cycle(
        "http://127.0.0.1:18101",
        "http://127.0.0.1:18102",
        2,
        1,
        "private shared prefix",
        1,
    )

    assert len(cycle["requests"]) == 4
    assert {request["role"] for request in cycle["requests"]} == {
        "executor",
        "specialist",
    }
    assert all(request["status"] == "passed" for request in cycle["requests"])
    rendered = json.dumps(cycle)
    assert "private shared prefix" not in rendered
    assert "SOAK_EXECUTOR" not in rendered


def test_soak_evidence_is_durable_and_summary_fails_closed(tmp_path: Path) -> None:
    evidence = tmp_path / "soak.jsonl"
    header = {
        "type": "header",
        "duration_target_seconds": 10,
        "providers": {"executor": {"provider": "sglang"}},
    }
    passed_cycle = {
        "type": "cycle",
        "elapsed_seconds": 10,
        "requests": [
            {"status": "passed", "latency_seconds": 1.0},
            {"status": "passed", "latency_seconds": 2.0},
        ],
        "runtime": runtime_snapshot(),
    }
    MODULE.append_event(evidence, header, create=True)
    MODULE.append_event(evidence, passed_cycle)
    MODULE.append_event(
        evidence,
        {
            "type": "footer",
            "finished_at": "2026-07-26T00:00:10+00:00",
            "interrupted": False,
        },
    )

    events = MODULE.load_events(evidence)
    passed = MODULE.summarize(events)

    assert passed["passed"] is True
    assert passed["requests"] == 2
    assert passed["cached_tokens_total"] == 0
    assert passed["maximum_container_memory_bytes"]["executor"] == 64_000_000_000
    assert passed["minimum_memavailable_kib"] == 20_000_000
    assert evidence.stat().st_mode & 0o777 == 0o600

    failed_cycle = {
        **passed_cycle,
        "requests": [{"status": "failed", "failure": "request_failed"}],
    }
    footer = {
        "type": "footer",
        "finished_at": "2026-07-26T00:00:10+00:00",
        "interrupted": False,
    }
    failed = MODULE.summarize([header, failed_cycle, footer])
    assert failed["passed"] is False
    assert failed["request_failures"] == 1

    oom_cycle = {
        **passed_cycle,
        "runtime": {
            **runtime_snapshot(),
            "containers": {
                **runtime_snapshot()["containers"],
                "executor": {
                    "available": True,
                    "status": "exited",
                    "oom_killed": True,
                },
            },
        },
    }
    oom = MODULE.summarize([header, oom_cycle, footer])
    assert oom["passed"] is False
    assert oom["runtime_failure_or_oom"] is True

    truncated = MODULE.summarize([header, passed_cycle])
    assert truncated["passed"] is False
    assert truncated["completed"] is False

    invalid_header = {**header, "duration_target_seconds": 0}
    with pytest.raises(ValueError, match="duration target"):
        MODULE.summarize([invalid_header, passed_cycle, footer])
