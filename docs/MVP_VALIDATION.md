# MVP validation

Synthetic validation exercises gateway HTTP streaming, tool-call ID preservation,
tool-result continuation in a persisted session, repository identity isolation,
restart persistence, read-only, one-file, multi-file, recovery, and
reviewer-correction task shapes. Run `scripts/validate-opencode-synthetic.sh` for
one OpenCode-compatible HTTP execution covering all six required shapes, then
`scripts/run-mvp-benchmark.sh` for fixed fixtures.

For a live authenticated gateway, run `scripts/validate-opencode-loop.sh`; it
checks model discovery, tool-call ID preservation, normalized tool continuation,
and streaming without executing a real filesystem tool.
`scripts/smoke-test.sh` is an alias for this check.

Physical remote OpenCode completion and the Mistral heavy-judge transaction are
recorded against active services in `docs/VALIDATION.md`. The physical OpenCode
baseline is one isolated file update with tool continuation, final SSE stop,
and bounded exit; it does not replace the synthetic six-shape suite.
