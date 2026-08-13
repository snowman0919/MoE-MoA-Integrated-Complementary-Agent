# Pilot Worktree Inventory — 2026-08-13

The operator owns every retained worktree and stash. None is a production
source. Production is the clean `/home/kotori9/dgx-moa-agent` checkout of
`main`; development is the clean primary checkout of `dev`.

| Worktree | Purpose | Disposition |
| --- | --- | --- |
| `MoE-MoA-Integrated-Complementary-Agent-observability-eval` | concurrent observability/event-feed evaluation | preserve dirty state |
| `MoE-MoA-sglang-gemma4` | rejected Candidate-B runtime evidence | preserve clean |
| `MoE-MoA-sglang-topology-integration` | topology integration evidence | preserve clean |
| `dgx-moa-imp-2026-0001` | isolated controller experiment | preserve dirty state |
| `moa-pilot-v1-release-candidate` | Pilot release and client-quality evidence | preserve |
| `moa-pilot-write-canary-01` | detached write-canary evidence | preserve |
| `/var/tmp/dgx-moa-avatarforge-v171/workspace` | detached client-quality evidence | preserve |
| `/var/tmp/dgx-moa-long-v34/codex-workspace` | detached long-run evidence | preserve |
| `/var/tmp/dgx-moa-long-v35/codex-workspace` | detached long-run evidence with one untracked artifact | preserve |

Five stashes are retained rollback/conflict evidence; `stash@{0}` is the
pre-release normalization snapshot. Divergent `archive/*`, `auto/*`, and
`codex/*` branches are not merged or deleted by this epoch.

Running services retained at audit time are the fixed production gateway,
Pilot attempt 12, v112 and v127 client-quality gateways, Candidate A v67, and
the v67 validation gateway. Candidate A is production-critical. The others are
operator-owned evidence/reproduction runtimes and must not be stopped by an
unrelated cleanup. No `dgx-moa-reasoner.service` is installed.
