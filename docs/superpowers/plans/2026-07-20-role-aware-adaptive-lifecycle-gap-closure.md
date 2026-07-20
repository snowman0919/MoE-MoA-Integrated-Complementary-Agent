# Role-Aware Adaptive Lifecycle Gap-Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the verified gaps between the existing lifecycle implementation and the approved role-aware adaptive lifecycle goal without touching production.

**Architecture:** Extend the existing `Settings`, `LifecycleStore`, `LifecycleCoordinator`, `UsageStore`, and FastAPI request path. Keep one SQLite database, exact allowlisted user-systemd operations, immediate JSON 503 cold responses, and full process stop/start; do not add a second supervisor or database.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, SQLite, asyncio, user systemd, pytest, Ruff, MyPy.

## Global Constraints

- Work only in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` on `dev`.
- Treat `/home/kotori9/dgx-moa-agent` on `main` as read-only.
- Do not bind port `9000`, restart production services, deploy, push, open or merge a PR.
- Preserve executor context `65536`, `max_num_seqs=1`, `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN.
- Keep exact full process stop/start as the only unload mechanism.
- Keep the gateway in Python; do not enable Frontier, recursive improvement, or change AppArmor.
- Keep checked-in defaults `lifecycle_mode: disabled` and `lifecycle_unit_map: {}`.
- Store no prompt, response, tool arguments, credentials, authorization headers, or filesystem contents in lifecycle/usage tables.
- Every schema change must be idempotent and restart-safe.
- Starting dev commit is `f7d90cf26055152e6ef775755d7877247977a15d`; production reference is read-only `e63fa6ff322466b4e4b41f4199a2db7afaed307e`.

## Verified Gap Map

- Existing: persisted role state, UUID transition ownership, leases/guards, exact-unit driver, single-flight load, bounded progress parser, typed 503, fixed/adaptive scheduler, full-stop unload, content-free request usage, status endpoints, isolated physical executor evidence.
- Missing: `disabled` and `unload_queued` persisted states; numeric load generation; role-specific planner/reviewer/reasoner/executor policy; executor long-idle opt-in; load/unload cooldown; explicit continuation TTL configuration; role-level request rows; weekday/hour aggregation; required role/generation 503 headers; persisted overall progress; circuit breaker; atomic rollback command; explicit reasoner selection; physical planner/reviewer/reasoner and failure-injection evidence.

---

### Task 1: Add Strict Role-Aware Lifecycle Configuration

**Files:**
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `config/models.yaml`
- Modify: `config/models.example.yaml`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces: `LifecycleRolePolicy`, `LifecyclePolicy`, and `Settings.lifecycle`.
- Preserves: `Settings.lifecycle_mode`, `Settings.lifecycle_unit_map`, and their existing environment overrides.

- [ ] **Step 1: Add failing default and validation tests**

```python
def test_role_lifecycle_defaults_match_approved_policy() -> None:
    settings = load_settings(Path("config/models.yaml"))
    assert settings.lifecycle.roles["executor"].normally_resident is True
    assert settings.lifecycle.roles["executor"].idle_unload_enabled is False
    assert settings.lifecycle.roles["executor"].fallback_timeout_seconds == 14_400
    assert settings.lifecycle.roles["planner"].fallback_timeout_seconds == 1_200
    assert settings.lifecycle.roles["reviewer"].fallback_timeout_seconds == 1_200
    assert settings.lifecycle.roles["reasoner"].fallback_timeout_seconds == 600
    assert settings.lifecycle.recent_sample_window == 100
    assert settings.lifecycle.minimum_samples == 20
    assert settings.lifecycle.percentile == 0.75
    assert settings.lifecycle.multiplier == 1.5
    assert settings.lifecycle.load_unload_cooldown_seconds == 300
    assert settings.lifecycle.continuation_lease_ttl_seconds == 900
    assert settings.lifecycle.failure_limit == 3
    assert settings.lifecycle.failure_window_seconds == 900
```

