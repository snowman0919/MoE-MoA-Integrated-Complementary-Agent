#!/usr/bin/env bash
set -euo pipefail

root=${DGX_MOA_CODEX_PROFILE_ROOT:-"$HOME/.local/share/dgx-moa/codex-profiles"}
action=${1:?login|logout|status|test required}
profile=${2:-}
valid_profile() { [[ $1 =~ ^[a-z][a-z0-9-]{0,31}$ ]]; }
show_status() {
  local name=$1 home="$root/$1"
  if [[ ! -d $home ]]; then
    printf 'profile=%s authenticated=no authentication_mode=oauth state=not_configured\n' "$name"
  elif CODEX_HOME="$home" codex login status >/dev/null 2>&1; then
    printf 'profile=%s authenticated=yes authentication_mode=oauth state=available\n' "$name"
  else
    printf 'profile=%s authenticated=no authentication_mode=oauth state=unavailable\n' "$name"
  fi
}
case $action in
  status)
    if [[ -n $profile ]]; then valid_profile "$profile" || exit 64; show_status "$profile"
    elif [[ -d $root ]]; then for home in "$root"/*; do [[ -d $home ]] && show_status "${home##*/}"; done
    else
      show_status primary
      show_status secondary
    fi ;;
  login)
    valid_profile "$profile" || exit 64
    install -d -m 700 "$root/$profile"
    umask 077
    CODEX_HOME="$root/$profile" codex login --device-auth
    [[ ! -f "$root/$profile/auth.json" ]] || chmod 600 "$root/$profile/auth.json" ;;
  logout)
    valid_profile "$profile" || exit 64
    CODEX_HOME="$root/$profile" codex logout >/dev/null
    printf 'profile=%s authenticated=no authentication_mode=oauth state=logged_out\n' "$profile" ;;
  test)
    valid_profile "$profile" || exit 64
    show_status "$profile"
    [[ ${DGX_MOA_CODEX_MODEL:-} ]] || { echo 'DGX_MOA_CODEX_MODEL required' >&2; exit 64; }
    output=$(mktemp)
    trap 'rm -f "$output"' EXIT
    if ! CODEX_HOME="$root/$profile" codex exec --ephemeral --json --sandbox read-only --model "$DGX_MOA_CODEX_MODEL" 'Reply READY.' | tee "$output"; then
      echo "profile=$profile test_failed" >&2
      exit 1
    fi
    rg -q '"type":"turn.completed"' "$output" || { echo "profile=$profile test_failed" >&2; exit 1; } ;;
  *) exit 64 ;;
esac
