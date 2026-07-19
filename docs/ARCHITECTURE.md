# Architecture

OpenCode connects directly over tailnet TCP to the configurable gateway port
`9000`. Deterministic controller stores session state in SQLite and calls
loopback-only role servers on ports `8101`, `8102`, `8103`, or `8110`.
Resident and judge profiles are mutually exclusive systemd targets.

The public aliases separate client policy without adding gateways:
`dgx-moa-chat` and `dgx-moa-agent` call only the executor, while
`dgx-moa-orchestrated` deterministically selects executor-only, planner/executor,
or planner/executor/reviewer roles from the request class. External agents own
the native tool-call/result loop. Standard OpenAI fields are forwarded to the
executor; project metadata remains optional.

Streaming is a bounded forwarding path, not a review buffer. Complete SSE events
are released immediately, native deltas are preserved, duplicate DONE events
are filtered, and clean EOF receives one DONE. Capture and per-event bounds are
both 1,000,000 bytes. Streaming review is deferred. Non-streaming review uses at
most 16,000 characters of external evidence; low-risk review failure preserves
valid executor output, while high-risk orchestration may fail closed.

The checked-in, undeployed resident target requires only the Qwen3-Coder-Next
executor and gateway. Planner, reviewer, and reasoner remain optional services;
their `PartOf=dgx-moa-resident.target` relationship ensures a resident stop also
stops any optional role loaded separately. Judge runs only
`nvidia/Mistral-Medium-3.5-128B-NVFP4`; coding requests return retryable `503`
while judge profile is active. Health is public; inference uses
`DGX_MOA_AUTH_ENABLED`, and admin profile switching is disabled by default.

This topology is a development handoff, not a deployed production change.
Checked-in lifecycle control remains disabled with an empty unit map, so the
target alone does not activate optional on-demand loading. A later reviewed
fixed/adaptive deployment with authorized unit mappings is required before cold
optional roles can use the typed loading/unavailable `503` contract.

The topology follows physical Phase 3 evidence. Exact full process stop/start
is the selected executor unload and mandatory fallback. The retained executor
runtime remains context 65,536, one sequence, 1,700,000,000 KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN. Three transient-systemd cycles passed
the complete quality contract and left both process-group and unit-cgroup
PSS/RSS at zero after every stop. Sleep levels, live cache reset, and the
one-variable memory candidates did not satisfy the same memory/stability/quality
selection rule. Exact rows are in `MEMORY_OPTIMIZATION.md`.

`main` is the reviewed production control plane and trace producer. `dev` is the
integration branch. Future recursive work follows `main` MoA -> OpenCode -> an
isolated `auto/*` worktree created from `dev`; candidate code runs only as an
evaluation target and never edits the production worktree.

Primary session state and event references live in SQLite. Append-oriented v2
JSONL traces are date-partitioned by runtime channel and origin and indexed from
SQLite. State persistence fails closed; secondary trace failure degrades
observability without discarding an otherwise safe coding task.

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

Usage is stored once per request and once per participating role. Idle decisions
consume only recent successful gaps for that role, so executor traffic cannot
keep an unused reasoner resident or cause a planner unload. Three lifecycle
mutation failures inside the configured window latch automation off; status and
already-ready inference remain available, but new start/stop mutations do not.
Rollback atomically restores disabled mode and an empty authorization map.

The gateway remains Python. Its isolated five-minute peak process-group PSS was
`48741376` bytes, idle CPU was `0.24998221036527596%`, and loopback health p99
was `2.1657010074704885` ms. These values passed the predeclared no-Rust
thresholds; `RUST_EVALUATION.md` records the boundary and limitations.