- [ ] **Step 2: Run the tests and confirm the missing interface fails**

Run: `uv run pytest tests/test_lifecycle.py::test_role_lifecycle_defaults_match_approved_policy -q`

Expected: failure because `Settings.lifecycle` does not exist.

- [ ] **Step 3: Implement strict nested Pydantic policy models**

```python
class LifecycleRolePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    normally_resident: bool = False
    idle_unload_enabled: bool = True
    fallback_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    minimum_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    maximum_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    minimum_ready_residency_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_timeout_order(self) -> "LifecycleRolePolicy":
        if not self.minimum_timeout_seconds <= self.fallback_timeout_seconds <= self.maximum_timeout_seconds:
            raise ValueError("role idle thresholds must satisfy minimum <= fallback <= maximum")
        return self


class LifecyclePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: dict[str, LifecycleRolePolicy] = Field(default_factory=default_lifecycle_roles)
    minimum_samples: int = Field(default=20, ge=1)
    recent_sample_window: int = Field(default=100, ge=2, le=10_000)
    percentile: float = Field(default=0.75, gt=0, lt=1, allow_inf_nan=False)
    multiplier: float = Field(default=1.5, gt=0, allow_inf_nan=False)
    load_unload_cooldown_seconds: float = Field(default=300, ge=0, allow_inf_nan=False)
    continuation_lease_ttl_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    failure_limit: int = Field(default=3, ge=1)
    failure_window_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
```

Use exact defaults: executor `7200/14400/28800`, planner and reviewer `600/1200/3600`, reasoner `300/600/1800`; executor unload disabled, judge lifecycle policy disabled.

- [ ] **Step 4: Preserve old installs and add one JSON environment override**

Keep existing flat mode/map variables. Parse optional `DGX_MOA_LIFECYCLE_POLICY` JSON into `gateway["lifecycle"]`; an absent nested policy uses safe defaults and existing installations remain disabled.

- [ ] **Step 5: Update checked-in YAML and run config tests**

Run: `uv run pytest -q tests/test_config_auth.py tests/test_lifecycle.py -k 'config or default or limit or policy'`

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/config.py config/models.yaml config/models.example.yaml tests/test_lifecycle.py
git commit -m "feat(lifecycle): configure role-aware idle policy"
```

---

### Task 2: Migrate the Persisted State Machine and Durable Generation

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces: `LifecycleRecord.generation`, `load_started_at`, `ready_at`, `last_requested_at`, `last_completed_at`, `overall_load_percent`, `service_unit`, and sanitized last error fields.
- Produces: `LifecycleStore.disable_all()`, `queue_unload()`, `cancel_queued_unload()`, and idempotent column migration.

- [ ] **Step 1: Add failing migration and transition tests**

```python
def test_lifecycle_schema_migrates_generation_and_required_fields(tmp_path: Path) -> None:
    store = LifecycleStore(tmp_path / "state.db", ("planner",), unit_map={"planner": "dgx-moa-dev-planner.service"})
    record = store.get("planner")
    assert record.state == "disabled"
    assert record.generation == 0
    assert record.service_unit == "dgx-moa-dev-planner.service"


def test_unload_queue_is_explicit_and_reversible(tmp_path: Path) -> None:
    store = LifecycleStore(tmp_path / "state.db", ("planner",))
    ready = store.recover_state("planner", "ready")
    queued = store.queue_unload("planner", expected_transition_id=ready.transition_id)
    assert queued.state == "unload_queued"
    restored = store.cancel_queued_unload("planner", expected_transition_id=queued.transition_id)
    assert restored.state == "ready"
