#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --user --no-pager status dgx-moa.target dgx-moa-resident.target \
  dgx-moa-judge.target dgx-moa-gateway.service dgx-moa-executor.service \
  dgx-moa-planner.service dgx-moa-reviewer.service dgx-moa-judge.service || true

