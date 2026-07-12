#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
output=${1:-data/datasets/agentic-traces.jsonl}
mkdir -p "$(dirname "$output")"
find data/traces -name '*.jsonl' -type f -print0 | sort -z | xargs -0r cat >"$output"
