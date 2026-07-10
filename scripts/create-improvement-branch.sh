#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
layer=${1:?controller, prompt, routing, context, or model-adapter required}
proposal=${2:?proposal ID required}
destination=${3:-../"$proposal"}
[[ $layer =~ ^(controller|prompt|routing|context|model-adapter)$ ]] || exit 64
[[ $proposal =~ ^IMP-[0-9]{4}-[0-9]{4}$ ]] || exit 64
git diff --quiet && git diff --cached --quiet || { echo 'clean baseline required' >&2; exit 65; }
git worktree add -b "auto/$layer/$proposal" "$destination" HEAD
