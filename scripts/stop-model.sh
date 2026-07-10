#!/usr/bin/env bash
set -Eeuo pipefail
role=${1:?role required}
systemctl --user stop "dgx-moa-$role.service"
