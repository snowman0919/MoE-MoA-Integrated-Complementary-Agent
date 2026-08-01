# Model Compatibility

Updated: 2026-08-02

## Runtime Baseline

- Architecture: `aarch64`, NVIDIA GB10 (`sm_121`)
- Driver/CUDA: `580.159.03` / `13.0`
- Production rollback stack: vLLM `0.22.1`, PyTorch `2.11.0`, Transformers `5.8.1`
- Isolated candidate stack: pinned `lmsysorg/sglang:dev-cu13` image
- Container candidate `docker/model-runner@sha256:1d084f67fc52bd71035397bbf3868ddfee1ccfaa14060952b7ecf5d2cc5102a6` is llama.cpp, therefore rejected for vLLM serving.

## Selected Checkpoints

| Role | Repository | Revision | License | Quantization | Size | Status |
|---|---|---|---|---|---:|---|
| Executor | `Cirrascale/Qwen3-Coder-Next-NVFP4` | `15c399c8189eccc9c47d17dcf8adf3c16e8bb3f8` | Apache-2.0 | ModelOpt NVFP4 | `47500860663` | isolated SGLang candidate validated |
| Planner + Reviewer | `nvidia/Gemma-4-26B-A4B-NVFP4` | `a19cfe00be84568a6867111c9a68c9c44fdcffe6` | NVIDIA Open Model License | ModelOpt NVFP4 | `18825681233` | isolated SGLang candidate validated |
| Judge | `nvidia/Mistral-Medium-3.5-128B-NVFP4` | `b8c66d2098edd8c9c26bde2b2ff41b5967e111ae` | NVIDIA Open Model License / Mistral Modified MIT terms | ModelOpt NVFP4 | `95259207898` | downloaded; runtime validation pending |

The previous Nemotron Planner and North Reviewer remain pinned only for the
explicit vLLM rollback procedure. They are not selected candidate models.

## Runtime Notes

- Candidate Executor parser `qwen3_coder` preserved tool-call ID and JSON arguments.
- Candidate Planner and Reviewer intentionally share one Gemma 4 MoE process,
  parser, fixed revision, and loopback endpoint. Readiness still requires a real
  inference probe for each role.
- Local vLLM initially failed with `ModuleNotFoundError: No module named
  'flash_attn.ops'`; local compatibility shim uses vLLM's bundled rotary kernel.
- The vLLM rollback runtime selected Marlin weight-only FP4, not native FP4
  compute. The isolated candidate explicitly uses SGLang `modelopt_fp4`.
- The rollback Nemotron model requires parser `nemotron_v3`; the rollback North
  model requires Cohere-compatible parsing. Those constraints do not apply to
  the Gemma candidate.
- Judge model card validates vLLM `0.21.0`, `trust_remote_code`, and native
  `Mistral3ForConditionalGeneration`; local runtime is vLLM `0.22.1`.
- Judge is dense 128B, native text context `262144`, with no tool-call parser;
  gateway enforces read-only strict `JudgeVerdict` JSON.
