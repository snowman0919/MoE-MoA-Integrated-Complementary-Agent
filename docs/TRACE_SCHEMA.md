# Trace schema

`schemas/agent-trace-v1.json` defines JSONL decision-point traces. Required data
includes session/task identity, route reasons, model revisions, context settings,
events, completion evidence, and metrics. Tool observations are structured and
bounded; secrets are redacted.

`scripts/export-agentic-traces.sh` exports stable file-order JSONL. Full source,
authorization headers, and environment secrets are excluded.
