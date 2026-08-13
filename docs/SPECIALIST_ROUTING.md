# Dynamic Specialist Routing

Planner and Reviewer remain local specialist roles. When a managed local role is
`READY` (only after a real inference probe) and its queue-aware completion
estimate is within the configured cost margin, the request uses the local
provider. A busy, cold, loading, degraded, evicting, failed, or slower local
role does not delay an ordinary request: OpenCode Go handles that specialist
call while a singleflight local warm-up runs independently when needed. The
warmed role is eligible only for later calls. Explicit local-only policy may
queue behind a healthy busy specialist.

The measured remote cold-start model is `deepseek-v4-pro` for both Planner and
Reviewer. It does not replace the local models. The separate Kimi K3
`JudgeProvider` is never used as their fallback. Provider choice is pinned after
dispatch; race-to-first is disabled and local and remote partial outputs are
never combined.

The default 60-second local preference margin keeps a READY, healthy local
Planner or Reviewer selected. Cold, loading, busy, degraded, or materially
queued specialists route immediately to their remote fallback while one local
warm-up generation continues independently.

Checked-in defaults are disabled. Enable with a protected runtime environment:

```text
OPENCODE_GO_API_KEY=<operator-owned secret>
DGX_MOA_SPECIALIST_ROUTING={"enabled":true,"provider":"opencode_go","endpoint":"https://opencode.ai/zen/go","api_key_env":"OPENCODE_GO_API_KEY","models":{"planner":"deepseek-v4-pro","reviewer":"deepseek-v4-pro"}}
```

Never commit the key or copy `opencode_api` into deployment artifacts. Local
role endpoints stay loopback-only. Executor and Reasoner remain protected from
specialist eviction. Planner and Reviewer retain role-local minimum residency,
idle windows, blockers, recent-use prediction, and exact service stop/start
lifecycle behavior.

Routing, prediction, queue, warm-up generation, latency, cost, failure, quality,
task outcome, and eviction snapshots are persisted without prompts or repository
labels. Weekly packages include:

- `datasets/routing/specialist-residency-routing.jsonl`
- `datasets/routing/local-vs-remote-routing.jsonl`
- `datasets/routing/warmup-decisions.jsonl`
- `datasets/routing/eviction-decisions.jsonl`
- `datasets/routing/latency-prediction.jsonl`

After explicit approval and protected credential injection, run:

```bash
uv run python scripts/validate-specialist-routing.py \
  --output data/diagnostics/opencode-completion/specialists-YYYYMMDD.json
```

The validator atomically checkpoints each completed role using only model,
status, latency, usage, and failure class; prompts and raw provider output are
not persisted. The 2026-07-22 live checks, full automated suite, ordinary
cold-role remote-routing test, independent singleflight warm-up, subsequent-call
local eligibility, and rollback verification passed; production routing is
enabled from its protected environment. GLM 5.2 remained reasoning-only across
the bounded v3 retry gate. The measured DeepSeek V4 Pro replacement passed both
approval and failed-test rejection; the checked-in routing gate remains
disabled pending the remaining production gates.
