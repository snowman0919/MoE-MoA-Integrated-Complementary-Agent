#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi
base=${DGX_MOA_BASE_URL:-http://${DGX_MOA_BIND_HOST:-127.0.0.1}:${DGX_MOA_BIND_PORT:-9000}}
curl -fsS "$base/healthz"
curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY:?}" "$base/v1/models"
curl -fsS "$base/readyz"
