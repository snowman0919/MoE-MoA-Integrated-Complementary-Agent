from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import threading
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pytest
from dgx_moa.config import Limits, Settings, load_settings
from pydantic import ValidationError

STATES = {
    "disabled",
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unload_queued",
    "unloading",
    "failed",
}
TRANSITIONS = {
    "disabled": {"cold"},
    "cold": {"disabled", "load_queued"},
    "load_queued": {"disabled", "cold", "process_starting", "failed"},
    "process_starting": {"disabled", "cold", "loading_weights", "failed"},
    "loading_weights": {"disabled", "cold", "initializing_engine", "failed"},
    "initializing_engine": {"disabled", "cold", "warming_up", "failed"},
    "warming_up": {"disabled", "cold", "ready", "failed"},
    "ready": {"disabled", "sleeping", "unload_queued", "unloading", "failed"},
    "sleeping": {"disabled", "cold", "ready", "unloading", "failed"},
    "unload_queued": {"disabled", "ready", "unloading", "failed"},
    "unloading": {"disabled", "cold", "failed"},
    "failed": {"disabled", "cold", "load_queued"},
}
PATHS = {
    "disabled": ("disabled",),
    "cold": (),
    "load_queued": ("load_queued",),
    "process_starting": ("load_queued", "process_starting"),
    "loading_weights": ("load_queued", "process_starting", "loading_weights"),
    "initializing_engine": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
    ),
    "warming_up": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
    ),
    "ready": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
        "ready",
    ),
    "sleeping": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
        "ready",
        "sleeping",
    ),
    "unloading": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
        "ready",
        "unloading",
    ),
    "unload_queued": (
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
        "ready",
        "unload_queued",
    ),
    "failed": ("load_queued", "failed"),
}


def lifecycle() -> Any:
    return import_module("dgx_moa.lifecycle")


def policy_record(
    module: Any,
    role: str = "executor",
    *,
    state: str = "ready",
    ready_since: float | None = 0.0,
    last_used_at: float | None = 0.0,
) -> Any:
    return module.LifecycleRecord(
        role=role,
        state=state,
        transition_id="d4f650df-11fb-4477-98c9-fc8aa7093684",
        transitioned_at=0.0,
        updated_at=0.0,
        ready_since=ready_since,
        last_used_at=last_used_at,
    )


def policy_usage(accepted_at: float, roles: tuple[str, ...] = ("executor",)) -> Any:
    from dgx_moa.usage import RequestUsageStart

    return RequestUsageStart(
        request_id=f"request-{accepted_at}-{roles}",
        session_id=f"session-{accepted_at}-{roles}",
        client_class="openai-compatible",
        model_alias="dgx-moa-agent",
        runtime_mode="agent",
        request_class="native_agent_turn",
        roles_required=roles,
        accepted_at=accepted_at,
        streaming=False,
        model_state="warm",
    )


def policy_usage_from_gaps(gaps: list[float], roles: tuple[str, ...] = ("executor",)) -> list[Any]:
    accepted = [0.0]
    for gap in gaps:
        accepted.append(accepted[-1] + gap)
    return [policy_usage(value, roles) for value in accepted]


@pytest.fixture(autouse=True)
def block_real_service_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    def tripwire(*args: object, **kwargs: object) -> None:
        pytest.fail(f"unexpected real service command: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "run", tripwire)


def reach(store: Any, role: str, state: str) -> Any:
    record = store.get(role)
    for target in PATHS[state]:
        record = store.transition(role, target, expected_transition_id=record.transition_id)
    return record


def test_lifecycle_defaults_are_disabled_and_empty() -> None:
    settings = Settings(auth_enabled=False)

    assert settings.lifecycle_mode == "disabled"
    assert settings.lifecycle_poll_seconds == 30
    assert settings.lifecycle_unit_map == {}


def test_role_lifecycle_defaults_match_approved_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    settings = load_settings(Path("config/models.yaml"))

    assert settings.lifecycle.roles["executor"].normally_resident is True
    assert settings.lifecycle.roles["executor"].idle_unload_enabled is False
    assert settings.lifecycle.roles["executor"].fallback_timeout_seconds == 14_400
    assert settings.lifecycle.roles["planner"].fallback_timeout_seconds == 1_200
    assert settings.lifecycle.roles["reviewer"].fallback_timeout_seconds == 1_200
    assert settings.lifecycle.roles["reasoner"].fallback_timeout_seconds == 600
    assert settings.lifecycle.roles["judge"].enabled is False
    assert settings.lifecycle.recent_sample_window == 100
    assert settings.lifecycle.minimum_samples == 20
    assert settings.lifecycle.percentile == 0.75
    assert settings.lifecycle.multiplier == 1.5
    assert settings.lifecycle.load_unload_cooldown_seconds == 300
    assert settings.lifecycle.continuation_lease_ttl_seconds == 900
    assert settings.lifecycle.failure_limit == 3
    assert settings.lifecycle.failure_window_seconds == 900


def test_role_lifecycle_partial_environment_override_preserves_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_LIFECYCLE_POLICY",
        '{"roles":{"planner":{"fallback_timeout_seconds":1800}}}',
    )

    settings = load_settings(Path("config/models.yaml"))

    planner = settings.lifecycle.roles["planner"]
    assert planner.minimum_timeout_seconds == 600
    assert planner.fallback_timeout_seconds == 1_800
    assert planner.maximum_timeout_seconds == 3_600
    assert settings.lifecycle.roles["executor"].idle_unload_enabled is False
    assert settings.lifecycle.roles["judge"].enabled is False


def test_role_lifecycle_rejects_unknown_role_and_invalid_timeout_order() -> None:
    with pytest.raises(ValidationError, match="unknown lifecycle role"):
        Settings(auth_enabled=False, lifecycle={"roles": {"mystery": {}}})

    with pytest.raises(ValidationError, match="minimum <= fallback <= maximum"):
        Settings(
            auth_enabled=False,
            lifecycle={
                "roles": {
                    "reasoner": {
                        "minimum_timeout_seconds": 700,
                        "fallback_timeout_seconds": 600,
                    }
                }
            },
        )


def test_lifecycle_schema_migrates_generation_and_required_fields(tmp_path: Path) -> None:
    module = lifecycle()
    database_path = tmp_path / "state.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "CREATE TABLE model_lifecycle ("
            "role TEXT PRIMARY KEY, state TEXT NOT NULL, transition_id TEXT NOT NULL, "
            "transitioned_at REAL NOT NULL, updated_at REAL NOT NULL, ready_since REAL, "
            "last_used_at REAL, failure_class TEXT, failure_detail TEXT, "
            "retry_count INTEGER NOT NULL, active_request_count INTEGER NOT NULL, "
            "open_stream_count INTEGER NOT NULL, continuation_lease_count INTEGER NOT NULL, "
            "evaluation_guard INTEGER NOT NULL, profile_guard INTEGER NOT NULL, "
            "progress_value REAL, progress_quality TEXT, eta_seconds REAL, "
            "last_load_duration_seconds REAL, last_unload_duration_seconds REAL, "
            "memory_before_bytes INTEGER, memory_after_bytes INTEGER)"
        )

    store = module.LifecycleStore(
        database_path,
        ("planner",),
        unit_map={"planner": "dgx-moa-dev-planner.service"},
    )
    record = store.get("planner")

    assert record.state == "disabled"
    assert record.generation == 0
    assert record.service_unit == "dgx-moa-dev-planner.service"
    assert record.load_started_at is None
    assert record.ready_at is None
    assert record.last_requested_at is None
    assert record.last_completed_at is None
    assert record.weight_load_percent is None
    assert record.overall_load_percent is None
    assert record.last_error_class is None
    assert record.last_error_message_redacted is None

    restarted = module.LifecycleStore(
        database_path,
        ("planner",),
        unit_map={"planner": "dgx-moa-dev-planner.service"},
    )
    assert restarted.get("planner") == record


def test_unload_queue_is_explicit_and_reversible(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("planner",))
    ready = store.recover_state("planner", "ready")

    queued = store.queue_unload("planner", expected_transition_id=ready.transition_id)
    assert queued.state == "unload_queued"

    restored = store.cancel_queued_unload("planner", expected_transition_id=queued.transition_id)
    assert restored.state == "ready"
    assert restored.ready_at == ready.ready_at


def test_load_generation_increments_once_per_cold_queue(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("planner",))
    cold = store.get("planner")

    queued = store.transition("planner", "load_queued", expected_transition_id=cold.transition_id)

    assert queued.generation == cold.generation + 1
    assert queued.overall_load_percent == 0.0
    with pytest.raises(module.StaleTransitionError):
        store.transition("planner", "load_queued", expected_transition_id=cold.transition_id)
    assert store.get("planner").generation == queued.generation

    starting = store.transition(
        "planner", "process_starting", expected_transition_id=queued.transition_id
    )
    assert starting.load_started_at is not None
    assert starting.overall_load_percent == 5.0


def test_new_load_generation_resets_progress_and_disable_all_is_durable(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    path = tmp_path / "state.db"
    store = module.LifecycleStore(path, ("planner", "reviewer"))
    planner = store.get("planner")
    first = store.transition("planner", "load_queued", expected_transition_id=planner.transition_id)
    progressed = store.update(
        "planner",
        first.transition_id,
        progress_value=42.0,
        overall_load_percent=34.0,
        progress_quality="measured_bytes",
    )
    failed = store.transition(
        "planner",
        "failed",
        expected_transition_id=progressed.transition_id,
        failure_class="LOAD Timeout",
        failure_detail="secret\nredacted",
    )

    second = store.transition("planner", "load_queued", expected_transition_id=failed.transition_id)
    assert second.generation == first.generation + 1
    assert second.weight_load_percent is None
    assert second.overall_load_percent == 0.0
    assert second.last_error_class == "load_timeout"
    assert second.last_error_message_redacted == "secret redacted"

    disabled = store.disable_all()
    assert {role: record.state for role, record in disabled.items()} == {
        "planner": "disabled",
        "reviewer": "disabled",
    }
    restarted = module.LifecycleStore(path, ("planner", "reviewer"))
    assert restarted.get("planner").state == "disabled"
    assert restarted.get("planner").generation == second.generation


def test_progress_bands_are_monotonic_within_a_generation(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("planner",))
    record = store.get("planner")
    queued = store.transition("planner", "load_queued", expected_transition_id=record.transition_id)
    starting = store.transition(
        "planner", "process_starting", expected_transition_id=queued.transition_id
    )
    loading = store.transition(
        "planner", "loading_weights", expected_transition_id=starting.transition_id
    )
    measured = store.update(
        "planner",
        loading.transition_id,
        progress_value=50.0,
        overall_load_percent=35.0,
        progress_quality="measured_shards",
    )
    stale_log = store.update(
        "planner",
        measured.transition_id,
        progress_value=40.0,
        overall_load_percent=29.0,
        progress_quality="measured_shards",
    )
    initialized = store.transition(
        "planner", "initializing_engine", expected_transition_id=stale_log.transition_id
    )
    warmed = store.transition(
        "planner", "warming_up", expected_transition_id=initialized.transition_id
    )
    ready = store.transition("planner", "ready", expected_transition_id=warmed.transition_id)

    assert queued.overall_load_percent == 0.0
    assert starting.overall_load_percent == 5.0
    assert loading.overall_load_percent == 5.0
    assert stale_log.weight_load_percent == 50.0
    assert stale_log.overall_load_percent == 35.0
    assert initialized.overall_load_percent == 70.0
    assert warmed.overall_load_percent == 90.0
    assert ready.overall_load_percent == 100.0


def test_idle_policy_limits_have_conservative_defaults_and_yaml_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "executor_idle_fallback_seconds": 2_700.0,
        "executor_idle_minimum_seconds": 900.0,
        "executor_idle_maximum_seconds": 7_200.0,
        "executor_minimum_ready_residency_seconds": 600.0,
        "optional_idle_fallback_seconds": 900.0,
        "optional_idle_minimum_seconds": 300.0,
        "optional_idle_maximum_seconds": 2_700.0,
        "optional_minimum_ready_residency_seconds": 300.0,
    }

    limits = Limits()
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    configured = load_settings(Path("config/models.yaml")).limits

    for field, value in expected.items():
        assert getattr(limits, field) == value
        assert getattr(configured, field) == value


