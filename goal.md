# Dynamic MoA release direction

## Document role

This file defines the final direction and release gates. It is not runtime
evidence or an operations runbook. Current facts belong in `docs/STATE.md`,
operations in `docs/OPERATIONS.md`, and measured successes and failures in the
append-only `docs/VALIDATION.md`.

Frozen plans, protocol epochs, incidents, traces, rollback assets, and archive
tags remain evidence and must not be rewritten as current authority. The full
pre-closeout charter remains reachable with `git show 6e050aa53:goal.md`.

## Status boundary

```text
2026-08-14 Runtime Completion audit = COMPLETE_WITH_EXCEPTIONS
현재 Gateway release = PILOT_ACTIVE
전체 Dynamic MoA 프로젝트 = IN_PROGRESS
PRODUCTION_BETA / STABLE = 미달성
```

The audit result covers its measured Runtime, client, security, deployment,
rollback, and repository-cleanup scope only. It does not mean the final Dynamic
MoA topology or release program is complete.

## Final direction

Build an authenticated OpenAI-compatible gateway in which the Executor owns
tools, routing authority, bounded engineering loops, and client-visible final
synthesis. `dgx-moa` remains the primary Reasoner + Executor policy path and
`dgx-moa-fast` the only intentional Executor-only compatibility path.

Runtime owns canonical request/evidence state and supplies bounded,
role-specific projections. Collaborators receive structured artifacts without
hidden reasoning, cannot mutate the Frontier host, and cannot recursively
delegate. API-key data, traces, and training candidates remain isolated and
secret-free.

Local role endpoints stay loopback-only. Only the bearer-authenticated gateway
may bind `0.0.0.0`. Checked-in optional lifecycle, specialist, graph,
observation, training, weekly, and self-improvement defaults remain disabled
until their own physical promotion gates pass.

## Release stages

```text
DEVELOPMENT -> PILOT_READY -> PILOT_ACTIVE -> PRODUCTION_BETA -> STABLE
```

The current Gateway stage is `PILOT_ACTIVE`. `main` is the reviewed production
source and `dev` is integration. Experiments branch from `dev`; promotion follows
`dev -> main -> production` with explicit approval and a preserved rollback.

### PILOT_ACTIVE contract

- authenticated Chat and Responses, streaming, native tools, continuation,
  cancellation, and recovery;
- API-key isolation and a bounded Executor fallback;
- durable request, event, evidence, and role-projection lineage;
- gateway-only wildcard exposure and fail-closed high-risk behavior;
- a fixed release revision, canary evidence, and physical rollback/redeploy.

The 2026-08-14 audit physically revalidated this narrow contract with the local
Executor intentionally stopped and DeepSeek V4 Flash active. Exceptions remain
listed in `docs/STATE.md`.

### PRODUCTION_BETA gates

- select and physically qualify the intended resident local Executor topology
  before enabling it; do not confuse its checked-in target with the current
  DeepSeek fallback runtime;
- complete fresh representative client validation for any changed runtime path;
- close required specialist, Judge, and ExecutionGraph termination/safety gates
  before enabling those paths;
- reconcile release provenance metadata and enforce reviewed deployment policy;
- configure GitHub required CI and force-push/delete protection with repository
  administration authority;
- keep production canary and exact rollback evidence for the promoted revision.

### STABLE gates

- pass the preregistered blind non-inferiority and Reasoner ablation programs;
- demonstrate long-horizon reliability and bounded convergence without false
  completion;
- physically qualify any promoted training, weekly, observation, Runtime Skill,
  Runtime Knowledge, or recursive-improvement path;
- show sustained operational reliability and release-integrity enforcement;
- resolve remaining architecture debt without changing public security, tool,
  streaming, or continuation semantics.

## Codebase cleanup boundary

Git branch/worktree cleanup and structural code reduction are separate claims.
The former is complete for the audit; the latter is not. Remove only launchers,
aliases, wrappers, or adapters proven unreferenced by source, tests, durable
continuations, and rollback assets. Retain compatibility code when deletion is
riskier than accurately documenting it.

Large decomposition of `gateway/src/dgx_moa/api.py` and `controller.py` is an
independent post-Pilot backlog. It must not be mixed into a closeout or used to
manufacture a line-count reduction.

## Completion rule

Do not infer completion from a Goal checkbox, mock tests, or documentation.
Promote a stage only when current source, configuration, physical runtime,
client-visible behavior, CI, security evidence, canary, and rollback agree.
Until the later gates pass, the overall Dynamic MoA project remains
`IN_PROGRESS` and neither `PRODUCTION_BETA` nor `STABLE` is achieved.
