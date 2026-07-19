# Trace, Usage, and Adaptive Lifecycle Implementation Plan

> Execute this plan on `dev` in the existing repository. Use strict TDD and the
> subagent-driven-development task/review loop. Production remains read-only and
> production services remain untouched.

**Goal:** Make API traces complete, add content-free usage statistics, and
implement safe single-flight loading plus bounded adaptive full-stop unloading
without reducing 65,536-token support.

**Architecture:** Keep the existing FastAPI gateway and SQLite database. Add two
focused modules: `usage.py` for content-free records/statistics and
`lifecycle.py` for persisted per-role state, exact-unit service control,
single-flight loading, leases, progress, and adaptive scheduling. Lifecycle is
disabled by default; isolated dev validation uses a fake or explicitly named
dev driver. No external queue/database/service is added.

**Tech stack:** Python 3.12, FastAPI, Pydantic, SQLite, httpx, asyncio, existing
systemd user services, pytest, Ruff, MyPy.

**Starting dev commit:** `08cb8ff`
**Production reference:** `c2a9af0d6b5db8dd940842c56a7236ac867061ff`

**Design:** `docs/superpowers/specs/2026-07-18-lifecycle-usage-trace-design.md`

## Global Constraints

- Work only in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` on
  `dev`.
- `/home/kotori9/dgx-moa-agent` is read-only; do not start, stop, restart, edit,
  deploy, merge, or signal production services/processes.
- Keep public executor context 65,536; output default/cap 4,096/16,384; review
  evidence 16,000; SSE event/capture bounds 1,000,000.
- Preserve immediate SSE, native tool calls, typed errors, external tool-loop
  ownership, and the phase-one client contracts.
- No dependency, Redis/Celery/Kafka/Kubernetes/dashboard, arbitrary shell,
  AppArmor, Frontier, recursive improvement, Rust implementation, vLLM upgrade,
  or production topology change.
- Lifecycle/admin requests never accept units, paths, commands, runtime channel,
  or production provenance from ordinary request bodies.
- Lifecycle default stays `disabled`; no production recommendation is activated
  before physical memory evidence.
- Test first for every behavior. Commit each task independently and review its
  bounded diff before continuing.

---

### Task 1: Restore Terminal Trace Integrity and Deterministic Audit Selection

**Files:**
- Modify: `gateway/src/dgx_moa/trace.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/controller.py`
- Modify: `tests/test_trace_v2.py`
- Modify: `tests/test_api.py`

**Produces:** Complete v2 terminal traces for standard clients; v2-over-v1 audit
selection; no mutation/deletion of the legacy corpus.

- [ ] **Step 1: Add failing trace-selection and terminal-path tests**

Add tests proving:

```python
def test_audit_prefers_v2_over_duplicate_legacy_session(tmp_path: Path) -> None:
    # A lexicographically later v1 file must not replace the complete v2 record.
    report = audit_traces(tmp_path)
    assert report["total_sessions"] == 1
    assert report["complete_sessions"] == 1
    assert report["legacy_sessions"] == 0
```

For standard requests without project headers, require:

```python
assert trace["task_id"] == session_id
assert trace["workspace_identity"]["workspace_identifier"] == "external-api"
assert "session_ended" in {event["event_type"] for event in trace["events"]}
assert all(decision["task_id"] == session_id for decision in trace["agent_decisions"])
```

Cover non-stream success, stream DONE, preterminal disconnect/cancellation,
upstream error after state creation, and StageTimeout. Require one terminal event
and one final trace per request, without duplicate `request_timing`.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_trace_v2.py tests/test_api.py -q
```

- [ ] **Step 3: Populate safe fallback provenance before decisions**

After public validation and before route/decision creation:

```python
task_id = supplied_task_id or state_session_id
state.task_id = task_id
if not supplied_repository:
    state.repository = {
        "workspace_identifier": "external-api",
        "identity_quality": "client_unspecified",
    }
```

Explicit authenticated validation headers still win. Do not accept runtime
channel/trace origin from request JSON.

- [ ] **Step 4: Add one idempotent terminal finalizer**

The helper must record `session_ended`, timing, state, and trace exactly once.
Call it from non-stream success, streaming generator finalization, post-state
failure, timeout, and cancellation. Never finalize before a streaming generator
actually terminates.

- [ ] **Step 5: Make audit selection schema-aware**

