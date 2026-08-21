# Architecture

The Runtime owns a versioned, immutable canonical evidence snapshot for every
collaboration boundary. Original request data, observed tool/diff/test/failure
evidence, and model contributions remain separate. Reasoner, Planner, Frontier
A, Executor, Reviewer, Judge, and Frontier B receive allowlisted read-only role
projections with snapshot/projection hashes and causal provenance. No role uses
the Executor draft as a replacement for original evidence. The Executor still
solely owns tools, mutation, routing decisions, correction execution, and
client-visible synthesis.

Runtime Knowledge is a versioned SQLite/WAL fact registry retrieved only by the
Executor; it grants no procedure, tool, or policy authority. The Remote Judge
is read-only OpenCode Go `kimi-k3`, receives a sanitized Runtime-owned Judge
projection through the Judge Evidence Package, and returns strict structured
corrections.

OpenCode connects over tailnet or local-LAN TCP to the authenticated gateway.
The controller stores session state in SQLite and calls loopback-only local role servers.
The checked-in Reasoner target is Qwythos on loopback `127.0.0.1:11434`.
Its process lifecycle remains externally managed, but its inference endpoint
must not bind or route through LAN, tailnet, or a wildcard address.
Resident and judge profiles remain mutually exclusive systemd targets.

The public catalog exposes only `dgx-moa` and `dgx-moa-fast`. The primary
`dgx-moa` invokes the Reasoner before the Executor and applies deterministic
safety overrides to select optional Planner, Reviewer, Frontier, or Heavy Judge.
`dgx-moa-fast` alone bypasses the Reasoner. The Executor alone emits native tool
calls and client-visible content.

Reasoner, Planner, and Frontier A start concurrently from the same immutable
pre-dispatch snapshot and cannot observe one another's output. Their independent
contributions are joined by the Runtime into a new Executor projection.
Reviewer, Judge, and Frontier B each receive a direct projection from the
current Runtime snapshot; the Executor draft is merely one explicitly labeled
model contribution. All projection manifests are durable and visible in the
Dashboard without hidden reasoning or secrets.

Streaming is a bounded forwarding path, not a review buffer. Complete SSE events
are released immediately, native deltas are preserved, duplicate DONE events
are filtered, and EOF without either a finish reason or DONE fails instead of
promoting a partial draft. Capture and per-event bounds are
both 1,000,000 bytes. Streaming review is deferred. Non-streaming review uses at
most 16,000 characters of external evidence; low-risk review failure preserves
valid executor output, while high-risk orchestration may fail closed.

The last physically promoted resident target is Qwen3.8 27B NVFP4 + DSpark and
the gateway. The checked-in Qwen manifest remains fail-closed and is not the
production overlay.
Planner and Reviewer are optional local services whose
`PartOf=dgx-moa-resident.target` relationship ensures a resident stop also stops
any role loaded separately. The Ollama Reasoner is a separately started,
memory-bounded service and is never locally idle-unloaded. Judge runs only
`nvidia/Mistral-Medium-3.5-128B-NVFP4`; coding requests return retryable `503`
while judge profile is active. Health is public; inference uses
`DGX_MOA_AUTH_ENABLED`, and admin profile switching is disabled by default.

Safe checked-in lifecycle control remains disabled with an empty unit map. The
ignored 0600 production overlay owns the exact physically reviewed Executor
unit; optional local role units were inactive at the 2026-08-20 inspection.
Cold optional roles use the typed loading/unavailable `503` contract when remote
specialist routing is disabled. Judge and the externally managed Reasoner stay outside
the checked-in map.

Exact full process stop/start remains the selected executor unload and mandatory
fallback. Phase 3 context 65,536, one sequence, 1,700,000,000 KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN remain preserved rollback evidence.
The active Qwen overlay instead uses the measured 262,144-context DSpark
contract in `docs/STATE.md`; rejected sleep/cache/eager/chunk/offload experiments
remain non-production evidence.

ExecutionGraph remains shadow-only. New graphs use explicit
`EXECUTOR_EVIDENCE`, `EXECUTOR_PRIMARY`, and `EXECUTOR_FALLBACK` node types;
legacy `EXECUTOR` is read compatibility only. At request finalization the
Runtime compares graph role attempts with the Controller invocation ledger and
records a parity result. Any delta makes the graph ineligible for authority;
there is no checked-in authoritative mode.

After mandatory Reasoner work, optional Planner, Reviewer, and Frontier fan-in
shares one bounded deadline. Finished artifacts participate; late optional
tasks are cancelled before Executor preparation. Required safety roles bypass
that optimization. Projection manifests retain source IDs and a per-role
evidence/contribution delta while role inputs remain independent one-shot
artifacts.

`main` is the reviewed production control plane and trace producer. `dev` is the
integration branch. Future recursive work follows `main` MoA -> OpenCode -> an
isolated `auto/*` worktree created from `dev`; candidate code runs only as an
evaluation target and never edits the production worktree.

Primary session state and event references live in SQLite. Append-oriented v2
JSONL traces are date-partitioned by runtime channel and origin and indexed from
SQLite. State persistence fails closed; secondary trace failure degrades
observability without discarding an otherwise safe coding task.

The `dev` source also contains a disabled Phase A engineering-loop state inside
the same persisted session. It gives acceptance criteria evidence references,
remaining action budgets, progress state, normalized failure fingerprints, and
explicit termination reasons. It does not yet autonomously advance actions and
is not part of the production topology. See `docs/LOOP_ENGINEERING.md`.

## Model lifecycle

`LifecycleStore` persists one state row per role plus request/stream/continuation
leases, evaluation/profile guards, current idle decisions, and lifecycle samples.
`LifecycleCoordinator` serializes role work, owns single-flight load and shutdown,
and runs a first-sleep scheduler. Optional roles are considered before executor.
`SystemdLifecycleDriver` accepts only the exact validated role-to-unit map and
uses argument vectors for status/start/stop and bounded progress reads.
For a never-started unit with no journal entries, it captures the current global
user-journal cursor and still reads subsequent progress only from the exact unit;
malformed or unsafe cursors fail closed.

Managed requests acquire active and stream leases under the same role locks used
by unloading. Policy checks use activity and content-free usage gaps; atomic
admission rechecks state, transition, activity, every lease, and every guard.
Executable unload is exact-unit full service stop, inactive verification, memory
sampling, then a `cold` transition and sample. Failures become sanitized
`failed` state. Full state, mode, race, recovery, and API contracts are in
`docs/MODEL_LIFECYCLE.md`.

Usage is stored once per request and once per participating role. Detailed
request-stage latency telemetry is queued to one bounded-batch SQLite writer;
canonical state and request finalization remain synchronous. Model-invocation
CSV aggregation is delayed until store shutdown instead of running per model
call. Idle decisions
consume only recent successful gaps for that role, so aggregate Executor traffic
cannot substitute for Planner or Reviewer activity. Three lifecycle
mutation failures inside the configured window latch automation off; status and
already-ready inference remain available, but new start/stop mutations do not.
Rollback atomically restores disabled mode and an empty authorization map.
Observe mode reconciles exact-unit status and health read-only so candidate
deadlines use real ready/residency facts; its decisions cannot call start/stop or
sample unload memory.

The gateway remains Python. Its isolated five-minute peak process-group PSS was
`48741376` bytes, idle CPU was `0.24998221036527596%`, and loopback health p99
was `2.1657010074704885` ms. These values passed the predeclared no-Rust
thresholds; `RUST_EVALUATION.md` records the boundary and limitations.
