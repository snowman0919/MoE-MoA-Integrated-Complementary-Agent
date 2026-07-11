# Trace schema

`schemas/agent-trace-v1.json` defines JSONL decision-point traces. Required data
includes session/task identity, route reasons, model revisions, context settings,
events, completion evidence, and metrics. Tool observations are structured and
bounded; secrets are redacted.

Benchmark traces read pinned role provenance from `config/models.yaml`; the
benchmark harness never sends model requests while doing so.

Tool failure observations are classified deterministically where recognizable
(`NONEXISTENT_PATH`, syntax/type, context, timeout, model-backend, or repeated
action); unrecognized failures remain `TEST_FAILURE`.

`scripts/export-agentic-traces.sh` exports stable file-order JSONL. Full source,
authorization headers, and environment secrets are excluded.

Frontier decisions use events `frontier_eligible`, `frontier_profile_selected`,
`frontier_run_started`, `frontier_run_completed`, `frontier_run_failed`,
`frontier_usage_limited`, `frontier_candidate_evaluated`,
`frontier_candidate_rejected`, and `frontier_candidate_awaiting_approval`.
Events retain profile names and bounded result summaries only, never credentials.