def test_executor_long_idle_is_disabled_while_optional_roles_adapt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = lifecycle()
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    settings = load_settings(Path("config/models.yaml"))
    records = policy_usage_from_gaps(
        [600.0] * 100,
        ("executor", "planner", "reasoner"),
    )

    executor = module.calculate_idle_policy(
        "executor",
        "adaptive",
        records,
        policy_record(module, "executor"),
        policy=settings.lifecycle.roles["executor"],
        lifecycle=settings.lifecycle,
        now=100_000.0,
    )
    planner = module.calculate_idle_policy(
        "planner",
        "adaptive",
        records,
        policy_record(module, "planner"),
        policy=settings.lifecycle.roles["planner"],
        lifecycle=settings.lifecycle,
        now=100_000.0,
    )
    reasoner = module.calculate_idle_policy(
        "reasoner",
        "adaptive",
        records,
        policy_record(module, "reasoner"),
        policy=settings.lifecycle.roles["reasoner"],
        lifecycle=settings.lifecycle,
        now=100_000.0,
    )

    assert executor.action_allowed is False
    assert executor.reason == "idle_unload_disabled"
    assert planner.threshold_seconds == 900.0
    assert planner.threshold_seconds <= 3_600
    assert reasoner.threshold_seconds == 900.0
    assert reasoner.threshold_seconds <= 1_800


def test_role_policy_cooldown_blocks_otherwise_eligible_unload() -> None:
    module = lifecycle()
    from dgx_moa.config import LifecyclePolicy, LifecycleRolePolicy

    lifecycle_policy = LifecyclePolicy(load_unload_cooldown_seconds=300)
    role_policy = LifecycleRolePolicy(
        minimum_timeout_seconds=1,
        fallback_timeout_seconds=10,
        maximum_timeout_seconds=100,
        minimum_ready_residency_seconds=1,
    )
    record = policy_record(module, "planner", ready_since=0.0, last_used_at=0.0)

    decision = module.calculate_idle_policy(
        "planner",
        "fixed",
        (),
        record,
        policy=role_policy,
        lifecycle=lifecycle_policy,
        now=100.0,
        previous_mode="fixed",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=1,
    )

    assert decision.action_allowed is False
    assert decision.reason == "cooldown"


@pytest.mark.asyncio
async def test_failure_circuit_trips_after_three_mutations_and_blocks_fourth(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    from dgx_moa.config import LifecyclePolicy

    class FailingStartDriver(module.FakeLifecycleDriver):
        def start(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("start", role))
            raise module.LifecycleDriverError("start", "command_failed")

    roles = ("planner", "reviewer", "reasoner", "executor")
    store = module.LifecycleStore(tmp_path / "state.db", roles, clock=lambda: 100.0)
    driver = FailingStartDriver({role: "inactive" for role in roles})
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=False),
        timeout_seconds=10,
        poll_seconds=0.1,
        clock=lambda: 100.0,
        lifecycle_policy=LifecyclePolicy(failure_limit=3, failure_window_seconds=900),
    )

    for role in roles[:3]:
        check = await coordinator.ensure_ready(role)
        assert check.load_triggered is True
        await coordinator._tasks[role]

    circuit = store.automation_status()
    assert circuit.automation_disabled is True
    assert circuit.failure_count == 3
    assert circuit.disabled_at == 100.0
    fourth = await coordinator.ensure_ready("executor")

    assert fourth.load_triggered is False
    assert store.get("executor").state == "cold"
    assert driver.calls.count(("start", "executor")) == 0
    assert sum(operation == "start" for operation, _ in driver.calls) == 3
    assert len(store.recent_failure_events()) == 3

    reset = store.reset_automation()
    assert reset.automation_disabled is False
    assert reset.failure_count == 0
    assert len(store.recent_failure_events()) == 3
    after_reset = store.record_failure(
        "executor",
        "manual_probe",
        "probe_failed",
        0,
        failure_limit=3,
        failure_window_seconds=900,
    )
    assert after_reset.automation_disabled is False
    assert after_reset.failure_count == 1
    await coordinator.close()


@pytest.mark.parametrize(
    "field",
    [
        "executor_idle_fallback_seconds",
        "executor_idle_minimum_seconds",
        "executor_idle_maximum_seconds",
        "executor_minimum_ready_residency_seconds",
        "optional_idle_fallback_seconds",
        "optional_idle_minimum_seconds",
        "optional_idle_maximum_seconds",
        "optional_minimum_ready_residency_seconds",
    ],
)
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_idle_policy_limits_reject_non_positive_or_non_finite_values(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate({field: value})


@pytest.mark.parametrize("role_class", ["executor", "optional"])
def test_idle_policy_limits_require_minimum_fallback_maximum_order(
    role_class: str,
) -> None:
    prefix = f"{role_class}_idle"
    for values in (
        {f"{prefix}_minimum_seconds": 901, f"{prefix}_fallback_seconds": 900},
        {f"{prefix}_fallback_seconds": 901, f"{prefix}_maximum_seconds": 900},
    ):
        with pytest.raises(ValidationError, match="minimum.*fallback.*maximum"):
            Limits.model_validate(values)


def test_idle_policy_modes_separate_evidence_from_action_authority() -> None:
    module = lifecycle()
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=20,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )
    records = policy_usage_from_gaps([10.0] * 20)
    record = policy_record(module)

    disabled = module.calculate_idle_policy(
        "executor",
        "disabled",
        records,
        record,
        now=1_000.0,
        limits=limits,
        previous_mode="disabled",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=1,
    )
    observe = module.calculate_idle_policy(
        "executor",
        "observe",
        records,
        record,
        now=1_000.0,
        limits=limits,
        previous_mode="observe",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=1,
    )
    fixed = module.calculate_idle_policy(
        "executor",
        "fixed",
        records,
        record,
        now=1_000.0,
        limits=limits,
        previous_mode="fixed",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=1,
    )
    adaptive = module.calculate_idle_policy(
        "executor",
        "adaptive",
        records,
        record,
        now=1_000.0,
        limits=limits,
        previous_mode="adaptive",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=1,
    )

    assert (disabled.threshold_seconds, disabled.threshold_source) == (20.0, "disabled")
    assert disabled.next_consecutive_check_count == 0
    assert disabled.would_unload is False
    assert disabled.action_allowed is False
    assert disabled.reason == "mode_disabled"
    assert (observe.threshold_seconds, observe.threshold_source) == (15.0, "adaptive_p75")
    assert observe.would_unload is True
    assert observe.action_allowed is False
    assert (fixed.threshold_seconds, fixed.threshold_source) == (20.0, "fixed")
    assert fixed.would_unload is True
    assert fixed.action_allowed is True
    assert (adaptive.threshold_seconds, adaptive.threshold_source) == (
        15.0,
        "adaptive_p75",
    )
    assert adaptive.would_unload is True
    assert adaptive.action_allowed is True


def test_adaptive_policy_requires_twenty_positive_role_gaps() -> None:
    module = lifecycle()
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=20,
        executor_idle_maximum_seconds=100,
    )
    record = policy_record(module)

    sparse = module.calculate_idle_policy(
        "executor",
        "adaptive",
        policy_usage_from_gaps([10.0] * 19),
        record,
        now=1_000.0,
        limits=limits,
    )
    sufficient = module.calculate_idle_policy(
        "executor",
        "adaptive",
        policy_usage_from_gaps([10.0] * 20),
        record,
        now=1_000.0,
        limits=limits,
    )

    assert (sparse.sample_count, sparse.threshold_seconds, sparse.threshold_source) == (
        19,
        20.0,
        "sparse_fallback",
    )
    assert (
        sufficient.sample_count,
        sufficient.threshold_seconds,
        sufficient.threshold_source,
    ) == (20, 15.0, "adaptive_p75")


@pytest.mark.parametrize(
    ("gaps", "minimum", "fallback", "maximum", "expected"),
    [
        ([float(value) for value in range(1, 21)], 1.0, 20.0, 100.0, 22.875),
        ([1.0] * 20, 10.0, 20.0, 100.0, 10.0),
        ([1_000.0] * 20, 10.0, 20.0, 100.0, 100.0),
        ([10.0] * 19 + [1_000_000.0], 5.0, 20.0, 100.0, 15.0),
    ],
)
def test_adaptive_p75_uses_exact_interpolation_and_both_clamps(
    gaps: list[float],
    minimum: float,
    fallback: float,
    maximum: float,
    expected: float,
) -> None:
    module = lifecycle()
    limits = Limits(
        executor_idle_minimum_seconds=minimum,
        executor_idle_fallback_seconds=fallback,
        executor_idle_maximum_seconds=maximum,
    )

    decision = module.calculate_idle_policy(
        "executor",
        "adaptive",
        list(reversed(policy_usage_from_gaps(gaps))),
        policy_record(module),
        now=2_000_000.0,
        limits=limits,
    )

    assert decision.sample_count == 20
    assert decision.threshold_seconds == pytest.approx(expected)
    assert minimum <= decision.threshold_seconds <= maximum


def test_role_samples_are_sorted_separated_and_bounded_before_gap_calculation() -> None:
    module = lifecycle()
    limits = Limits(
        usage_sample_window=3,
        adaptive_minimum_samples=2,
        executor_idle_minimum_seconds=1,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=2_000,
        optional_idle_minimum_seconds=1,
        optional_idle_fallback_seconds=10,
        optional_idle_maximum_seconds=2_000,
    )
    records = [
        policy_usage(1.0, ("planner",)),
        policy_usage(1_000.0),
        policy_usage(10.0),
        policy_usage(10.0, ("planner",)),
        policy_usage(0.0),
        policy_usage(6.0, ("planner",)),
        policy_usage(20.0),
        policy_usage(3.0, ("planner",)),
    ]

    executor = module.calculate_idle_policy(
        "executor",
        "adaptive",
        records,
        policy_record(module),
        now=2_000.0,
        limits=limits,
    )
    planner = module.calculate_idle_policy(
        "planner",
        "adaptive",
        records,
        policy_record(module, "planner"),
        now=2_000.0,
        limits=limits,
    )

    assert (executor.sample_count, executor.threshold_seconds) == (2, pytest.approx(1_106.25))
    assert (planner.sample_count, planner.threshold_seconds) == (2, pytest.approx(5.625))


def test_minimum_residency_blocks_old_activity_and_never_used_ready_uses_ready_since() -> None:
    module = lifecycle()
    limits = Limits(
        optional_idle_minimum_seconds=10,
        optional_idle_fallback_seconds=50,
        optional_idle_maximum_seconds=100,
        optional_minimum_ready_residency_seconds=300,
    )

    too_new = module.calculate_idle_policy(
        "planner",
        "fixed",
        (),
        policy_record(module, "planner", ready_since=1_000.0, last_used_at=0.0),
        now=1_100.0,
        limits=limits,
        previous_consecutive_check_count=1,
    )
    never_used = module.calculate_idle_policy(
        "planner",
        "fixed",
        (),
        policy_record(module, "planner", ready_since=1_000.0, last_used_at=None),
        now=1_400.0,
        limits=limits,
    )

    assert (too_new.idle_seconds, too_new.residency_seconds) == (100.0, 100.0)
    assert too_new.next_consecutive_check_count == 0
    assert too_new.reason == "minimum_residency"
    assert (never_used.idle_seconds, never_used.residency_seconds) == (400.0, 400.0)
    assert never_used.next_consecutive_check_count == 1
    assert never_used.reason == "first_idle_check"


