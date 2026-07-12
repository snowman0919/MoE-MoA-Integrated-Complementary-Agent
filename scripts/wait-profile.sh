#!/usr/bin/env bash
set -Eeuo pipefail
profile=${1:?resident or judge required}
timeout=${2:-1200}
case "$profile" in
  resident) ports=(8101 8102 8103); minimum=20000000000 ;;
  judge) ports=(8110); minimum=17179869184 ;;
  *) exit 64 ;;
esac
deadline=$((SECONDS + timeout))
while :; do
  ready=true
  for port in "${ports[@]}"; do
    curl -fsS "http://127.0.0.1:$port/v1/models" >/dev/null || ready=false
  done
  if $ready; then
    available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
    (( available >= minimum )) || {
      echo "profile=$profile memory safety available_bytes=$available minimum_bytes=$minimum" >&2
      exit 70
    }
    echo "profile=$profile ready available_bytes=$available"
    exit 0
  fi
  for role in executor planner reviewer judge; do
    if [[ "$(systemctl --user show "dgx-moa-$role.service" -p ExecMainStatus --value 2>/dev/null || true)" == 1 ]]; then
      echo "profile=$profile service_failed=dgx-moa-$role.service" >&2
      exit 1
    fi
  done
  (( SECONDS < deadline )) || { echo "profile=$profile readiness timeout=$timeout" >&2; exit 1; }
  sleep 5
done
