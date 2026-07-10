#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
args=()
for role in "$@"; do args+=(--role "$role"); done
uv run python -m dgx_moa.model_download verify \
  --config "${DGX_MOA_CONFIG:-config/models.yaml}" "${args[@]}"

