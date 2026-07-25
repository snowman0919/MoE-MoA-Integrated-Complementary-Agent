#!/usr/bin/env bash
set -Eeuo pipefail

production_root="${DGX_MOA_PRODUCTION_ROOT:-/home/kotori9/dgx-moa-agent}"
runtime_user="${SUDO_USER:-$(id -un)}"
runtime_uid="${SUDO_UID:-$(id -u)}"
runtime_home="$(getent passwd "$runtime_user" | cut -d: -f6)"
runtime_dir="/run/user/$runtime_uid"
runtime_bus="unix:path=$runtime_dir/bus"

executor_revision="27a8f16f463b9a13c91c332c40cf93e09717347e"
planner_revision="0893e1606ff3d5f97a441f405d5fc541a6bdf404"
reviewer_revision="1e55f4aa327aba4c0b7a1da0d0f24626d3af5c90"

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

verify_revision() {
  local model_path=$1 expected=$2 metadata
  metadata="$model_path/.cache/huggingface/download/config.json.metadata"
  [[ -f "$metadata" && "$(sed -n '1p' "$metadata")" == "$expected" ]] || {
    printf 'baseline revision mismatch: %s\n' "$model_path" >&2
    return 1
  }
}

verify_command() {
  local role=$1
  shift
  local pid command pattern
  pid="$(run_as_runtime_user systemctl --user show "dgx-moa-$role.service" -p MainPID --value)"
  [[ "$pid" =~ ^[1-9][0-9]*$ && -r "/proc/$pid/cmdline" ]] || {
    printf 'baseline process unavailable: %s\n' "$role" >&2
    return 1
  }
  command="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
  for pattern in "$@"; do
    [[ "$command" == *"$pattern"* ]] || {
      printf 'baseline command mismatch: %s field=%s\n' "$role" "$pattern" >&2
      return 1
    }
  done
}

probe() {
  local port=$1 model=$2 marker=$3 response
  response="$(
    curl -fsS --max-time 300 \
      -H 'Content-Type: application/json' \
      -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly: $marker\"}],\"temperature\":0,\"max_tokens\":32}" \
      "http://127.0.0.1:$port/v1/chat/completions"
  )"
  [[ "$response" == *"$marker"* ]] || {
    printf 'baseline inference probe failed: %s\n' "$model" >&2
    return 1
  }
}

preflight() {
  [[ "${DGX_MOA_RESTORE_ACK:-}" == "1" ]] || {
    printf 'set DGX_MOA_RESTORE_ACK=1 for an approved rollback window\n' >&2
    return 1
  }
  [[ -S "$runtime_dir/bus" ]] || {
    printf 'user systemd bus is unavailable: %s\n' "$runtime_dir/bus" >&2
    return 1
  }
  [[ -x "$production_root/scripts/wait-model.sh" ]] || {
    printf 'production wait-model helper unavailable\n' >&2
    return 1
  }
  local container
  for container in dgx-moa-exp-sglang-specialist dgx-moa-exp-sglang-executor; do
    if [[ "$(docker container inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == "true" ]]; then
      printf 'candidate container is still running: %s\n' "$container" >&2
      return 1
    fi
  done
  verify_revision /home/kotori9/models/dgx-moa/executor "$executor_revision"
  verify_revision /home/kotori9/models/specialist-unified-qwen36-27b-nvfp4 "$planner_revision"
  verify_revision /home/kotori9/models/dgx-moa/reviewer "$reviewer_revision"

  local executor_unit planner_unit reviewer_unit
  executor_unit="$(run_as_runtime_user systemctl --user cat dgx-moa-executor.service)"
  planner_unit="$(run_as_runtime_user systemctl --user cat dgx-moa-planner.service)"
  reviewer_unit="$(run_as_runtime_user systemctl --user cat dgx-moa-reviewer.service)"
  [[ "$executor_unit" == *"DGX_MOA_EXECUTOR_BACKEND=vllm"* ]]
  [[ "$executor_unit" == *"$production_root/.venv/bin/python -m dgx_moa.serve executor"* ]]
  [[ "$planner_unit" == *"/home/kotori9/models/specialist-unified-qwen36-27b-nvfp4:/model:ro"* ]]
  [[ "$planner_unit" == *"sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0"* ]]
  [[ "$reviewer_unit" == *"$production_root/.venv/bin/python -m dgx_moa.serve reviewer"* ]]
}

restore() {
  preflight
  run_as_runtime_user systemctl --user reset-failed \
    dgx-moa-executor.service dgx-moa-planner.service dgx-moa-reviewer.service

  run_as_runtime_user systemctl --user start dgx-moa-executor.service
  run_as_runtime_user "$production_root/scripts/wait-model.sh" executor
  verify_command executor \
    "/vllm serve /home/kotori9/models/dgx-moa/executor" \
    "--max-model-len 65536" \
    "--max-num-seqs 1" \
    "--kv-cache-memory-bytes 1700000000" \
    "--gpu-memory-utilization 0.50" \
    "--moe-backend MARLIN"
  probe 8101 dgx-moa-executor EXECUTOR_ROLLBACK_READY

  run_as_runtime_user systemctl --user start dgx-moa-planner.service
  run_as_runtime_user "$production_root/scripts/wait-model.sh" planner
  verify_command planner \
    "/home/kotori9/models/specialist-unified-qwen36-27b-nvfp4:/model:ro" \
    "--context-length 65536" \
    "--max-running-requests 1" \
    "--quantization modelopt"
  probe 8102 dgx-moa-planner PLANNER_ROLLBACK_READY

  run_as_runtime_user systemctl --user start dgx-moa-reviewer.service
  run_as_runtime_user "$production_root/scripts/wait-model.sh" reviewer
  verify_command reviewer \
    "/vllm serve /home/kotori9/models/dgx-moa/reviewer" \
    "--max-model-len 65536" \
    "--max-num-seqs 1" \
    "--reasoning-parser cohere_command4"
  probe 8103 dgx-moa-reviewer REVIEWER_ROLLBACK_READY

  curl -fsS --max-time 10 http://127.0.0.1:9000/readyz >/dev/null
  printf 'production vLLM/North baseline restored and inference-ready\n'
}

case "${1:-}" in
  preflight) preflight ;;
  restore) restore ;;
  *)
    printf 'usage: %s {preflight|restore}\n' "$0" >&2
    exit 64
    ;;
esac
