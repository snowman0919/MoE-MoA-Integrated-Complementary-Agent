#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
uv run python -m dgx_moa.model_registry inspect \
  Qwen/Qwen3-Coder-Next Qwen/Qwen3-Coder-Next-FP8 RedHatAI/Qwen3-Coder-Next-NVFP4 \
  nvidia/Nemotron-Cascade-2-30B-A3B cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit \
  CohereLabs/North-Mini-Code-1.0 CohereLabs/North-Mini-Code-1.0-w4a16 \
  Qwen/Qwen3.5-122B-A10B nvidia/Qwen3.5-122B-A10B-NVFP4 \
  --output data/state/model-candidates.json

