# Model lifecycle contract

This is the canonical lifecycle contract. Checked-in configuration remains
`lifecycle_mode: disabled` with `lifecycle_unit_map: {}`. Lifecycle control is
not a production recommendation; physical evidence listed below is pending.

## States

| State | Meaning |
| --- | --- |
| `cold` | Authorized service is inactive; next managed request may queue one load. |
| `load_queued` | One single-flight load owns the role. |
| `process_starting` | Exact authorized service is starting. |
| `loading_weights` | Service journal may report weight progress. |
| `initializing_engine` | Weights may be complete while engine setup continues. |
| `warming_up` | Engine is active but health warmup is not complete. |
| `ready` | Health passed; managed requests may acquire leases. |
| `sleeping` | Reserved state; no sleep mechanism is implemented. |
| `unloading` | Atomic admission passed and full service stop is owned. |
| `failed` | Load, recovery, memory sampling, or unload failed safely. |

Transitions use an opaque transition ID. Stale updates fail. In `fixed` and
`adaptive`, a request for a `cold` role starts at most one load task; concurrent
requests observe that single-flight transition. A failed role has a bounded load
retry count. Failed or unmanaged managed roles return typed `503` responses.

## Cold and loading response

Managed inference does not wait for a cold load. It returns an
OpenAI-compatible `503` with these headers:

- `Retry-After`
- `X-DGX-MOA-Model-State`
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
    "state": "loading_weights",
    "transition_id": "opaque",
    "weight_load_percent": 42.0,
    "progress_quality": "measured_bytes",
    "overall_load_percent": null,
    "estimated_ready_seconds": null
  }
}
```

`weight_load_percent` reports weights, not total readiness:

- `measured_bytes`: parsed loaded/total byte counters.
- `measured_shards`: parsed loaded/total checkpoint shards.
- `estimated`: monotonic carry-forward or stage inference, not a measurement.
- `unavailable`: no trustworthy progress signal.

Weight progress can be 100% while engine initialization or warmup remains.
`overall_load_percent` therefore stays null. Readiness requires the health probe,
not 100% weight progress.

## Modes and idle policy

| Mode | Restart and runtime behavior |
| --- | --- |
| `disabled` | No scheduler, reconciliation, load, unload, memory probe, or lifecycle driver call. Status reports external state as unmanaged. |
| `observe` | Lease recovery and a first-sleep scheduler persist decisions only. No startup reconciliation, memory probe, or lifecycle driver call. |
| `fixed` | Managed roles reconcile exact service state, then use fixed thresholds and executable load/unload. |
| `adaptive` | Same control path as fixed, but enough role-local request gaps select a bounded adaptive threshold. |

Restart always removes stale active-request and open-stream leases and prunes
expired continuations. `fixed` and `adaptive` reconcile authorized roles:
inactive becomes `cold`, failed service becomes `failed`, healthy active becomes
`ready`, and unhealthy or unreadable state becomes `failed`. Observe keeps its
persisted lifecycle state without driver reconciliation. In-memory hysteresis
resets on every restart. Gateway shutdown cancels and joins the scheduler, owns any
in-flight full stop to completion, cancels and joins load tasks, and waits for
owned driver work; no detached lifecycle work remains.

Scheduler polling is 30-second by checked-in default. Optional roles are checked
before `executor`. An idle threshold must be exceeded on two consecutive checks
with unchanged activity. Any request activity, blocker, mode change, transient
state, or restart resets hysteresis. Minimum residency must also pass.

| Role class | Minimum idle | Fallback idle | Maximum idle | Minimum residency |
| --- | ---: | ---: | ---: | ---: |
| Executor | 900 | 2700 | 7200 | 600 |
| Optional role | 300 | 900 | 2700 | 300 |

Values are seconds. `fixed` uses fallback idle. `observe` and `adaptive` use the
fallback until there are 20 usable positive role-local gaps. With enough data,
the threshold is inclusive p75 times 1.5, clamped to the role-class minimum and
maximum. Only `fixed` and `adaptive` may act. Decisions are persisted after each
check, but status exposes only decisions matching the current-mode filter.

## Authorization, blockers, and races

`lifecycle_unit_map` is the sole role-to-unit authorization input. Roles must be
known, unit names must be valid and unique, and non-main runtimes accept only the
`dgx-moa-dev-*` namespace. Request bodies cannot supply a unit, path, command,
runtime channel, or production provenance. The only implemented unload action
and fallback is full service stop of the exact mapped unit; sleep, KV eviction,
and offload are not implemented.

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

## Isolated development shape and rollback

Lifecycle experiments require an isolated `dev` configuration, state database,
run directory, loopback gateway port, and exact `dgx-moa-dev-*` units. This shape
must not reuse the production worktree, database, port, run directory, process,
or unit names. See [Operations](OPERATIONS.md) for environment examples. Those
examples are configuration guidance, not executed or physical evidence.

Safe rollback is configuration-only: restore disabled + empty unit map, then
start a fresh isolated dev gateway under its normal test owner. Disabled mode
does not reconcile or control model services.

## Pending physical evidence

All items below remain explicitly pending; automated tests do not prove them:

- cold-load and progress behavior against real isolated model services;
- memory bytes recovered by a real full stop;
- idle-unload guards under physical client traffic;
- mechanism comparison among full stop, sleep, KV eviction, and offload;
- 64K physical quality near the context limit;
- any production recommendation, enablement, topology, or threshold change.
