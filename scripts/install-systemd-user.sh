#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
start=false
[[ ${1:-} != --start ]] || start=true
units=(
  systemd/dgx-moa-gateway.service
  systemd/dgx-moa-loopback.service
  systemd/dgx-moa-loopback.socket
)
systemd-analyze --user verify "${units[@]}"
mkdir -p "$HOME/.config/systemd/user"
for unit in "${units[@]}"; do install -m 0644 "$unit" "$HOME/.config/systemd/user/"; done
if systemctl --user list-unit-files dgx-moa-agent.service --no-legend 2>/dev/null | grep -q .; then
  systemctl --user disable --now dgx-moa-agent.service || true
  rm -f "$HOME/.config/systemd/user/dgx-moa-agent.service"
fi
systemctl --user daemon-reload
systemctl --user disable dgx-moa-resident.target 2>/dev/null || true
systemctl --user enable dgx-moa-gateway.service dgx-moa-loopback.socket
if $start; then
  systemctl --user start dgx-moa-gateway.service
  systemctl --user start dgx-moa-loopback.socket
fi
scripts/systemd-status.sh