Preserve every file. For duplicate session IDs prefer v2 over v1, and within the
same schema keep the later read sequence. Do not use lexicographic path order as
recency.

- [ ] **Step 6: Verify and commit**

```bash
uv run pytest tests/test_trace_v2.py tests/test_api.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
scripts/audit-trace-completeness.sh data/traces
git diff --check
git add gateway/src/dgx_moa/trace.py gateway/src/dgx_moa/api.py \
  gateway/src/dgx_moa/controller.py tests/test_trace_v2.py tests/test_api.py
git commit -m "fix(trace): finalize API sessions completely"
```

The checked-in corpus audit must exit 0 without deleting legacy evidence.

---

### Task 2: Add Content-Free Usage Storage and Statistics

**Files:**
- Create: `gateway/src/dgx_moa/usage.py`
- Create: `tests/test_usage.py`
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `config/models.yaml`

**Produces:** SQLite usage ledger and pure bounded statistics; no prompt/response
content.

- [ ] **Step 1: Write failing repository/statistics tests**

Test schema creation, idempotent start/finalize, hour/day counts, gaps, EWMA,
p50/p75/p90/p95, role frequency, warm latency, cold starts, load/unload durations,
and a bounded recent sample window.

Add a serialization test that stores sentinel prompt/response/tool/secret text in
the input object and proves none appears in the SQLite file or report.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_usage.py -q
```

- [ ] **Step 3: Implement minimal records and calculations**

Use one `request_usage` table and one `lifecycle_samples` table in the existing
state database path. Store only fields listed in the design. Implement percentile
calculation without NumPy and EWMA with a configured alpha.

Add limits:

```python
usage_sample_window: int = 512
usage_ewma_alpha: float = 0.25
adaptive_minimum_samples: int = 20
```

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_usage.py tests/test_config_auth.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/usage.py gateway/src/dgx_moa/config.py \
  config/models.yaml tests/test_usage.py
git commit -m "feat(usage): store content-free request statistics"
```

---

### Task 3: Integrate Usage Finalization and Protected Reporting

**Files:**
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/runtime_status.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_runtime_status.py`
- Modify: `tests/test_usage.py`

**Produces:** One usage row per accepted request and protected content-free
runtime report.

- [ ] **Step 1: Add failing lifecycle-path integration tests**

Cover non-stream success, stream success, disconnect, timeout, validation after
state creation, and backend error. Require exactly one finalized row and correct
status/stage/token/streaming fields. Assert message/response/tool text is absent.

Require authenticated, admin-enabled `GET /v1/admin/runtime-status`; disabled
returns 404. The existing CLI reports last request, active requests, role states,
gaps, current idle timeout, cold starts, loading failures, and unload memory.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_api.py tests/test_runtime_status.py tests/test_usage.py -q
```

- [ ] **Step 3: Reuse request finalization**

Start a usage row after public request validation. Finalize it from the Task 1
idempotent terminal finalizer; do not add a second set of scattered error hooks.
Capture upstream usage tokens only when present.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_api.py tests/test_runtime_status.py tests/test_usage.py -q
uv run mypy
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/runtime_status.py \
  tests/test_api.py tests/test_runtime_status.py tests/test_usage.py
git commit -m "feat(usage): report API activity safely"
```

---

### Task 4: Add Persisted Lifecycle State and Exact-Unit Driver

**Files:**
- Create: `gateway/src/dgx_moa/lifecycle.py`
- Create: `tests/test_lifecycle.py`
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `config/models.yaml`

**Produces:** Per-role lifecycle rows, atomic transitions, fake driver, and narrow
systemd driver. No gateway behavior changes yet.

- [ ] **Step 1: Write failing state/driver tests**

Cover every allowed state, valid/invalid transitions, restart reconciliation,
role isolation, atomic transition IDs, exact-unit allowlist, argument-vector
systemctl calls, non-main rejection of production unit names, timeout/failure,
and absence of `shell=True`.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_lifecycle.py -q
```

- [ ] **Step 3: Implement the minimal lifecycle domain**

Use a `model_lifecycle` SQLite table and typed `LifecycleRecord`. Add settings:

```python
lifecycle_mode: Literal["disabled", "observe", "fixed", "adaptive"] = "disabled"
lifecycle_poll_seconds: float = 30
lifecycle_unit_map: dict[str, str] = {}
```