```

- [ ] **Step 2: Confirm both tests fail on the current schema**

Run: `uv run pytest tests/test_lifecycle.py -k 'schema_migrates_generation or unload_queue_is_explicit' -q`

- [ ] **Step 3: Extend the state graph without removing legacy columns**

Add `disabled` and `unload_queued`; retain `sleeping` only as a non-entered compatibility state. Required transitions include `disabled -> cold`, `ready -> unload_queued`, `unload_queued -> ready|unloading|failed`, and safe transitions from every transient state to `disabled` during rollback.

- [ ] **Step 4: Add idempotent SQLite migration**

Use `PRAGMA table_info(model_lifecycle)` and `database.execute(f"ALTER TABLE model_lifecycle ADD COLUMN {name} {definition}")` only for a fixed internal map of absent columns. Store numeric `generation INTEGER NOT NULL DEFAULT 0`; increment it transactionally only on `cold|failed -> load_queued`. Keep UUID `transition_id` for stale-owner protection.

- [ ] **Step 5: Persist role timestamps and progress atomically**

Set `last_requested_at` while acquiring the first active lease, `last_completed_at` when releasing the final active lease, `load_started_at` on `process_starting`, `ready_at` on `ready`, and reset generation-local progress only when generation changes.

- [ ] **Step 6: Run state and migration tests**

Run: `uv run pytest -q tests/test_lifecycle.py -k 'transition or schema or migration or generation or reconcile or lease'`

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add gateway/src/dgx_moa/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(lifecycle): persist generations and unload queue"
```

---

### Task 3: Persist Role-Specific Usage and Adaptive Statistics

**Files:**
- Modify: `gateway/src/dgx_moa/usage.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/runtime_status.py`
- Test: `tests/test_usage.py`
- Test: `tests/test_api.py`
- Test: `tests/test_runtime_status.py`

**Interfaces:**
- Produces: `RoleRequestUsageStart`, `RoleRequestUsageFinalization`, `UsageStore.start_roles()`, `finalize_roles()`, and `role_statistics()`.
- Preserves: existing request-level `request_usage` rows and reports.

- [ ] **Step 1: Add failing role-row and content-free tests**

```python
def test_role_usage_is_independent_and_content_free(tmp_path: Path) -> None:
    usage = UsageStore(tmp_path / "state.db", sample_window=100)
    usage.start_roles("request-1", ("planner", "reviewer"), requested_at=1_000.0, client_mode="orchestrated", request_class="explicit_orchestrated", states={"planner": "cold", "reviewer": "warm"}, load_triggered={"planner": True, "reviewer": False})
    usage.finalize_roles("request-1", completed_at=1_010.0, first_byte_at=1_005.0, success=True, failure_class=None)
    rows = usage.recent_role_requests("planner") + usage.recent_role_requests("reviewer")
    assert [row.role for row in rows] == ["planner", "reviewer"]
    assert rows[0].load_triggered is True
    assert rows[1].load_triggered is False
    with sqlite3.connect(tmp_path / "state.db") as database:
        columns = {row[1] for row in database.execute("PRAGMA table_info(role_request_usage)")}
    assert columns == {"request_id", "session_id_hash", "role", "client_mode", "request_class", "requested_at", "load_triggered", "cold_or_warm", "ready_at", "first_byte_at", "completed_at", "success", "failure_class", "active_duration_ms"}
```

- [ ] **Step 2: Confirm the missing role API fails**

Run: `uv run pytest tests/test_usage.py::test_role_usage_is_independent_and_content_free -q`

- [ ] **Step 3: Add `role_request_usage` with an idempotent composite key**

Create a table keyed by `(request_id, role)` with `session_id_hash`, role, client mode, request class, requested/load-triggered/cold-or-warm/ready/first-byte/completed timestamps, success, failure class, and active duration. Hash a safely available session ID; never store raw prompt/tool/auth data.

- [ ] **Step 4: Implement role-filtered aggregates**

For each role, report request count, hour count, weekday-hour counts, bounded successful inter-arrival gaps, EWMA, p50/p75/p90/p95, cold-start count/frequency, mean load duration, mean warm latency, and last-used timestamp. Exclude failed rows from adaptive gaps while retaining failure counts.

- [ ] **Step 5: Integrate exactly-once start/finalize in the shared API finalizer**

