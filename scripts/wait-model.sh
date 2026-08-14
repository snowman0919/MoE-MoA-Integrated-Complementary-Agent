#!/usr/bin/env bash
set -Eeuo pipefail
role=${1:?role required}
case "$role" in
  executor) port=9001; minimum=5368709120 ;;
  planner) port=8102; minimum=5368709120 ;;
  reviewer) port=8103; minimum=5368709120 ;;
  reasoner) port=11435; minimum=10737418240 ;;
  judge) port=8110; minimum=17179869184 ;;
  *) exit 64 ;;
esac
unit="dgx-moa-$role.service"
timeout=${DGX_MOA_MODEL_START_TIMEOUT:-1200}
deadline=$((SECONDS + timeout))
path=/v1/models
[[ $role != reasoner ]] || path=/api/tags
until curl -fsS "http://127.0.0.1:$port$path" | grep -q "${role/reasoner/Qwythos-v2-9B:Q4}"; do
  (( SECONDS < deadline )) || { echo "role=$role readiness timeout=$timeout" >&2; exit 1; }
  main_pid=$(systemctl --user show "$unit" -p MainPID --value 2>/dev/null || true)
  status=$(systemctl --user show "$unit" -p ExecMainStatus --value 2>/dev/null || true)
  if [[ "$main_pid" == 0 && "$status" == 1 ]]; then
    echo "role=$role service_failed unit=$unit" >&2
    exit 1
  fi
  sleep 5
done
if [[ $role == reasoner ]]; then
  curl -fsS "http://127.0.0.1:$port/api/generate" \
    -d '{"model":"Qwythos-v2-9B:Q4","prompt":"ready","stream":false,"keep_alive":-1,"options":{"num_ctx":65536,"num_predict":1}}' \
    >/dev/null
fi
available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
(( available >= minimum )) || {
  echo "role=$role memory safety available_bytes=$available minimum_bytes=$minimum" >&2
  exit 70
}
echo "role=$role ready port=$port available_bytes=$available"
