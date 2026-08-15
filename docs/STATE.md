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
development overlay and stale branch/worktree inventory are now integrated and
clean. The re-audit remains in progress because the selected resident Executor
cannot coexist with the still-running Pilot GPU process, and repository branch
protection still requires external administration authority. This does not
promote policy-disabled paths.

## Inspected production release

| Item | Current fact |
| --- | --- |
| Source | Runtime code `main@b3c867854`; clean production checkout `main@5d504f1f4` adds only current evidence/graph updates |
| Rollback | `875f35b8d`; physical rollback and redeploy to `5d504f1f4` both passed authenticated canaries |
| Gateway | PID `3946154`, `NRestarts=0`, healthy authenticated listener on `0.0.0.0:9000`; `/readyz` is honestly `503` while Executor is unavailable |
| Public catalog | only `dgx-moa` and `dgx-moa-fast`, both `context_length: 131072` |
| Active Executor | `opencode_go/deepseek-v4-flash`; local `dgx-moa-executor` is failed and no `9001` listener exists |
| Resident conflict | isolated Pilot PID `3790208` listens on tailnet `100.125.239.72:19000` and occupies the GPU required by local Mistral |
| Lifecycle | `fixed`, exact map `executor -> dgx-moa-executor.service`; operator control is available and generation `27` is failed |
| Enabled integration | Dashboard, Codex OAuth Frontier, DeepSeek Flash scheduling, remote Planner/Reviewer specialist routing |
| Disabled policy paths | ExecutionGraph control, Remote Judge, Loop Engineering, Runtime Skills/Knowledge/Evolution, declarative policy, training collection, weekly jobs |

The ignored production environment reports `runtime_channel=main`,
`trace_origin=production`, and `controller_commit=9d4045b`. That last value is
stale configuration metadata, not source-deployment authority; Git history and
the physical deploy/rollback record establish `b3c867854` as the running code
epoch. Correcting the metadata would require a runtime configuration change and
restart, so it is not part of this documentation-only closeout.

## Executor authority layers

| Layer | Authority |
| --- | --- |
| Active production request path | DeepSeek V4 Flash while local Mistral is unavailable |
| Bounded overflow path | DeepSeek V4 Flash for low/medium risk; a missing required native tool call gets one Codex OAuth Frontier attempt, then remains fail-closed |
| Public API context | `131072`, as returned by `/v1/models` and loaded production config |
| Resident local target | Mistral Small 4 on loopback `9001`, `131072`, seq1, 3.4 GB KV, native allocator, explicit FlashInfer B12x dense/MoE, TRITON_MLA, `FULL_DECODE_ONLY`; currently failed before weight loading because the Pilot leaves insufficient free GPU memory |
| Preserved rollback baseline | Phase 3 `65536`, seq1, 1.7 GB KV, `gpu_memory_utilization=0.5`, MARLIN |

The 65K MARLIN profile remains safety/rollback evidence, not the public context
or the current production provider.

## Implementation matrix

| Capability | Current classification | Measured boundary |
| --- | --- | --- |
| Chat / Responses common execution | `PHYSICALLY_VERIFIED` | current-release authenticated Chat, Responses, SSE and prior cancellation/recovery/long-context gates |
| Codex / OpenCode / Hermes compatibility | `PHYSICALLY_VERIFIED` | Docker-isolated public and hidden validators; preserved pre-fix failures are in `docs/VALIDATION.md` |
| ExecutionGraph | `DISABLED_BY_POLICY` | production aggregate reports `graph_count=0`; graph control remains non-authoritative |
| Role Context projection | `PHYSICALLY_VERIFIED` | current Executor provider input recorded snapshot `1610`, projection `2377`, rendered prompt `10885` bytes, and `2390` provider prompt tokens |
| Evidence persistence | `PHYSICALLY_VERIFIED` | four current-release trace-v3 sessions plus request, role, provider, projection, Dashboard and usage lineage |
| Planner / Reviewer / Judge / Frontier | `PHYSICALLY_VERIFIED` / `DISABLED_BY_POLICY` | remote Planner/Reviewer and Codex OAuth Frontier are live; local optional roles and Remote Judge remain disabled |
| API-key isolation / overflow Executor | `PHYSICALLY_VERIFIED` | current evaluation key was TTL/request/token bounded, denied admin/Dashboard, stored hash-only, revoked, and returned post-revoke `401`; all five requests used Flash |
| Tool call / continuation | `PHYSICALLY_VERIFIED` | current release produced one native tool call and accepted its result in the same session before final synthesis |
| Streaming / cancellation / recovery | `PHYSICALLY_VERIFIED` | SSE terminal, consumer close, active-request drain, Codex reconnect family fixed and replayed |
| Dashboard / WebSocket | `PHYSICALLY_VERIFIED` | operator private-detail audit returned current trace/projection data; WebSocket handshake returned `101` and first frame `connected` |
| Logging / training candidate | `PHYSICALLY_VERIFIED` / `DISABLED_BY_POLICY` | safe runtime logs are live; collection and promotion remain disabled |
| Deployment / rollback | `PHYSICALLY_VERIFIED` | current release physically rolled back to `875f35b8d` and redeployed to `5d504f1f4`; both authenticated canaries passed |

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
  protection and repository rulesets are absent. The available token has
  administration read permission only: `EXTERNAL_PERMISSION_REQUIRED`.
- The required resident Executor port `9001` is not restored. Three unchanged
  baseline starts failed because Pilot PID `3790208` held the GPU, leaving
  `49.15 GiB` free against the `60.81 GiB` startup requirement. Neither the
  qualified baseline nor the unrelated Pilot was changed.
- Structural codebase reduction is not claimed. The overlay integration added
  focused attribution guards/tests and canonical graph artifacts; no legacy
  adapter or rollback asset was proven unreferenced enough to delete.
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
local branches in both clones match those remote refs. The single registered
development worktree and separate production clone are clean, and stash count
is zero. Four clean stale hotfix worktrees and eleven merged local branches were
removed only after ancestry and archive-tag containment were verified.
Twenty-one `archive/20260814/*` tags continue to preserve auxiliary branch,
detached-worktree, and stash commits.
