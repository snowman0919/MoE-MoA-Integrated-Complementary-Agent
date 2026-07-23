#!/usr/bin/env bash
set -Eeuo pipefail

gateway_url="${DGX_MOA_GATEWAY_URL:-http://127.0.0.1:9000}"
timeout_seconds="${DGX_MOA_DRAIN_TIMEOUT_SECONDS:-300}"
: "${DGX_MOA_OPERATOR_KEY:?set DGX_MOA_OPERATOR_KEY to an active admin key}"

request() {
    printf 'header = "Authorization: Bearer %s"\n' "$DGX_MOA_OPERATOR_KEY" |
        curl --fail --silent --show-error --config - "$@"
}

cancel_drain() {
    request --request DELETE "$gateway_url/v1/admin/drain" >/dev/null 2>&1 || true
}

trap cancel_drain ERR INT TERM
request --request POST "$gateway_url/v1/admin/drain" >/dev/null
deadline=$((SECONDS + timeout_seconds))

while true; do
    active="$(
        request "$gateway_url/v1/admin/drain" |
            python3 -c 'import json,sys; print(int(json.load(sys.stdin)["active_request_count"]))'
    )"
    if ((active == 0)); then
        break
    fi
    if ((SECONDS >= deadline)); then
        echo "drain timed out with active_request_count=$active" >&2
        exit 1
    fi
    sleep 1
done

trap - ERR INT TERM
systemctl --user restart dgx-moa-gateway.service
healthcheck="$(dirname "$0")/healthcheck.sh"
for ((attempt = 1; attempt <= 30; attempt++)); do
    if "$healthcheck" >/dev/null 2>&1; then
        "$healthcheck"
        exit 0
    fi
    sleep 1
done
"$healthcheck"
