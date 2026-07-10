#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
requested=${1:?resident, judge, restore, or status required}
[[ $requested =~ ^(resident|judge|restore|status)$ ]] || exit 64
if [[ $requested == status ]]; then
  uv run python -m dgx_moa.profiles status
  printf 'resident_target=%s\n' "$(systemctl --user is-active dgx-moa-resident.target || true)"
  printf 'judge_target=%s\n' "$(systemctl --user is-active dgx-moa-judge.target || true)"
  exit 0
fi
target=$requested
[[ $target != restore ]] || target=resident
runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$UID}/dgx-moa
mkdir -p "$runtime_dir" data/run
exec 9>"$runtime_dir/profile.lock"
flock -n 9 || { echo 'profile switch already active' >&2; exit 75; }
current=$(uv run python -m dgx_moa.profiles status | uv run python -c \
  'import json,sys; print(json.load(sys.stdin)["active_profile"])')
if [[ $current == "$target" ]] && systemctl --user is-active --quiet "dgx-moa-$target.target"; then
  scripts/wait-profile.sh "$target"
  uv run python -m dgx_moa.profiles ready "$target" >/dev/null
  exit 0
fi
uv run python -m dgx_moa.profiles transition "$target" >/dev/null
uv run python -m dgx_moa.profiles checkpoint >/dev/null
printf '{"timestamp":"%s","from":"%s","to":"%s","status":"starting"}\n' \
  "$(date --iso-8601=seconds)" "$current" "$target" >>data/run/profile-audit.jsonl

rollback() {
  code=$1
  uv run python -m dgx_moa.profiles failed "$target" >/dev/null
  systemctl --user stop "dgx-moa-$target.target" || true
  scripts/verify-profile-stopped.sh "$target" || true
  if [[ $current == resident || $target == judge ]]; then
    if systemctl --user start dgx-moa-resident.target && scripts/wait-profile.sh resident; then
      uv run python -m dgx_moa.profiles ready resident >/dev/null
    fi
  elif [[ $current == judge ]]; then
    if systemctl --user start dgx-moa-judge.target && scripts/wait-profile.sh judge; then
      uv run python -m dgx_moa.profiles ready judge >/dev/null
    fi
  fi
  printf '{"timestamp":"%s","from":"%s","to":"%s","status":"rollback","exit_code":%s}\n' \
    "$(date --iso-8601=seconds)" "$current" "$target" "$code" >>data/run/profile-audit.jsonl
  echo "profile switch failed target=$target rollback=$current exit_code=$code" >&2
  exit "$code"
}

if [[ $target == judge ]]; then
  systemctl --user stop dgx-moa-resident.target || rollback $?
  scripts/verify-profile-stopped.sh resident || rollback $?
else
  systemctl --user stop dgx-moa-judge.target || rollback $?
  scripts/verify-profile-stopped.sh judge || rollback $?
fi
available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
echo "profile=$target prestart_available_bytes=$available"
systemctl --user start "dgx-moa-$target.target" || rollback $?
scripts/wait-profile.sh "$target" || rollback $?
uv run python -m dgx_moa.profiles ready "$target" >/dev/null
printf '{"timestamp":"%s","from":"%s","to":"%s","status":"ready"}\n' \
  "$(date --iso-8601=seconds)" "$current" "$target" >>data/run/profile-audit.jsonl
