#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
proposal=${1:-IMP-2026-0001}
directory=data/improvements/$proposal
mkdir -p "$directory"
cp data/benchmarks/mvp-baseline.json "$directory/baseline.json"
cp data/benchmarks/mvp-baseline.json "$directory/candidate.json"
uv run python -m dgx_moa.improvement compare "$directory/baseline.json" "$directory/candidate.json" \
  "$directory/comparison.json"
