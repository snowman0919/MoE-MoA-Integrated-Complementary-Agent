#!/usr/bin/env bash
set -Eeuo pipefail
role=${1:?role required}
if [[ "$role" == reasoner ]]; then
  echo "start-model skipped for external-managed reasoner role=reasoner" >&2
  exit 0
fi
systemctl --user start "dgx-moa-$role.service"
