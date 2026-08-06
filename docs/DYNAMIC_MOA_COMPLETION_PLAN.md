# Dynamic MoA Completion Plan (v1)

This document is the immutable execution contract for the active goal. No protocol
or evaluation logic changes are allowed without creating a new immutable epoch.

## 1) Scope freeze

- Runtime topology target (final):
  - Executor: fixed `Qwen3-Coder-Next-NVFP4` on dedicated loopback instance.
  - Planner/Reviewer: unified local `nvidia/Gemma-4-26B-A4B-NVFP4` on dedicated loopback instance.
  - Context / concurrency: `context=65536`, `max_num_seqs=1`, `radix cache` enabled.
  - Gateway remains loopback-only for model endpoints and tailnet-only for gateway auth.
- Remote fallback policy:
  - OpenRouter is best-effort tail fallback only; Frontier remains operator/codex
    collaboration path and must not replace local specialists by default.
- Hard guard:
  - New changes do not bypass authenticated gateway, provider pinning, privacy redaction,
    or fail-closed policy for mandatory risk-level work.
- This plan is effective only for work in `dev`/`auto/*` candidates. No production worktree edits.

## 2) Branching and role normalization

- Branch contract:
  - `main`: production-tracked source only.
  - `dev`: integration/testing candidate baseline.
  - `auto/<layer>/<proposal-id>`: isolated experiments only.
- Mandatory state preservation before edits:
  - current branches, worktrees, stash list, merge-base/main ancestry, production commit.
- Worktree policy:
  - candidate and long-horizon experiments run only in detached/isolated worktrees.
  - main and dev must stay checkout roles above.
- Merge contract:
  - `auto -> dev -> release verification -> main` only.

## 3) Refactor boundaries

- Consolidate shared execution core:
  - Chat/Responses orchestration
  - inference/admin/training router
  - Controller orchestration/review/evidence responsibilities
  - lifespan-aware HTTP client
  - SQLite usage/quota schema boundaries
- No duplicate wrappers/adapters once a shared implementation is confirmed.
- Remove fake-model/dead code only when referenced by runtime/tests with live evidence.

## 4) Cache contract and routing policy

- Separate caches:
  - `prompt_cache` (input-level prefix reuse)
  - `runtime_prefix_cache` (provider-runtime prefix state)
- Policy:
  - cache hints are normalized before logging/dispatch.
  - cached-token missing values and zero must remain distinguishable.
  - Planner/Reviewer usage in same specialist runtime must be aggregated at request-level.
- Routing:
  - cold specialist never blocks normal request completion.
  - local unready -> remote immediate, trigger warmup singleflight.
- Eviction and residency:
  - keep existing role-specific protected/residency contracts unless a validated reason to change is produced.

## 5) Telemetry and storage schema

- Required trace fields:
  - selected provider/model, routing reason, load/queue timing,
    remote fallback reason, local completion estimates, quality outcome, task outcome.
- Must not emit raw prompt/response, prompt text, API key/token/cookie, tool arguments, reasoning.
- Retention:
  - admin/audit records remain 90 days.
- All new fields require schema update in `docs/TRACE_SCHEMA.md` equivalent path and
  SQLite columns only through content-free columns.

## 6) Evaluation protocol

- Use frozen 10h evaluation prompt:
  - `/home/kotori9/.codex/attachments/536d35e4-c763-4ee5-ae8d-72e663c3bc2b/avatarforge-10h-validation-goal.md`
- Compare non-trivially with:
  - GPT-5.6-sol equivalent
  - Claude Opus 5-tier frontier path
- Required gates (all with confidence bounds):
  - quality non-inferiority in Codex/OpenCode/Hermes matrix
  - throughput/latency/cost reliability with preserved confidence intervals
  - live context continuity and reconnect stability
  - five-hour+ or longer operational stress without session collapse
  - rollback rehearsal and post-rehearsal canary validation
- INCONCLUSIVE is not pass.

## 7) Production hard gates

- Canary: production canary + gateway-only security + rollback rehearsal must pass after merge.
- Recovery:
  - readiness proof on 8101/8102 and end-to-end request proof on 9000.
- Deployment blockers:
  - no merge/deploy/model deletion until all hard gates pass for current epoch.
- Model retirement:
  - keep explicit evidence package: model id, revision, hash, and retirement rationale.

## 8) Epoch controls

- If protocol or schema changes, open new immutable attempt:
  - copy `docs/DYNAMIC_MOA_COMPLETION_PLAN.md` with `epoch` suffix
  - rerun evidence pipeline from scratch
  - never patch prior epoch as equivalent.

## 8.1 Frozen checkpoint marker

- This version is immutable for current edits unless a new epoch is created:
  - `DYNAMIC_MOA_COMPLETION_PLAN.md.sha256 = d5a56be6dd4e807854df33a7981078e087be39d7da00e41490cdcb6a7a40ece7`
