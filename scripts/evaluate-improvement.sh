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
COMPARISON="$directory/comparison.json" VERDICT="$directory/verdict.md" uv run python - <<'PY'
import json, os
result=json.load(open(os.environ['COMPARISON']))
open(os.environ['VERDICT'], 'w').write(
    f"# {result['verdict']}\n\n"
    f"Target failure reduction: {result['target_failure_reduction']:.1%}.\n"
    "\nAutomatic merge: false. Human approval remains required.\n"
)
PY
