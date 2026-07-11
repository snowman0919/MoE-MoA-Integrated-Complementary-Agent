#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --profile && ${3:-} == --systemd ]]; then
  : "${DGX_MOA_FRONTIER_TASK:?frontier task path required}"
  : "${DGX_MOA_FRONTIER_WORKTREE:?frontier worktree required}"
  : "${DGX_MOA_CODEX_MODEL:?verified Codex model required}"
  exec uv run python -m dgx_moa.frontier run --profile "$2" --task "$DGX_MOA_FRONTIER_TASK" \
    --worktree "$DGX_MOA_FRONTIER_WORKTREE" --model "$DGX_MOA_CODEX_MODEL"
fi
exec uv run python -m dgx_moa.frontier run "$@"
