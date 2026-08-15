# State

Updated: 2026-08-15

## Current decision authority

This file contains current operating facts only. Measured successes and failures
are append-only in `docs/VALIDATION.md`; frozen plans and the pre-closeout state
remain reachable through `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`,
`archive/20260814/*`, and `git show 6e050aa53:docs/STATE.md`.

```text
2026-08-14 Runtime Completion audit = COMPLETE_WITH_EXCEPTIONS
2026-08-15 Runtime Completion re-audit = IN_PROGRESS_WITH_EXCEPTIONS
현재 Gateway release = PILOT_ACTIVE
전체 Dynamic MoA 프로젝트 = IN_PROGRESS
PRODUCTION_BETA / STABLE = 미달성
```

The current Runtime release, isolated clients, temporary-key isolation,
production canary, and rollback rehearsal passed their measured gates. The
re-audit remains in progress because an independently created dirty development
overlay was preserved instead of being overwritten, so the requested final
worktree cleanup is not complete. This does not promote policy-disabled paths.

## Inspected production release

| Item | Current fact |
| --- | --- |
| Source | Runtime code `main@10f8248fc`; the clean production checkout also includes the current evidence update |
| Rollback | Code rollback `a030d51e7`; physical source rollback/redeploy also passed against `c9bf3e3d8` |
| Gateway | PID `3209048`, `NRestarts=0`, healthy authenticated listener on `0.0.0.0:9000` |
| Public catalog | only `dgx-moa` and `dgx-moa-fast`, both `context_length: 131072` |
| Active Executor | local Mistral `dgx-moa-executor`, PID `3229568`, loopback `127.0.0.1:9001` |
| Overflow Executor | `opencode_go/deepseek-v4-flash`; physically used while local Mistral was operator-disabled |
| Lifecycle | `fixed`, exact map `executor -> dgx-moa-executor.service`; operator control is active |
| Enabled integration | Dashboard, Codex OAuth Frontier, DeepSeek Flash Executor scheduling |
| Disabled policy paths | ExecutionGraph control, specialist routing, Remote Judge, Loop Engineering, Runtime Skills/Knowledge/Evolution, declarative policy, training collection, weekly jobs |

The ignored production environment reports `runtime_channel=main`,
`trace_origin=production`, and `controller_commit=9d4045b`. That last value is
stale configuration metadata, not source-deployment authority; Git history and
the physical deploy/rollback record establish `10f8248fc` as the running code
epoch. Correcting the metadata would require a runtime configuration change and
restart, so it is not part of this documentation-only closeout.

## Executor authority layers

| Layer | Authority |
| --- | --- |
| Active production request path | local Mistral Executor on loopback `9001` |
| Bounded overflow path | DeepSeek V4 Flash for low/medium risk; a missing required native tool call gets one Codex OAuth Frontier attempt, then remains fail-closed |
| Public API context | `131072`, as returned by `/v1/models` and loaded production config |
| Resident local candidate | Mistral Small 4 on loopback `9001`, `131072`, seq1, 3.4 GB KV, native allocator, explicit FlashInfer B12x dense/MoE, TRITON_MLA, `FULL_DECODE_ONLY` |
| Preserved rollback baseline | Phase 3 `65536`, seq1, 1.7 GB KV, `gpu_memory_utilization=0.5`, MARLIN |

The 65K MARLIN profile remains safety/rollback evidence, not the public context
or the current production provider.

## Implementation matrix

