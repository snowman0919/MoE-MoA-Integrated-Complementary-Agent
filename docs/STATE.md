# State

Updated: 2026-07-11T00:00:00+09:00

## Verified Host

- Host: `kodex9-thinkstation` (`kodex9-thinkstation.tailda041a.ts.net`)
- Platform: Lenovo ThinkStation PGX, NVIDIA GB10, compute capability `12.1`
- OS: Ubuntu `24.04.4 LTS`; kernel `6.17.0-1021-nvidia`; `aarch64`
- CPU: 20 cores; 10 Cortex-X925 and 10 Cortex-A725
- Unified memory: `128452014080` bytes total; `121050546176` bytes available
- Swap: `17179865088` bytes total; `14845390848` bytes free
- Driver: `580.159.03`; CUDA runtime/SDK: `13.0` / `13.0.3`
- Root/home filesystem: ext4; `320534515712` bytes available
- Docker: `29.2.1`, Compose `v5.0.2`, GPU smoke test passed
- Tailscale: `1.98.4`, logged in, backend `Running`, direct tailnet TCP configured
- Tailscale IP: `100.125.239.72`
- Host vLLM: `0.22.1`; PyTorch `2.11.0`; Transformers `5.8.1`
- Hugging Face CLI: `1.17.0`; authenticated as `snowman0919`
- Existing caches: `~106G` Hugging Face, `~65G` under `~/models`
- Existing production-model target: absent
- User systemd: available but degraded; passwordless sudo unavailable
- Ports `8101`, `8102`, `8103`, `8110`, and `9000`: free

## Safety Findings

- NVIDIA-SMI reports unified GPU memory as `Not Supported`; use host available memory.
- Existing Docker containers and model caches are unrelated and remain untouched.
- Local image `docker/model-runner:latest-vllm-cuda` is llama.cpp `b9592`, not vLLM.
- Disk allows cautious downloads, but four large checkpoints may exceed safe capacity.

## Model Progress

- Executor `RedHatAI/Qwen3-Coder-Next-NVFP4` revision
  `27a8f16f463b9a13c91c332c40cf93e09717347e`: downloaded, structurally
  verified, loaded, completion passed, tool call passed, stopped cleanly.
- Reviewer `CohereLabs/North-Mini-Code-1.0-w4a16` revision
  `1e55f4aa327aba4c0b7a1da0d0f24626d3af5c90`: downloaded, structurally
  verified, loaded, strict JSON review passed, stopped cleanly.
- Planner `cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit` revision
  `49cee6bbed2edd4e2d305d948ac443714a2ab242`: downloaded, structurally
  verified, loaded, strict JSON plan passed, stopped cleanly.
- Global four-model conservative storage preflight: unsafe; required
  `341791321430` bytes with `320384012288` bytes free.
- Reviewer and planner remain individually safe before download.
- Heavy judge `nvidia/Mistral-Medium-3.5-128B-NVFP4`, revision
  `b8c66d2098edd8c9c26bde2b2ff41b5967e111ae`, exact size `95259207898` bytes;
  final-headroom gate passed and download/verification is in progress.
- Selected resident topology: executor + planner + reviewer, all resident.
- Resident context limits: `16384`, `8192`, `8192`; `max_num_seqs=1`.
- Resident KV reservations: `500000000`, `750000000`, `750000000` bytes.
- Measured resident available-memory headroom: `25148334080` bytes.
- Total downloaded model directory usage: `87764024323` bytes.
- Remaining filesystem capacity: `230613487616` bytes.

## Deployment

- User service `dgx-moa-gateway.service`: active; gateway on tailnet bind
  `100.125.239.72:9000`.
- Model ports `8101`, `8102`, `8103`: loopback-only and ready.
- Gateway health, readiness, non-streaming, streaming, real tool call, and
  SQLite restart persistence passed.
- Docker Compose gateway image built as
  `sha256:2a1f97eb4c54c6b5644621a3ace80ac15b9259410dcbb06cf5702b869fc3742b`.
- Tailscale Serve and Funnel remain disabled by design.

## Current Phase

Resident systemd profile is ready; heavy judge download/runtime validation and
empirical context tuning remain in progress.

## Development Branch Evidence

- `codex/goal` adds repository-aware session state, route reasons, normalized
  tool observations, role-specific bounded contexts, JSONL decision-point traces,
  deterministic fixture benchmarking, and guarded improvement/dataset/adapter tools.
- The benchmark baseline is synthetic; it does not replace resident runtime or
  physical remote OpenCode validation.
