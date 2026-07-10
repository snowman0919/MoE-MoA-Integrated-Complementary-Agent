# DGX MoA Agent

OpenAI-compatible gateway exposing `dgx-moa-agent`, routing locally among the
executor, planner, reviewer, and mutually-exclusive heavy judge.

```bash
uv sync
cp .env.example .env
uv run dgx-moa
```

See `docs/OPERATIONS.md` and `config/opencode.example.json` for deployment.

Direct tailnet access uses `http://<DGX_TAILSCALE_IP>:9000/v1`; set
`DGX_MOA_BIND_HOST="$(tailscale ip -4 | head -n1)"` in `.env.local` after
resolving it in the shell. Tailscale Serve and Funnel are not required.
