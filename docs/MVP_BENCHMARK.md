# MVP benchmark

`data/benchmarks/mvp-baseline.json` and `.csv` hold a deterministic synthetic
baseline. It has ten fixed generated Git fixtures: analysis, two one-file fixes,
regression test, two multi-file tasks, two recovery tasks, ambiguous scope, and
reviewer correction.

Each task records its fixture remote identifier, commit, branch, clean status,
and workspace identifier in its trace, preventing benchmark-session mixing.

Token counts are `null` because this synthetic run has no model usage telemetry.
Use its timing and route results only for this harness, not resident-model claims.
