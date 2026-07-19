from __future__ import annotations

import json
from pathlib import Path

from dgx_moa import runtime_status
from dgx_moa.config import Limits
from dgx_moa.lifecycle import LifecycleRecord, LifecycleStore, calculate_idle_policy
from dgx_moa.state import StateStore
from dgx_moa.usage import (
    LifecycleSample,
    RequestUsageFinalization,
    RequestUsageStart,
    UsageStore,
)


def test_runtime_report_contains_bounded_content_free_usage(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    state_db = tmp_path / "state.db"
    StateStore(state_db)
    usage = UsageStore(state_db)
    usage.start(
        RequestUsageStart(
            request_id="00000000-0000-4000-8000-000000000001",
            session_id="SENTINEL_RAW_SESSION_83da0f",
            client_class="httpx",
            model_alias="dgx-moa-agent",
            runtime_mode="agent",
            request_class="native_agent_turn",
            roles_required=("executor",),
            accepted_at=100.0,
            streaming=False,
            model_state="warm",
        )
    )
    usage.finalize(
        "00000000-0000-4000-8000-000000000001",
        RequestUsageFinalization(
            first_byte_at=100.5,
            completed_at=101.0,
            status="completed",
            prompt_tokens=2,
            completion_tokens=3,
            total_tokens=5,
        ),
    )
    usage.record_lifecycle_sample(
        LifecycleSample(
            role="executor",
            kind="unload",
            duration_seconds=4.0,
            memory_before_bytes=100,
            memory_after_bytes=200,
        )
    )

    def fake_command(*args: str) -> str:
        if args[0] == "systemctl":
            return "ActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0"
        if args[0] == "git":
            return "abc123"
        return ""

    monkeypatch.setattr(runtime_status, "command", fake_command)
    monkeypatch.setattr(runtime_status, "memory_available", lambda: 300)

    result = runtime_status.report(state_db, tmp_path)

    assert result["usage"] == {
        "last_request": {
            "request_id": "00000000-0000-4000-8000-000000000001",
            "client_class": "httpx",
            "model_alias": "dgx-moa-agent",
            "runtime_mode": "agent",
            "request_class": "native_agent_turn",
            "roles_required": ["executor"],
            "accepted_at": 100.0,
            "first_byte_at": 100.5,
            "completed_at": 101.0,
            "active_duration_seconds": 1.0,
            "status": "completed",
            "streaming": False,
            "model_state": "warm",
            "load_triggered": False,
            "retryable_failure_class": None,
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "total_tokens": 5,
        },
        "active_request_count": 0,
        "request_statistics": {
            "request_count": 1,
            "requests_last_hour": 0,
            "requests_last_day": 0,
            "inter_arrival_gaps_seconds": [],
            "inter_arrival_ewma_seconds": None,
            "inter_arrival_percentiles_seconds": {
                "p50": None,
                "p75": None,
                "p90": None,
                "p95": None,
            },
            "adaptive_policy_samples": {"usable": 0, "minimum": 20, "sufficient": False},
            "role_frequency": {"executor": 1},
            "warm_latency_seconds": {
                "count": 1,
                "mean": 1.0,
                "p50": 1.0,
                "p75": 1.0,
                "p90": 1.0,
                "p95": 1.0,
            },
            "cold_starts": 0,
        },
        "role_statistics": {},
        "role_states": {"executor": "warm"},
        "adaptive_idle_timeout_seconds": None,
        "idle_decisions": {},
        "cold_starts": 0,
        "loading_failures": 0,
        "lifecycle": {
            "load_duration_seconds": {
                "count": 0,
                "mean": None,
                "p50": None,
                "p75": None,
                "p90": None,
                "p95": None,
            },
            "unload_duration_seconds": {
                "count": 1,
                "mean": 4.0,
                "p50": 4.0,
                "p75": 4.0,
                "p90": 4.0,
                "p95": 4.0,
            },
            "samples": [
                {
                    "role": "executor",
                    "kind": "unload",
                    "duration_seconds": 4.0,
                    "memory_before_bytes": 100,
                    "memory_after_bytes": 200,
                }
            ],
        },
    }
    serialized = json.dumps(result, sort_keys=True)
    assert "SENTINEL_RAW_SESSION_83da0f" not in serialized
    assert str(state_db) not in serialized
    assert "systemctl" not in serialized
    assert "dgx-moa-executor.service" not in serialized


def test_runtime_active_count_includes_rows_outside_statistics_window(tmp_path: Path) -> None:
    state_db = tmp_path / "state.db"
    usage = UsageStore(state_db)
    for index in range(513):
        usage.start(
            RequestUsageStart(
                request_id=f"request-{index}",
                session_id=f"session-{index}",
                client_class="openai-compatible",
                model_alias="dgx-moa-agent",
                runtime_mode="agent",
                request_class="native_agent_turn",
                roles_required=("executor",),
                accepted_at=float(index),
                streaming=False,
                model_state="warm",
            )
        )

    assert len(usage.recent_requests()) == 512
    assert runtime_status.usage_status(state_db)["active_request_count"] == 513


def test_runtime_usage_exposes_only_latest_bounded_idle_decisions(tmp_path: Path) -> None:
    state_db = tmp_path / "decision.db"
    store = LifecycleStore(state_db, ("executor",), clock=lambda: 100.0)
    decision = calculate_idle_policy(
        "executor",
        "fixed",
        (),
        LifecycleRecord(
            role="executor",
            state="ready",
            transition_id="4f0d36aa-76b9-4c74-a733-2600ac45c6e1",
            transitioned_at=0.0,
            updated_at=0.0,
            ready_since=0.0,
            last_used_at=0.0,
        ),
        now=100.0,
        limits=Limits(
            executor_idle_minimum_seconds=5,
            executor_idle_fallback_seconds=20,
            executor_idle_maximum_seconds=100,
            executor_minimum_ready_residency_seconds=1,
        ),
    )
    store.persist_decision(decision)

    assert runtime_status.usage_status(state_db)["idle_decisions"] == {}
    result = runtime_status.usage_status(
        state_db,
        lifecycle_mode="fixed",
        managed_roles=("executor",),
    )

    assert result["adaptive_idle_timeout_seconds"] == 20.0
    assert result["idle_decisions"] == {
        "executor": decision.model_dump(mode="json") | {"decided_at": 100.0}
    }
    serialized = json.dumps(result)
    assert str(state_db) not in serialized
    assert "service" not in serialized
