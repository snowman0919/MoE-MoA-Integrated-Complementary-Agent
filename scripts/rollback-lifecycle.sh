#!/usr/bin/env bash
set -Eeuo pipefail
config_arg=${1:?explicit lifecycle config path required}
[[ $# -eq 1 ]] || exit 64
config=$(realpath "$config_arg")
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

.venv/bin/python -m dgx_moa.lifecycle_admin rollback --config "$config"
systemctl --user restart dgx-moa-gateway.service
scripts/switch-profile.sh resident
scripts/healthcheck.sh

base=${DGX_MOA_BASE_URL:-http://${DGX_MOA_BIND_HOST:-127.0.0.1}:${DGX_MOA_BIND_PORT:-9000}}
status_json=$(curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY:?}" \
  "$base/v1/model-status")
printf '%s' "$status_json" | .venv/bin/python -c '
import json, sys
status = json.load(sys.stdin)
if status.get("lifecycle_mode") != "disabled":
    raise SystemExit("lifecycle rollback verification failed")
if status.get("automation", {}).get("automation_disabled"):
    raise SystemExit("lifecycle circuit reset verification failed")
'
