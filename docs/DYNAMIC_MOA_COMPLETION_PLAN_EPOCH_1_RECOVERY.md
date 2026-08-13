# Dynamic MoA Completion Plan v1 recovery snapshot

이 문서는 2026-08-08 preflight 당시 canonical plan의 dirty worktree 내용을
보존한다. 새 epoch의 평가 결과와 혼합하지 않는다.

- recovered_at: `2026-08-08T15:49:10+09:00`
- source_worktree_sha256: `d21912c5694cb6c4631d68b8d1cf6b7fd8c0eed1ef3539f075e27c1ef766033b`
- source_worktree_blob: `0da011efc543fc4706e981629982d9f424005713`
- source_index_sha256: `280fe2733fb006aa3ad98969a26ec2d4ad8e61c5de843f91d35ba127a262e40b`
- source_index_blob: `3cc55d2f6662ab4a2753e33a998514c3bdf5692c`
- source_recorded_sidecar: `3348801fbae4331187ade5dbecaaab57eda1013116bfbcb80826f4c06b6903af`
- recovery_reason: embedded self-hash와 sidecar가 exact file hash와 불일치하고 새 목표의 topology/protocol이 v1과 달라 새 epoch가 필요함

## Recovered worktree content

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
  - `DYNAMIC_MOA_COMPLETION_PLAN.md.sha256 = 3348801fbae4331187ade5dbecaaab57eda1013116bfbcb80826f4c06b6903af`

## 8.2 AvatarForge 10h benchmark protocol (frozen fixture)

- Fixture source: `/home/kotori9/.codex/attachments/536d35e4-c763-4ee5-ae8d-72e663c3bc2b/avatarforge-10h-validation-goal.md`
- Fixture prompt hash (frozen): `37878be8c6e67262e80b680cea5effa504ed3cafef55d886ae41e9bc35d507fa`
  (stored in `.goal-avatarforge-goal-sha256.txt`)
- Execution contract:
  - Per tool-path (Codex/OpenCode/Hermes) run `>=5h` active-work with same repository, same seed, same fixture.
  - Every tool-path run writes a run artifact root under a unique `run_id` and never reuses live production runtime state.
  - Each run keeps: plan file snapshot, command transcript, client stdout/stderr, readiness probe result, failure/retry/reconnect events, and completion markers.
- Gatekeeper checks before pass:
  - `generic` and `primary` model calls on the harness gateway both return `200`.
  - each client receives exact marker phrase for its path without tool-carrying fallback tricks.
  - execution has no `INCONCLUSIVE`, `BLOCKED`, or unclassified incomplete state.
  - non-empty `executor` and `reasoner` invocation counts are recorded and >0.
- Failure handling:
  - if a client hangs beyond command timeout, stop and mark protocol as `RUN_ERROR` with timeout evidence, then restart that segment with a smaller scope only for that tool-path.
