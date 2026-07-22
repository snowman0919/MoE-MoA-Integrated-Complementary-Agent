# Dynamic Specialist Routing

Planner and Reviewer remain local specialist roles. When a managed local role is
`READY` (only after a real inference probe) and its queue-aware completion
estimate is within the configured cost margin, the request uses the local
provider. A cold, loading, degraded, evicting, failed, or slower local role does
not delay an ordinary request: OpenCode Go handles that specialist call while a
singleflight local warm-up runs independently. The warmed role is eligible only
for later calls.

The remote cold-start models are `deepseek-v4-pro` for Planner and
`deepseek-v4-flash` for Reviewer. They do not replace the local models. The
separate GLM-5.2 `JudgeProvider` is never used as their fallback. Provider choice
is pinned after dispatch; race-to-first is disabled and local and remote partial
outputs are never combined.

Checked-in defaults are disabled. Enable with a protected runtime environment:

```text
OPENCODE_GO_API_KEY=<operator-owned secret>
DGX_MOA_SPECIALIST_ROUTING={"enabled":true,"provider":"opencode_go","endpoint":"https://opencode.ai/zen/go","api_key_env":"OPENCODE_GO_API_KEY","models":{"planner":"deepseek-v4-pro","reviewer":"deepseek-v4-flash"}}
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

Use `scripts/validate-specialist-routing.py` for credentialed structured-output
checks. Production enablement requires those live checks, the full automated
suite, an ordinary cold-role remote-routing test, and rollback verification.
