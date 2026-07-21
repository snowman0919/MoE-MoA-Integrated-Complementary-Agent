# Trace schema

`schemas/agent-trace-v3.json` defines the current decision-trajectory archive.
Each record links runtime provenance and repository identity to first-class
agent decisions, tool executions, evaluations, failure attribution/resolution,
completion evidence, training eligibility, and observability state. Context
manifests record visible identifiers and bounded summaries, never hidden reasoning.

Dynamic MoA records additionally contain bounded `reasoner_contributions`,
structured `orchestration_decisions`, `agent_invocations`, `agent_artifacts`,
`recommendation_resolutions`, `derived_confidence`, an `evidence_graph`, and an
optional `engineering_loop` snapshot for role-specific loop training and exact
replay.
Evidence nodes distinguish user constraints, model assertions, tool-observed
facts, test-confirmed facts, and unverified assumptions. Edges use `supports`,
`contradicts`, `depends_on`, `supersedes`, `generated_from`, or `validated_by`.
Frontier records transmitted evidence categories, latency, token counts, and
cost only when the provider reports or configuration can calculate them.
The original fields are mandatory in v3. Older valid v3 archives remain readable
without `engineering_loop`; new exports always include it. Pre-Dynamic-MoA v2
archives retain their original immutable contract and remain readable without
the v3 fields. The explicit version prevents a current trace from downgrading
itself by deleting mandatory fields or runtime metrics.

Strict provenance values are `main|dev|candidate` and
`production|benchmark|validation|diagnostic|candidate_evaluation`. Production is
valid only with `main`; candidate evaluation is valid only with `candidate`.
Archives use `data/traces/<runtime>/<origin>/<date>/<session>.jsonl` and remain
discoverable through the SQLite trace index.

V1 remains readable as `legacy`, but is never silently counted as complete v2/v3
or exported for training. Run `scripts/audit-trace-completeness.sh data/traces` to
report complete, incomplete, legacy, missing fields, and missing lifecycle events.

Benchmark traces read pinned role provenance from `config/models.yaml`; the
benchmark harness never sends model requests while doing so.

Tool failure observations are classified deterministically where recognizable
(`NONEXISTENT_PATH`, syntax/type, context, timeout, model-backend, or repeated
action); unrecognized failures remain `TEST_FAILURE`.

Phase-one request metrics are content-free. `metrics` records
`request_timing_ms`, `runtime_mode`, `request_class`, `roles_required`, and
`truncated`. Timing keys can include acceptance, upstream start, first upstream
byte, first downstream byte, planner/reviewer duration, executor total, and
request completion. The separate `request_timing` event records per-stage
completed, timed-out, failed, deferred, cancelled, or aborted status. A
`finish_reason` of `length` sets `truncated: true` and never proves completion.

Streaming observations retain at most 1,000,000 bytes and are used only for
bounded state/evidence; SSE events are forwarded before review. Native content
and tool deltas are not copied into request timing metrics.

`scripts/export-agentic-traces.sh` exports stable file-order JSONL. Training
export is separate from collection and includes only explicit eligible v2/v3 traces.
Full source, authorization headers, and environment secrets are excluded.

Frontier decisions use events `frontier_eligible`, `frontier_profile_selected`,
`frontier_run_started`, `frontier_run_completed`, `frontier_run_failed`,
`frontier_usage_limited`, `frontier_candidate_evaluated`,
`frontier_candidate_rejected`, and `frontier_candidate_awaiting_approval`.
Events retain profile names and bounded result summaries only, never credentials.
When frontier is connected but disabled, eligibility records `FRONTIER_DISABLED`
without invoking Codex.

## Content-free runtime tables

Agent traces describe decision trajectories. SQLite `request_usage` describes
request timing, status, roles, token counts, streaming, model state, and bounded
failure classes; its `load_triggered` flag supplies the cold-start count.
`model_lifecycle_decisions` records per-role mode, threshold, sample count,
idle/residency values, hysteresis, action eligibility, reason, and timestamp.
`lifecycle_samples` records role, load/unload kind, duration, and optional
before/after memory integers.

These tables and lifecycle status never store raw prompt, response, tool output,
authorization, unit, path, command, environment value, or hidden reasoning.
Trace/session IDs may correlate a request across stores; lifecycle rows remain
content-free and are not training transcripts. Status exposes only decisions
matching current mode. See `docs/MODEL_LIFECYCLE.md` for retention boundaries
and lifecycle behavior.
