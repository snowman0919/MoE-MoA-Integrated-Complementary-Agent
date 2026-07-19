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

Managed requests acquire active and stream leases under the same role locks used
by unloading. Policy checks use activity and content-free usage gaps; atomic
admission rechecks state, transition, activity, every lease, and every guard.
Executable unload is exact-unit full service stop, inactive verification, memory
sampling, then a `cold` transition and sample. Failures become sanitized
`failed` state. Full state, mode, race, recovery, and API contracts are in
`docs/MODEL_LIFECYCLE.md`.