| Capability | Current classification | Measured boundary |
| --- | --- | --- |
| Chat / Responses common execution | `PHYSICALLY_VERIFIED` | authenticated Chat, Responses, SSE, cancellation, recovery, long context |
| Codex / OpenCode / Hermes compatibility | `PHYSICALLY_VERIFIED` | Docker-isolated public and hidden validators; preserved pre-fix failures are in `docs/VALIDATION.md` |
| ExecutionGraph | `DISABLED_BY_POLICY` | shadow artifacts remain non-authoritative |
| Role Context projection | `PHYSICALLY_VERIFIED` | provider-input byte/token lineage recorded for Executor, Reasoner, and Frontier |
| Evidence persistence | `PHYSICALLY_VERIFIED` | canonical snapshots, projections, provider invocations, trace and usage lineage |
| Planner / Reviewer / Judge / Frontier | `DISABLED_BY_POLICY` / `PHYSICALLY_VERIFIED` | local optional roles and Judge remain disabled; bounded Reviewer degradation and Codex OAuth Frontier are live |
| API-key isolation / overflow Executor | `PHYSICALLY_VERIFIED` | evaluation scope, TTL, hash-only storage, deny-admin, revoke and post-revoke `401` |
| Tool call / continuation | `PHYSICALLY_VERIFIED` | native tool call plus same-session result continuation |
| Streaming / cancellation / recovery | `PHYSICALLY_VERIFIED` | SSE terminal, consumer close, active-request drain, Codex reconnect family fixed and replayed |
| Dashboard / WebSocket | `PHYSICALLY_VERIFIED` | honest ON/OFF state and exact fixed-mode control |
| Logging / training candidate | `PHYSICALLY_VERIFIED` / `DISABLED_BY_POLICY` | safe runtime logs are live; collection and promotion remain disabled |
| Deployment / rollback | `PHYSICALLY_VERIFIED` | drained restart, source rollback/redeploy, health and authenticated canaries |

## Public behavior

- `dgx-moa` is the primary Reasoner + Executor policy path.
- `dgx-moa-fast` is the intentional Executor-only compatibility path.
- The client owns tool execution and sends matching tool results back to the
  gateway; the Executor owns routing and client-visible final synthesis.
- Historical inputs such as `dgx-moa-agent`, `dgx-moa-orchestrated`, and
  `dgx-moa-chat` remain internal compatibility inputs for durable continuation
  and rollback only. They are not discoverable public aliases.
- Bearer authentication remains mandatory. Role inference endpoints are not
  exposed on wildcard interfaces.

See `docs/API_CLIENT_MODES.md` for the public request contract and
`docs/MODEL_LIFECYCLE.md` for lifecycle semantics.

## Audit exceptions and remaining gates

- CI is checked in and green on both long-lived branches, but GitHub branch
  protection is absent. The available token received `403` when attempting to
  require CI and prohibit force-push/delete: `EXTERNAL_PERMISSION_REQUIRED`.
- The separate production checkout is clean, but the primary development
  worktree contains an independently created dirty overlay (`AGENTS.md`, API /
  controller attribution changes, tests, and `graphify-out/`). It was neither
  committed nor discarded. Final branch/worktree cleanup is therefore open.
- Structural codebase reduction is not claimed. From rollback `c9bf3e3d8` to
  `10f8248fc`, no file was added or removed; 11 files changed by `+567/-26`
  lines for measured tracing, lifecycle, routing, and regression coverage.
- Internal compatibility aliases, wrappers, and rollback assets remain because
  references, durable continuations, tests, or physical rollback depend on
  them. No dead public launcher was proven safe to delete in this closeout.
- Large `api.py`/`controller.py` decomposition is a separate post-Pilot backlog,
  not a Runtime-audit completion claim.
- Fresh blind non-inferiority, Reasoner ablation, specialist/Judge/ExecutionGraph
  promotion, training/weekly gates, and release-integrity enforcement remain
  incomplete. They gate `PRODUCTION_BETA` or `STABLE`, not this narrow audit.

## Repository state

Remote long-lived branches are `main` and `dev` at the release revision. The
separate production checkout is clean. The registered development worktree's
independent dirty overlay is preserved, and one temporary integrated worktree
remains until this documentation commit is promoted; stash count is zero.
Twenty-one `archive/20260814/*` tags preserve auxiliary branch, detached
worktree, and stash commits. Dirty overlays remain in the mode-`0600` archive
recorded by hash in `docs/VALIDATION.md`.
