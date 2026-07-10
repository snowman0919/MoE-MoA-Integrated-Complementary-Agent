#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
systemctl --user stop dgx-moa.target dgx-moa-resident.target dgx-moa-judge.target \
  dgx-moa-gateway.service dgx-moa-executor.service dgx-moa-planner.service \
  dgx-moa-reviewer.service dgx-moa-judge.service 2>/dev/null || true
systemctl --user disable dgx-moa-resident.target 2>/dev/null || true
for unit in systemd/dgx-moa-*.service systemd/dgx-moa*.target; do
  rm -f "$HOME/.config/systemd/user/$(basename "$unit")"
done
systemctl --user daemon-reload

