# Goal

Deploy a production-grade local MoA coding-agent gateway on this GB10 system.
OpenCode retains shell, filesystem, LSP, and Git tools. DGX owns inference,
deterministic routing, session state, compression, loop prevention, review,
completion validation, and mutually exclusive resident/judge profiles.

## Acceptance

- Expose only `dgx-moa-agent` through authenticated OpenAI-compatible HTTP.
- Bind all model servers and gateway to loopback; expose gateway with Tailscale Serve.
- Keep at least 20 GB unified-memory headroom.
- Validate models independently before claiming runtime support.
- Preserve streaming, tool calls, usage, and durable session state.
- Prevent duplicate failed actions and require review evidence before completion.

