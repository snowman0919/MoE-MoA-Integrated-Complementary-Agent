#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
runtime_user="${SUDO_USER:-$(id -un)}"
runtime_uid="${SUDO_UID:-$(id -u)}"
runtime_home="$(getent passwd "$runtime_user" | cut -d: -f6)"
runtime_group="$(id -gn "$runtime_user")"
runtime_dir="/run/user/$runtime_uid"
runtime_bus="unix:path=$runtime_dir/bus"
unit_root="$runtime_home/.config/systemd/user"
dropin_root="$unit_root/dgx-moa-executor.service.d"

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

[[ -S "$runtime_dir/bus" ]] || {
  echo "user systemd bus is unavailable: $runtime_dir/bus" >&2
  exit 1
}

run_as_runtime_user install -d -m 0755 "$dropin_root"
run_as_runtime_user install -m 0644 \
  "$root/systemd/dgx-moa-executor-vllm-restore.conf" \
  "$dropin_root/99-vllm-restore.conf"
if [[ "$(id -u)" == 0 ]]; then
  chown -R "$runtime_user:$runtime_group" "$dropin_root"
fi
run_as_runtime_user systemctl --user daemon-reload

run_as_runtime_user systemctl --user stop dgx-moa-planner.service dgx-moa-reviewer.service
run_as_runtime_user systemctl --user stop dgx-moa-executor.service
run_as_runtime_user systemctl --user start dgx-moa-executor.service
"$root/scripts/wait-model.sh" executor

executor_pid="$(
  run_as_runtime_user systemctl --user show dgx-moa-executor.service -p MainPID --value
)"
executor_command="$(tr '\0' ' ' <"/proc/$executor_pid/cmdline")"
[[ "$executor_command" == *"/vllm serve "* ]] || {
  echo "vLLM restore verification failed: executor backend is not vLLM" >&2
  exit 1
}

run_as_runtime_user systemctl --user start dgx-moa-planner.service
"$root/scripts/wait-model.sh" planner
run_as_runtime_user systemctl --user start dgx-moa-reviewer.service
"$root/scripts/wait-model.sh" reviewer

echo "vLLM executor and local specialists restored"
