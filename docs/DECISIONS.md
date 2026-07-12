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
