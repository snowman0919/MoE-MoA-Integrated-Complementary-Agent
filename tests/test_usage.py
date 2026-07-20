from __future__ import annotations

import json
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from dgx_moa.config import Limits, load_settings
from pydantic import ValidationError


def usage_module() -> Any:
    return import_module("dgx_moa.usage")


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        ("curl/8.14.1", "curl"),
        ("OpenAI/Python 1.109.1", "openai-python"),
        ("python-httpx/0.28.1", "httpx"),
        ("opencode/1.17.18", "opencode"),
        ("Hermes-Agent/0.18.2", "hermes-agent"),
        ("unknown-client/1.0", "openai-compatible"),
        (None, "openai-compatible"),
    ],
)
def test_client_classification_is_bounded_and_content_free(
    user_agent: str | None, expected: str
) -> None:
    module = usage_module()

    assert module.classify_client(user_agent) == expected


def start_record(
    module: Any,
    request_id: str,
    accepted_at: float,
    *,
    model_state: str = "warm",
    load_triggered: bool = False,
    roles_required: tuple[str, ...] = ("executor",),
) -> Any:
    return module.RequestUsageStart(
        request_id=request_id,
        session_id=f"session-{request_id}",
        client_class="openai-compatible",
        model_alias="dgx-moa-agent",
        runtime_mode="agent",
        request_class="native_agent_turn",
        roles_required=roles_required,
        accepted_at=accepted_at,
        streaming=False,
        model_state=model_state,
        load_triggered=load_triggered,
    )


def finalization(module: Any, completed_at: float, duration: float) -> Any:
    return module.RequestUsageFinalization(
        first_byte_at=completed_at - duration / 2,
        completed_at=completed_at,
        active_duration_seconds=duration,
        status="completed",
        prompt_tokens=2,
        completion_tokens=3,
        total_tokens=5,
    )


def test_schema_and_start_finalize_are_idempotent(tmp_path: Path) -> None:
    module = usage_module()
    path = tmp_path / "usage.db"
    store = module.UsageStore(path)

    store.start(start_record(module, "request-1", 100.0))
    duplicate = start_record(module, "request-1", 999.0)
    duplicate.client_class = "curl"
    store.start(duplicate)
    store.finalize("request-1", finalization(module, 104.0, 4.0))
    store.finalize(
        "request-1",
        module.RequestUsageFinalization(
            completed_at=999.0,
            active_duration_seconds=999.0,
            status="failed",
            retryable_failure_class="backend_error",
        ),
    )

    record = store.get("request-1")
    assert record is not None
    assert record.request_id == "request-1"
    assert record.session_id == "session-request-1"
    assert record.client_class == "openai-compatible"
    assert record.model_alias == "dgx-moa-agent"
    assert record.runtime_mode == "agent"
    assert record.request_class == "native_agent_turn"
    assert record.roles_required == ("executor",)
    assert record.accepted_at == 100.0
    assert record.first_byte_at == 102.0
    assert record.completed_at == 104.0
    assert record.active_duration_seconds == 4.0
    assert record.status == "completed"
    assert record.streaming is False
    assert record.model_state == "warm"
    assert record.load_triggered is False
    assert record.retryable_failure_class is None
    assert record.prompt_tokens == 2
    assert record.completion_tokens == 3
    assert record.total_tokens == 5

    with sqlite3.connect(path) as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        request_columns = {row[1] for row in database.execute("PRAGMA table_info(request_usage)")}
        lifecycle_columns = {
            row[1] for row in database.execute("PRAGMA table_info(lifecycle_samples)")
        }

    assert tables == {"request_usage", "role_request_usage", "lifecycle_samples"}
    assert request_columns == {
        "request_id",
        "session_id",
        "client_class",
        "model_alias",
        "runtime_mode",
        "request_class",
        "roles_required",
        "accepted_at",
        "first_byte_at",
        "completed_at",
        "active_duration_seconds",
        "status",
        "streaming",
        "model_state",
        "load_triggered",
        "retryable_failure_class",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
    }
    assert lifecycle_columns == {
        "sample_id",
        "role",
        "kind",
        "duration_seconds",
        "memory_before_bytes",
        "memory_after_bytes",
    }


