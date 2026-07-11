# Repository Instructions

- Keep role-model inference endpoints loopback-only; expose only the authenticated
  gateway on the configured tailnet address.
- Never commit secrets or model weights.
- Record measured evidence in `docs/VALIDATION.md`; do not infer benchmarks.
- Prefer standard-library implementations and small focused diffs.
- Treat `main` as the stable production source and `dev` as integration.
- Create recursive experiments from `dev` as `auto/<layer>/<proposal-id>` worktrees.
- Never edit the production worktree from an experiment or let a candidate MoA
  act as its own primary improvement executor.
- Do not merge, deploy, change security/systemd topology, or export training data
  without the required human approval.
- Use `docs/STATE.md`, `docs/OPERATIONS.md`, `docs/VALIDATION.md`, and
  `docs/TRACE_SCHEMA.md` as the current operational authorities.