Driver methods are `status`, `start`, `stop`, and bounded progress reads. Unit
names come only from validated startup settings.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_lifecycle.py tests/test_config_auth.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/config.py \
  config/models.yaml tests/test_lifecycle.py
git commit -m "feat(lifecycle): persist role state safely"
```

---

### Task 5: Implement Single-Flight Loading, Honest Progress, and Typed 503

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_api.py`

**Produces:** Background one-load-per-role, progress parser, model status endpoints,
and pre-SSE loading responses.

- [ ] **Step 1: Add failing single-flight/progress/API tests**

Prove 20 concurrent cold requests call driver start once and share one transition
ID. Cover load failure/retry bound, measured shards, measured bytes when supplied,
engine/warmup states, monotonic progress, null ETA without history, and safe status
payloads.

Require cold stream request to return JSON 503 before SSE with:

```python
assert response.status_code == 503
assert response.json()["error"]["code"] == "model_loading"
assert response.json()["model_state"]["role"] == "executor"
assert response.headers["Retry-After"]
assert response.headers["X-DGX-MOA-Model-State"]
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py -q
```

- [ ] **Step 3: Implement coordinator and status**

Create one per-role lock/task registry. Request path checks required roles after
classification but before controller/provider mutation. `disabled` preserves
phase-one behavior. Controlled modes schedule in background and return immediately.

Add authenticated safe endpoints:

```text
GET /v1/model-status
GET /v1/model-status/{role}
```

Never expose unit/path/command fields.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/api.py \
  tests/test_lifecycle.py tests/test_api.py
git commit -m "feat(lifecycle): return progress while loading"
```

---

### Task 6: Protect Active Requests, Streams, Continuations, and Cancellation

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_api.py`

**Produces:** Idempotent leases and unload guards across every terminal path.

- [ ] **Step 1: Add failing lease tests**

Cover active non-stream request, open stream, first-byte setup cancellation,
midstream disconnect, provider error, terminal DONE, tool-call continuation lease,
matching tool-result release, expiry after tool-continuation timeout, evaluation
guard, and restart cleanup. Each acquire/release must happen exactly once.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py -q
```

- [ ] **Step 3: Integrate leases through `finally`**

Acquire required-role active leases only after readiness. Streaming holds its
executor stream lease until upstream closure. `finish_reason=tool_calls` creates
a bounded session lease; a matching tool-role message consumes it. Uncertain or
unexpired leases always block unload.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py tests/test_streaming.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/api.py \
  tests/test_lifecycle.py tests/test_api.py
git commit -m "fix(lifecycle): guard active model use"
```

---

### Task 7: Implement Bounded Adaptive Idle Policy

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `config/models.yaml`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_usage.py`

**Produces:** Deterministic fixed/adaptive thresholds, clamps, sample fallback,
minimum residency, and two-check hysteresis.

- [ ] **Step 1: Write failing pure policy tests**

Cover fewer than 20 gaps, exactly 20, p75 formula, one extreme gap, role-specific
fallback/min/max, disabled/observe/fixed/adaptive, minimum residency, two idle
checks, activity reset, hour/day statistics without policy use when sparse, and
bounded sample window.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_lifecycle.py tests/test_usage.py -q
```

- [ ] **Step 3: Implement pure calculation**

Use `clamp(1.5 * p75_gap, min, max)` after 20 samples. Defaults match the design:
executor 45m/15m/120m; optional 15m/5m/45m; ready residency 10m/5m. Add short
dev-only values only through isolated config, never production YAML defaults.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_lifecycle.py tests/test_usage.py tests/test_config_auth.py -q
uv run mypy
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/config.py \
  config/models.yaml tests/test_lifecycle.py tests/test_usage.py
git commit -m "feat(lifecycle): adapt bounded idle thresholds"
```

---

### Task 8: Add Resident Scheduler, Full-Stop Unload, and Recovery

**Files:**
- Modify: `gateway/src/dgx_moa/lifecycle.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/runtime_status.py`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_runtime_status.py`

**Produces:** Bounded scheduler in gateway lifespan, observe/fixed/adaptive actions,
full-stop fallback, memory/load samples, and restart reconciliation.

- [ ] **Step 1: Add failing scheduler/unload tests**

