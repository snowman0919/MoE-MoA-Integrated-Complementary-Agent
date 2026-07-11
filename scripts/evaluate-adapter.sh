#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
metadata=${1:?adapter metadata path required}
baseline=${2:?baseline benchmark path required}
candidate=${3:?candidate benchmark path required}
output=${4:?evaluation output path required}
uv run python -m dgx_moa.adapters "$metadata" --baseline "$baseline" --candidate "$candidate" \
  --output "$output"
