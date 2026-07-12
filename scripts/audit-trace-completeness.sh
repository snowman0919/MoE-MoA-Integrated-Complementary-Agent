#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m dgx_moa.trace audit "${1:-data/traces}"
