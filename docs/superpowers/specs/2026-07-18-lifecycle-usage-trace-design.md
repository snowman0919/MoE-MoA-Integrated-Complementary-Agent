# Trace, Usage, and Adaptive Model Lifecycle Design

Date: 2026-07-18
Status: approved Goal-constrained architecture
Starting dev commit: `f0416d42f414e8a0f25581988097a48c2b06210f`
Production reference commit: `c2a9af0d6b5db8dd940842c56a7236ac867061ff`

## Scope and Acceptance Boundary

This is the second sub-project of the runtime-reliability Goal. Phase one proved
real OpenAI-compatible streaming, executor output, client aliases, OpenCode, and
Hermes. Phase two provides the reliable evidence and control plane required for
adaptive unloading:

- complete terminal traces for ordinary API clients and deterministic audit
  selection when legacy and v2 records share an identifier;
- content-free request usage statistics in the existing SQLite database;
- per-role persisted lifecycle state and narrow, allowlisted service control;
- single-flight cold loading with immediate typed 503 and honest progress;
- active request, open stream, continuation, and evaluation unload guards;
- bounded fixed/adaptive idle policy with minimum residency and hysteresis;
- full-stop unload as the mandatory reliable mechanism until the later memory
  study proves another mechanism better.

Phase two does not change production services, activate unloading in production,
select FP8 KV cache, claim a final memory mechanism, perform the near-64K quality
study, complete the full physical client matrix/soak, push, or open the PR. Those
remain phase three and phase four work.

## Verified Starting State

The clean `dev` branch has 181 passing tests and passes Ruff format/check, MyPy,
systemd verification, shell syntax, and diff checks. Physical curl, OpenAI
Python, HTTPX, OpenCode 1.17.18, and Hermes Agent 0.18.2 requests pass. Immediate
streaming begins 6.693879185 seconds before executor completion in the measured
twenty-line request.

Trace completeness is the verified blocker:

- repository corpus: 4/10 complete because six legacy-v1 records replace newer
  v2 records with the same session IDs by lexicographic path order;
- physical client corpus: 0/13 complete, missing terminal lifecycle events,
  safe workspace identity, task IDs, and decision task IDs;
- timeout corpus: 0/1 complete, missing only `session_ended`.

All production units are inactive, the production worktree is clean, and no
production path or service is changed by this design.

## Design Principles

1. Keep the authenticated FastAPI gateway and SQLite state store resident.
2. Use standard-library/Pydantic/httpx components already present; add no Redis,
   queue, scheduler platform, or second gateway.
3. API requests never wait through multi-minute loading: schedule once and
   immediately return a retryable 503 before SSE headers.
4. Exact role-to-unit mappings are configuration, not request parameters. API
   users can never name units, paths, or commands.
5. Every transition is persisted before an external side effect and reconciled
   after restart.
6. Unload safety is more important than memory recovery. Any active/uncertain
   lease blocks unload.
7. Production control stays disabled or observe-only until isolated measurements
   select and validate a mechanism.

## Trace Integrity

### Terminal trace finalization

Use one idempotent request finalizer shared by non-streaming success, streaming
success, validation/backend failure after state creation, timeout, cancellation,
and disconnect. It records, in this order:

1. final request/stage status and monotonic timing;
2. `session_ended` with status and request ID;
3. persisted session state;
4. one final v2 trace record.

Streaming finalization remains inside the generator so terminal evidence is not
written before the client receives DONE or disconnects. Pre-state validation
errors have no session and therefore no fabricated trace.

Standard clients are not required to send project metadata. The gateway assigns:

- `task_id = supplied X-Task-ID/metadata task_id`, otherwise the state session
  ID;
- a content-free fallback workspace identity such as
  `{workspace_identifier: "external-api", identity_quality: "client_unspecified"}`.

Explicit supplied repository provenance still wins. Decision records are created
only after the state task ID is populated, so their `task_id` is never empty.

### Audit selection

Audit preserves legacy evidence but prefers a v2 record over v1 for the same
session. Within the same schema version it selects the last record in file order
using an explicit monotonically assigned read sequence, not path name semantics.
Legacy-only sessions remain reported as legacy and incomplete. The checked-in
corpus is not deleted or rewritten to make the audit green.

## Content-Free Usage Statistics

Add a `request_usage` SQLite table keyed by request ID. Store only:

- request/session ID and safe client class;
- public model alias, runtime mode, request class, and required roles;
- accepted/first-byte/completed timestamps and active duration;
- status, streaming flag, warm/cold/loading state, load-triggered flag, and
  retryable failure class;
- prompt/completion/total token counts when the backend reports them.

Never store messages, prompts, response content, tool arguments, authorization,
or raw client configuration in this table.

Pure statistics functions compute inter-arrival gaps, EWMA, p50/p75/p90/p95,
hour/day counts, warm latency, cold starts, role-use frequency, and load/unload
durations. Fewer than 20 usable samples is explicitly insufficient for adaptive
policy. Extend the protected runtime-status CLI and add an authenticated admin
endpoint, disabled by default, for the same content-free report.

## Lifecycle State

Persist one row per configured role (`executor`, `planner`, `reviewer`,
`reasoner`, `judge`) with:

- state: `cold`, `load_queued`, `process_starting`, `loading_weights`,
  `initializing_engine`, `warming_up`, `ready`, `sleeping`, `unloading`, `failed`;
- transition ID, timestamps, ready-since, last-used, failure, retry count;
- active request count, open stream count, continuation leases, evaluation/profile
  guards;
- progress value/quality, ETA when measured history exists;
- last load/unload duration and before/after MemAvailable samples.

