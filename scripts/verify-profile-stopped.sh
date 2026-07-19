#!/usr/bin/env bash
set -Eeuo pipefail
profile=${1:?resident or judge required}
case "$profile" in
  resident) services=(executor planner reviewer reasoner); ports=(8101 8102 8103 8104) ;;
  judge) services=(judge); ports=(8110) ;;
  *) exit 64 ;;
esac
deadline=$((SECONDS + 180))
while :; do
  stopped=true
  for service in "${services[@]}"; do
    systemctl --user is-active --quiet "dgx-moa-$service.service" && stopped=false
  done
  for port in "${ports[@]}"; do
    curl -fsS "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1 && stopped=false
  done
  $stopped && exit 0
  (( SECONDS < deadline )) || { echo "profile=$profile stop verification timeout" >&2; exit 1; }
  sleep 2
done