Using fake clock/driver, cover optional-before-executor ordering, guard recheck
under lock, observe no-action, fixed/adaptive stop, stop failure, no rapid retry,
memory before/after, next cold request load, background task shutdown, and restart
recovery from each transient state.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py -q
```

- [ ] **Step 3: Implement scheduler lifecycle**

Start one scheduler task in app lifespan only when mode is not disabled. Cancel
and await it on shutdown. Recheck every guard under the per-role lock. Full stop
is the only executable unload mechanism in phase two; sleep/KV options remain
reported candidates.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py -q
uv run mypy
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
git add gateway/src/dgx_moa/lifecycle.py gateway/src/dgx_moa/api.py \
  gateway/src/dgx_moa/runtime_status.py tests/test_lifecycle.py tests/test_api.py \
  tests/test_runtime_status.py
git commit -m "feat(lifecycle): unload idle roles safely"
```

---

### Task 9: Document Lifecycle Contracts and Dev Operations

**Files:**
- Create: `docs/MODEL_LIFECYCLE.md`
- Modify: `README.md`
- Modify: `docs/STATE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/TRACE_SCHEMA.md`
- Modify: `docs/DECISIONS.md`
- Modify: `tests/test_goal_tooling.py`

**Produces:** Accurate lifecycle/status/statistics API and isolated-dev operations;
no unmeasured production recommendation.

- [ ] **Step 1: Add failing documentation contracts**

Require state names, 503 example/headers, progress-quality semantics, modes,
fallback/min/max values, exact-unit authorization, continuation guard, status/admin
routes, disabled production default, full-stop fallback, and rollback.

- [ ] **Step 2: Run RED and write docs**

```bash
uv run pytest tests/test_goal_tooling.py -q
```

Document only automated facts at this task. Mark physical/memory claims pending.

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_goal_tooling.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
git add README.md docs/MODEL_LIFECYCLE.md docs/STATE.md docs/OPERATIONS.md \
  docs/ARCHITECTURE.md docs/TRACE_SCHEMA.md docs/DECISIONS.md \
  tests/test_goal_tooling.py
git commit -m "docs: publish model lifecycle contracts"
```

---

### Task 10: Run Isolated Cold-Load, Idle-Unload, and Trace Validation

**Files:**
- Modify: `docs/VALIDATION.md`
- Modify: `docs/STATE.md`

**Produces:** Real isolated evidence for single-flight loading, progress, guards,
full-stop memory recovery, retry, and trace completeness.

- [ ] **Step 1: Run complete pre-gates**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check
```

All eight must exit 0 before physical lifecycle testing.

- [ ] **Step 2: Start an isolated dev lifecycle runtime**

Use a new temporary directory, state/trace/run/log paths, environment-only key,
non-production ports, and explicit `dgx-moa-dev-*` transient units or controlled
driver. Verify production units inactive and production tree clean before/after.

- [ ] **Step 3: Validate cold load and progress**

With executor cold, send simultaneous requests. Require prompt JSON 503, one
transition/start, monotonic measured shard/byte progress, safe status endpoint,
ready state, and successful retry. Record raw timestamps and load duration.

- [ ] **Step 4: Validate unload guards and memory**

Use short dev-only fixed thresholds. Prove active non-stream request, open stream,
and pending continuation each block unload. After release and residency/hysteresis,
prove optional role then executor stop, state cold, and record MemAvailable/RSS/PSS
before/after plus unload duration. Next request must single-flight load and retry.

- [ ] **Step 5: Audit traces and teardown**

Require checked-in, physical lifecycle, cancellation, and timeout trace audits all
exit 0. Stop only owned dev units/processes. Verify all ports unbound, memory
returned, production units inactive, production tree clean, and no owned GPU
process remains.

- [ ] **Step 6: Update evidence and rerun gates**

Append successes and failures to `docs/VALIDATION.md`; update `docs/STATE.md` only
with verified facts. Run every Step 1 gate after the last edit.

- [ ] **Step 7: Commit**

```bash
git add docs/VALIDATION.md docs/STATE.md
git commit -m "docs(validation): record adaptive lifecycle evidence"
```

## Phase-Two Completion Audit

Compare every design requirement to direct code/test/trace/physical evidence.
Keep the overall Goal active. Phase three still must evaluate unload/memory/KV
mechanisms, validate near-64K quality, select backend flags, and measure cold/warm
memory. Phase four still must run the full required client counts, bounded soak,
finish docs, push `dev`, and open the unmerged PR.
