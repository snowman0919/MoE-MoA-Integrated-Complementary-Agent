#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --user --no-pager status \
  dgx-moa-gateway.service dgx-moa-loopback.socket dgx-moa-loopback.service || true
docker ps --filter "name=dgx-moa-exp-sglang-" \
  --format '{{.Names}} {{.Status}} {{.Ports}}'
