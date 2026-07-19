# Repository Instructions

- Keep role-model inference endpoints loopback-only; expose only the authenticated
  gateway on the configured tailnet address.
- Never commit secrets or model weights.
- Record measured evidence in `docs/VALIDATION.md`; do not infer benchmarks.
- Preserve the Phase 3 executor baseline unless new physical evidence passes the
  same safety and quality contract: context `65536`, one sequence,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN.
- Treat exact full service stop/start as the selected executor unload and
  mandatory fallback. Sleep, cache reset, FP8 KV, eager mode, chunking, and
  offload experiments are rejected evidence, not approved production changes.
- The checked-in gateway+executor resident target is undeployed. Do not describe
  optional-role on-demand loading as active while lifecycle mode is `disabled`
  and its unit map is empty.
- Keep the gateway in Python unless a separately approved study crosses the
  measured Rust thresholds documented in `docs/RUST_EVALUATION.md`.
- Prefer standard-library implementations and small focused diffs.
- Treat `main` as the stable production source and `dev` as integration.
- The canonical GitHub remote is
  `https://github.com/snowman0919/MoE-MoA-Integrated-Complementary-Agent`.
  Prefer the local checkout for repository facts; use this exact URL only when
  an external fetch is necessary.
- Create recursive experiments from `dev` as `auto/<layer>/<proposal-id>` worktrees.
- Never edit the production worktree from an experiment or let a candidate MoA
  act as its own primary improvement executor.
- Do not merge, deploy, change security/systemd topology, or export training data
  without the required human approval.
- Use `docs/STATE.md`, `docs/OPERATIONS.md`, `docs/VALIDATION.md`, and
  `docs/TRACE_SCHEMA.md` as the current operational authorities. Phase 3 did not
  change the trace schema.
