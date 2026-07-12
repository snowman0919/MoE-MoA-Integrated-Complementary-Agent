#!/usr/bin/env bash
set -Eeuo pipefail
role=${1:?role required}
case "$role" in
  executor) port=8101; minimum=10737418240 ;;
  planner) port=8102; minimum=10737418240 ;;
  reviewer) port=8103; minimum=10737418240 ;;
  reasoner) port=8104; minimum=10737418240 ;;
  judge) port=8110; minimum=17179869184 ;;
  *) exit 64 ;;
esac
unit="dgx-moa-$role.service"
timeout=${DGX_MOA_MODEL_START_TIMEOUT:-1200}
deadline=$((SECONDS + timeout))
until curl -fsS "http://127.0.0.1:$port/v1/models" >/dev/null; do
  (( SECONDS < deadline )) || { echo "role=$role readiness timeout=$timeout" >&2; exit 1; }
  main_pid=$(systemctl --user show "$unit" -p MainPID --value 2>/dev/null || true)
  status=$(systemctl --user show "$unit" -p ExecMainStatus --value 2>/dev/null || true)
  if [[ "$main_pid" == 0 && "$status" == 1 ]]; then
    echo "role=$role service_failed unit=$unit" >&2
    exit 1
  fi
  sleep 5
done
available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
(( available >= minimum )) || {
  echo "role=$role memory safety available_bytes=$available minimum_bytes=$minimum" >&2
  exit 70
}
echo "role=$role ready port=$port available_bytes=$available"
