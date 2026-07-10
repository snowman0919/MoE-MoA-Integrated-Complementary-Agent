#!/usr/bin/env bash
set -Eeuo pipefail
role=${1:?role required}
case "$role" in
  executor) port=8101; minimum=21474836480 ;;
  planner) port=8102; minimum=21474836480 ;;
  reviewer) port=8103; minimum=21474836480 ;;
  judge) port=8110; minimum=17179869184 ;;
  *) exit 64 ;;
esac
timeout=${DGX_MOA_MODEL_START_TIMEOUT:-1200}
deadline=$((SECONDS + timeout))
until curl -fsS "http://127.0.0.1:$port/v1/models" >/dev/null; do
  (( SECONDS < deadline )) || { echo "role=$role readiness timeout=$timeout" >&2; exit 1; }
  sleep 5
done
available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
(( available >= minimum )) || {
  echo "role=$role memory safety available_bytes=$available minimum_bytes=$minimum" >&2
  exit 70
}
echo "role=$role ready port=$port available_bytes=$available"