def test_role_usage_is_independent_and_content_free(tmp_path: Path) -> None:
    module = usage_module()
    path = tmp_path / "state.db"
    store = module.UsageStore(path, sample_window=100)
    session_secret = "raw-session-must-not-be-stored"

    store.start_roles(
        "request-1",
        ("planner", "reviewer"),
        session_id=session_secret,
        requested_at=1_000.0,
        client_mode="orchestrated",
        request_class="explicit_orchestrated",
        states={"planner": "cold", "reviewer": "warm"},
        load_triggered={"planner": True, "reviewer": False},
    )
    store.finalize_roles(
        "request-1",
        completed_at=1_010.0,
        first_byte_at=1_005.0,
        success=True,
        failure_class=None,
    )

    rows = store.recent_role_requests("planner") + store.recent_role_requests("reviewer")
    assert [row.role for row in rows] == ["planner", "reviewer"]
    assert rows[0].load_triggered is True
    assert rows[0].cold_or_warm == "cold"
    assert rows[1].load_triggered is False
    assert rows[1].cold_or_warm == "warm"
    assert rows[0].active_duration_ms == 10_000
    assert rows[0].session_id_hash != session_secret
    assert len(rows[0].session_id_hash) == 64

    with sqlite3.connect(path) as database:
        columns = {row[1] for row in database.execute("PRAGMA table_info(role_request_usage)")}
    assert columns == {
        "request_id",
        "session_id_hash",
        "role",
        "client_mode",
        "request_class",
        "requested_at",
        "load_triggered",
        "cold_or_warm",
        "ready_at",
        "first_byte_at",
        "completed_at",
        "success",
        "failure_class",
        "active_duration_ms",
    }
    persisted = b"".join(
        candidate.read_bytes() for candidate in (path, Path(f"{path}-wal")) if candidate.exists()
    )
    assert session_secret.encode() not in persisted


def test_role_statistics_use_only_successful_role_local_gaps(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(
        tmp_path / "state.db",
        sample_window=100,
        ewma_alpha=0.5,
        adaptive_minimum_samples=2,
    )
    requested_times = (1_000.0, 1_010.0, 1_030.0, 1_060.0)
    for index, requested_at in enumerate(requested_times):
        request_id = f"request-{index}"
        cold = index == 0
        store.start_roles(
            request_id,
            ("planner",),
            session_id=f"session-{index}",
            requested_at=requested_at,
            client_mode="orchestrated",
            request_class="explicit_orchestrated",
            states={"planner": "cold" if cold else "warm"},
            load_triggered={"planner": cold},
            ready_at={"planner": requested_at + 5 if cold else requested_at},
        )
        store.finalize_roles(
            request_id,
            completed_at=requested_at + 3,
            first_byte_at=requested_at + 2,
            success=index < 3,
            failure_class=None if index < 3 else "backend_error",
        )

    statistics = store.role_statistics("planner", now=1_100.0)

    assert statistics["request_count"] == 4
    assert statistics["failure_count"] == 1
    assert statistics["inter_arrival_gaps_seconds"] == [10.0, 20.0]
    assert statistics["inter_arrival_ewma_seconds"] == 15.0
    assert statistics["inter_arrival_percentiles_seconds"] == {
        "p50": 15.0,
        "p75": 17.5,
        "p90": 19.0,
        "p95": 19.5,
    }
    assert statistics["adaptive_policy_samples"] == {
        "usable": 2,
        "minimum": 2,
        "sufficient": True,
    }
    assert statistics["cold_start_count"] == 1
    assert statistics["cold_start_frequency"] == 0.25
    assert statistics["average_load_duration_seconds"] == 5.0
    assert statistics["average_warm_latency_seconds"] == 2.0
    assert statistics["last_used_at"] == 1_063.0
    assert sum(statistics["requests_by_hour_utc"].values()) == 4
    assert sum(statistics["requests_by_weekday_hour_utc"].values()) == 4
    assert store.role_statistics("reviewer", now=1_100.0)["request_count"] == 0


def test_role_aggregate_counts_are_not_limited_by_adaptive_sample_window(
    tmp_path: Path,
) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "state.db", sample_window=2)
    for index in range(5):
        request_id = f"request-{index}"
        store.start_roles(
            request_id,
            ("reasoner",),
            session_id=f"session-{index}",
            requested_at=float(index),
            client_mode="orchestrated",
            request_class="high_risk_task",
            states={"reasoner": "warm"},
            load_triggered={"reasoner": False},
        )
        store.finalize_roles(
            request_id,
            completed_at=float(index + 1),
            first_byte_at=float(index) + 0.5,
            success=True,
            failure_class=None,
        )

    statistics = store.role_statistics("reasoner", now=10.0)

    assert statistics["request_count"] == 5
    assert statistics["inter_arrival_gaps_seconds"] == [1.0]
    assert sum(statistics["requests_by_hour_utc"].values()) == 5


