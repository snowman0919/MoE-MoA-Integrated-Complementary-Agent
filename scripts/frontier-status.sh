#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/codex-profile.sh" status "$@"