def test_idle_hysteresis_requires_two_checks_then_authorizes() -> None:
    module = lifecycle()
    limits = Limits(
        executor_idle_minimum_seconds=10,
        executor_idle_fallback_seconds=50,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=10,
    )
    record = policy_record(module)
    first = module.calculate_idle_policy("executor", "fixed", (), record, now=100.0, limits=limits)
    second = module.calculate_idle_policy(
        "executor",
        "fixed",
        (),
        record,
        now=101.0,
        limits=limits,
        previous_mode="fixed",
        previous_last_activity_at=0.0,
        previous_consecutive_check_count=first.next_consecutive_check_count,
    )

    assert (first.next_consecutive_check_count, first.would_unload, first.action_allowed) == (
        1,
        False,
        False,
    )
    assert first.reason == "first_idle_check"
    assert (second.next_consecutive_check_count, second.would_unload, second.action_allowed) == (
        2,
        True,
        True,
    )
    assert second.reason == "idle_confirmed"


@pytest.mark.parametrize(
    ("record", "now", "has_blockers", "previous_mode", "previous_activity", "reason"),
    [
        ("activity", 100.0, False, "fixed", 0.0, "activity_reset"),
        ("ready", 100.0, True, "fixed", 0.0, "blocked"),
        ("cold", 100.0, False, "fixed", 0.0, "state_not_ready"),
        ("below", 50.0, False, "fixed", 0.0, "below_threshold"),
        ("ready", 100.0, False, "adaptive", 0.0, "mode_changed"),
    ],
)
def test_idle_hysteresis_resets_on_activity_blocker_state_threshold_or_mode(
    record: str,
    now: float,
    has_blockers: bool,
    previous_mode: str,
    previous_activity: float,
    reason: str,
) -> None:
    module = lifecycle()
    limits = Limits(
        executor_idle_minimum_seconds=10,
        executor_idle_fallback_seconds=50,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=10,
    )
    lifecycle_record = (
        policy_record(module, state="cold", ready_since=None, last_used_at=None)
        if record == "cold"
        else policy_record(module, last_used_at=1.0 if record == "activity" else 0.0)
    )

    decision = module.calculate_idle_policy(
        "executor",
        "fixed",
        (),
        lifecycle_record,
        now=now,
        limits=limits,
        has_blockers=has_blockers,
        previous_mode=previous_mode,
        previous_last_activity_at=previous_activity,
        previous_consecutive_check_count=1,
    )

    assert decision.next_consecutive_check_count == 0
    assert decision.would_unload is False
    assert decision.action_allowed is False
    assert decision.reason == reason


