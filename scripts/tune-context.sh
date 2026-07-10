#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
profile=${1:?resident or judge required}
[[ $profile =~ ^(resident|judge)$ ]] || exit 64
set -a
source .env
[[ ! -f .env.local ]] || source .env.local
set +a
exec .venv/bin/python -m dgx_moa.context_tuning trial "$profile"
