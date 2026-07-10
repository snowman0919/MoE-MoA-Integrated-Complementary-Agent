# Model Compatibility

Updated: 2026-07-10

## Runtime Baseline

- Architecture: `aarch64`, NVIDIA GB10 (`sm_121`)
- Driver/CUDA: `580.159.03` / `13.0`
- Host stack: vLLM `0.22.1`, PyTorch `2.11.0`, Transformers `5.8.1`
- Container candidate `docker/model-runner@sha256:1d084f67fc52bd71035397bbf3868ddfee1ccfaa14060952b7ecf5d2cc5102a6` is llama.cpp, therefore rejected for vLLM serving.

## Selected Checkpoints

| Role | Repository | Revision | License | Quantization | Size | Status |
|---|---|---|---|---|---:|---|
| Executor | `RedHatAI/Qwen3-Coder-Next-NVFP4` | `27a8f16f463b9a13c91c332c40cf93e09717347e` | Apache-2.0 | NVFP4 compressed-tensors | `47613230236` | runtime validated |
| Planner | `cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit` | `49cee6bbed2edd4e2d305d948ac443714a2ab242` | NVIDIA Open Model License | AWQ compressed-tensors | `20767782252` | runtime validated |
| Reviewer | `CohereLabs/North-Mini-Code-1.0-w4a16` | `1e55f4aa327aba4c0b7a1da0d0f24626d3af5c90` | Apache-2.0 | NVFP4 W4A16 | `19382986619` | runtime validated |
| Judge | `nvidia/Mistral-Medium-3.5-128B-NVFP4` | `b8c66d2098edd8c9c26bde2b2ff41b5967e111ae` | NVIDIA Open Model License / Mistral Modified MIT terms | ModelOpt NVFP4 | `95259207898` | downloaded; runtime validation pending |

## Runtime Notes

- Executor README validates vLLM `0.14.1`; local vLLM `0.22.1` loaded it.
- Executor parser `qwen3_coder` preserved tool-call ID and JSON arguments.
- Local vLLM initially failed with `ModuleNotFoundError: No module named
  'flash_attn.ops'`; local compatibility shim uses vLLM's bundled rotary kernel.
- GB10 runtime selected Marlin weight-only FP4, not native FP4 compute.
- Planner model documentation requires vLLM `>=0.17.1`, parser `nemotron_v3`.
- Reviewer documentation requires vLLM main and Cohere Melody for accurate parsing;
  local vLLM `0.22.1` includes `cohere_command4`, but Melody is absent.
- Judge model card validates vLLM `0.21.0`, `trust_remote_code`, and native
  `Mistral3ForConditionalGeneration`; local runtime is vLLM `0.22.1`.
- Judge is dense 128B, native text context `262144`, with no tool-call parser;
  gateway enforces read-only strict `JudgeVerdict` JSON.