def test_invalid_policy_times_and_config_never_produce_an_authorized_nonfinite_decision() -> None:
    module = lifecycle()
    record = policy_record(module, ready_since=200.0, last_used_at=200.0)
    for now in (-1.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            module.calculate_idle_policy("executor", "fixed", (), record, now=now, limits=Limits())

    invalid_limits = Limits.model_construct(executor_idle_fallback_seconds=float("inf"))
    with pytest.raises(ValueError):
        module.calculate_idle_policy(
            "executor", "fixed", (), record, now=100.0, limits=invalid_limits
        )

    from dgx_moa.usage import RequestUsageStart

    invalid_records = [
        RequestUsageStart.model_construct(accepted_at=value, roles_required=("executor",))
        for value in (-1.0, float("nan"), float("inf"), float("-inf"))
    ]
    decision = module.calculate_idle_policy(
        "executor",
        "adaptive",
        invalid_records,
        record,
        now=100.0,
        limits=Limits(),
        previous_consecutive_check_count=1,
    )

    assert decision.sample_count == 0
    assert decision.idle_seconds == 0.0
    assert decision.residency_seconds == 0.0
    assert decision.would_unload is False
    assert decision.action_allowed is False
    for field in (decision.threshold_seconds, decision.idle_seconds, decision.residency_seconds):
        assert field == field and abs(field) != float("inf")


def test_idle_policy_output_is_typed_bounded_and_content_free() -> None:
    module = lifecycle()
    sentinel = "SENTINEL_POLICY_CONTENT_723a55"
    record = policy_usage(0.0)
    record.session_id = sentinel

    decision = module.calculate_idle_policy(
        "executor",
        "fixed",
        (record,),
        policy_record(module),
        now=3_000.0,
        limits=Limits(),
    )

    assert isinstance(decision, module.IdlePolicyDecision)
    assert set(decision.model_dump()) == {
        "role",
        "mode",
        "threshold_seconds",
        "threshold_source",
        "sample_count",
        "idle_seconds",
        "residency_seconds",
        "next_consecutive_check_count",
        "would_unload",
        "action_allowed",
        "reason",
    }
    assert sentinel not in decision.model_dump_json()


@pytest.mark.parametrize(
    ("role", "mode", "has_blockers"),
    [
        ("unknown", "fixed", False),
        ("executor", "automatic", False),
        ("executor", "fixed", "SENTINEL_ARBITRARY_BLOCKER"),
    ],
)
def test_idle_policy_rejects_unbounded_role_mode_and_blocker_inputs(
    role: str, mode: str, has_blockers: object
) -> None:
    module = lifecycle()

    with pytest.raises(ValueError):
        module.calculate_idle_policy(
            role,
            mode,
            (),
            policy_record(module),
            now=100.0,
            limits=Limits(),
            has_blockers=has_blockers,
        )


@pytest.mark.parametrize("mode", ["disabled", "observe", "fixed", "adaptive"])
def test_lifecycle_modes_are_bounded(mode: str) -> None:
    assert Settings(auth_enabled=False, lifecycle_mode=mode).lifecycle_mode == mode


def test_invalid_lifecycle_mode_and_poll_interval_are_rejected() -> None:
    with pytest.raises(ValidationError, match="lifecycle_mode"):
        Settings(auth_enabled=False, lifecycle_mode="automatic")
    with pytest.raises(ValidationError, match="lifecycle_poll_seconds"):
        Settings(auth_enabled=False, lifecycle_poll_seconds=0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_lifecycle_poll_interval_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValidationError, match="lifecycle_poll_seconds"):
        Settings(auth_enabled=False, lifecycle_poll_seconds=value)


@pytest.mark.parametrize(
    ("unit_map", "message"),
    [
        ({"unknown": "dgx-moa-dev-unknown.service"}, "unknown lifecycle role"),
        ({"executor": "../executor.service"}, "invalid systemd unit"),
        ({"executor": "executor target"}, "invalid systemd unit"),
        (
            {
                "executor": "dgx-moa-dev-shared.service",
                "planner": "dgx-moa-dev-shared.service",
            },
            "duplicate lifecycle unit",
        ),
    ],
)
def test_lifecycle_unit_map_rejects_unknown_unsafe_and_duplicate_units(
    unit_map: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(auth_enabled=False, lifecycle_unit_map=unit_map)


@pytest.mark.parametrize(
    "unit",
    ["dgx-moa-executor.service", "custom-executor.service", "dgx-moa-candidate.service"],
)
def test_non_main_runtime_requires_isolated_dev_units(unit: str) -> None:
    with pytest.raises(ValidationError, match="dgx-moa-dev"):
        Settings(
            auth_enabled=False,
            runtime_channel="dev",
            lifecycle_unit_map={"executor": unit},
        )


def test_main_and_isolated_dev_lifecycle_units_are_accepted() -> None:
    main = Settings(
        auth_enabled=False,
        runtime_channel="main",
        lifecycle_unit_map={"executor": "dgx-moa-executor.service"},
    )
    dev = Settings(
        auth_enabled=False,
        runtime_channel="dev",
        lifecycle_unit_map={"executor": "dgx-moa-dev-executor.service"},
    )

    assert main.lifecycle_unit_map == {"executor": "dgx-moa-executor.service"}
    assert dev.lifecycle_unit_map == {"executor": "dgx-moa-dev-executor.service"}


def test_lifecycle_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv("DGX_MOA_LIFECYCLE_MODE", "observe")
    monkeypatch.setenv("DGX_MOA_LIFECYCLE_POLL_SECONDS", "2.5")
    monkeypatch.setenv("DGX_MOA_LIFECYCLE_UNIT_MAP", '{"executor":"dgx-moa-dev-executor.service"}')

    settings = load_settings(config)

    assert settings.lifecycle_mode == "observe"
    assert settings.lifecycle_poll_seconds == 2.5
    assert settings.lifecycle_unit_map == {"executor": "dgx-moa-dev-executor.service"}


def test_schema_persists_every_lifecycle_field_without_changing_usage_tables(
    tmp_path: Path,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    path = tmp_path / "state.db"
    UsageStore(path)
    store = module.LifecycleStore(path, ("executor", "planner"), clock=lambda: 100.0)

    executor = store.get("executor")
    assert isinstance(executor, module.LifecycleRecord)
    assert executor.model_dump() == {
        "role": "executor",
        "generation": 0,
        "state": "cold",
        "transition_id": executor.transition_id,
        "transitioned_at": 100.0,
        "updated_at": 100.0,
        "ready_since": None,
        "last_used_at": None,
        "load_started_at": None,
        "ready_at": None,
        "last_requested_at": None,
        "last_completed_at": None,
        "failure_class": None,
        "failure_detail": None,
        "retry_count": 0,
        "active_request_count": 0,
        "open_stream_count": 0,
        "continuation_lease_count": 0,
        "evaluation_guard": False,
        "profile_guard": False,
        "progress_value": None,
        "weight_load_percent": None,
        "overall_load_percent": None,
        "progress_quality": None,
        "eta_seconds": None,
        "last_load_duration_seconds": None,
        "last_unload_duration_seconds": None,
        "memory_before_bytes": None,
        "memory_after_bytes": None,
        "service_unit": None,
        "last_error_class": None,
        "last_error_message_redacted": None,
    }
    UUID(executor.transition_id)

    with sqlite3.connect(path) as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        columns = {row[1] for row in database.execute("PRAGMA table_info(model_lifecycle)")}
        lease_columns = {
            row[1] for row in database.execute("PRAGMA table_info(model_lifecycle_leases)")
        }

    assert tables == {
        "request_usage",
        "role_request_usage",
        "lifecycle_samples",
        "lifecycle_failure_events",
        "lifecycle_automation",
        "model_lifecycle",
        "model_lifecycle_decisions",
        "model_lifecycle_leases",
    }
    assert columns == set(module.LifecycleRecord.model_fields)
    assert lease_columns == set(module.LifecycleLease.model_fields)


def test_latest_idle_decision_is_migration_safe_typed_and_content_free(tmp_path: Path) -> None:
    module = lifecycle()
    path = tmp_path / "state.db"
    store = module.LifecycleStore(path, ("executor",), clock=lambda: 100.0)
    sentinel = "SENTINEL_DECISION_CONTENT_882fab"
    usage = policy_usage(0.0)
    usage.session_id = sentinel
    decision = module.calculate_idle_policy(
        "executor",
        "fixed",
        (usage,),
        policy_record(module),
        now=100.0,
        limits=Limits(
            executor_idle_minimum_seconds=5,
            executor_idle_fallback_seconds=20,
            executor_idle_maximum_seconds=100,
            executor_minimum_ready_residency_seconds=1,
        ),
    )

    first = store.persist_decision(decision)
    duplicate = store.persist_decision(decision)
    restarted = module.LifecycleStore(path, ("executor",), clock=lambda: 101.0)

    assert duplicate == first
    assert restarted.latest_decision("executor") == first
    assert restarted.latest_decisions() == {"executor": first}
    assert first.model_dump() == decision.model_dump() | {"decided_at": 100.0}
    persisted = b"".join(
        candidate.read_bytes() for candidate in (path, Path(f"{path}-wal")) if candidate.exists()
    )
    assert sentinel.encode() not in persisted


def test_unload_admission_atomically_rechecks_transition_and_every_blocker(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor",), clock=lambda: 100.0)
    ready = reach(store, "executor", "ready")
    request_id = "d7c1a25f-3f6e-4356-b13c-96bbbd2c447e"
    active = store.acquire_request_leases(
        request_id,
        ("executor",),
        kind="active_request",
    )

    assert (
        store.admit_unload(
            "executor",
            expected_transition_id=ready.transition_id,
            memory_before_bytes=1_000,
        )
        is None
    )
    assert store.get("executor").state == "ready"

    store.release_leases(lease.lease_id for lease in active)
    assert (
        store.admit_unload(
            "executor",
            expected_transition_id=ready.transition_id,
            memory_before_bytes=1_000,
        )
        is None
    )
    ready = store.get("executor")
    admitted = store.admit_unload(
        "executor",
        expected_transition_id=ready.transition_id,
        expected_ready_since=ready.ready_since,
        expected_last_used_at=ready.last_used_at,
        memory_before_bytes=1_000,
    )

    assert admitted is not None
    assert admitted.state == "unloading"
    assert admitted.memory_before_bytes == 1_000
    assert (
        store.admit_unload(
            "executor",
            expected_transition_id=ready.transition_id,
            memory_before_bytes=1_000,
        )
        is None
    )


@pytest.mark.parametrize(
    "blocker",
    ["open_stream", "continuation", "evaluation_guard", "profile_guard"],
)
def test_unload_admission_rejects_each_live_blocker(tmp_path: Path, blocker: str) -> None:
    module = lifecycle()
    store = module.LifecycleStore(
        tmp_path / f"{blocker}.db",
        ("executor",),
        clock=lambda: 100.0,
    )
    ready = reach(store, "executor", "ready")
    request_id = "d0fb4c14-965a-484f-9265-6976db828fdd"
    if blocker == "open_stream":
        store.acquire_request_leases(request_id, ("executor",), kind="open_stream")
    elif blocker == "continuation":
        store.refresh_continuation(
            request_id,
            "executor",
            module.continuation_correlation("blocked-session"),
            expires_at=200.0,
        )
    else:
        store.set_guard(
            "executor",
            blocker,
            True,
            expected_transition_id=ready.transition_id,
        )

    assert (
        store.admit_unload(
            "executor",
            expected_transition_id=ready.transition_id,
            memory_before_bytes=1_000,
        )
        is None
    )
    assert store.get("executor").state == "ready"


def test_active_leases_are_idempotent_and_counted_exactly_per_role(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor", "planner"))
    request_id = "82b630ac-9a15-4fc2-b258-31aaf47e2140"

    acquired = store.acquire_request_leases(
        request_id,
        ("executor", "planner"),
        kind="active_request",
    )
    duplicate = store.acquire_request_leases(
        request_id,
        ("executor", "planner"),
        kind="active_request",
    )

    assert duplicate == acquired
    assert len({lease.lease_id for lease in acquired}) == 2
    assert {lease.role for lease in acquired} == {"executor", "planner"}
    assert all(lease.kind == "active_request" for lease in acquired)
    assert store.get("executor").active_request_count == 1
    assert store.get("planner").active_request_count == 1

    store.release_leases(lease.lease_id for lease in acquired)
    store.release_leases(lease.lease_id for lease in acquired)

    assert store.get("executor").active_request_count == 0
    assert store.get("planner").active_request_count == 0


def test_active_release_marks_activity_once_at_terminal_cleanup(tmp_path: Path) -> None:
    module = lifecycle()
    clock = [100.0]
    store = module.LifecycleStore(
        tmp_path / "activity.db",
        ("executor", "planner"),
        clock=lambda: clock[0],
    )
    leases = store.acquire_request_leases(
        "e5078c84-3bb3-4d28-bb02-da4ea0fda769",
        ("executor", "planner"),
        kind="active_request",
    )
    assert store.get("executor").last_requested_at == 100.0
    assert store.get("planner").last_requested_at == 100.0

    clock[0] = 125.0
    store.release_leases(lease.lease_id for lease in leases)
    assert store.get("executor").last_used_at == 125.0
    assert store.get("planner").last_used_at == 125.0
    assert store.get("executor").last_completed_at == 125.0
    assert store.get("planner").last_completed_at == 125.0

    clock[0] = 150.0
    store.release_leases(lease.lease_id for lease in leases)
    assert store.get("executor").last_used_at == 125.0
    assert store.get("planner").last_used_at == 125.0


@pytest.mark.asyncio
async def test_coordinator_acquires_multiple_ready_roles_atomically_or_none(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "coordinated.db", ("executor", "planner"))
    executor = reach(store, "executor", "ready")
    reach(store, "planner", "ready")
    coordinator = module.LifecycleCoordinator(
        store,
        module.FakeLifecycleDriver({"executor": "active", "planner": "active"}),
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
    )

    leases = await coordinator.acquire_request_leases(
        "48d1c9a5-1bc0-4756-8894-89d76b2e767c",
        ("executor", "planner"),
        kind="active_request",
        require_ready=True,
    )
    assert {lease.role for lease in leases} == {"executor", "planner"}
    await coordinator.release_request_leases(lease.lease_id for lease in leases)
    executor = store.get("executor")
    admitted = store.admit_unload(
        "executor",
        expected_transition_id=executor.transition_id,
        expected_ready_since=executor.ready_since,
        expected_last_used_at=executor.last_used_at,
        memory_before_bytes=1_000,
    )
    assert admitted is not None

    with pytest.raises(module.LifecycleNotReadyError) as error:
        await coordinator.acquire_request_leases(
            "53f4c311-c5a5-4f44-890e-b6d7edba3987",
            ("planner", "executor"),
            kind="active_request",
            require_ready=True,
        )

    assert error.value.record.state == "unloading"
    assert store.get("planner").active_request_count == 0
    await coordinator.close()


def test_stream_and_continuation_leases_are_content_free_and_expire(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    clock = [100.0]
    path = tmp_path / "state.db"
    store = module.LifecycleStore(path, ("executor",), clock=lambda: clock[0])
    request_id = "6e3737e7-8142-4e56-a2f5-2a93ed200d13"
    raw_session = "SENTINEL_RAW_SESSION_982a54"
    owner = module.continuation_correlation(raw_session)

    stream = store.acquire_request_leases(
        request_id,
        ("executor",),
        kind="open_stream",
    )
    continuation = store.refresh_continuation(
        request_id,
        "executor",
        owner,
        expires_at=130.0,
    )
    refreshed = store.refresh_continuation(
        request_id,
        "executor",
        owner,
        expires_at=130.0,
    )

    assert refreshed == continuation
    assert len(owner) == 64
    assert continuation.expires_at == 130.0
    assert store.get("executor").open_stream_count == 1
    assert store.get("executor").continuation_lease_count == 1
    persisted = b"".join(
        candidate.read_bytes() for candidate in (path, Path(f"{path}-wal")) if candidate.exists()
    )
    assert raw_session.encode() not in persisted

    store.release_leases(lease.lease_id for lease in stream)
    clock[0] = 131.0
    assert store.prune_expired_continuations() == 1
    assert store.get("executor").open_stream_count == 0
    assert store.get("executor").continuation_lease_count == 0


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_invalid_lease_clock_never_reaches_sql(tmp_path: Path, value: float) -> None:
    module = lifecycle()
    clock = [100.0]
    store = module.LifecycleStore(tmp_path / "state.db", ("executor",), clock=lambda: clock[0])
    clock[0] = value

    with pytest.raises(ValueError):
        store.acquire_request_leases(
            "fc087974-e48b-4f3c-a95f-059c7027ce33",
            ("executor",),
            kind="active_request",
        )

    with sqlite3.connect(store.path) as database:
        lease_count = database.execute("SELECT COUNT(*) FROM model_lifecycle_leases").fetchone()
    assert lease_count == (0,)
    assert store.get("executor").active_request_count == 0


def test_unload_blockers_cover_every_lease_and_uncertain_guard(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor",), clock=lambda: 100.0)
    request_id = "97722e98-6549-43e4-bad6-15b356001faf"
    owner = module.continuation_correlation("guarded-session")
    transition_id = store.get("executor").transition_id
    active = store.acquire_request_leases(
        request_id,
        ("executor",),
        kind="active_request",
    )
    stream = store.acquire_request_leases(
        request_id,
        ("executor",),
        kind="open_stream",
    )
    store.refresh_continuation(
        request_id,
        "executor",
        owner,
        expires_at=130.0,
    )
    store.set_guard(
        "executor",
        "evaluation_guard",
        True,
        expected_transition_id=transition_id,
    )
    store.set_guard(
        "executor",
        "profile_guard",
        True,
        expected_transition_id=transition_id,
    )

    assert store.unload_blockers("executor") == frozenset(
        {
            "active_request",
            "open_stream",
            "continuation",
            "evaluation_guard",
            "profile_guard",
        }
    )

    store.release_leases(lease.lease_id for lease in (*active, *stream))
    store.release_continuation("executor", owner)
    store.set_guard(
        "executor",
        "evaluation_guard",
        False,
        expected_transition_id=transition_id,
    )
    store.set_guard(
        "executor",
        "profile_guard",
        False,
        expected_transition_id=transition_id,
    )

    assert store.unload_blockers("executor") == frozenset()


def test_multi_role_guard_claim_is_atomic_when_a_guard_is_already_owned(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "guard-claim.db", ("executor", "planner"))
    planner = store.get("planner")
    store.set_guard(
        "planner",
        "profile_guard",
        True,
        expected_transition_id=planner.transition_id,
    )

    with pytest.raises(module.LifecycleError, match="already active"):
        store.claim_guards(("executor", "planner"), "profile_guard")

    assert store.get("executor").profile_guard is False
    assert store.get("planner").profile_guard is True


def test_guard_release_preserves_uncertainty_after_a_transition(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "guard-stale.db", ("executor", "planner"))
    executor = reach(store, "executor", "ready")
    ownership = store.claim_guards(("executor", "planner"), "profile_guard")
    store.transition(
        "executor",
        "unloading",
        expected_transition_id=executor.transition_id,
    )

    store.release_guards(ownership, "profile_guard")

    assert store.get("executor").profile_guard is True
    assert store.get("planner").profile_guard is False


def test_restart_recovery_removes_orphans_and_preserves_live_guards(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    clock = [100.0]
    path = tmp_path / "state.db"
    roles = ("executor", "planner")
    store = module.LifecycleStore(path, roles, clock=lambda: clock[0])
    request_id = "984088f6-d602-43f1-9536-f19cfebc3a1c"
    store.acquire_request_leases(request_id, roles, kind="active_request")
    store.acquire_request_leases(request_id, ("executor",), kind="open_stream")
    store.refresh_continuation(
        request_id,
        "executor",
        module.continuation_correlation("expired-session"),
        expires_at=110.0,
    )
    store.refresh_continuation(
        request_id,
        "planner",
        module.continuation_correlation("live-session"),
        expires_at=200.0,
    )
    executor = store.get("executor")
    planner = store.get("planner")
    store.set_guard(
        "executor",
        "evaluation_guard",
        True,
        expected_transition_id=executor.transition_id,
    )
    store.set_guard(
        "planner",
        "profile_guard",
        True,
        expected_transition_id=planner.transition_id,
    )

    clock[0] = 120.0
    restarted = module.LifecycleStore(path, roles, clock=lambda: clock[0])
    recovered = restarted.recover_leases()

    assert recovered["executor"].active_request_count == 0
    assert recovered["executor"].open_stream_count == 0
    assert recovered["executor"].continuation_lease_count == 0
    assert recovered["executor"].evaluation_guard is True
    assert recovered["planner"].active_request_count == 0
    assert recovered["planner"].continuation_lease_count == 1
    assert recovered["planner"].profile_guard is True
    assert restarted.unload_blockers("executor") == frozenset({"evaluation_guard"})
    assert restarted.unload_blockers("planner") == frozenset({"continuation", "profile_guard"})


def test_transition_graph_is_explicit_and_exhaustive(tmp_path: Path) -> None:
    module = lifecycle()
    assert set(module.LIFECYCLE_STATES) == STATES
    assert {state: set(targets) for state, targets in module.TRANSITIONS.items()} == TRANSITIONS

    for source in STATES:
        for target in STATES - {source}:
            store = module.LifecycleStore(
                tmp_path / f"{source}-{target}.db", ("executor",), clock=lambda: 200.0
            )
            before = reach(store, "executor", source)
            if target in TRANSITIONS[source]:
                after = store.transition(
                    "executor", target, expected_transition_id=before.transition_id
                )
                assert after.state == target
                assert after.transition_id != before.transition_id
                UUID(after.transition_id)
            else:
                with pytest.raises(module.InvalidTransitionError):
                    store.transition(
                        "executor", target, expected_transition_id=before.transition_id
                    )
                assert store.get("executor") == before


def test_updates_and_transitions_reject_stale_ids_atomically(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor", "planner"))
    initial = store.get("executor")
    queued = store.transition(
        "executor", "load_queued", expected_transition_id=initial.transition_id
    )
    updated = store.update(
        "executor",
        queued.transition_id,
        progress_value=25.0,
        progress_quality="estimated",
        retry_count=1,
    )

    assert updated.transition_id == queued.transition_id
    assert updated.progress_value == 25.0
    assert updated.retry_count == 1
    with pytest.raises(module.StaleTransitionError):
        store.update("executor", initial.transition_id, progress_value=99.0)
    with pytest.raises(module.StaleTransitionError):
        store.transition(
            "executor", "process_starting", expected_transition_id=initial.transition_id
        )
    assert store.get("executor") == updated
    assert store.get("planner").state == "cold"


@pytest.mark.parametrize(
    "field",
    [
        "ready_since",
        "last_used_at",
        "progress_value",
        "eta_seconds",
        "last_load_duration_seconds",
        "last_unload_duration_seconds",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_lifecycle_updates_roll_back(tmp_path: Path, field: str, value: float) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / f"{field}-{value}.db", ("executor",))
    before = store.get("executor")

    with pytest.raises(ValidationError):
        store.update("executor", before.transition_id, **{field: value})

    assert store.get("executor") == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_clock_transition_rolls_back(tmp_path: Path, value: float) -> None:
    module = lifecycle()
    clock = [100.0]
    store = module.LifecycleStore(
        tmp_path / f"clock-{value}.db", ("executor",), clock=lambda: clock[0]
    )
    before = store.get("executor")
    clock[0] = value

    with pytest.raises(ValidationError):
        store.transition("executor", "load_queued", expected_transition_id=before.transition_id)

    assert store.get("executor") == before


def test_failure_is_sanitized_and_role_changes_are_isolated(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor", "reviewer"))
    queued = reach(store, "executor", "load_queued")
    failed = store.transition(
        "executor",
        "failed",
        expected_transition_id=queued.transition_id,
        failure_class="Start Timeout!",
        failure_detail="unsafe\ncontrol\x00" + "x" * 400,
    )

    assert failed.failure_class == "start_timeout"
    assert failed.failure_detail is not None
    assert "\n" not in failed.failure_detail
    assert "\x00" not in failed.failure_detail
    assert len(failed.failure_detail) <= 256
    assert store.get("reviewer").state == "cold"


def test_restart_reconciliation_uses_driver_reality(tmp_path: Path) -> None:
    module = lifecycle()
    roles = ("executor", "planner", "reviewer", "reasoner")
    path = tmp_path / "state.db"
    store = module.LifecycleStore(path, roles)
    old = {
        "executor": reach(store, "executor", "ready"),
        "planner": reach(store, "planner", "loading_weights"),
        "reviewer": reach(store, "reviewer", "ready"),
        "reasoner": store.get("reasoner"),
    }
    store = module.LifecycleStore(path, roles)
    driver = module.FakeLifecycleDriver(
        {
            "executor": "inactive",
            "planner": "active",
            "reviewer": "failed",
            "reasoner": "inactive",
        }
    )

    records = store.reconcile(driver)

    assert {role: record.state for role, record in records.items()} == {
        "executor": "cold",
        "planner": "process_starting",
        "reviewer": "failed",
        "reasoner": "cold",
    }
    assert records["reasoner"].transition_id == old["reasoner"].transition_id
    for role in ("executor", "planner", "reviewer"):
        assert records[role].transition_id != old[role].transition_id
    assert driver.calls == [
        ("status", "executor"),
        ("status", "planner"),
        ("status", "reviewer"),
        ("status", "reasoner"),
    ]


def test_fake_driver_is_exact_role_only() -> None:
    module = lifecycle()
    driver = module.FakeLifecycleDriver(
        {"executor": "inactive"}, progress={"executor": ("one", "two")}
    )

    driver.start("executor")
    assert driver.status("executor") == "active"
    cursor = driver.capture_progress_cursor("executor")
    assert driver.progress("executor", cursor) == ("one", "two")
    driver.stop("executor")
    assert driver.status("executor") == "inactive"
    with pytest.raises(module.UnknownRoleError):
        driver.start("planner")


def test_systemd_driver_uses_only_exact_argument_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = lifecycle()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        if "show" in args:
            stdout = "active\nrunning\n"
        elif "--show-cursor" in args:
            stdout = "-- cursor: s=exact123;i=4\n"
        else:
            stdout = "one\ntwo\nthree\nfour\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    units = {"executor": "dgx-moa-dev-executor.service"}
    driver = module.SystemdLifecycleDriver(units, timeout_seconds=7.0, journal_lines=3)
    units["executor"] = "changed.service"

    assert driver.status("executor") == "active"
    driver.start("executor")
    driver.stop("executor")
    cursor = driver.capture_progress_cursor("executor")
    assert driver.progress("executor", cursor) == ("two", "three", "four")

    assert [args for args, _ in calls] == [
        [
            "systemctl",
            "--user",
            "show",
            "dgx-moa-dev-executor.service",
            "--property=ActiveState",
            "--property=SubState",
            "--value",
        ],
        ["systemctl", "--user", "start", "dgx-moa-dev-executor.service"],
        ["systemctl", "--user", "stop", "dgx-moa-dev-executor.service"],
        [
            "journalctl",
            "--user",
            "-u",
            "dgx-moa-dev-executor.service",
            "--no-pager",
            "-n",
            "0",
            "--show-cursor",
        ],
        [
            "journalctl",
            "--user",
            "-u",
            "dgx-moa-dev-executor.service",
            "--no-pager",
            "-n",
            "3",
            "--after-cursor",
            "s=exact123;i=4",
            "--output=cat",
        ],
    ]
    assert all(
        kwargs == {"capture_output": True, "text": True, "timeout": 7.0, "check": False}
        for _, kwargs in calls
    )
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_systemd_driver_uses_global_cursor_for_never_started_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = lifecycle()
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        output = (
            "-- No entries --\n"
            if "-u" in args
            else "-- No entries --\n-- cursor: s=global123;i=5\n"
        )
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    assert driver.capture_progress_cursor("executor") == "s=global123;i=5"
    assert calls == [
        [
            "journalctl",
            "--user",
            "-u",
            "dgx-moa-dev-executor.service",
            "--no-pager",
            "-n",
            "0",
            "--show-cursor",
        ],
        ["journalctl", "--user", "--no-pager", "-n", "0", "--show-cursor"],
    ]


def test_systemd_progress_is_scoped_to_a_valid_bounded_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = lifecycle()
    calls: list[list[str]] = []
    cursor = "s=abc123;i=4;b=def456"

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if "--show-cursor" in args:
            stdout = f"-- cursor: {cursor}\n"
        elif "--after-cursor" in args:
            stdout = "Loading safetensors checkpoint shards: 2/4\n"
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    driver = module.SystemdLifecycleDriver(
        {"executor": "dgx-moa-dev-executor.service"}, journal_lines=3
    )

    captured = driver.capture_progress_cursor("executor")
    lines = driver.progress("executor", captured)
    progress = module.parse_load_progress(lines)

    assert captured == cursor
    assert progress.state == "loading_weights"
    assert progress.weight_load_percent == 50.0
    assert calls == [
        [
            "journalctl",
            "--user",
            "-u",
            "dgx-moa-dev-executor.service",
            "--no-pager",
            "-n",
            "0",
            "--show-cursor",
        ],
        [
            "journalctl",
            "--user",
            "-u",
            "dgx-moa-dev-executor.service",
            "--no-pager",
            "-n",
            "3",
            "--after-cursor",
            cursor,
            "--output=cat",
        ],
    ]


@pytest.mark.parametrize(
    "output",
    [
        "",
        "-- cursor: unsafe cursor\n",
        "-- cursor: " + "x" * 1_025 + "\n",
        "-- cursor: one\n-- cursor: two\n",
    ],
)
def test_systemd_driver_rejects_malformed_progress_cursor(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    module = lifecycle()

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.LifecycleDriverError) as raised:
        driver.capture_progress_cursor("executor")
    assert raised.value.operation == "cursor"
    assert raised.value.kind == "malformed_output"


def test_systemd_driver_rejects_unsafe_supplied_cursor_without_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = lifecycle()
    calls: list[object] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.LifecycleDriverError) as raised:
        driver.progress("executor", "unsafe cursor")
    assert raised.value.operation == "progress"
    assert raised.value.kind == "malformed_output"
    assert calls == []


@pytest.mark.parametrize(
    "method", ["status", "start", "stop", "capture_progress_cursor", "progress"]
)
def test_systemd_driver_rejects_unknown_roles_without_running(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    module = lifecycle()
    calls: list[object] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.UnknownRoleError):
        if method == "progress":
            driver.progress("planner", "s=safe")
        else:
            getattr(driver, method)("planner")
    assert calls == []


@pytest.mark.parametrize("operation", ["status", "start", "stop", "cursor", "progress"])
def test_systemd_driver_converts_timeout_to_safe_typed_error(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    module = lifecycle()

    def timeout(args: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(args, 1.0, stderr="secret-stderr")

    monkeypatch.setattr(module.subprocess, "run", timeout)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.LifecycleDriverError) as raised:
        if operation == "cursor":
            driver.capture_progress_cursor("executor")
        elif operation == "progress":
            driver.progress("executor", "s=safe")
        else:
            getattr(driver, operation)("executor")
    assert raised.value.kind == "timeout"
    assert raised.value.operation == operation
    assert "systemctl" not in str(raised.value)
    assert "journalctl" not in str(raised.value)
    assert "secret" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    formatted = "".join(traceback.format_exception(raised.value))
    for secret in (
        "systemctl",
        "journalctl",
        "dgx-moa-dev-executor.service",
        "secret-stderr",
    ):
        assert secret not in formatted


@pytest.mark.parametrize("operation", ["status", "start", "stop", "cursor", "progress"])
def test_systemd_driver_converts_nonzero_to_safe_typed_error(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    module = lifecycle()

    def nonzero(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="secret-stderr")

    monkeypatch.setattr(module.subprocess, "run", nonzero)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.LifecycleDriverError) as raised:
        if operation == "cursor":
            driver.capture_progress_cursor("executor")
        elif operation == "progress":
            driver.progress("executor", "s=safe")
        else:
            getattr(driver, operation)("executor")
    assert raised.value.kind == "command_failed"
    assert raised.value.operation == operation
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("output", ["", "active\n", "mystery\nrunning\n"])
def test_systemd_status_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    module = lifecycle()

    def malformed(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(module.subprocess, "run", malformed)
    driver = module.SystemdLifecycleDriver({"executor": "dgx-moa-dev-executor.service"})

    with pytest.raises(module.LifecycleDriverError) as raised:
        driver.status("executor")
    assert raised.value.kind == "malformed_output"


@pytest.mark.parametrize(
    ("timeout_seconds", "journal_lines"),
    [
        (0.0, 10),
        (-1.0, 10),
        (float("nan"), 10),
        (float("inf"), 10),
        (float("-inf"), 10),
        (1.0, 0),
        (1.0, 1001),
    ],
)
def test_systemd_driver_bounds_timeout_and_progress_lines(
    timeout_seconds: float, journal_lines: int
) -> None:
    module = lifecycle()
    with pytest.raises(ValueError):
        module.SystemdLifecycleDriver(
            {"executor": "dgx-moa-dev-executor.service"},
            timeout_seconds=timeout_seconds,
            journal_lines=journal_lines,
        )


def test_progress_parser_prefers_measured_bytes_over_shards() -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        (
            "Loading safetensors checkpoint shards: 2/4",
            "Loading model weights: 75/100 bytes",
        )
    )

    assert progress.state == "loading_weights"
    assert progress.weight_load_percent == 75.0
    assert progress.progress_quality == "measured_bytes"


def test_progress_parser_measures_checkpoint_shards() -> None:
    module = lifecycle()

    progress = module.parse_load_progress(("Loading safetensors checkpoint shards: 3/8",))

    assert progress.state == "loading_weights"
    assert progress.weight_load_percent == 37.5
    assert progress.progress_quality == "measured_shards"


def test_progress_parser_rejects_nonfinite_numeric_overflow() -> None:
    module = lifecycle()
    huge = "9" * 500

    progress = module.parse_load_progress((f"Loading model weights: {huge}/{huge} bytes",))

    assert progress.weight_load_percent is None
    assert progress.progress_quality == "unavailable"


@pytest.mark.parametrize(
    ("line", "expected_state"),
    [
        ("Starting engine initialization", "initializing_engine"),
        ("Warming up model runner", "warming_up"),
    ],
)
def test_progress_parser_recognizes_post_weight_stages(line: str, expected_state: str) -> None:
    module = lifecycle()

    progress = module.parse_load_progress((line,), previous_percent=82.0)

    assert progress.state == expected_state
    assert progress.weight_load_percent == 100.0
    assert progress.progress_quality == "measured_phase"


@pytest.mark.parametrize(
    (
        "lines",
        "previous_percent",
        "previous_quality",
        "expected_state",
        "expected_quality",
    ),
    [
        (
            ("Loading safetensors checkpoint shards: 4/4", "Warming up model runner"),
            None,
            None,
            "warming_up",
            "measured_shards",
        ),
        (
            ("Starting engine initialization",),
            100.0,
            "measured_bytes",
            "initializing_engine",
            "measured_bytes",
        ),
        (
            ("Loading safetensors checkpoint shards: 1/4", "Warming up model runner"),
            None,
            None,
            "warming_up",
            "measured_phase",
        ),
    ],
)
def test_post_weight_stage_preserves_only_measured_complete_progress(
    lines: tuple[str, ...],
    previous_percent: float | None,
    previous_quality: str | None,
    expected_state: str,
    expected_quality: str,
) -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        lines,
        previous_percent=previous_percent,
        previous_quality=previous_quality,
    )

    assert progress.state == expected_state
    assert progress.weight_load_percent == 100.0
    assert progress.progress_quality == expected_quality


def test_progress_parser_ignores_malformed_ambiguous_and_unbounded_input() -> None:
    module = lifecycle()
    lines = tuple("x" * 10_000 for _ in range(2_000)) + (
        "Loading model weights: 5/0 bytes",
        "Loading safetensors checkpoint shards: two/four",
        "75% complete",
    )

    progress = module.parse_load_progress(lines)

    assert progress.state == "loading_weights"
    assert progress.weight_load_percent is None
    assert progress.progress_quality == "unavailable"


def test_progress_parser_never_decreases_weight_progress() -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        ("Loading safetensors checkpoint shards: 1/4",), previous_percent=60.0
    )

    assert progress.weight_load_percent == 60.0
    assert progress.progress_quality == "measured_shards"


def test_progress_parser_does_not_erase_an_earlier_valid_measurement() -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        (
            "Loading model weights: 40/100 bytes",
            "Loading model weights: 5/0 bytes",
        )
    )

    assert progress.weight_load_percent == 40.0
    assert progress.progress_quality == "measured_bytes"


def test_progress_parser_never_regresses_from_warmup_to_engine_initialization() -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        (
            "Warming up model runner",
            "Starting engine initialization",
        )
    )

    assert progress.state == "warming_up"
    assert progress.weight_load_percent == 100.0


@pytest.mark.parametrize(
    "lines",
    [(), ("Loading model weights: 5/0 bytes", "checkpoint shards: invalid")],
)
def test_unavailable_progress_preserves_prior_measurement(lines: tuple[str, ...]) -> None:
    module = lifecycle()

    progress = module.parse_load_progress(
        lines,
        previous_percent=60.0,
        previous_quality="measured_shards",
    )

    assert progress.state == "loading_weights"
    assert progress.weight_load_percent == 60.0
    assert progress.progress_quality == "measured_shards"


@pytest.mark.asyncio
async def test_coordinator_preserves_prior_progress_when_new_logs_are_invalid(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    blocked = asyncio.Event()
    second_poll = asyncio.Event()
    sleep_calls = 0
    store = module.LifecycleStore(tmp_path / "preserve-progress.db", ("executor",))
    driver = module.FakeLifecycleDriver(
        {"executor": "inactive"},
        progress={"executor": ("Loading safetensors checkpoint shards: 3/5",)},
    )

    async def health_probe(role: str) -> bool:
        return False

    async def sleeper(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            driver._progress["executor"] = ("checkpoint shards: invalid",)
            return
        second_poll.set()
        await blocked.wait()

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=sleeper,
    )

    await coordinator.ensure_ready("executor")
    await asyncio.wait_for(second_poll.wait(), timeout=1.0)
    record = store.get("executor")

    assert record.progress_value == 60.0
    assert record.overall_load_percent == 41.0
    assert record.progress_quality == "measured_shards"
    await coordinator.close()


@pytest.mark.asyncio
async def test_progress_parser_exception_does_not_fail_a_healthy_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "parser-exception.db", ("executor",))
    driver = module.FakeLifecycleDriver({"executor": "inactive"})

    def fail_parser(*args: object, **kwargs: object) -> None:
        raise ValueError("untrusted journal parser failure")

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return True

    monkeypatch.setattr(module, "parse_load_progress", fail_parser)
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
    )

    await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    record = store.get("executor")

    assert record.state == "ready"
    assert record.progress_value == 100.0
    assert record.progress_quality == "estimated"
    assert record.failure_class is None
    await coordinator.close()


@pytest.mark.asyncio
async def test_twenty_concurrent_cold_checks_share_one_load(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    clock = [100.0]
    release_poll = asyncio.Event()
    store = module.LifecycleStore(tmp_path / "state.db", ("executor",), clock=lambda: clock[0])
    driver = module.FakeLifecycleDriver({"executor": "inactive"})

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return False

    async def sleeper(seconds: float) -> None:
        assert seconds == 0.25
        await release_poll.wait()

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: clock[0],
        sleeper=sleeper,
    )

    checks = await asyncio.gather(*(coordinator.ensure_ready("executor") for _ in range(20)))
    for _ in range(1_000):
        if ("start", "executor") in driver.calls:
            break
        await asyncio.sleep(0.001)

    assert sum(check.load_triggered for check in checks) == 1
    assert {check.record.state for check in checks} == {"load_queued"}
    assert len({check.record.transition_id for check in checks}) == 1
    assert driver.calls.count(("start", "executor")) == 1
    assert len(coordinator._tasks) == 1
    assert not coordinator._tasks["executor"].done()

    await coordinator.close()
    assert coordinator._tasks == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "failure_class"),
    [("timeout", "start_timeout"), ("command_failed", "start_command_failed")],
)
async def test_start_failure_allows_only_one_bounded_manual_retry(
    tmp_path: Path, kind: str, failure_class: str
) -> None:
    module = lifecycle()

    class FailingStartDriver(module.FakeLifecycleDriver):
        def start(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("start", role))
            raise module.LifecycleDriverError("start", kind)

    store = module.LifecycleStore(tmp_path / f"{kind}.db", ("executor",))
    driver = FailingStartDriver({"executor": "inactive"})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"start failure probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"start failure slept for {seconds}")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=reject_health,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=reject_sleep,
    )

    first = await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    first_failure = store.get("executor")
    second = await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    second_failure = store.get("executor")
    blocked = await coordinator.ensure_ready("executor")

    assert first.load_triggered is True
    assert first_failure.failure_class == failure_class
    assert first_failure.retry_count == 1
    assert second.load_triggered is True
    assert second.record.state == "load_queued"
    assert second_failure.failure_class == failure_class
    assert second_failure.retry_count == module.MAX_LOAD_RETRIES
    assert blocked.load_triggered is False
    assert blocked.record == second_failure
    assert driver.calls == [
        ("cursor", "executor"),
        ("start", "executor"),
        ("cursor", "executor"),
        ("start", "executor"),
    ]
    await coordinator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("service_status", ["inactive", "failed"])
async def test_inactive_or_failed_service_gets_a_typed_failure(
    tmp_path: Path, service_status: str
) -> None:
    module = lifecycle()

    class UnstartedDriver(module.FakeLifecycleDriver):
        def start(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("start", role))

    store = module.LifecycleStore(tmp_path / f"{service_status}.db", ("executor",))
    driver = UnstartedDriver({"executor": service_status})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"inactive service probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"inactive service slept for {seconds}")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=reject_health,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=reject_sleep,
    )

    await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    failure = store.get("executor")

    assert failure.state == "failed"
    assert failure.failure_class == f"service_{service_status}"
    assert failure.retry_count == 1
    assert driver.calls == [
        ("cursor", "executor"),
        ("start", "executor"),
        ("status", "executor"),
    ]
    await coordinator.close()


@pytest.mark.asyncio
async def test_health_timeout_is_typed_and_does_not_auto_retry(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "health-timeout.db", ("executor",))
    driver = module.FakeLifecycleDriver({"executor": "inactive"})

    async def health_probe(role: str) -> bool:
        return False

    async def timeout_sleep(seconds: float) -> None:
        raise TimeoutError

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=timeout_sleep,
    )

    await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    failure = store.get("executor")

    assert failure.state == "failed"
    assert failure.failure_class == "health_timeout"
    assert failure.retry_count == 1
    assert driver.calls.count(("start", "executor")) == 1
    assert not any(operation == "stop" for operation, _ in driver.calls)
    await coordinator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shards", "expected_quality"),
    [("1/4", "estimated"), ("4/4", "measured_shards")],
)
async def test_health_ready_only_preserves_a_measured_complete_quality(
    tmp_path: Path, shards: str, expected_quality: str
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / f"ready-{shards.replace('/', '-')}.db", ("executor",))
    driver = module.FakeLifecycleDriver(
        {"executor": "inactive"},
        progress={"executor": (f"Loading safetensors checkpoint shards: {shards}",)},
    )

    async def health_probe(role: str) -> bool:
        assert role == "executor"
        return True

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"healthy load slept for {seconds}")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=reject_sleep,
    )

    await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    ready = store.get("executor")

    assert ready.state == "ready"
    assert ready.progress_value == 100.0
    assert ready.progress_quality == expected_quality
    await coordinator.close()


