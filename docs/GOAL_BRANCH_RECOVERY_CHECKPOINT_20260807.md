# Goal branch recovery checkpoint (2026-08-07)

## 1) Repository role status

- `main`: production-tracked branch, checked out in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent`.
- `dev`: integration branch, currently aligned with `origin/dev`.
- `auto/*`: keep as isolated experiment branches/worktrees.

## 2) Commit and upstream snapshot

- `main`: `396e0458f25977293281b953d2c804cf5b689970` (`origin/main`)
- `dev`: `f2c20a78d814ef9cd59424f372fa42d503874054` (`origin/dev`)
- `origin/HEAD`: `main`

## 3) Worktree map

- `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` → `dev` (this repo path is currently on `main`/`dev` role depending on checkout step; after checkpoint it is the repo root for normal role work).
- `/home/kotori9/code/MoE-MoA-sglang-gemma4` → `auto/runtime/sglang-gemma4-v1`
- `/home/kotori9/code/MoE-MoA-sglang-topology-integration` → `auto/integration/sglang-topology-v1`
- `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent-observability-eval` → `auto/validation/all-model-observability-eval`
- `/home/kotori9/code/dgx-moa-imp-2026-0001` → `auto/controller/IMP-2026-0001`

## 4) Evidence preservation (stashes)

- `stash@{0}`: dev — plan + refactor/keys/provider/test hardening set (`docs/DYNAMIC_MOA_COMPLETION_PLAN.md`, `gateway/src/dgx_moa/*`, `tests/test_api*.py`)
- `stash@{1}`: dev — cleanup fake-model + client quality matrix adjustments
- `stash@{2}`: main — frontier/controller/frontier testset changes
- `stash@{3}`: dev — large historical snapshot including controller/dashboard/test stack

## 5) Active execution contract

- Restored contract file: `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`
- Restored hash file: `docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256`
- Verified `sha256(contents(plan)) == hashfile`.
