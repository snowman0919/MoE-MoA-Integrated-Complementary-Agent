# Decisions

## 2026-07-10

- Use host vLLM `0.22.1` first: already installed and GPU-capable on GB10.
- Use SQLite and an explicit state machine; no workflow framework or external database.
- Use host available memory as unified-memory evidence because NVIDIA-SMI omits GB10 memory.
- Reuse valid Hugging Face cache objects; never clean or duplicate unrelated caches.
- Defer exact resident topology until independent model startup measurements exist.
- Add a local namespace shim for vLLM's bundled rotary kernel: host `flash-attn-4`
  exposes `flash_attn` but not legacy `flash_attn.ops`, causing vLLM `0.22.1`
  startup to fail before weights load.
- Generate a reviewer-only HF config override changing `model_type` from
  `cohere2_moe` to compatible `cohere2`. vLLM `0.22.1` contains the native
  `Cohere2MoeForCausalLM` loader, while Transformers `5.8.1` lacks only the
  config mapping; all MoE fields remain preserved.
- Calibrate vLLM `--gpu-memory-utilization` per role even with explicit KV
  bytes. vLLM still performs its startup guard first; default `0.92` rejected a
  valid second process before loading weights.

## 2026-07-12

- Define `main` as stable production and recursive control plane, `dev` as
  integration, and isolated `auto/*` worktrees from `dev` as experiments.
- Use decision trajectories, not raw transcripts, as the learning evidence unit.
- Keep append-oriented JSONL plus SQLite indexing; date-partition v2 archives by
  runtime provenance and classify v1 as legacy.
- Fail closed on primary state loss; continue safely with explicit degraded
  observability when only the secondary trace archive fails.
- Require explicit training eligibility and keep trace collection separate from export.
- Exclude resolved, expected, synthetic, false-positive, and superseded failures
  from default mining; rank evidence using configurable provenance weights.
- Keep Frontier Codex connected but disabled while the minimal bubblewrap
  capability issue remains unresolved; do not weaken host or sandbox security.
- Preserve the measured judge, resident model, KV, context, unit topology, and
  headroom settings unless new direct evidence invalidates them.
- Wait for unified-memory reclamation before profile startup. The resident
  readiness gate is 10 GiB under explicit operator approval on 2026-07-13;
  kernel OOM or any lower measurement still rejects startup.
- Treat raw task and observation text as untrusted data for reviewer/judge roles;
  give those roles acceptance criteria and a final literal JSON-only boundary.

## 2026-07-18

- Expose fixed `dgx-moa-chat`, `dgx-moa-agent`, and `dgx-moa-orchestrated`
  aliases through the existing authenticated gateway; direct modes remain
  executor-only and external agents own native tool loops.
- Require only standard OpenAI request fields. Keep project metadata and
  provenance headers optional, preserve upstream response/tool fields, default
  executor output to 4096 tokens, and cap it at 16384.
- Forward complete SSE events immediately with exactly one DONE. Bound both
  streaming observation capture and one SSE event to 1,000,000 bytes, and record
  `finish_reason=length` as truncation rather than completion.
- Keep streaming review off the critical path. Bound non-streaming reviewer
  evidence to 16,000 characters, preserve valid output on low-risk review
  failure, and allow high-risk explicit orchestration to fail closed.
- Keep lifecycle `disabled` with an empty unit map by default. Automated safety
  contracts do not establish physical memory recovery or production readiness.
- Use full service stop as the only executable unload fallback today because it
  is exact-unit authorized and has a verifiable inactive state. Do not imply a
  sleep, KV-eviction, or offload implementation.
- Bound adaptive idle policy by role-class minimum/fallback/maximum and minimum
  residency. Require two idle checks and 20 positive role-local gaps before the
  inclusive-p75-times-1.5 threshold can replace fallback.
- Keep sleep, KV eviction, offload, mechanism selection, production enablement,
  and threshold recommendations pending physical measurement. Canonical states,
  routes, blockers, and pending evidence are in `docs/MODEL_LIFECYCLE.md`.

## 2026-07-19

- Select exact transient-systemd full process stop/start for executor unload and
  retain it as mandatory fallback. Sleep level 1 returned only 47.12% of the
  matched full-stop MemAvailable delta and failed owned-PSS stability; sleep
  level 2 and live reset failed exact post-wake/reset quality.
- Keep the executor baseline unchanged at context 65,536, one sequence,
  1,700,000,000 KV bytes, `gpu_memory_utilization=0.5`, and MARLIN. FP8,
  prefix-off, eager, chunked prefill, CPU offload, and KV offload did not beat
  the deterministic memory/safety/quality rule.
- Change only the undeployed checked-in resident target to gateway+executor.
  Planner, reviewer, and reasoner remain optional with target cleanup. Keep
  lifecycle disabled and the unit map empty until a separate human-reviewed
  fixed/adaptive deployment proves migration and rollback.
- Keep the gateway in Python. Its five-minute isolated peak PSS, idle CPU, and
  health p99 were 46.48 MiB, 0.250%, and 2.166 ms, all below the predeclared
  256 MiB, 1%, and 50 ms Rust thresholds; focused recovery tests passed.
- Preserve all failed/partial Phase 3 roots and content-free evidence. Host
  MemAvailable remains noisy, unified-memory GPU-byte fields remain null, and
  model equality remains a metadata fingerprint rather than a content hash.

## 2026-07-20

- Adopt role-aware adaptive lifecycle as the `dev` release candidate, with
  executor normally resident and idle unload disabled. Planner, reviewer, and
  reasoner may unload by their own bounded successful-request gaps; judge stays
  outside automation.
- Return an immediate typed JSON `503` for a required cold role and expose honest
  role/state/generation/weight/overall/ETA data. Explicit optional reasoner use
  may degrade and continue; ordinary chat/agent requests never add reasoner.
- Latch lifecycle mutations off after three failures in the configured window,
  while preserving status and already-ready traffic. Use atomic, idempotent
  disabled-mode rollback as the recovery boundary.
- Treat the passing four-role user-systemd fake-weight result as control-plane
  evidence only. Do not infer real-weight memory savings or call production
  deployed until a separately approved migration runs the real model matrix.
