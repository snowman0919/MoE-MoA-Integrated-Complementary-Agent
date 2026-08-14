# State

Updated: 2026-08-15

## Current decision authority

This file contains current operating facts only. Measured successes and failures
are append-only in `docs/VALIDATION.md`; frozen plans and the pre-closeout state
remain reachable through `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`,
`archive/20260814/*`, and `git show 6e050aa53:docs/STATE.md`.

```text
2026-08-14 Runtime Completion audit = COMPLETE_WITH_EXCEPTIONS
현재 Gateway release = PILOT_ACTIVE
전체 Dynamic MoA 프로젝트 = IN_PROGRESS
PRODUCTION_BETA / STABLE = 미달성
```

`COMPLETE_WITH_EXCEPTIONS` is limited to the Runtime audit: the shared Runtime
fixes, isolated client batches, temporary-key isolation, production canaries,
rollback/redeploy, and Git/worktree cleanup passed. It does not promote the
policy-disabled MoA paths or satisfy later release stages.

## Inspected production release

| Item | Current fact |
| --- | --- |
| Source | Runtime code `main@22424effe`; production checkout contains it plus the current evidence update |
| Rollback | Pre-toggle source `0905d3880`; exact ignored environment/unit backup under `~/.local/state/dgx-moa/rollback-executor-toggle-20260815` |
| Gateway | PID `2888487`, `NRestarts=0`, healthy authenticated listener on `0.0.0.0:9000` |
| Public catalog | only `dgx-moa` and `dgx-moa-fast`, both `context_length: 131072` |
| Active Executor | `opencode_go/deepseek-v4-flash` through the reviewed production scheduling override |
| Local Executor | operator-disabled after a physical ON/canary/OFF cycle; no listener on loopback `9001` |
| Lifecycle | `fixed`, exact map `executor -> dgx-moa-executor.service`; operator control is active |
| Enabled integration | Dashboard, Codex OAuth Frontier, DeepSeek Flash Executor scheduling |
| Disabled policy paths | ExecutionGraph control, specialist routing, Remote Judge, Loop Engineering, Runtime Skills/Knowledge/Evolution, declarative policy, training collection, weekly jobs |

The ignored production environment reports `runtime_channel=main`,
`trace_origin=production`, and `controller_commit=9d4045b`. That last value is
stale configuration metadata, not source-deployment authority; Git history and
the physical deploy/rollback record establish `22424effe` as the running code
epoch. Correcting the metadata would require a runtime configuration change and
restart, so it is not part of this documentation-only closeout.

## Executor authority layers

| Layer | Authority |
| --- | --- |
| Active production request path | DeepSeek V4 Flash Executor; low/medium-risk fallback while local Mistral is operator-stopped |
| Public API context | `131072`, as returned by `/v1/models` and loaded production config |
| Operator-disabled local candidate | Mistral Small 4 on loopback `9001`, `131072`, seq1, 3.4 GB KV, native allocator, explicit FlashInfer B12x dense/MoE, TRITON_MLA, `FULL_DECODE_ONLY` |
| Preserved rollback baseline | Phase 3 `65536`, seq1, 1.7 GB KV, `gpu_memory_utilization=0.5`, MARLIN |

The operator-disabled local candidate is not described as the active Executor. The 65K
MARLIN profile remains safety/rollback evidence, not the public context or the
current production provider.

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
- Git/worktree cleanup is complete, but structural codebase reduction is not.
  The audited release kept file counts at `50/6/62` and added 129 source lines
  for shared safety/recovery. No net code reduction is claimed.
- Internal compatibility aliases, wrappers, and rollback assets remain because
  references, durable continuations, tests, or physical rollback depend on
  them. No dead public launcher was proven safe to delete in this closeout.
- Large `api.py`/`controller.py` decomposition is a separate post-Pilot backlog,
  not a Runtime-audit completion claim.
- Fresh blind non-inferiority, Reasoner ablation, specialist/Judge/ExecutionGraph
  promotion, training/weekly gates, and release-integrity enforcement remain
  incomplete. They gate `PRODUCTION_BETA` or `STABLE`, not this narrow audit.

## Repository state

Local and remote long-lived branches remain only `main` and `dev`. The
registered development worktree and separate production checkout are clean;
stash count is zero.
Twenty-one `archive/20260814/*` tags preserve auxiliary branch, detached
worktree, and stash commits. Dirty overlays remain in the mode-`0600` archive
recorded by hash in `docs/VALIDATION.md`.