Start all required/optional role rows after routing. Finalize them on success, typed 503, timeout, cancellation, provider failure, and early validation after usage acceptance. Reuse the existing idempotent request finalizer.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest -q tests/test_usage.py tests/test_runtime_status.py tests/test_api.py -k 'usage or statistics or finaliz or content_free'`

- [ ] **Step 7: Commit**

```bash
git add gateway/src/dgx_moa/usage.py gateway/src/dgx_moa/api.py gateway/src/dgx_moa/runtime_status.py tests/test_usage.py tests/test_api.py tests/test_runtime_status.py
git commit -m "feat(usage): persist role-specific request statistics"
```

---

### Task 4: Complete Cold API, Honest Progress, and Reasoner Policy

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/routing.py`
- Modify: `gateway/src/dgx_moa/schemas.py`
- Test: `tests/test_lifecycle.py`
- Test: `tests/test_api.py`
- Test: `tests/test_state_routing.py`

**Interfaces:**
- Produces: `required_roles()` plus `optional_roles()` for explicit reasoner policy.
- Produces: cold response headers `Retry-After`, model role/state/generation/weight percent.

- [ ] **Step 1: Add failing exact 503 contract test**

```python
def assert_loading_response(response: Response, role: str, generation: int) -> None:
    assert response.status_code == 503
    assert response.headers["X-DGX-MOA-Model-Role"] == role
    assert response.headers["X-DGX-MOA-Model-State"] in {"load_queued", "process_starting", "loading_weights", "initializing_engine", "warming_up"}
    assert response.headers["X-DGX-MOA-Load-Generation"] == str(generation)
    assert "Retry-After" in response.headers
    state = response.json()["model_state"]
    assert state["generation"] == generation
    assert state["ready"] is False
```

- [ ] **Step 2: Add failing stream-before-SSE and explicit reasoner tests**

Verify a cold `stream=true` request has JSON content type and no SSE prefix. Verify ordinary chat/OpenCode/Hermes routing never includes reasoner; `dgx-moa-orchestrated` with validated metadata `reasoner_mode="required"` includes reasoner, while `"optional"` records degradation and proceeds when cold.

- [ ] **Step 3: Implement monotonic phase progress**

Persist `overall_load_percent` by generation using state-derived bounded bands: queued `0`, process start `5`, weight loading `5 + 0.60 * weight_percent` when measured, initializing `70`, warming `90`, ready `100`. Never derive from elapsed time. Use `measured_bytes`/`measured_shards` for measured weight progress, `measured_phase` for structured phase-only progress, and `unavailable` when neither exists.

- [ ] **Step 4: Add all required safe status fields**

Return generation, ready boolean, weight/overall progress, last requested/completed, active/stream/continuation counts, adaptive timeout, idle seconds, load/ready timestamps, and sanitized last error class. Omit service units, paths, commands, raw errors, and credentials.

- [ ] **Step 5: Run API and routing tests**

Run: `uv run pytest -q tests/test_api.py tests/test_lifecycle.py tests/test_state_routing.py -k 'loading or progress or model_status or reasoner or stream'`

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/api.py gateway/src/dgx_moa/routing.py gateway/src/dgx_moa/schemas.py tests/test_lifecycle.py tests/test_api.py tests/test_state_routing.py
git commit -m "feat(lifecycle): complete cold progress contract"
```

---

### Task 5: Enforce Role Policy, Cooldown, and Failure Circuit Breaker

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/runtime_status.py`
- Test: `tests/test_lifecycle.py`
- Test: `tests/test_api.py`
- Test: `tests/test_runtime_status.py`

**Interfaces:**
- Changes: `calculate_idle_policy(role, mode, records, record, *, policy, lifecycle, now, has_blockers=False, previous_mode=None, previous_last_activity_at=None, previous_consecutive_check_count=0)` consumes exact role and global policy.
- Produces: persisted lifecycle failure events and `automation_disabled` circuit state.

- [ ] **Step 1: Add failing executor opt-out and role-bound tests**

