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

    assert tables == {"request_usage", "lifecycle_samples"}
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
