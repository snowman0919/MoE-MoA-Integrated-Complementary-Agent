# Model lifecycle contract

This is the canonical lifecycle contract. Safe checked-in configuration remains
`lifecycle_mode: disabled` with `lifecycle_unit_map: {}`. The reviewed production
deployment supplies an ignored 0600 `adaptive` override mapping the exact
Executor, Planner, and Reviewer units; it is active and physically validated.

The current dynamic MoA design changes role policy, not the measured local
Executor mechanism. Executor remains normally resident with idle unload off.
The Ollama Reasoner is externally lifecycle-managed, persistently resident
(`keep_alive=-1`), and never targeted by local systemd start/stop or short-idle
policy. Planner and Reviewer are local adaptive/on-demand roles. Heavy Judge is
an exclusive, operator-controlled profile outside idle automation. Exact full
service stop/start remains the only selected local unload and fallback.

If the external Reasoner is missing or Ollama has evicted it, the default MoA
must use a bounded readiness wait or return a typed loading/unavailable response;
it must not silently claim a Reasoner contribution or degrade to Executor-only.
The client may explicitly retry with `dgx-moa-fast` only when its policy permits.
Readiness uses Ollama `/api/ps`, requires the exact served model to be resident,
and requires its reported context to be at least 65,536. `/api/tags` proves only
that a model is installed and is not a residency signal. Each Reasoner request
sets `num_ctx=65536` and `keep_alive=-1`; a bounded reload may therefore occur
after eviction, while fixed/adaptive health returns typed unavailable until the
resident contract is restored.

## States

| State | Meaning |
| --- | --- |
| `disabled` | Role is not controlled by lifecycle automation. |
| `cold` | Persisted controller state from which managed loading may be queued. |
| `load_queued` | One single-flight load owns the role. |
| `process_starting` | Exact authorized service is starting. |
| `loading_weights` | Service journal may report weight progress. |
| `initializing_engine` | Weights may be complete while engine setup continues. |
| `warming_up` | Engine is active but health warmup is not complete. |
| `ready` | Health passed; managed requests may acquire leases. |
| `sleeping` | Reserved state; no sleep mechanism is implemented. |
| `unload_queued` | Policy selected unload; atomic blockers are being rechecked. |
| `unloading` | Atomic admission passed and full service stop is owned. |
| `failed` | Load, recovery, memory sampling, or unload failed safely. |

A `cold` record is persisted controller state, not standalone proof that its
service is inactive. Exact inactivity is established only by `fixed`/`adaptive`
startup reconciliation or a successful full stop that verifies inactive status.

Transitions use an opaque transition ID. Stale updates fail. In `fixed` and
`adaptive`, a request for a `cold` role starts at most one load task; concurrent
requests observe that single-flight transition. A failed role has a bounded load
retry count. Failed or unmanaged managed roles return typed `503` responses.

## Cold and loading response

Managed inference does not wait for a cold load. It returns an
OpenAI-compatible `503` with these headers:

- `Retry-After`
- `X-DGX-MOA-Model-Role`
- `X-DGX-MOA-Model-State`
- `X-DGX-MOA-Load-Generation`
- `X-DGX-MOA-Weight-Load-Percent`

Example body:

```json
{
  "error": {
    "message": "Model dgx-moa-executor is loading. Retry later.",
    "type": "model_loading",
    "code": "model_loading",
    "param": null
  },
  "model_state": {
    "role": "executor",
    "generation": 3,
    "state": "loading_weights",
    "transition_id": "opaque",
    "weight_load_percent": 42.0,
    "progress_quality": "measured_bytes",
    "overall_load_percent": 30.2,
    "estimated_ready_seconds": null,
    "ready": false
  }
}
```

`weight_load_percent` reports weights, not total readiness:

- `measured_bytes`: parsed loaded/total byte counters.
- `measured_shards`: parsed loaded/total checkpoint shards.
- `estimated`: monotonic carry-forward or stage inference, not a measurement.
- `unavailable`: no trustworthy progress signal.

Weight progress can be 100% while engine initialization or warmup remains.
Overall progress is monotonic within one generation: queued 0%, process start
5%, weights 5%-65%, engine initialization 70%, warmup 90%, and health-confirmed
ready 100%. These bands communicate phase, not measured total work. Readiness
requires the health probe, not 100% weight progress. If no trustworthy counter
exists, weight progress and its header are `null`/`unavailable`; elapsed time is
never relabeled as measured weight progress.

## Modes and idle policy