@pytest.mark.asyncio
async def test_outer_model_load_deadline_is_distinct_from_health_timeout(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "load-timeout.db", ("executor",))
    driver = module.FakeLifecycleDriver({"executor": "inactive"})
    poll_entered = asyncio.Event()

    async def health_probe(role: str) -> bool:
        return False

    async def blocked_sleep(seconds: float) -> None:
        poll_entered.set()
        await asyncio.Event().wait()

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=0.25,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=blocked_sleep,
    )

    await coordinator.ensure_ready("executor")
    await asyncio.wait_for(poll_entered.wait(), timeout=1)
    await coordinator._tasks["executor"]
    failure = store.get("executor")

    assert failure.state == "failed"
    assert failure.failure_class == "load_timeout"
    assert failure.retry_count == 1
    assert driver.calls.count(("start", "executor")) == 1
    await coordinator.close()


@pytest.mark.asyncio
async def test_close_waits_for_owned_load_start_and_prevents_post_close_driver_mutation(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    entered = threading.Event()
    release = threading.Event()

    class BlockingStartDriver(module.FakeLifecycleDriver):
        def capture_progress_cursor(self, role: str) -> str:
            self._require_role(role)
            self.calls.append(("cursor", role))
            entered.set()
            assert release.wait(timeout=2)
            return self._cursors[role]

    store = module.LifecycleStore(tmp_path / "shutdown-load.db", ("executor",))
    driver = BlockingStartDriver({"executor": "inactive"})
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
    )
    await coordinator.ensure_ready("executor")
    for _ in range(1_000):
        if entered.is_set():
            break
        await asyncio.sleep(0.001)
    assert entered.is_set()

    closing = asyncio.create_task(coordinator.close())
    await asyncio.sleep(0.01)
    was_pending = not closing.done()
    release.set()
    await asyncio.wait_for(closing, timeout=1)

    failure = store.get("executor")
    assert was_pending
    assert ("start", "executor") not in driver.calls
    assert failure.state == "failed"
    assert failure.failure_class == "load_cancelled"
    calls_at_close = tuple(driver.calls)
    await asyncio.sleep(0.01)
    assert tuple(driver.calls) == calls_at_close


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("completed_state", "retry_count", "expected_state", "expected_trigger"),
    [
        ("ready", 0, "ready", False),
        ("failed", 1, "load_queued", True),
        ("failed", 2, "failed", False),
    ],
)
async def test_done_load_task_refreshes_before_the_normal_retry_decision(
    tmp_path: Path,
    completed_state: str,
    retry_count: int,
    expected_state: str,
    expected_trigger: bool,
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / f"race-{completed_state}.db", ("executor",))
    stale = reach(
        store,
        "executor",
        "warming_up" if completed_state == "ready" else "load_queued",
    )
    if completed_state == "ready":
        current = store.transition("executor", "ready", expected_transition_id=stale.transition_id)
    else:
        current = store.transition(
            "executor",
            "failed",
            expected_transition_id=stale.transition_id,
            failure_class="health_timeout",
            retry_count=retry_count,
        )
    driver = module.FakeLifecycleDriver({"executor": "active"})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"completed task probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"completed task slept for {seconds}")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=reject_health,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=reject_sleep,
    )
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    coordinator._tasks["executor"] = task
    real_get = store.get
    reads = 0

    def stale_then_current(role: str):  # type: ignore[no-untyped-def]
        nonlocal reads
        reads += 1
        return stale if reads == 1 else real_get(role)

    store.get = stale_then_current  # type: ignore[method-assign]

    check = await coordinator.ensure_ready("executor")

    assert check.record.state == expected_state
    assert check.load_triggered is expected_trigger
    assert reads == 2
    assert driver.calls == []
    if expected_trigger:
        assert check.record.transition_id != current.transition_id
        assert set(coordinator._tasks) == {"executor"}
    else:
        assert check.record == current
        assert coordinator._tasks == {}
    await coordinator.close()


