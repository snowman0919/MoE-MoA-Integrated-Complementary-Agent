#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/run data/state
exec 9>data/run/download.lock
flock -n 9 || { echo 'another model download is active' >&2; exit 75; }
roles=("${@:-executor reviewer planner judge}")
failures=0
for role in ${roles[*]}; do
  echo "role=$role state=preflight"
  if ! scripts/estimate-model-storage.sh "$role"; then
    echo "role=$role state=capacity-blocked" >&2
    failures=1
    continue
  fi
  started=$(date +%s)
  if uv run python -m dgx_moa.model_download download --role "$role" \
    --config "${DGX_MOA_CONFIG:-config/models.yaml}" | tee "data/state/download-$role.json"; then
    echo "role=$role state=verified elapsed_seconds=$(($(date +%s)-started))"
  else
    code=$?
    echo "role=$role state=failed exit_code=$code" >&2
    failures=1
  fi
done
exit "$failures"
