#!/usr/bin/env bash
set -Eeuo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
image="lmsysorg/sglang:dev-cu13@sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0"
executor_model="${DGX_MOA_EXPERIMENT_EXECUTOR_MODEL:-/home/kotori9/models/experimental/qwen3-coder-next-modelopt-nvfp4-15c399c8}"
specialist_model="${DGX_MOA_EXPERIMENT_SPECIALIST_MODEL:-/home/kotori9/models/experimental/gemma-4-31b-it-nvfp4-4135a98a}"
executor_revision="15c399c8189eccc9c47d17dcf8adf3c16e8bb3f8"
specialist_revision="4135a98a9b728a548947683219633b25682223ac"
executor_container="dgx-moa-exp-sglang-executor"
specialist_container="dgx-moa-exp-sglang-specialist"
runtime_user="${SUDO_USER:-$(id -un)}"
runtime_uid="${SUDO_UID:-$(id -u)}"
runtime_home="$(getent passwd "$runtime_user" | cut -d: -f6)"
runtime_dir="/run/user/$runtime_uid"
runtime_bus="unix:path=$runtime_dir/bus"

run_as_runtime_user() {
  if [[ "$(id -u)" == "$runtime_uid" ]]; then
    env \
      HOME="$runtime_home" \
      XDG_RUNTIME_DIR="$runtime_dir" \
      DBUS_SESSION_BUS_ADDRESS="$runtime_bus" \
      "$@"
  else
    runuser -u "$runtime_user" -- env \
      HOME="$runtime_home" \
      XDG_RUNTIME_DIR="$runtime_dir" \
      DBUS_SESSION_BUS_ADDRESS="$runtime_bus" \
      "$@"
  fi
}

executor_command=(
  docker run -d --name "$executor_container" --pull never
  --restart unless-stopped
  --gpus all --network bridge -p 127.0.0.1:18101:18101
  --memory 72g --memory-swap 72g --oom-score-adj 1000
  -v "$executor_model:/model:ro"
  -v dgx-moa-exp-sglang-executor-cache:/root/.cache
  "$image"
  python -m sglang.launch_server
  --model-path /model --host 0.0.0.0 --port 18101
  --served-model-name dgx-moa-executor-candidate
  --context-length 65536 --mem-fraction-static 0.45
  --max-running-requests 1 --max-total-tokens 65536
  --max-mamba-cache-size 5 --quantization modelopt_fp4
  --disable-overlap-schedule
  --cuda-graph-backend-decode disabled
  --cuda-graph-backend-prefill disabled
  --tool-call-parser qwen3_coder
  --enable-metrics --enable-cache-report --incremental-streaming-output
)

specialist_command=(
  docker run -d --name "$specialist_container" --pull never
  --restart unless-stopped
  --gpus all --network bridge -p 127.0.0.1:18102:18102
  --memory 48g --memory-swap 48g --oom-score-adj 1000
  -v "$specialist_model:/model:ro"
  -v dgx-moa-exp-sglang-specialist-cache:/root/.cache
  "$image"
  python -m sglang.launch_server
  --model-path /model --host 0.0.0.0 --port 18102
  --served-model-name dgx-moa-specialist-candidate
  --context-length 65536 --mem-fraction-static 0.90
  --max-running-requests 1 --max-total-tokens 65536
  --swa-full-tokens-ratio 0.06
  --quantization modelopt_fp4
  --cuda-graph-backend-decode disabled
  --cuda-graph-backend-prefill disabled
  --reasoning-parser gemma4 --tool-call-parser gemma4
  --enable-metrics --enable-cache-report --incremental-streaming-output
)

print_command() {
  printf '%q ' "$@"
  printf '\n'
}

check_revision() {
  local model_path=$1 expected=$2 metadata
  metadata="$model_path/.cache/huggingface/download/config.json.metadata"
  [[ -f "$metadata" ]] || {
    printf 'missing revision metadata: %s\n' "$metadata" >&2
    return 1
  }
  [[ "$(sed -n '1p' "$metadata")" == "$expected" ]] || {
    printf 'unexpected model revision: %s\n' "$model_path" >&2
    return 1
  }
}

check_content() {
  local model_path=$1 manifest=$2
  (cd "$model_path" && sha256sum --strict --status -c "$manifest") || {
    printf 'model content hash mismatch: %s\n' "$model_path" >&2
    return 1
  }
}

preflight() {
  [[ "${DGX_MOA_ISOLATED_ACK:-}" == "1" ]] || {
    printf 'set DGX_MOA_ISOLATED_ACK=1 for an approved maintenance window\n' >&2
    return 1
  }
  [[ -S "$runtime_dir/bus" ]] || {
    printf 'user systemd bus is unavailable: %s\n' "$runtime_dir/bus" >&2
    return 1
  }
  local unit
  for unit in dgx-moa-executor dgx-moa-planner dgx-moa-reviewer; do
    if run_as_runtime_user systemctl --user is-active --quiet "$unit"; then
      printf 'production model service is active: %s\n' "$unit" >&2
      return 1
    fi
  done
  docker image inspect "$image" >/dev/null
  check_revision "$executor_model" "$executor_revision"
  check_revision "$specialist_model" "$specialist_revision"
  check_content "$executor_model" "$repository_root/config/sglang-executor.sha256"
  check_content "$specialist_model" "$repository_root/config/sglang-specialist.sha256"
  [[ -z "$(ss -ltnH 'sport = :18101 or sport = :18102')" ]] || {
    printf 'candidate port already in use\n' >&2
    return 1
  }
  ! docker container inspect "$executor_container" >/dev/null 2>&1
  ! docker container inspect "$specialist_container" >/dev/null 2>&1
}

wait_server() {
  local container=$1 url=$2 deadline=$((SECONDS + 1800))
  until curl -fsS "$url/v1/models" >/dev/null 2>&1; do
    if ((SECONDS >= deadline)) || [[ "$(docker container inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != "true" ]]; then
      printf 'candidate server did not become available: %s\n' "$container" >&2
      return 1
    fi
    sleep 5
  done
}

stop_candidates() {
  local container
  for container in "$specialist_container" "$executor_container"; do
    if docker container inspect "$container" >/dev/null 2>&1; then
      if [[ "$(docker container inspect -f '{{.State.Running}}' "$container")" == "true" ]]; then
        docker stop -t 180 "$container" >/dev/null
      fi
      docker rm "$container" >/dev/null
    fi
  done
}

case "${1:-}" in
  print)
    print_command "${executor_command[@]}"
    print_command "${specialist_command[@]}"
    ;;
  preflight)
    preflight
    ;;
  start)
    preflight
    "${executor_command[@]}"
    if ! wait_server "$executor_container" "http://127.0.0.1:18101"; then
      stop_candidates
      exit 1
    fi
    if ! "${specialist_command[@]}"; then
      stop_candidates
      exit 1
    fi
    if ! wait_server "$specialist_container" "http://127.0.0.1:18102"; then
      stop_candidates
      exit 1
    fi
    ;;
  stop)
    stop_candidates
    ;;
  status)
    docker ps --filter "name=dgx-moa-exp-sglang-" \
      --format '{{.Names}} {{.Status}} {{.Ports}}'
    ;;
  *)
    printf 'usage: %s {print|preflight|start|stop|status}\n' "$0" >&2
    exit 64
    ;;
esac
