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
