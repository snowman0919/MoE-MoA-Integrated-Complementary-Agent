#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
start=false
[[ ${1:-} != --start ]] || start=true
units=(systemd/dgx-moa-*.service systemd/dgx-moa-*.socket systemd/dgx-moa*.target)
systemd-analyze --user verify "${units[@]}"
mkdir -p "$HOME/.config/systemd/user"
for unit in "${units[@]}"; do install -m 0644 "$unit" "$HOME/.config/systemd/user/"; done
if systemctl --user list-unit-files dgx-moa-agent.service --no-legend 2>/dev/null | grep -q .; then
  systemctl --user disable --now dgx-moa-agent.service || true
  rm -f "$HOME/.config/systemd/user/dgx-moa-agent.service"
fi
systemctl --user daemon-reload
systemctl --user enable dgx-moa-resident.target dgx-moa-loopback.socket
if $start; then
  scripts/stop-legacy-models.sh
  uv run python -m dgx_moa.profiles ready stopped >/dev/null
  scripts/switch-profile.sh resident
  systemctl --user start dgx-moa-loopback.socket
fi
scripts/systemd-status.sh