SQLite transactions provide atomic transitions. At gateway restart, transient
states are reconciled against the configured driver rather than assumed ready.

## Narrow Service Driver and Single Flight

`SystemdLifecycleDriver` receives an exact role-to-unit dictionary at startup.
It invokes only argument-vector forms of:

- `systemctl --user start <exact-unit>`;
- `systemctl --user stop <exact-unit>`;
- `systemctl --user show <exact-unit> ...`;
- bounded `journalctl --user -u <exact-unit> ...` for progress.

No shell, glob, user-supplied unit, or arbitrary command is accepted. In a dev
runtime, configured units must use a distinct `dgx-moa-dev-*` namespace or a
fake/controlled driver. A non-main runtime rejects production unit names.

An in-process per-role `asyncio.Lock` and task registry provide single flight.
The first cold request atomically creates `load_queued`, starts one background
load task, and returns 503. Concurrent requests observe the same transition ID
and return the same state; they never start another unit. Startup and readiness
are bounded by the configured model-load timeout.

## Cold Request and Progress Contract

After alias classification and before planner/executor provider calls, resolve
required roles. If any required role is not ready:

1. schedule its single-flight load if cold/failed and retry is allowed;
2. return JSON 503 before an SSE stream starts;
3. include `Retry-After`, `X-DGX-MOA-Model-State`, and
   `X-DGX-MOA-Weight-Load-Percent` when available.

The OpenAI error remains `{message,type,code,param}` and adds `model_state` with
role, state, weight percent, progress quality, overall percent, ETA, and
transition ID.

Progress parsing is bounded and honest:

- checkpoint bytes when an index and byte counters are available;
- otherwise parsed shard `loaded/total` as `measured_shards`;
- fixed stage bands only for `overall_load_percent`, labelled `estimated`;
- after weights reach 100%, state moves separately through engine initialization
  and warmup;
- ETA is null until historical load samples exist.

Safe authenticated `GET /v1/model-status` and `/v1/model-status/{role}` expose
only these fields. They never expose filesystem paths, unit names, commands, or
credentials.

## Activity Guards and Continuations

Each role provider call acquires an active-request lease. A streaming executor
also holds an open-stream lease until its generator finalizer has closed the
upstream response. `finish_reason=tool_calls` creates a bounded continuation
lease keyed by session; a matching tool-result request consumes it. Expired
leases are released after the configured continuation timeout and recorded.

Unload is prohibited when any of these are nonzero/true:

- active role request;
- open stream or cancellation cleanup;
- continuation lease;
- profile transition;
- controlled evaluation;
- load/unload transition.

Lease release is idempotent and occurs in `finally` on success, error, timeout,
and cancellation.

## Adaptive Idle Policy

Modes are `disabled`, `observe`, `fixed`, and `adaptive`.

- `disabled`: no lifecycle action; preserve existing externally managed models.
- `observe`: calculate/record decisions without start/stop.
- `fixed`: use configured role timeout.
- `adaptive`: with fewer than 20 gaps, use fixed fallback; otherwise use
  `clamp(1.5 * p75_gap, minimum, maximum)`.

Defaults:

| Role class | Fallback | Minimum | Maximum | Minimum ready residency |
| --- | ---: | ---: | ---: | ---: |
| executor | 45 min | 15 min | 120 min | 10 min |
| optional | 15 min | 5 min | 45 min | 5 min |

Only the most recent bounded sample window is used. One extreme gap cannot move
the p75 outside configured clamps. Hysteresis requires the idle threshold to be
exceeded on two scheduler checks and forbids unload during minimum residency.

The resident scheduler wakes at a bounded configurable interval, computes a
decision, persists it, and either observes or invokes full stop. Optional roles
use their own last-use timestamps and normally unload before executor.

## Unload and Restart Recovery

Full service stop is the phase-two executable mechanism because it is the
required fallback and is most likely to return unified system memory. Sleep mode
and KV-cache-only options remain evaluation candidates, not active policy.

Unload flow:

1. atomically recheck guards under the role lock;
2. persist `unloading` and memory-before;
3. stop the exact unit with a bounded timeout;
4. verify inactive;
5. persist `cold`, duration, memory-after, and an unload usage event.

Failure persists `failed`, never lies about cold memory, and does not retry in a
tight loop. On restart, the driver reconciles `ready`/transient rows with actual
unit and `/v1/models` health.

## Security and Deployment Defaults

All lifecycle/admin routes require existing bearer authentication. Admin usage
report additionally requires `admin_api_enabled`. Request bodies and headers
cannot select lifecycle units, commands, runtime channel, or provenance.

Configuration defaults preserve current behavior: lifecycle mode is `disabled`
until isolated validation; production units/config are not edited or activated.
Conservative documented production recommendations may be written only after
physical memory and stability evidence.

## Testing and Validation

Test-first coverage includes trace terminal paths/audit selection; content-free
statistics; lifecycle transitions/recovery; exact-unit authorization; single
flight; loading failure; typed 503/progress/headers; active/stream/continuation
guards; adaptive bounds/hysteresis; and full-stop fallback.

Isolated physical validation uses separate SQLite/trace/run directories and
controlled dev units/processes. It proves cold request 503, one load, monotonic
measured progress, ready retry, active-stream unload prevention, idle full stop,
MemAvailable recovery, next-request reload, and trace completeness. Production
services and the production worktree remain untouched.

## Later Phases

Phase three measures full stop, sleep modes, KV-cache options, FP8 KV cache,
prefix cache, offload, CUDA graph/eager, and 64K behavior before selecting memory
settings. Phase four runs the full client counts, near-64K request, bounded soak,
remaining docs, push, and draft PR. No phase claims evidence from a later phase
before it is physically measured.