@pytest.mark.asyncio
async def test_done_task_exception_is_retrieved_even_when_failure_persistence_raises(
    tmp_path: Path,
) -> None:
    module = lifecycle()

    class FailingStartDriver(module.FakeLifecycleDriver):
        def start(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("start", role))
            raise module.LifecycleDriverError("start", "command_failed")

    store = module.LifecycleStore(tmp_path / "task-error.db", ("executor",))
    driver = FailingStartDriver({"executor": "inactive"})

    async def reject_health(role: str) -> bool:
        raise AssertionError(f"failed start probed health for {role}")

    async def reject_sleep(seconds: float) -> None:
        raise AssertionError(f"failed start slept for {seconds}")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=reject_health,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=reject_sleep,
    )

    def fail_persistence(*args: object, **kwargs: object) -> None:
        raise RuntimeError("failure persistence unavailable")

    coordinator._fail = fail_persistence  # type: ignore[method-assign]
    await coordinator.ensure_ready("executor")
    task = coordinator._tasks["executor"]
    while not task.done():
        await asyncio.sleep(0)

    try:
        check = await coordinator.ensure_ready("executor")
        retrieved = not task._log_traceback
    finally:
        if task._log_traceback:
            task.exception()

    assert retrieved
    assert check.record == store.get("executor")
    assert check.load_triggered is False
    assert coordinator._tasks == {}


