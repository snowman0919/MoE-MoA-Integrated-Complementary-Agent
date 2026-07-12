#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
uv run python -m dgx_moa.dataset data/traces data/datasets/executor-sft.jsonl \
  data/datasets/manifests/executor-sft.json
