from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from dgx_moa.config import Settings, load_settings
from pydantic import ValidationError

STATES = {
    "cold",
    "load_queued",
    "process_starting",
    "loading_weights",
    "initializing_engine",
    "warming_up",
    "ready",
    "sleeping",
    "unloading",
    "failed",
}
TRANSITIONS = {
    "cold": {"load_queued"},
    "load_queued": {"cold", "process_starting", "failed"},
    "process_starting": {"cold", "loading_weights", "failed"},
    "loading_weights": {"cold", "initializing_engine", "failed"},
    "initializing_engine": {"cold", "warming_up", "failed"},
    "warming_up": {"cold", "ready", "failed"},
    "ready": {"sleeping", "unloading", "failed"},
    "sleeping": {"cold", "ready", "unloading", "failed"},
    "unloading": {"cold", "failed"},
    "failed": {"cold", "load_queued"},
}
PATHS = {
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
    "failed": ("load_queued", "failed"),
}


def lifecycle() -> Any:
    return import_module("dgx_moa.lifecycle")


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
        "state": "cold",
        "transition_id": executor.transition_id,
        "transitioned_at": 100.0,
        "updated_at": 100.0,
        "ready_since": None,
        "last_used_at": None,
        "failure_class": None,
        "failure_detail": None,
        "retry_count": 0,
        "active_request_count": 0,
        "open_stream_count": 0,
        "continuation_lease_count": 0,
        "evaluation_guard": False,
        "profile_guard": False,
        "progress_value": None,
        "progress_quality": None,
        "eta_seconds": None,
        "last_load_duration_seconds": None,
        "last_unload_duration_seconds": None,
        "memory_before_bytes": None,
        "memory_after_bytes": None,
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

    assert tables == {"request_usage", "lifecycle_samples", "model_lifecycle"}
    assert columns == set(module.LifecycleRecord.model_fields)


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
    assert progress.progress_quality == "estimated"


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
            "estimated",
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
        if sleep_calls == 2:
            break
        await asyncio.sleep(0)
    record = store.get("executor")

    assert record.progress_value == 60.0
    assert record.progress_quality == "measured_shards"
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
    for _ in range(100):
        if ("start", "executor") in driver.calls:
            break
        await asyncio.sleep(0)

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

    async def health_probe(role: str) -> bool:
        return False

    async def blocked_sleep(seconds: float) -> None:
        await asyncio.Event().wait()

    coordinator = module.LifecycleCoordinator(
        store,
        driver,
        health_probe=health_probe,
        timeout_seconds=0.01,
        poll_seconds=0.25,
        clock=lambda: 100.0,
        sleeper=blocked_sleep,
    )

    await coordinator.ensure_ready("executor")
    await coordinator._tasks["executor"]
    failure = store.get("executor")

    assert failure.state == "failed"
    assert failure.failure_class == "load_timeout"
    assert failure.retry_count == 1
    assert driver.calls.count(("start", "executor")) == 1
    await coordinator.close()


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