def test_recent_successful_role_window_ignores_newer_failures(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "state.db", sample_window=2)
    outcomes = (True, True, True, False, False, False, False)
    for index, success in enumerate(outcomes):
        request_id = f"request-{index}"
        store.start_roles(
            request_id,
            ("planner",),
            session_id=f"session-{index}",
            requested_at=float(index),
            client_mode="orchestrated",
            request_class="explicit_orchestrated",
            states={"planner": "warm"},
            load_triggered={"planner": False},
        )
        store.finalize_roles(
            request_id,
            completed_at=float(index) + 0.5,
            first_byte_at=float(index) + 0.25,
            success=success,
            failure_class=None if success else "model_loading",
        )

    recent = store.recent_role_requests("planner")
    successful = store.recent_role_requests("planner", success=True, limit=3)

    assert [row.success for row in recent] == [False, False]
    assert [row.requested_at for row in successful] == [0.0, 1.0, 2.0]


def test_token_counts_are_bounded_to_sqlite_signed_integer_range() -> None:
    module = usage_module()
    maximum = 2**63 - 1

    accepted = module.RequestUsageFinalization(
        completed_at=1.0,
        status="completed",
        prompt_tokens=maximum,
        completion_tokens=maximum,
        total_tokens=maximum,
    )

    assert accepted.total_tokens == maximum
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        with pytest.raises(ValidationError):
            module.RequestUsageFinalization.model_validate(
                {"completed_at": 1.0, "status": "completed", field: maximum + 1}
            )


