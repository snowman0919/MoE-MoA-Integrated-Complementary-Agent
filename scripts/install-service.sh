#!/usr/bin/env bash
set -Eeuo pipefail
exec "$(dirname "$0")/install-systemd-user.sh" "$@"
