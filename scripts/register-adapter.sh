#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
uv run python -m dgx_moa.adapters "${1:?adapter metadata path required}"