def test_active_request_count_is_not_limited_by_statistics_window(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db", sample_window=2)
    for index in range(5):
        store.start(start_record(module, f"active-{index}", float(index)))

    assert len(store.recent_requests()) == 2
    assert store.active_request_count() == 5

    store.finalize(
        "active-0",
        module.RequestUsageFinalization(completed_at=10.0, status="completed"),
    )
    assert store.active_request_count() == 4


def test_statistics_cover_gaps_ewma_percentiles_roles_latency_and_lifecycle(
    tmp_path: Path,
) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db")
    accepted_at = 1_700_000_000.0

    for index in range(21):
        roles = ("executor", "planner") if index and index % 2 == 0 else ("executor",)
        store.start(
            start_record(
                module,
                f"request-{index:02}",
                accepted_at,
                model_state="cold" if index == 0 else "warm",
                load_triggered=index == 0,
                roles_required=roles,
            )
        )
        duration = 99.0 if index == 0 else float(index)
        store.finalize(
            f"request-{index:02}", finalization(module, accepted_at + duration, duration)
        )
        accepted_at += index + 1

    store.record_lifecycle_sample(
        module.LifecycleSample(
            role="executor",
            kind="load",
            duration_seconds=10.0,
            memory_before_bytes=100,
            memory_after_bytes=80,
        )
    )
    store.record_lifecycle_sample(
        module.LifecycleSample(role="planner", kind="load", duration_seconds=20.0)
    )
    store.record_lifecycle_sample(
        module.LifecycleSample(role="executor", kind="unload", duration_seconds=4.0)
    )

    report = store.report(now=accepted_at)
    expected_ewma = 1.0
    for gap in range(2, 21):
        expected_ewma = 0.25 * gap + 0.75 * expected_ewma

    assert report["request_count"] == 21
    assert report["requests_last_hour"] == 21
    assert report["requests_last_day"] == 21
    assert report["inter_arrival_gaps_seconds"] == [float(value) for value in range(1, 21)]
    assert report["inter_arrival_ewma_seconds"] == pytest.approx(expected_ewma)
    assert report["inter_arrival_percentiles_seconds"] == {
        "p50": 10.5,
        "p75": 15.25,
        "p90": pytest.approx(18.1),
        "p95": pytest.approx(19.05),
    }
    assert report["adaptive_policy_samples"] == {
        "usable": 20,
        "minimum": 20,
        "sufficient": True,
    }
    assert report["role_frequency"] == {"executor": 21, "planner": 10}
    assert report["warm_latency_seconds"] == {
        "count": 20,
        "mean": 10.5,
        "p50": 10.5,
        "p75": 15.25,
        "p90": pytest.approx(18.1),
        "p95": pytest.approx(19.05),
    }
    assert report["cold_starts"] == 1
    assert report["load_duration_seconds"] == {
        "count": 2,
        "mean": 15.0,
        "p50": 15.0,
        "p75": 17.5,
        "p90": 19.0,
        "p95": 19.5,
    }
    assert report["unload_duration_seconds"] == {
        "count": 1,
        "mean": 4.0,
        "p50": 4.0,
        "p75": 4.0,
        "p90": 4.0,
        "p95": 4.0,
    }
    samples = store.recent_lifecycle_samples()
    assert samples[0].memory_before_bytes == 100
    assert samples[0].memory_after_bytes == 80


def test_recent_window_bounds_all_statistics_and_sparse_samples_are_insufficient(
    tmp_path: Path,
) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db", sample_window=3)
    accepted_times = [0.0, 1.0, 3.0, 6.0, 10.0]

    for index, accepted_at in enumerate(accepted_times):
        store.start(start_record(module, f"request-{index}", accepted_at))
    for duration in (1.0, 2.0, 3.0, 4.0):
        store.record_lifecycle_sample(
            module.LifecycleSample(role="executor", kind="load", duration_seconds=duration)
        )

    report = store.report(now=10.0)

    assert [record.request_id for record in store.recent_requests()] == [
        "request-2",
        "request-3",
        "request-4",
    ]
    assert report["request_count"] == 3
    assert report["inter_arrival_gaps_seconds"] == [3.0, 4.0]
    assert report["adaptive_policy_samples"] == {
        "usable": 2,
        "minimum": 20,
        "sufficient": False,
    }
    assert report["load_duration_seconds"]["count"] == 3
    assert report["load_duration_seconds"]["mean"] == 3.0


def test_zero_inter_arrival_gaps_are_preserved_in_statistics(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db")
    for index, accepted_at in enumerate((100.0, 100.0, 101.0)):
        store.start(start_record(module, f"request-{index}", accepted_at))

    report = store.report(now=101.0)

    assert report["inter_arrival_gaps_seconds"] == [0.0, 1.0]
    assert report["inter_arrival_ewma_seconds"] == 0.25
    assert report["inter_arrival_percentiles_seconds"] == {
        "p50": 0.5,
        "p75": 0.75,
        "p90": 0.9,
        "p95": 0.95,
    }


def test_zero_gaps_count_toward_adaptive_sample_sufficiency(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db")
    for index in range(21):
        store.start(start_record(module, f"request-{index}", 100.0))

    report = store.report(now=100.0)

    assert report["inter_arrival_gaps_seconds"] == [0.0] * 20
    assert report["adaptive_policy_samples"] == {
        "usable": 20,
        "minimum": 20,
        "sufficient": True,
    }


def test_hour_and_day_counts_use_the_report_time(tmp_path: Path) -> None:
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db")
    now = 100_000.0
    for index, accepted_at in enumerate((now - 90_000, now - 4_000, now - 10, now + 1)):
        store.start(start_record(module, f"request-{index}", accepted_at))

    report = store.report(now=now)

    assert report["requests_last_hour"] == 1
    assert report["requests_last_day"] == 2


def test_forbidden_request_content_never_reaches_sqlite_or_report(tmp_path: Path) -> None:
    module = usage_module()
    path = tmp_path / "usage.db"
    store = module.UsageStore(path)
    sentinels = {
        "prompt": "SENTINEL_PROMPT_7b9276",
        "response": "SENTINEL_RESPONSE_28b4e9",
        "message": "SENTINEL_MESSAGE_8d86ae",
        "tool_name": "SENTINEL_TOOL_NAME_081846",
        "tool_arguments": "SENTINEL_TOOL_ARGUMENTS_30559d",
        "tool_result": "SENTINEL_TOOL_RESULT_dcf106",
        "authorization": "SENTINEL_AUTHORIZATION_9ce8de",
        "secret": "SENTINEL_SECRET_3e6b5c",
        "metadata": "SENTINEL_RAW_METADATA_8c656f",
        "client_configuration": "SENTINEL_CLIENT_CONFIG_262872",
    }
    raw_input = {
        "request_id": "safe-request",
        "session_id": "safe-session",
        "client_class": "openai-compatible",
        "model_alias": "dgx-moa-agent",
        "runtime_mode": "agent",
        "request_class": "native_agent_turn",
        "roles_required": ["executor"],
        "accepted_at": 100.0,
        "streaming": True,
        "model_state": "warm",
        "load_triggered": False,
        "prompt": sentinels["prompt"],
        "response": sentinels["response"],
        "messages": [{"content": sentinels["message"]}],
        "tool_name": sentinels["tool_name"],
        "tool_arguments": sentinels["tool_arguments"],
        "tool_result": sentinels["tool_result"],
        "authorization": sentinels["authorization"],
        "secret": sentinels["secret"],
        "metadata": {"raw": sentinels["metadata"]},
        "client_configuration": sentinels["client_configuration"],
    }
    store.start(module.RequestUsageStart.model_validate(raw_input))
    store.finalize(
        "safe-request",
        module.RequestUsageFinalization.model_validate(
            {
                "completed_at": 101.0,
                "active_duration_seconds": 1.0,
                "status": "completed",
                "response": sentinels["response"],
                "tool_result": sentinels["tool_result"],
                "authorization": sentinels["authorization"],
            }
        ),
    )

    sqlite_bytes = b"".join(file.read_bytes() for file in tmp_path.glob("usage.db*"))
    serialized_report = json.dumps(store.report(now=101.0), sort_keys=True)

    for sentinel in sentinels.values():
        assert sentinel.encode() not in sqlite_bytes
        assert sentinel not in serialized_report


@pytest.mark.parametrize(
    ("field", "value", "sentinel"),
    [
        ("client_class", "SENTINEL_CATEGORY_CLIENT", "SENTINEL_CATEGORY_CLIENT"),
        ("model_alias", "SENTINEL_CATEGORY_MODEL", "SENTINEL_CATEGORY_MODEL"),
        ("runtime_mode", "SENTINEL_CATEGORY_MODE", "SENTINEL_CATEGORY_MODE"),
        ("request_class", "SENTINEL_CATEGORY_REQUEST", "SENTINEL_CATEGORY_REQUEST"),
        ("roles_required", ["executor", "SENTINEL_CATEGORY_ROLE"], "SENTINEL_CATEGORY_ROLE"),
        ("model_state", "SENTINEL_CATEGORY_STATE", "SENTINEL_CATEGORY_STATE"),
    ],
)
def test_request_start_rejects_category_sentinels_before_persistence(
    tmp_path: Path, field: str, value: object, sentinel: str
) -> None:
    module = usage_module()
    path = tmp_path / "usage.db"
    store = module.UsageStore(path)
    raw = {
        "request_id": "safe-request",
        "session_id": "safe-session",
        "client_class": "openai-compatible",
        "model_alias": "dgx-moa-agent",
        "runtime_mode": "agent",
        "request_class": "native_agent_turn",
        "roles_required": ["executor"],
        "accepted_at": 100.0,
        "streaming": False,
        "model_state": "warm",
        "load_triggered": False,
    }
    raw[field] = value

    with pytest.raises(ValidationError):
        store.start(module.RequestUsageStart.model_validate(raw))

    sqlite_bytes = b"".join(file.read_bytes() for file in tmp_path.glob("usage.db*"))
    assert sentinel.encode() not in sqlite_bytes
    assert sentinel not in json.dumps(store.report(now=100.0), sort_keys=True)


@pytest.mark.parametrize("field", ["status", "retryable_failure_class"])
def test_request_finalization_rejects_category_sentinels_before_persistence(
    tmp_path: Path, field: str
) -> None:
    module = usage_module()
    path = tmp_path / "usage.db"
    store = module.UsageStore(path)
    store.start(start_record(module, "safe-request", 100.0))
    sentinel = f"SENTINEL_CATEGORY_{field.upper()}"
    raw = {
        "completed_at": 101.0,
        "active_duration_seconds": 1.0,
        "status": "failed",
        "retryable_failure_class": "backend_error",
        field: sentinel,
    }

    with pytest.raises(ValidationError):
        store.finalize("safe-request", module.RequestUsageFinalization.model_validate(raw))

    assert store.get("safe-request").completed_at is None
    sqlite_bytes = b"".join(file.read_bytes() for file in tmp_path.glob("usage.db*"))
    assert sentinel.encode() not in sqlite_bytes
    assert sentinel not in json.dumps(store.report(now=101.0), sort_keys=True)


@pytest.mark.parametrize("field", ["role", "kind"])
def test_lifecycle_sample_rejects_category_sentinels_before_persistence(
    tmp_path: Path, field: str
) -> None:
    module = usage_module()
    path = tmp_path / "usage.db"
    store = module.UsageStore(path)
    sentinel = f"SENTINEL_CATEGORY_{field.upper()}"
    raw = {
        "role": "executor",
        "kind": "load",
        "duration_seconds": 1.0,
        field: sentinel,
    }

    with pytest.raises(ValidationError):
        store.record_lifecycle_sample(module.LifecycleSample.model_validate(raw))

    sqlite_bytes = b"".join(file.read_bytes() for file in tmp_path.glob("usage.db*"))
    assert sentinel.encode() not in sqlite_bytes
    assert sentinel not in json.dumps(store.report(now=100.0), sort_keys=True)


def test_usage_limits_have_exact_defaults_and_yaml_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = Limits()
    assert limits.usage_sample_window == 512
    assert limits.usage_ewma_alpha == 0.25
    assert limits.adaptive_minimum_samples == 20

    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    configured = load_settings(Path("config/models.yaml"))
    assert configured.limits.usage_sample_window == 512
    assert configured.limits.usage_ewma_alpha == 0.25
    assert configured.limits.adaptive_minimum_samples == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("usage_sample_window", 0),
        ("usage_ewma_alpha", 2),
        ("adaptive_minimum_samples", 0),
    ],
)
def test_usage_limits_reject_out_of_bounds_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate({field: value})


def test_busy_hour_counts_do_not_make_a_sparse_optional_role_adaptive(tmp_path: Path) -> None:
    lifecycle = import_module("dgx_moa.lifecycle")
    module = usage_module()
    store = module.UsageStore(tmp_path / "usage.db")
    start = 100_000.0
    for index in range(30):
        roles = ("executor", "planner") if index in {0, 29} else ("executor",)
        store.start(start_record(module, f"request-{index}", start + index, roles_required=roles))

    report = store.report(now=start + 30)
    record = lifecycle.LifecycleRecord(
        role="planner",
        state="ready",
        transition_id="502713d8-6d11-436c-829f-757ec8d3fbf2",
        transitioned_at=0.0,
        updated_at=0.0,
        ready_since=0.0,
        last_used_at=0.0,
    )
    decision = lifecycle.calculate_idle_policy(
        "planner",
        "adaptive",
        store.recent_requests(),
        record,
        now=start + 30,
        limits=Limits(),
    )

    assert report["requests_last_hour"] == 30
    assert report["requests_last_day"] == 30
    assert report["adaptive_policy_samples"]["sufficient"] is True
    assert decision.sample_count == 1
    assert decision.threshold_source == "sparse_fallback"
    assert decision.threshold_seconds == 900.0