```python
def test_executor_long_idle_is_disabled_while_optional_roles_adapt() -> None:
    module = lifecycle()
    settings = load_settings(Path("config/models.yaml"))
    records = policy_usage_from_gaps([600.0] * 100, ("executor", "planner", "reasoner"))
    executor = module.calculate_idle_policy("executor", "adaptive", records, policy_record(module, "executor"), policy=settings.lifecycle.roles["executor"], lifecycle=settings.lifecycle, now=40_000.0)
    planner = module.calculate_idle_policy("planner", "adaptive", records, policy_record(module, "planner"), policy=settings.lifecycle.roles["planner"], lifecycle=settings.lifecycle, now=4_000.0)
    reasoner = module.calculate_idle_policy("reasoner", "adaptive", records, policy_record(module, "reasoner"), policy=settings.lifecycle.roles["reasoner"], lifecycle=settings.lifecycle, now=2_000.0)
    assert executor.action_allowed is False
    assert planner.threshold_seconds <= 3_600
    assert reasoner.threshold_seconds <= 1_800
```

- [ ] **Step 2: Add failing cooldown and circuit tests**

Use a fake driver to inject three start/stop failures inside 900 seconds. Assert one persisted circuit trip, no fourth driver mutation, current services unchanged, ordinary unmanaged executor traffic unaffected, and status exposes only content-free counts/timestamps.

- [ ] **Step 3: Refactor policy calculation to use configured percentile and multiplier**

Use only the latest `recent_sample_window` successful role gaps. Before `minimum_samples`, use fallback; otherwise calculate configured percentile times multiplier and clamp to exact role minimum/maximum. Apply minimum residency, two-check hysteresis, and load/unload cooldown.

- [ ] **Step 4: Add persisted bounded failure policy**

Create `lifecycle_failure_events` and one `lifecycle_automation` row. Record role, operation stage, sanitized class, generation, and timestamp. Trip after configured failures in the configured window; scheduler/load mutation then fails closed without repeated systemd calls. Provide explicit store reset for manual/rollback recovery.

- [ ] **Step 5: Run safety and failure tests**

Run: `uv run pytest -q tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py -k 'idle or cooldown or blocker or failure or circuit or retry'`

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/api.py gateway/src/dgx_moa/runtime_status.py tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py
git commit -m "feat(lifecycle): fail closed with bounded automation"
```

---

### Task 6: Add Atomic Disabled-Mode Rollback

**Files:**
- Create: `gateway/src/dgx_moa/lifecycle_admin.py`
- Create: `scripts/rollback-lifecycle.sh`
- Test: `tests/test_lifecycle_admin.py`
- Test: `tests/test_systemd_units.py`

**Interfaces:**
- Produces: `atomic_disable_lifecycle(config_path: Path) -> None`.
- Produces: `dgx-moa-lifecycle rollback --config PATH` and the documented shell wrapper.

- [ ] **Step 1: Add failing atomic configuration tests**

```python
def test_atomic_disable_is_idempotent_and_preserves_evidence(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"gateway": {"lifecycle_mode": "adaptive", "lifecycle_unit_map": {"planner": "dgx-moa-dev-planner.service"}}, "models": {}}))
    evidence = tmp_path / "state.db"
    evidence.write_bytes(b"sqlite-evidence")
    atomic_disable_lifecycle(config)
    atomic_disable_lifecycle(config)
    loaded = yaml.safe_load(config.read_text())
    assert loaded["gateway"]["lifecycle_mode"] == "disabled"
    assert loaded["gateway"]["lifecycle_unit_map"] == {}
    assert evidence.read_bytes() == b"sqlite-evidence"
