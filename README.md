# DGX MoA Agent 2.0

Authenticated OpenAI-compatible gateway for an Executor-directed Dynamic MoA.
The current Gateway release is `PILOT_ACTIVE`; the overall project remains
`IN_PROGRESS`. `PRODUCTION_BETA` and `STABLE` have not been reached.

```bash
uv sync
cp .env.example .env
uv run dgx-moa
```

## Public API

The gateway binds `0.0.0.0:9000`; bearer authentication is mandatory. Tailnet
or LAN clients use the host address and local clients use
`http://127.0.0.1:9000/v1`. Role-model endpoints are never exposed on wildcard
interfaces.

The discoverable production catalog contains only:

| Alias | Policy | Tool-loop owner | Context |
| --- | --- | --- | --- |
| `dgx-moa` | primary Reasoner + Executor path | client | `131072` |
| `dgx-moa-fast` | Executor-only compatibility path | client | `131072` |

The client executes native tool calls and returns matching tool results. The
Executor owns routing authority and client-visible final synthesis. Historical
`dgx-moa-agent`, `dgx-moa-orchestrated`, and `dgx-moa-chat` inputs are retained
internally for durable continuation and rollback compatibility, but are not
public aliases.

See `docs/API_CLIENT_MODES.md` for requests, streaming, tools, errors, and client
examples. See `docs/HERMES_AGENT.md` for Hermes configuration.

## Current production topology

The operator intentionally stopped the local Mistral Executor. The active
production Executor is the reviewed `opencode_go/deepseek-v4-flash` fallback.
The public context remains `131072`; the Phase 3 65K/MARLIN profile is retained
as rollback evidence, not advertised as the active backend.

Production currently enables Dashboard, Codex OAuth Frontier, and DeepSeek
Flash Executor scheduling. Lifecycle control uses `disabled` with an empty unit
map. ExecutionGraph control, specialist routing, Remote Judge, Loop Engineering,
Runtime Skills/Knowledge/Evolution, declarative policy, training collection,
and weekly jobs are disabled. Their source or historical evidence is not a
production-capability claim.

## Development and release

Production source is the reviewed `main` branch at
`/home/kotori9/dgx-moa-agent`; `dev` is integration. Experiments use isolated
`auto/<layer>/<proposal-id>` worktrees from `dev`. Production changes require
reviewed promotion and rollback evidence.

Safe checked-in lifecycle and optional-feature defaults remain disabled. See
`docs/MODEL_LIFECYCLE.md` for lifecycle semantics. Do not copy ignored
operator-owned overrides or credentials into Git.

The undeployed `dev` manifest routes the Executor as
`local/qwen3.8-27b -> opencode/mimo-v2.5 -> opencode/deepseek-v4-flash` and
contains a gated SGLang 262K candidate. It is not a claim about the running
production topology; current blockers and measured evidence are recorded in
`docs/STATE.md` and `docs/VALIDATION.md`.

Current authorities:

- `docs/STATE.md` — current operating facts and release status
- `goal.md` — final direction and staged gates
- `docs/OPERATIONS.md` — operations
- `docs/VALIDATION.md` — append-only measured evidence
- `docs/TRACE_SCHEMA.md` — trace contract
