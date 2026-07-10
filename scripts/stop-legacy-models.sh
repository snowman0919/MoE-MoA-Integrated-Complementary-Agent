#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for role in planner reviewer executor judge; do
  pidfile="data/run/$role.pid"
  [[ -s $pidfile ]] || continue
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for _ in {1..60}; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  fi
  rm -f "$pidfile"
done

