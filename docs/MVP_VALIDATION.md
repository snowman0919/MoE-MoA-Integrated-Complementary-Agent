# MVP validation

Synthetic validation exercises gateway HTTP streaming, tool-call ID preservation,
tool-result continuation in a persisted session, repository identity isolation,
restart persistence, read-only, one-file, multi-file, recovery, and
reviewer-correction task shapes. Run `scripts/run-mvp-benchmark.sh`.

For a live authenticated gateway, run `scripts/validate-opencode-loop.sh`; it
checks model discovery, tool-call ID preservation, normalized tool continuation,
and streaming without executing a real filesystem tool.

Remaining runtime evidence: physical remote OpenCode client and Mistral heavy
judge startup/rollback. Do not claim either until run against active services.
