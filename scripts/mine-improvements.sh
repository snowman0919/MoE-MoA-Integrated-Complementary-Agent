#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
uv run python -m dgx_moa.improvement mine data/benchmarks/mvp-baseline.json \
  data/improvements/IMP-2026-0001/proposal.json