@pytest.mark.asyncio
async def test_load_scopes_progress_immediately_before_start_without_persisting_cursor(
    tmp_path: Path,
) -> None:
    module = lifecycle()
    cursor = "s=sentinel123;i=1;b=abc"
    blocked = asyncio.Event()
    store = module.LifecycleStore(tmp_path / "cursor.db", ("executor",))
    driver = module.FakeLifecycleDriver(
        {"executor": "inactive"},
        progress={"executor": ("Loading safetensors checkpoint shards: 1/2",)},
        cursors={"executor": cursor},
    )

    async def health_probe(role: str) -> bool:
        return False

    async def sleeper(seconds: float) -> None:
        await blocked.wait()

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=10.0,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=sleeper,
    )

    await coordinator.ensure_ready("executor")
    for _ in range(100):
        if ("progress", "executor") in driver.calls:
            break
        await asyncio.sleep(0.001)

    assert driver.calls[:2] == [("cursor", "executor"), ("start", "executor")]
    assert driver.progress_cursors == [("executor", cursor)]
    assert cursor.encode() not in store.path.read_bytes()
    await coordinator.close()


@pytest.mark.asyncio
async def test_disabled_has_no_scheduler_and_observe_records_without_side_effects(
    tmp_path: Path,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    first_poll = asyncio.Event()
    block = asyncio.Event()
    sleep_calls = 0
    store = module.LifecycleStore(tmp_path / "scheduler.db", ("executor",))
    reach(store, "executor", "ready")
    usage = UsageStore(store.path)
    driver = module.FakeLifecycleDriver({"executor": "active"})

    async def sleeper(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        assert seconds == 1.0
        if sleep_calls == 1:
            first_poll.set()
            return
        await block.wait()

    def reject_memory() -> int:
        raise AssertionError("observe sampled memory")

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: 10_000.0,
        sleeper=sleeper,
        memory_probe=reject_memory,
    )

    assert coordinator.start_scheduler("disabled", ("executor",), Limits(), usage) is None
    assert sleep_calls == 0
    scheduler = coordinator.start_scheduler("observe", ("executor",), Limits(), usage)
    assert scheduler is not None
    assert coordinator.start_scheduler("observe", ("executor",), Limits(), usage) is scheduler
    await asyncio.wait_for(first_poll.wait(), timeout=1)
    for _ in range(100):
        if store.latest_decision("executor") is not None:
            break
        await asyncio.sleep(0)

    decision = store.latest_decision("executor")
    assert decision is not None
    assert decision.mode == "observe"
    assert driver.calls == []
    assert not scheduler.done()
    await coordinator.close()
    assert scheduler.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fixed", "adaptive"])
async def test_scheduler_orders_optional_roles_before_executor_and_stops_on_second_check(
    tmp_path: Path,
    mode: Literal["fixed", "adaptive"],
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    roles = ("executor", "reviewer", "planner")
    store = module.LifecycleStore(tmp_path / "ordering.db", roles, clock=lambda: clock[0])
    for role in roles:
        reach(store, role, "ready")
    clock[0] = 100.0
    driver = module.FakeLifecycleDriver({role: "active" for role in roles})
    usage = UsageStore(store.path)
    memory_samples = iter((1_000, 1_100, 2_000, 2_100, 3_000, 3_100))
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
        optional_idle_minimum_seconds=5,
        optional_idle_fallback_seconds=10,
        optional_idle_maximum_seconds=100,
        optional_minimum_ready_residency_seconds=1,
    )
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=lambda: next(memory_samples),
    )

    await coordinator.run_scheduler_check(mode, roles, limits, usage)
    assert not any(operation == "stop" for operation, _ in driver.calls)
    clock[0] = 101.0
    await coordinator.run_scheduler_check(mode, roles, limits, usage)

    assert [role for operation, role in driver.calls if operation == "stop"] == [
        "planner",
        "reviewer",
        "executor",
    ]
    assert all(store.get(role).state == "cold" for role in roles)
    assert [sample.role for sample in usage.recent_lifecycle_samples()] == [
        "planner",
        "reviewer",
        "executor",
    ]
    assert all(
        store.latest_decision(role) is not None
        and store.latest_decision(role).action_allowed is False
        and store.latest_decision(role).reason == "state_not_ready"
        for role in roles
    )
    await coordinator.close()


@pytest.mark.asyncio
async def test_terminal_activity_release_resets_scheduler_hysteresis(tmp_path: Path) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "activity-reset.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    driver = module.FakeLifecycleDriver({"executor": "active"})
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=lambda: 1_000,
    )
    usage = UsageStore(store.path)
    clock[0] = 100.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    leases = store.acquire_request_leases(
        "7147bbd5-f70c-45d5-a396-9668c78d4d12",
        ("executor",),
        kind="active_request",
    )
    clock[0] = 101.0
    store.release_leases(lease.lease_id for lease in leases)
    clock[0] = 200.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)

    decision = store.latest_decision("executor")
    assert decision is not None
    assert decision.reason == "activity_reset"
    assert decision.next_consecutive_check_count == 0
    assert driver.calls == []
    await coordinator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_state", sorted(STATES - {"cold"}))
