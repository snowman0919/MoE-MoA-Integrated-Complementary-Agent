# DGX MoA Agent 2.0

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

The production `main` runtime implements the MoA contracts and role-aware
request statistics. Its lifecycle policy keeps the 65,536-token
Executor resident and keeps the external Ollama Reasoner persistently available;
Planner and Reviewer may unload after bounded role-local idle periods. With
specialist routing disabled, a cold managed local role returns retryable `503`
state, generation, weight progress, overall progress, and ETA fields while one
load owns the role. With validated specialist routing enabled, cold Planner and
Reviewer calls run remotely while that same singleflight local load proceeds in
the background. An isolated user-systemd run physically passed the four-role
control path, idle unload/reload, circuit breaker, and idempotent rollback. It
used fake weights to avoid duplicating the active 45G production executor, so it
does not add a new real-weight memory claim. Safe checked-in defaults remain
`disabled` with an empty unit map; the ignored 0600 production environment uses
reviewed `adaptive` control for Executor, Planner, and Reviewer and enables
Codex OAuth Frontier. Physical evidence covers the core, real clients, Planner,
Reviewer, Frontier, and the exclusive Heavy Judge resume path. The 2026-07-21
Heavy Judge validation rejected a drifted 12-GB KV configuration, then passed
the approved 4-GB readiness gate, normal adjudication, guard errors, teardown,
and fixed-resident restoration. Production enablement and later Responses
compatibility fixes were promoted through reviewed `dev`-to-`main` PRs.

`dev` also contains disabled, unit-tested bounded Loop Engineering, runtime
Skills and canaries, a separate Runtime Knowledge registry, OpenCode Go GLM-5.2
Remote Judge transport, remote-first cold-start routing for local Planner and
Reviewer specialists, declarative policy, typed Evidence Graph/replay, safe
Telegram observation (with an optional disabled Discord compatibility transport),
privacy-filtered training candidates, and Seoul
weekly 7z packaging/retention workflows. These are not production capabilities
until the physical client/provider/archive gates in `docs/VALIDATION.md` pass.

See `docs/MODEL_LIFECYCLE.md` for model states, role policies and statistics,
retryable loading responses, blockers, status routes, circuit breaker, and
rollback. Safe checked-in lifecycle control is deliberately `disabled` with an
empty unit map; production authorization remains an ignored operator-owned
override and must never be copied into Git.

Authoritative references: `docs/STATE.md` for current state,
`docs/OPERATIONS.md` for operation, `docs/VALIDATION.md` for measured evidence,
`docs/MOA_ORCHESTRATION.md` for collaboration, `docs/FRONTIER.md` for Codex OAuth,
`docs/TRACE_SCHEMA.md` for logging, `docs/LOOP_ENGINEERING.md` for the disabled
loop foundation, `docs/SKILLS.md`, `docs/KNOWLEDGE_BASE.md`,
`docs/REMOTE_JUDGE.md`, `docs/SPECIALIST_ROUTING.md`, `docs/LIVE_OBSERVATION.md`,
`docs/TRAINING_DATA.md`, and `docs/WEEKLY_PACKAGING.md` for the new disabled
workflows, `docs/RUNTIME_SELF_IMPROVEMENT.md` for governed Prompt/Policy/Routing
candidates, and `docs/RECURSIVE_IMPROVEMENT.md` for the branch workflow.
