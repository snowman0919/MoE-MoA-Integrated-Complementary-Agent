# DGX MoA Agent

OpenAI-compatible, Executor-directed dynamic Mixture-of-Agents gateway. OpenCode
and other clients connect to one authenticated tailnet endpoint. The primary
`dgx-moa` path always combines an external Ollama Reasoner with the local 80B
Executor. The Executor owns routing, native tool calls, and final synthesis; it
adds Planner, Reviewer, Codex OAuth Frontier collaboration, or the mutually
exclusive Heavy Judge only when the task and evidence require them.

`dgx-moa-fast` is the explicitly named Executor-only compatibility path.
`dgx-moa-agent` keeps the Reasoner + Executor core while the external client owns
the tool loop. `dgx-moa-orchestrated` enables dynamic local specialists and
frequent Frontier architecture/review collaboration.

```bash
uv sync
cp .env.example .env
uv run dgx-moa
```

Production is the human-reviewed `main` branch deployed at
`/home/kotori9/dgx-moa-agent`. `dev` is integration; recursive experiments use
isolated `auto/<layer>/<proposal-id>` worktrees created from `dev` and driven by
the stable `main` runtime.

Direct tailnet access uses `http://<DGX_TAILSCALE_IP>:9000/v1`; set
`DGX_MOA_BIND_HOST="$(tailscale ip -4 | head -n1)"` in `.env.local` after
resolving it in the shell. Tailscale Serve and Funnel are not required.

See `docs/API_CLIENT_MODES.md` for the model aliases, standard request and SSE
contracts, typed errors, curl/OpenAI SDK/OpenCode examples, and output limits.
See `docs/HERMES_AGENT.md` for the environment-only Hermes configuration.

The `dev` release candidate implements the new MoA contracts and role-aware
request statistics. The intended lifecycle policy keeps the 65,536-token
Executor resident and keeps the external Ollama Reasoner persistently available;
Planner and Reviewer may unload after bounded role-local idle periods. A cold
managed local role returns retryable `503`
state, generation, weight progress, overall progress, and ETA fields while one
load owns the role. An isolated user-systemd run physically passed the four-role
control path, idle unload/reload, circuit breaker, and idempotent rollback. It
used fake weights to avoid duplicating the active 45G production executor, so it
does not add a new real-weight memory claim. Checked-in and production lifecycle
settings remain `disabled` with an empty unit map. The dynamic MoA candidate has
isolated physical evidence for the core, real clients, Planner, Reviewer, and
Codex OAuth Frontier. The new Heavy Judge resume path remains physically
unverified, so the candidate is not production-enabled; production was not
restarted or changed.

See `docs/MODEL_LIFECYCLE.md` for model states, role policies and statistics,
retryable loading responses, blockers, status routes, circuit breaker, and
rollback. Checked-in lifecycle control is deliberately `disabled` with an empty
unit map until a reviewed deployment supplies exact authorized units.

Authoritative references: `docs/STATE.md` for current state,
`docs/OPERATIONS.md` for operation, `docs/VALIDATION.md` for measured evidence,
`docs/MOA_ORCHESTRATION.md` for collaboration, `docs/FRONTIER.md` for Codex OAuth,
`docs/TRACE_SCHEMA.md` for logging, and `docs/RECURSIVE_IMPROVEMENT.md` for the
branch workflow.
