# Architecture

The v2 development path adds two independent bounded resources. Runtime
Knowledge is a versioned SQLite/WAL fact registry retrieved only by the
Executor; it grants no procedure, tool, or policy authority. The Remote Judge
is a read-only NVIDIA NIM `z-ai/glm-5.2` provider receiving only a sanitized
Judge Evidence Package and returning strict structured corrections. The
existing local Heavy Judge remains an operator-only compatibility profile while
NIM physical validation is pending. Neither development feature changes the
Executor's sole ownership of tools, routing, corrections, final validation, or
client-visible synthesis.

OpenCode connects over tailnet TCP to the authenticated gateway. The controller
stores session state in SQLite and calls loopback-only local role servers. The
Reasoner is an externally managed Ollama service configured as an explicit
external dependency; no local role endpoint is exposed by this gateway.
Resident and judge profiles remain mutually exclusive systemd targets.

The primary `dgx-moa` and external-tool-loop `dgx-moa-agent` aliases invoke the
Reasoner before every Executor turn. `dgx-moa-fast` alone bypasses the Reasoner.
`dgx-moa-orchestrated` asks the Executor for a structured routing decision, then
applies deterministic safety overrides to select Planner, Reviewer, Frontier,
or Heavy Judge. The Executor alone emits native tool calls and client-visible
content. Standard OpenAI fields are forwarded to it; project metadata remains
optional.

Planner and Frontier architecture work run concurrently when independent.
Local Reviewer and Frontier code review initially receive the same bounded
evidence independently. All artifacts return to the Executor for evidence-based
synthesis; agent outputs are never concatenated into the client response.

Streaming is a bounded forwarding path, not a review buffer. Complete SSE events
are released immediately, native deltas are preserved, duplicate DONE events
are filtered, and clean EOF receives one DONE. Capture and per-event bounds are
both 1,000,000 bytes. Streaming review is deferred. Non-streaming review uses at
most 16,000 characters of external evidence; low-risk review failure preserves
valid executor output, while high-risk orchestration may fail closed.

The local resident target keeps the Qwen3-Coder-Next Executor and gateway.
Planner and Reviewer are optional local services whose
`PartOf=dgx-moa-resident.target` relationship ensures a resident stop also stops
any role loaded separately. The Ollama Reasoner is externally lifecycle-managed,
normally resident, and never locally idle-unloaded. Judge runs only
`nvidia/Mistral-Medium-3.5-128B-NVFP4`; coding requests return retryable `503`
while judge profile is active. Health is public; inference uses
`DGX_MOA_AUTH_ENABLED`, and admin profile switching is disabled by default.

This topology is production-enabled. Safe checked-in lifecycle control remains
disabled with an empty unit map, while the ignored 0600 production environment
enables reviewed adaptive control for the exact Executor, Planner, and Reviewer
units. Cold optional roles use the typed loading/unavailable `503` contract.
Judge stays outside that unit map and the Ollama Reasoner remains externally
managed.

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

Usage is stored once per request and once per participating role. Idle decisions
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