```

- [ ] **Step 2: Add failing rollback orchestration test with fake command runner**

Assert order: atomic config validation/replace, graceful gateway restart, `switch-profile.sh resident`, gateway health, lifecycle status disabled, circuit reset. A failed validation must leave the original config byte-identical and execute zero commands.

- [ ] **Step 3: Implement atomic YAML replacement**

Write a mode-`0600` sibling temporary file, fsync it, validate with `load_settings(temp)`, `os.replace`, and fsync the parent directory. Preserve unrelated YAML and historical SQLite evidence.

- [ ] **Step 4: Implement the exact rollback wrapper**

The wrapper accepts one explicit config path, invokes `.venv/bin/python -m dgx_moa.lifecycle_admin rollback --config "$config"`, restarts only `dgx-moa-gateway.service`, invokes the existing `scripts/switch-profile.sh resident`, runs `scripts/healthcheck.sh`, and verifies protected lifecycle status through existing credentials. It contains no user-supplied unit or shell command input.

- [ ] **Step 5: Run rollback and shell tests**

Run: `uv run pytest -q tests/test_lifecycle_admin.py tests/test_systemd_units.py && bash -n scripts/rollback-lifecycle.sh`

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/lifecycle_admin.py scripts/rollback-lifecycle.sh tests/test_lifecycle_admin.py tests/test_systemd_units.py
git commit -m "feat(lifecycle): add atomic disabled rollback"
```

---

### Task 7: Complete Documentation and Isolated Physical Validation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/STATE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/VALIDATION.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/MEMORY_OPTIMIZATION.md`
- Modify: `docs/MODEL_LIFECYCLE.md`
- Modify ignored validation harness: `.superpowers/sdd/task10-runtime/harness.py`
- Modify ignored validation tests: `.superpowers/sdd/task10-runtime/test_harness.py`

**Interfaces:**
- Produces: content-free physical result JSON and final PR evidence; no production mutation.

- [ ] **Step 1: Extend the ignored harness before physical execution**

Use fresh `/tmp` roots, loopback ports outside `9000`/`8101`-`8110`, separate SQLite/traces/run directories, and exact `dgx-moa-dev-*` transient units. Add planner/reviewer paired cold startup, five concurrent same-role requests, adaptive idle, active/SSE/continuation guards, reasoner routing, double rollback, and injected start/stop/readiness/SQLite failures.

- [ ] **Step 2: Run harness unit tests and dry-run preflight**

Run: `uv run pytest -q .superpowers/sdd/task10-runtime/test_harness.py`

Expected: all harness tests pass and dry-run proves production snapshot/read-only constraints.

- [ ] **Step 3: Run the full isolated physical matrix serially**

Required evidence: one generation/start for at least five concurrent cold requests; typed 503 and monotonic progress; retry 200; planner/reviewer independent states; reasoner absent from chat/OpenCode/Hermes and loaded only explicitly; all guards block unload; full stops recover measured MemAvailable; rollback twice is idempotent; four failure injections cause no loop; all owned processes/ports are gone.

- [ ] **Step 4: Update documentation with measured facts only**

Document exact role policy, SQLite schema, adaptive formula/defaults, 503 headers/body, progress semantics, status fields, safety/cooldown, circuit breaker, rollback command, measured timings/memory, failed attempts, and limitations. `STATE.md` contains only behavior physically proven by Step 3.

- [ ] **Step 5: Run the complete serialized gate matrix**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check origin/main...HEAD
```

Expected: every command exits zero.

- [ ] **Step 6: Perform a requirement-by-requirement diff review**

Check every numbered section in the approved attachment against code, tests, physical evidence, and docs. Required independent result: `Critical=0`, `Important=0`.

- [ ] **Step 7: Commit documentation and physical evidence references**

```bash
git add README.md AGENTS.md docs/STATE.md docs/ARCHITECTURE.md docs/OPERATIONS.md docs/VALIDATION.md docs/DECISIONS.md docs/MEMORY_OPTIMIZATION.md docs/MODEL_LIFECYCLE.md
git commit -m "docs(lifecycle): record adaptive validation evidence"
```

- [ ] **Step 8: Verify completion boundary**

Confirm dev is clean, production commit/status/units/ports equal the read-only preflight snapshot, no push or PR occurred, and prepare the final report using only the fields required by the approved goal.
