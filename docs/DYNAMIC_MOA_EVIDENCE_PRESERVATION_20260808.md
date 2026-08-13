# Dynamic MoA evidence preservation manifest

- captured_at: `2026-08-08T15:49:10+09:00`
- protocol_epoch: `dynamic-moa-v2-20260808`
- development: `dev@f2c20a78d814ef9cd59424f372fa42d503874054`
- production: `main@396e0458f25977293281b953d2c804cf5b689970`
- policy: 이 manifest의 reachability, dirty content, evidence verdict를 모두 확인하기 전
  branch/worktree/stash/model/runtime data를 삭제하지 않는다.

## Branches

| Branch | Commit | Upstream | Preservation note |
| --- | --- | --- | --- |
| `dev` | `f2c20a78d814ef9cd59424f372fa42d503874054` | `origin/dev` same | integration baseline |
| `main` | `396e0458f25977293281b953d2c804cf5b689970` | `origin/main` same | production source |
| `archive/dev-before-realign-20260807-041020` | `e6c6b512e02dda6a3f267fc4c17704d09dc4fb10` | none | dev에서 reachable; 삭제 전 evidence verdict |
| `archive/local-main-before-normalization-20260804` | `c0947cd52ba5b10b9e08c6c09857adb3f6c9b522` | none | dev 미도달 고유 commit 1개 |
| `auto/cleanup/shared-runtime-core` | `7a344eb9e4c562f1a4b15483c6ad4ea53c5aef7c` | none | dev에서 reachable |
| `auto/controller/IMP-2026-0001` | `9054f57a3c2695fbf6d36f7313f7275cc6828ed0` | none | 고유 commit 1개 + dirty worktree |
| `auto/evaluation/frontier-noninferiority-v1` | `5133cfc92f2b2ed7d9cfb1087001fb8a47d4d15d` | same remote | 고유 commits 2개 |
| `auto/integration/sglang-topology-v1` | `704fe5ce4534f3b5c0acfa1505e362ed7c2657bc` | none | 고유 commits 9개 |
| `auto/runtime/sglang-gemma4-v1` | `607a4a3c9908f16ff35df1104d44d7a997e2a666` | remote at `26bf6ba9...` | local이 remote보다 32 commits 앞섬 |
| `auto/validation/all-model-observability-eval` | `fc892f94e8d83179a059d3b9333d1f3b2897cc48` | none | dirty worktree |
| `codex/pre-rebase-dynamic-moa` | `69717556ca4fae14f1636d482f54d8f3c94a4d43` | none | dev 미도달 고유 commits 2개 |

Remote branches는 capture 시점에 `main`, `dev`,
`auto/evaluation/frontier-noninferiority-v1`, `auto/runtime/sglang-gemma4-v1` 네 개다.
Remote 삭제는 release/rollback 완료 후 별도 human approval을 요구한다.

## Worktrees

| Path | Commit/branch | State |
| --- | --- | --- |
| `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` | `dev@f2c20a78...` | dirty plan epoch transition |
| `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent-observability-eval` | `auto/validation/all-model-observability-eval@fc892f94...` | tracked + untracked dirty evidence |
| `/home/kotori9/code/MoE-MoA-sglang-gemma4` | `auto/runtime/sglang-gemma4-v1@607a4a3c...` | clean |
| `/home/kotori9/code/MoE-MoA-sglang-topology-integration` | `auto/integration/sglang-topology-v1@704fe5ce...` | clean |
| `/home/kotori9/code/dgx-moa-imp-2026-0001` | `auto/controller/IMP-2026-0001@9054f57a...` | tracked dirty |
| `/var/tmp/dgx-moa-avatarforge-v171/workspace` | detached `bed3669154a037d222d64b2c120ee772f953b7ea` | clean; commit reachable from SGLang branch |
| `/var/tmp/dgx-moa-long-v34/codex-workspace` | detached `bc46dfe69c23265e8b475849e255770a7388fe29` | clean; commit reachable from SGLang branch |
| `/var/tmp/dgx-moa-long-v35/codex-workspace` | detached `652cfa17b52281b5a17823e62fbc956aa656d9d7` | untracked `durable_job_core.py`; preserve separately |

추가 preservation refs:

- `refs/preservation/20260802/controller-dirty@6ab71eaf...`
- `refs/preservation/20260802/dev-dirty@3869e1c0...`
- `refs/preservation/20260802/long-v35-dirty@578afd1b...`
- `refs/preservation/20260802/observability-dirty@7b1eeeac...`

## Stashes

| Ref | Commit | Description | Approximate diff |
| --- | --- | --- | --- |
| `stash@{0}` | `07d70078ec6e10fd7d3cdc979e414cb6c57a798c` | dev plan/refactor/key/provider hardening | 8 files, `+78/-31` plus untracked artifacts |
| `stash@{1}` | `f0f7249110cd253606d9b021dff11b7c8e7042c0` | branch realign; fake-model/client matrix | 2 files, `+9/-84` plus plan |
| `stash@{2}` | `f250c123bdfdffac91b782975f33674425cae698` | main Frontier/controller changes | 7 files, `+423/-57` plus plan/config |
| `stash@{3}` | `bc52c3a3c297b499913432e9f39ae077608d0003` | historical Dynamic MoA implementation snapshot | 38 files, `+2831/-350` plus untracked implementation/evidence |

Stash 번호는 새 stash 생성 시 변하므로 commit SHA를 authoritative identifier로 사용한다.
적용하기 전에 isolated worktree에서 file-by-file patch-equivalence와 tests를 확인한다.

## Development ignored evidence

- `data/`: 약 140 MiB.
- `.superpowers/sdd/`: 약 3 MiB.
- ignored files 총 1,283개.
- 포함: `data/state/gateway.db`, `data/state/runtime.db`, weekly/evolution/knowledge DB,
  datasets, 88 trace files, 655 training-staging files, 392 staging files, 실험 reports/state.

이 데이터는 branch reachability와 무관하다. archive checksum/manifest와 복구 검증 없이
worktree cleanup 또는 model cleanup의 부수 효과로 제거하지 않는다.

## Production worktree and runtime state

Production path `/home/kotori9/dgx-moa-agent`는 `main@396e0458...`이지만 dirty다.

Tracked changes:

- `config/codex-frontier.yaml`
- `config/models.yaml`
- `gateway/src/dgx_moa/api.py`
- `gateway/src/dgx_moa/config.py`
- `gateway/src/dgx_moa/controller.py`
- `gateway/src/dgx_moa/frontier.py`
- `tests/test_frontier.py`
- total `+361/-66`

Untracked paths:

- `data/state/backups/sglang-transition-20260727-0125/env.local` (credential 가능; 내용 금지)
- `data/state/backups/sglang-transition-20260727-0125/models.yaml`
- `runtime_state.sqlite` (0 bytes at preflight)

실행 service가 tracked dirty source/config 중 무엇을 사용했는지는 아직 판정되지 않았다.
production tree를 reset/checkout/patch하지 않는다. 배포 manifest는 source commit, effective
config hash, service unit hash, model revision/hash, DB backup/checksum, rollback source를 함께 기록한다.

## Deletion gate

각 대상에 다음 record가 모두 있어야 삭제 가능하다.

```text
target
exact commit/path/hash
reachable_from_dev_or_main
patch_equivalent_or_rejected
dirty_content_archived
evidence_artifacts_archived
baseline/candidate verdict
reproduction_command
rollback_reference_absent
service/config/test reference count = 0
human_approval_id when required
```

하나라도 `MISSING`이면 보존한다.