| Mode | Restart and runtime behavior |
| --- | --- |
| `disabled` | No scheduler, reconciliation, load, unload, memory probe, or lifecycle driver call. Status reports external state as unmanaged. |
| `observe` | Read-only status/health reconciliation and a first-sleep scheduler persist candidate decisions. No start, stop, or memory mutation occurs. |
| `fixed` | Managed roles reconcile exact service state, then use fixed thresholds and executable load/unload. |
| `adaptive` | Same control path as fixed, but enough role-local request gaps select a bounded adaptive threshold. |

Restart always removes stale active-request and open-stream leases and prunes
expired continuations. `observe`, `fixed`, and `adaptive` reconcile authorized roles:
inactive becomes `cold`, failed service becomes `failed`, healthy active becomes
`ready`, and unhealthy or unreadable state becomes `failed`. Observe uses these
read-only facts only to calculate candidates; it never starts or stops a unit.
In-memory hysteresis resets on every restart. Gateway shutdown cancels and joins scheduler and load
tasks, waits for owned load driver capture/start work, and waits for any admitted
unload stop task. Bounded read-only status/progress probes and memory reads use
worker threads and may finish after parent cancellation; they do not control
service state.

Scheduler polling is 30-second by checked-in default. Optional roles are checked
before `executor`. An idle threshold must be exceeded on two consecutive checks
with unchanged activity. Any request activity, blocker, mode change, transient
state, or restart resets hysteresis. Minimum residency must also pass.

| Role | Minimum idle | Fallback idle | Maximum idle | Minimum residency |
| --- | ---: | ---: | ---: | ---: |
| Executor | 7200 | 14400 | 28800 | 600 |
| Planner | 600 | 1200 | 3600 | 600 |
| Reviewer | 600 | 1200 | 3600 | 600 |
| Reasoner (external) | n/a | n/a | n/a | n/a |

Executor is normally resident and its idle unload is disabled by default and in
production. Planner and Reviewer enable adaptive idle unload. The external
Reasoner and exclusive Judge are outside local idle automation.

Values are seconds. `fixed` uses fallback idle. `observe` and `adaptive` use the
fallback until there are 20 usable positive role-local gaps. With enough data,
the threshold is inclusive p75 times 1.5, clamped to the role-class minimum and
maximum. Only `fixed` and `adaptive` may act. Decisions are persisted after each
check, but status exposes only decisions matching the current-mode filter.

## Authorization, blockers, and races

`lifecycle_unit_map` is the sole role-to-unit authorization input. Roles must be
known, unit names must be valid and unique, and non-main runtimes accept only the
`dgx-moa-dev-*` namespace. Inference request fields and content are never
consulted for lifecycle unit/path/command authorization or driver argument
vectors. Only validated settings and `lifecycle_unit_map` authorize lifecycle
driver targets. The only implemented unload action and fallback is full service
stop of the exact mapped unit; sleep, KV eviction, and offload are not implemented.

Unload is blocked by any active request, open stream, unexpired tool continuation,
evaluation guard, profile guard, or transient state. Policy checks are advisory;
unload admission performs an atomic recheck of state, transition ID, activity,
leases, and guards. Request lease acquisition uses the same role lock and checks
readiness atomically, closing the acquire-versus-unload race. Profile switching
claims managed-role profile guards before its owned switch and releases the
original guard ownership afterward.

## Protected status and persistence

Bearer authentication protects `GET /v1/model-status` and
`GET /v1/model-status/{role}`. Admin enablement plus authentication protects
`GET /v1/admin/runtime-status`, `GET /admin/profile`, and profile switch routes
`POST /admin/profile/resident`, `POST /admin/profile/judge`, and
`POST /admin/profile/restore`. Status reads never call the lifecycle driver.
They return persisted state and current-mode decisions only; disabled or
unmapped roles remain explicit.

SQLite request usage, lifecycle decisions, and lifecycle samples are
content-free. They store identifiers, timestamps, roles, states, counts,
durations, progress metadata, and memory integers, never prompt, response, tool,
authorization, unit, path, command, or environment content. Public status also
omits internal failure detail.

Each request has one aggregate row and exactly one row per participating role.
Role reporting includes all-time count, last-used time, recent successful gaps,
UTC hourly and weekday-hour distributions, EWMA and percentile gaps, cold
request count, warm latency, and load duration. Idle policy uses only successful
gaps for the same role. Session identifiers are hashed and no content is stored.

