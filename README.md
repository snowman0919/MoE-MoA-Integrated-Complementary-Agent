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
| `dgx-moa` | primary Reasoner + Executor path | client | `262144` |
| `dgx-moa-fast` | Executor-only compatibility path | client | `262144` |

The client executes native tool calls and returns matching tool results. The
Executor owns routing authority and client-visible final synthesis. Historical
`dgx-moa-agent`, `dgx-moa-orchestrated`, and `dgx-moa-chat` inputs are retained
internally for durable continuation and rollback compatibility, but are not
public aliases.

See `docs/API_CLIENT_MODES.md` for requests, streaming, tools, errors, and client
examples. See `docs/HERMES_AGENT.md` for Hermes configuration.

## Current production topology

The last physically promoted production Executor is the generated Qwen3.8 27B
NVFP4 target with DSpark on loopback `127.0.0.1:9001`. The public catalog reports
context `262144`. The 2026-08-20 read-only inspection found both Gateway and
Executor active with zero restarts; only the authenticated Gateway listens on a
wildcard address. The Phase 3 65K/MARLIN profile remains preserved rollback
evidence.

The safe checked-in Reasoner target is loopback `127.0.0.1:11434`. The inspected
operator overlay still targets `100.90.167.128:11434`; that open production
exception is not approved by the current loopback-only role endpoint rule and
requires a separate deployment change.

Production currently enables Dashboard and Codex OAuth Frontier. The safe
checked-in lifecycle default remains `disabled` with an empty unit map; the
ignored reviewed production overlay owns the physically verified Executor unit.
ExecutionGraph authority, specialist routing, Remote Judge, Loop Engineering,
Runtime Skills/Knowledge/Evolution, declarative policy, training collection,
and weekly jobs are disabled. Their source or historical evidence is not a
production-capability claim.

The Qwen promotion proves local serving, context smokes, native tools,
controlled streaming, restart/reclamation, throughput, and one authenticated
`dgx-moa-fast` Gateway smoke. It does **not** certify the current Executor across
raw API, Codex, OpenCode, and Hermes repository tool loops. Current-Executor P0
release certification therefore remains open.

## Development and release

Production source is the reviewed `main` branch at
`/home/kotori9/dgx-moa-agent`; `dev` is integration. Experiments use isolated
`auto/<layer>/<proposal-id>` worktrees from `dev`. Production changes require
reviewed promotion and rollback evidence.

Safe checked-in lifecycle and optional-feature defaults remain disabled. See
`docs/MODEL_LIFECYCLE.md` for lifecycle semantics. Do not copy ignored
operator-owned overrides or credentials into Git.

The checked-in fail-closed manifest routes the Executor as
`local/qwen3.8-27b -> opencode/mimo-v2.5 -> opencode/deepseek-v4-flash` and
retains `runtime_validated: false`, memory fraction `0.5`, and DSpark disabled.
Those safe defaults are distinct from the ignored, measured production overlay
(memory fraction `0.35`, DSpark enabled). Current blockers and evidence are in
`docs/STATE.md` and `docs/VALIDATION.md`.

Current authorities:

- `docs/STATE.md` — current operating facts and release status
- `goal.md` — final direction and staged gates
- `docs/OPERATIONS.md` — operations
- `docs/VALIDATION.md` — append-only measured evidence
- `docs/TRACE_SCHEMA.md` — trace contract
