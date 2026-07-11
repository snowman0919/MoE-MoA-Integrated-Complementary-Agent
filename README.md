# DGX MoA Agent

OpenAI-compatible coding-agent gateway. OpenCode connects to one authenticated
tailnet endpoint; the controller routes locally among the executor, planner,
reviewer, and mutually-exclusive heavy judge.

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

Authoritative references: `docs/STATE.md` for current state,
`docs/OPERATIONS.md` for operation, `docs/VALIDATION.md` for measured evidence,
`docs/TRACE_SCHEMA.md` for logging, and `docs/RECURSIVE_IMPROVEMENT.md` for the
branch workflow.