@pytest.mark.parametrize(
    ("driver_status", "healthy", "expected_state"),
    [
        ("inactive", False, "cold"),
        ("failed", False, "failed"),
        ("active", True, "ready"),
        ("active", False, "failed"),
    ],
)
async def test_restart_reconciliation_maps_every_persisted_state_to_driver_reality(
    tmp_path: Path,
    source_state: str,
    driver_status: str,
    healthy: bool,
    expected_state: str,
) -> None:
    module = lifecycle()
    store = module.LifecycleStore(
        tmp_path / f"recover-{source_state}-{driver_status}-{healthy}.db",
        ("executor",),
        clock=lambda: 100.0,
    )
    reach(store, "executor", source_state)
    driver = module.FakeLifecycleDriver({"executor": driver_status})
    health_calls: list[str] = []

    async def health(role: str) -> bool:
        health_calls.append(role)
        return healthy

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health,
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: 200.0,
    )

    recovered = await coordinator.reconcile_managed(("executor",))

    assert recovered["executor"].state == expected_state
    assert driver.calls == [("status", "executor")]
    assert health_calls == (["executor"] if driver_status == "active" else [])
    if expected_state == "ready":
        assert recovered["executor"].ready_since is not None
    if driver_status == "active" and not healthy:
        assert recovered["executor"].failure_class == "recovery_unhealthy"
    await coordinator.close()


@pytest.mark.asyncio
async def test_restart_health_probe_is_bounded_and_never_starts_or_stops(tmp_path: Path) -> None:
    module = lifecycle()
    store = module.LifecycleStore(tmp_path / "recover-timeout.db", ("executor",))
    reach(store, "executor", "ready")
    driver = module.FakeLifecycleDriver({"executor": "active"})

    async def blocked_health(role: str) -> bool:
        await asyncio.Event().wait()
        return True

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=blocked_health,
        timeout_seconds=0.01,
        poll_seconds=1.0,
    )

    recovered = await coordinator.reconcile_managed(("executor",))

    assert recovered["executor"].state == "failed"
    assert recovered["executor"].failure_class == "recovery_unhealthy"
    assert driver.calls == [("status", "executor")]
    await coordinator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_point", "failure_class", "expected_stop_calls"),
    [
        ("memory_before", "memory_before_failed", 0),
        ("stop", "stop_command_failed", 1),
        ("status", "service_active", 1),
        ("memory_after", "memory_after_failed", 1),
        ("transition", "unload_failed", 1),
    ],
)
async def test_unload_failures_are_truthful_bounded_and_not_rapidly_retried(
    tmp_path: Path,
    failure_point: str,
    failure_class: str,
    expected_stop_calls: int,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / f"unload-{failure_point}.db",
        ("executor",),
        clock=lambda: clock[0],
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0

    class FailureDriver(module.FakeLifecycleDriver):
        def stop(self, role: str) -> None:
            if failure_point == "stop":
                self._require_role(role)
                self.calls.append(("stop", role))
                raise module.LifecycleDriverError("stop", "command_failed")
            if failure_point == "status":
                self._require_role(role)
                self.calls.append(("stop", role))
                return
            super().stop(role)

    driver = FailureDriver({"executor": "active"})
    memory_calls = 0

    def memory() -> int:
        nonlocal memory_calls
        memory_calls += 1
        if failure_point == "memory_before" and memory_calls == 1:
            raise RuntimeError("SENTINEL memory before")
        if failure_point == "memory_after" and memory_calls == 2:
            raise RuntimeError("SENTINEL memory after")
        return 1_000 + memory_calls

    if failure_point == "transition":

        def fail_complete_unload(role: str, **kwargs: Any):
            raise sqlite3.OperationalError("SENTINEL transition")

        store.complete_unload = fail_complete_unload  # type: ignore[method-assign]

    usage = UsageStore(store.path)
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=memory,
    )

    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    clock[0] = 101.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    clock[0] = 102.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)

    failed = store.get("executor")
    assert failed.state == "failed"
    assert failed.failure_class == failure_class
    assert driver.calls.count(("stop", "executor")) == expected_stop_calls
    assert usage.recent_lifecycle_samples() == []
    decision = store.latest_decision("executor")
    assert decision is not None
    assert decision.action_allowed is False
    assert "SENTINEL" not in failed.model_dump_json()
    await coordinator.close()


@pytest.mark.asyncio
async def test_successful_unload_records_memory_duration_and_one_sample(tmp_path: Path) -> None:
    from dgx_moa.usage import LifecycleSample, UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "unload-success.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0

    class TimedDriver(module.FakeLifecycleDriver):
        def stop(self, role: str) -> None:
            super().stop(role)
            clock[0] = 104.0

    usage = UsageStore(store.path)
    memory = iter((1_000, 1_250))
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )
    coordinator = module.LifecycleCoordinator(
        store,
        TimedDriver({"executor": "active"}),
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=lambda: next(memory),
    )

    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    clock[0] = 101.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)

    cold = store.get("executor")
    assert cold.state == "cold"
    assert cold.last_unload_duration_seconds == 3.0
    assert (cold.memory_before_bytes, cold.memory_after_bytes) == (1_000, 1_250)
    assert usage.recent_lifecycle_samples() == [
        LifecycleSample(
            role="executor",
            kind="unload",
            duration_seconds=3.0,
            memory_before_bytes=1_000,
            memory_after_bytes=1_250,
        )
    ]
    await coordinator.close()


@pytest.mark.asyncio
async def test_unload_sample_insert_failure_rolls_back_cold_transition(tmp_path: Path) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "unload-sample-failure.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0
    usage = UsageStore(store.path)
    with sqlite3.connect(store.path) as database:
        database.execute(
            "CREATE TRIGGER reject_unload_sample BEFORE INSERT ON lifecycle_samples "
            "WHEN NEW.kind = 'unload' BEGIN "
            "SELECT RAISE(FAIL, 'SENTINEL lifecycle sample'); END"
        )
    driver = module.FakeLifecycleDriver({"executor": "active"})
    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=lambda: 1_000,
    )
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )

    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    clock[0] = 101.0
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)

    failed = store.get("executor")
    assert failed.state == "failed"
    assert failed.failure_class == "unload_failed"
    assert driver.calls.count(("stop", "executor")) == 1
    assert usage.recent_lifecycle_samples() == []
    await coordinator.close()


@pytest.mark.asyncio
async def test_scheduler_shutdown_waits_for_owned_inflight_stop_and_finishes_transition(
    tmp_path: Path,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "shutdown-stop.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0
    entered = threading.Event()
    release = threading.Event()

    class BlockingStopDriver(module.FakeLifecycleDriver):
        def stop(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("stop", role))
            entered.set()
            assert release.wait(timeout=2)
            self._statuses[role] = "inactive"

    sleep_calls = 0

    async def sleeper(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls <= 2:
            return
        await asyncio.Event().wait()

    coordinator = module.LifecycleCoordinator(
        store,
        BlockingStopDriver({"executor": "active"}),
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        sleeper=sleeper,
        memory_probe=lambda: 1_000,
    )
    coordinator.start_scheduler(
        "fixed",
        ("executor",),
        Limits(
            executor_idle_minimum_seconds=5,
            executor_idle_fallback_seconds=10,
            executor_idle_maximum_seconds=100,
            executor_minimum_ready_residency_seconds=1,
        ),
        UsageStore(store.path),
    )
    for _ in range(1_000):
        if entered.is_set():
            break
        await asyncio.sleep(0.001)
    assert entered.is_set()

    closing = asyncio.create_task(coordinator.close())
    await asyncio.sleep(0)
    assert not closing.done()
    assert store.get("executor").state == "unloading"
    release.set()
    await asyncio.wait_for(closing, timeout=1)

    assert store.get("executor").state == "cold"
    assert coordinator._stop_tasks == {}
    decision = store.latest_decision("executor")
    assert decision is not None
    assert decision.action_allowed is False
    assert decision.reason == "state_not_ready"


@pytest.mark.asyncio
async def test_scheduler_cancellation_before_unload_admission_persists_hysteresis_reset(
    tmp_path: Path,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "cancel-before-admission.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0
    usage = UsageStore(store.path)
    limits = Limits(
        executor_idle_minimum_seconds=5,
        executor_idle_fallback_seconds=10,
        executor_idle_maximum_seconds=100,
        executor_minimum_ready_residency_seconds=1,
    )
    coordinator = module.LifecycleCoordinator(
        store,
        module.FakeLifecycleDriver({"executor": "active"}),
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        memory_probe=lambda: 1_000,
    )
    await coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    await coordinator._locks["executor"].acquire()
    check = asyncio.create_task(
        coordinator.run_scheduler_check("fixed", ("executor",), limits, usage)
    )
    try:
        for _ in range(1_000):
            decision = store.latest_decision("executor")
            if decision is not None and decision.action_allowed:
                break
            await asyncio.sleep(0.001)
        assert decision is not None
        assert decision.action_allowed is True

        check.cancel()
        with pytest.raises(asyncio.CancelledError):
            await check
    finally:
        coordinator._locks["executor"].release()

    reset = store.latest_decision("executor")
    assert reset is not None
    assert reset.action_allowed is False
    assert reset.next_consecutive_check_count == 0
    assert reset.reason == "state_reset"
    await coordinator.close()


@pytest.mark.asyncio
async def test_safe_decision_persistence_failure_cannot_consume_scheduler_cancellation(
    tmp_path: Path,
) -> None:
    from dgx_moa.usage import UsageStore

    module = lifecycle()
    clock = [0.0]
    store = module.LifecycleStore(
        tmp_path / "cancel-safe-persist.db", ("executor",), clock=lambda: clock[0]
    )
    reach(store, "executor", "ready")
    clock[0] = 100.0
    stop_entered = threading.Event()
    stop_release = threading.Event()
    resumed_after_cancel = asyncio.Event()

    class BlockingStopDriver(module.FakeLifecycleDriver):
        def stop(self, role: str) -> None:
            self._require_role(role)
            self.calls.append(("stop", role))
            stop_entered.set()
            assert stop_release.wait(timeout=2)
            self._statuses[role] = "inactive"

    sleep_calls = 0

    async def sleeper(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls <= 2:
            return
        resumed_after_cancel.set()
        await asyncio.Event().wait()

    persist = store.persist_decision
    persist_calls = 0

    def fail_terminal_safe_persistence(decision: Any):
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 3:
            raise sqlite3.OperationalError("SENTINEL safe persistence")
        return persist(decision)

    store.persist_decision = fail_terminal_safe_persistence  # type: ignore[method-assign]
    coordinator = module.LifecycleCoordinator(
        store,
        BlockingStopDriver({"executor": "active"}),
        health_probe=lambda role: asyncio.sleep(0, result=True),
        timeout_seconds=10.0,
        poll_seconds=1.0,
        clock=lambda: clock[0],
        sleeper=sleeper,
        memory_probe=lambda: 1_000,
    )
    scheduler = coordinator.start_scheduler(
        "fixed",
        ("executor",),
        Limits(
            executor_idle_minimum_seconds=5,
            executor_idle_fallback_seconds=10,
            executor_idle_maximum_seconds=100,
            executor_minimum_ready_residency_seconds=1,
        ),
        UsageStore(store.path),
    )
    assert scheduler is not None
    for _ in range(1_000):
        if stop_entered.is_set():
            break
        await asyncio.sleep(0.001)
    assert stop_entered.is_set()

    closing = asyncio.create_task(coordinator.close())
    resumed = asyncio.create_task(resumed_after_cancel.wait())
    stop_release.set()
    done, _ = await asyncio.wait({closing, resumed}, return_when=asyncio.FIRST_COMPLETED, timeout=1)
    closed_on_first_cancel = closing in done
    if not closed_on_first_cancel:
        scheduler.cancel()
        await asyncio.wait_for(closing, timeout=1)
    if not resumed.done():
        resumed.cancel()
    await asyncio.gather(resumed, return_exceptions=True)

    assert closed_on_first_cancel
    assert scheduler.cancelled()
    assert persist_calls == 3
