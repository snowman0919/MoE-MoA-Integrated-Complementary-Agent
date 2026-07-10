#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi
base=${DGX_MOA_BASE_URL:-http://${DGX_MOA_BIND_HOST:-127.0.0.1}:${DGX_MOA_BIND_PORT:-9000}}
auth=(-H "Authorization: Bearer ${DGX_MOA_API_KEY:?}")
curl -fsS "${auth[@]}" "$base/v1/models" | uv run python -c \
  'import json,sys; assert json.load(sys.stdin)["data"][0]["id"] == "dgx-moa-agent"'
curl -fsS "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Reply briefly."}]}' \
  "$base/v1/chat/completions" | uv run python -c \
  'import json,sys; assert json.load(sys.stdin)["choices"]'
curl -fsS -N "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"model":"dgx-moa-agent","stream":true,"messages":[{"role":"user","content":"Reply briefly."}]}' \
  "$base/v1/chat/completions" | grep -q 'data: \[DONE\]'
