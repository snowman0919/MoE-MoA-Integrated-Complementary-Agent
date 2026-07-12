# Goal

Maintain a production-grade local MoA coding-agent gateway on this GB10 system.
OpenCode retains shell, filesystem, LSP, and Git tools. DGX owns inference,
deterministic routing, session state, compression, loop prevention, review,
completion validation, and mutually exclusive resident/judge profiles.

## Acceptance

- Expose only `dgx-moa-agent` through authenticated OpenAI-compatible HTTP.
- Bind model servers to loopback and expose only the authenticated gateway on tailnet TCP.
- Keep at least 20 GB unified-memory headroom.
- Validate models independently before claiming runtime support.
- Preserve streaming, tool calls, usage, and durable session state.
- Prevent duplicate failed actions and require review evidence before completion.
- Persist causally linked v2 session, decision, tool, evaluation, failure, and
  resolution evidence with strict runtime provenance.
- Keep `main` stable, accumulate validated work on `dev`, and isolate recursive
  experiments in `auto/*` worktrees driven by the stable main runtime.