Three lifecycle mutation failures inside the configured 900-second window latch
automation off. The next start/stop mutation is blocked, while persisted status
and inference through already-ready roles remain available. Failure details are
sanitized. Reset clears only the latch and retains the event history.

## Isolated development shape and rollback

Lifecycle experiments require an isolated `dev` configuration, state database,
run directory, loopback gateway port, and exact `dgx-moa-dev-*` units. This shape
must not reuse the production worktree, database, port, run directory, process,
or unit names. See [Operations](OPERATIONS.md) for environment examples. Those
examples are configuration guidance, not executed or physical evidence.

`scripts/rollback-lifecycle.sh` accepts exactly one explicit configuration. It
atomically writes disabled mode and an empty unit map using a same-directory
0600 temporary file, validates it, fsyncs file and directory, replaces the
target, resets the circuit, restarts only the fixed gateway unit, restores the
resident profile, runs health, and verifies protected status. It is idempotent.
Lifecycle environment overrides must be absent; rollback fails if they defeat
the file. Disabled mode does not reconcile or control model services.

## 2026-07-20 isolated user-systemd control result

The result at `/tmp/dgx-moa-systemd-control-wbakbkm9/physical-result.json`,
SHA-256 `83ecea14eec43543f22bddf00dccff0e208d45e2e84609820891d54a939c8fdf`,
used the real gateway, SQLite store, systemd driver, journal progress path, and
runtime-linked user units with loopback fake weights. All four managed roles
started cold, reached ready, idled to inactive, and executor reloaded once at
generation 2. Five concurrent cold requests returned JSON 503 and caused one
executor start. Three cross-role injected failures opened the circuit; a fourth
mutation was zero while ready executor traffic returned 200. Two rollback runs
ended disabled with an empty map. Production fingerprints were identical before
and after, and all dev units were removed.

This proves the systemd control plane, not real-weight memory reclamation or
load duration. The Phase 3 executor full-stop trials remain the real-weight
memory evidence. A fresh-install defect found by this run was fixed: a unit with
no prior journal entries now anchors progress at the current global user-journal
cursor, then reads only the exact unit after that cursor.

## Measured full-stop and resident topology handoff

Phase 3 selected the existing 65,536-token executor configuration and exact
full transient-systemd stop/start. The independently reviewed result at
`/tmp/dgx-moa-phase3-1vjxvw8w/selected.json`, SHA-256
`fb2fc9261509acf4b51fad4b201b5210bd5a9bcb6c578006c45856e2692e7f9b`,
proves three isolated cycles. Ready times were `938.3187154009938`,
`270.0974161340855`, and `274.08552565216087` seconds. Each
cycle revalidated its transient unit identity and cgroup before stop, collected
the unit, left recorded PGID and unit-cgroup PSS/RSS at zero, released port
19301, reported 63,786 backend prompt tokens, and passed the complete quality
contract. This is development evidence only; production units were not
started, stopped, restarted, edited, or deployed.

The resident target requires gateway and executor, while optional services
retain `PartOf` for cleanup. Production has the reviewed target plus an adaptive
exact unit map for Executor, Planner, and Reviewer; optional-role on-demand
loading and typed `503` responses are active there. Safe checked-in defaults
remain disabled/empty. Rollback atomically restores those safe lifecycle values,
restarts the fixed gateway, restores resident, and verifies protected status.

The original Task 10 executor-only lifecycle evidence measured cold-load,
warm-reload, and unload durations of `942.7537190914154`,
`273.00104479002766`, and `1.361647605895996` seconds. Its warm-ready row had
`65156329472` bytes MemAvailable and `4532602880` bytes owned PSS; its initial
cold and best post-unload settled MemAvailable values were `120509042688` and
`120564150272` bytes with owned PSS/RSS zero after unload. The contemporaneous
checked-in record for the older three-role 64K resident says
`18525147136` bytes remained after planner start; its raw artifact was not
available to the final independent review. These are system-wide host snapshots
and not device-only memory measurements.

## Pending physical evidence

Items below remain explicitly pending; automated tests do not prove them:

- real-weight cold-load and progress for all four managed roles;
- memory bytes for additional roles, model versions, and hardware beyond the
  measured executor full stop;
- real-weight four-role cold/load/idle behavior under the later policy;
- idle-unload guards under real-weight physical client traffic;
- mechanism comparison replication across later runtime/model versions beyond
  the completed Phase 3 study;
- 64K physical quality under the later client matrix and soak beyond the
  completed fixed-contract executor trials;
- any later production recommendation, topology, or threshold change beyond the
  deployed Executor/Planner/Reviewer adaptive map.
