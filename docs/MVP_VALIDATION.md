# MVP validation

Synthetic validation covers streaming, tool-call ID preservation, tool-result
continuation state, restart persistence, read-only, one-file, multi-file,
recovery, and reviewer-correction task shapes. Run `scripts/run-mvp-benchmark.sh`.

Remaining runtime evidence: physical remote OpenCode client and Mistral heavy
judge startup/rollback. Do not claim either until run against active services.
