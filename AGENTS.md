# Repository Instructions

- Keep role-model inference endpoints loopback-only; expose only the authenticated
  gateway on the configured tailnet address.
- Treat `dgx-moa` as the primary Reasoner + Executor path. `dgx-moa-fast` is the
  only intentional Executor-only compatibility path. The Executor alone owns
  tools, routing authority, and client-visible final synthesis.
- Use Codex OAuth profiles for Frontier collaboration. Never create, store, or
  require an OpenAI API key for Frontier.
- Keep collaboration bounded: structured artifacts only, no hidden reasoning,
  no recursive agent-to-agent loop, and no direct Frontier host mutation.
- Never commit secrets or model weights.
- Record measured evidence in `docs/VALIDATION.md`; do not infer benchmarks.
- Preserve the Phase 3 executor baseline unless new physical evidence passes the
  same safety and quality contract: context `65536`, one sequence,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN.
- Treat exact full service stop/start as the selected executor unload and
  mandatory fallback. Sleep, cache reset, FP8 KV, eager mode, chunking, and
  offload experiments are rejected evidence, not approved production changes.
- Safe checked-in lifecycle defaults remain disabled with an empty unit map.
  Describe optional-role on-demand loading as active only when the inspected
  runtime has a physically verified fixed/adaptive mode and exact unit map; the
  reviewed production override currently does.
- Keep executor normally resident and idle unload disabled unless new physical
  evidence explicitly changes that policy. Planner/reviewer/reasoner use their
  own successful request gaps; never substitute aggregate gateway traffic.
- Cold responses must report honest role/state/generation and unavailable
  progress when journals expose no trustworthy weight counter. Never synthesize
  a weight percentage from elapsed time.
- Lifecycle rollback is `scripts/rollback-lifecycle.sh <one-config>`: atomically
  set disabled + empty unit map, reset only the automation latch, restart the
  fixed gateway unit, restore resident, and verify protected status. Do not aim
  it at production without separate deployment approval.
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
- Keep Loop Engineering, runtime Skills, observation controls, training
  collection, weekly jobs, retention apply, and replay admin paths disabled
  until their documented physical gates pass. Retention is dry-run unless an
  authenticated operator explicitly sets `apply=true`.
- Keep Runtime Knowledge, OpenCode Go specialist routing, and the OpenCode Go
  Remote Judge disabled until their documented isolated and provider-specific
  physical gates pass. Never store the OpenCode Go key or raw remote output in
  Git or training archives.
- Generated Skills require isolated evaluation, an Executor-evidenced helpful
  canary, and explicit promotion approval. Never treat weekly recommendations as
  authority to promote or delete a core Skill.
- Use `docs/STATE.md`, `docs/OPERATIONS.md`, `docs/VALIDATION.md`, and
  `docs/TRACE_SCHEMA.md` as the current operational authorities. Phase 3 did not
  change the trace schema.
