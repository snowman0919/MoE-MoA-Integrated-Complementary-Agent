# DGX MoA Agent

OpenAI-compatible coding-agent gateway. OpenCode and other clients connect to
one authenticated tailnet endpoint. `dgx-moa-chat` and `dgx-moa-agent` use the
executor directly; `dgx-moa-orchestrated` selects planner and reviewer roles by
deterministic policy. The heavy judge remains a mutually-exclusive profile.

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
See `docs/HERMES_AGENT.md` for the environment-only Hermes configuration. New
physical lifecycle validation remains pending.

See `docs/MODEL_LIFECYCLE.md` for model states, retryable loading responses,
idle policy, blockers, status routes, and isolated-development rules. Checked-in
lifecycle control is deliberately `disabled` with an empty unit map.

Authoritative references: `docs/STATE.md` for current state,
`docs/OPERATIONS.md` for operation, `docs/VALIDATION.md` for measured evidence,
`docs/TRACE_SCHEMA.md` for logging, and `docs/RECURSIVE_IMPROVEMENT.md` for the
branch workflow.
