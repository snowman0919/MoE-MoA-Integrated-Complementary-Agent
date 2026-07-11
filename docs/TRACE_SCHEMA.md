# Trace schema

`schemas/agent-trace-v2.json` defines the current decision-trajectory archive.
Each record links runtime provenance and repository identity to first-class
agent decisions, tool executions, evaluations, failure attribution/resolution,
completion evidence, training eligibility, and observability state. Context
manifests record visible identifiers and bounded summaries, never hidden reasoning.

Strict provenance values are `main|dev|candidate` and
`production|benchmark|validation|diagnostic|candidate_evaluation`. Production is
valid only with `main`; candidate evaluation is valid only with `candidate`.
Archives use `data/traces/<runtime>/<origin>/<date>/<session>.jsonl` and remain
discoverable through the SQLite trace index.

V1 remains readable as `legacy`, but is never silently counted as complete v2 or
exported for training. Run `scripts/audit-trace-completeness.sh data/traces` to
report complete, incomplete, legacy, missing fields, and missing lifecycle events.

Benchmark traces read pinned role provenance from `config/models.yaml`; the
benchmark harness never sends model requests while doing so.

Tool failure observations are classified deterministically where recognizable
(`NONEXISTENT_PATH`, syntax/type, context, timeout, model-backend, or repeated
action); unrecognized failures remain `TEST_FAILURE`.

`scripts/export-agentic-traces.sh` exports stable file-order JSONL. Training
export is separate from collection and includes only explicit eligible v2 traces.
Full source, authorization headers, and environment secrets are excluded.

Frontier decisions use events `frontier_eligible`, `frontier_profile_selected`,
`frontier_run_started`, `frontier_run_completed`, `frontier_run_failed`,
`frontier_usage_limited`, `frontier_candidate_evaluated`,
`frontier_candidate_rejected`, and `frontier_candidate_awaiting_approval`.
Events retain profile names and bounded result summaries only, never credentials.
When frontier is connected but disabled, eligibility records `FRONTIER_DISABLED`
without invoking Codex.
