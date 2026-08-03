from __future__ import annotations

import json
import signal
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from dgx_moa import isolated_sglang_soak as MODULE

SCRIPT = Path(MODULE.__file__)


def test_soak_defaults_to_continuous_performance_load() -> None:
    source = SCRIPT.read_text()
    assert 'run.add_argument("--interval-seconds", type=positive_float, default=1)' in source


def test_soak_records_the_stop_signal_for_future_attempts() -> None:
    try:
        MODULE.request_stop(signal.SIGTERM, None)
        assert MODULE.STOP_REQUESTED is True
        assert MODULE.STOP_SIGNAL == signal.SIGTERM
    finally:
        MODULE.STOP_REQUESTED = False
        MODULE.STOP_SIGNAL = None


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


def test_soak_cycle_runs_both_roles_concurrently_without_retaining_payloads() -> None:
    specialist_payloads: list[dict[str, Any]] = []

    def fake_post(
        _url: str, payload: dict[str, Any], _timeout: float
    ) -> tuple[dict[str, Any], float]:
        if payload["model"] == MODULE.SPECIALIST_MODEL:
            specialist_payloads.append(payload)
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

    backend = replace(
        MODULE.RUNTIME.validation_backend(),
        post_json=fake_post,
        runtime_snapshot=runtime_snapshot,
    )

    cycle = MODULE.run_cycle(
        "http://127.0.0.1:18101",
        "http://127.0.0.1:18102",
        2,
        1,
        "private shared prefix",
        1,
        backend=backend,
    )

    assert len(cycle["requests"]) == 4
    assert {request["role"] for request in cycle["requests"]} == {
        "executor",
        "specialist",
    }
    assert all(request["status"] == "passed" for request in cycle["requests"])
    assert specialist_payloads[0]["max_tokens"] == 32
    assert specialist_payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}
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
    assert passed["cache_by_role"] == {}
    assert passed["maximum_container_memory_bytes"]["executor"] == 64_000_000_000
    assert passed["minimum_memavailable_kib"] == 20_000_000
    assert passed["memory_headroom_passed"] is True
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

    low_memory = runtime_snapshot()
    low_memory["memory"]["memavailable_kib"] = MODULE.RUNTIME.MINIMUM_AVAILABLE_MEMORY_KIB - 1
    memory_failed = MODULE.summarize([{**header}, {**passed_cycle, "runtime": low_memory}, footer])
    assert memory_failed["passed"] is False
    assert memory_failed["memory_headroom_passed"] is False

    truncated = MODULE.summarize([header, passed_cycle])
    assert truncated["passed"] is False
    assert truncated["completed"] is False

    invalid_header = {**header, "duration_target_seconds": 0}
    with pytest.raises(ValueError, match="duration target"):
        MODULE.summarize([invalid_header, passed_cycle, footer])


def test_soak_reports_cache_reuse_per_role() -> None:
    header = {"type": "header", "duration_target_seconds": 1}
    cycle = {
        "type": "cycle",
        "elapsed_seconds": 1,
        "requests": [
            {"role": "executor", "status": "passed", "cached_tokens": 8192},
            {"role": "specialist", "status": "passed", "cached_tokens": 5000},
        ],
        "runtime": runtime_snapshot(),
    }
    footer = {
        "type": "footer",
        "finished_at": "2026-07-27T00:00:01+00:00",
        "interrupted": False,
    }

    result = MODULE.summarize([header, cycle, footer])

    assert result["cache_by_role"]["executor"]["positive_requests"] == 1
    assert result["cache_by_role"]["executor"]["cached_tokens_total"] == 8192
    assert result["cache_by_role"]["specialist"]["positive_requests"] == 1
