# Dynamic MoA completion audit — 2026-08-08

이 문서는 `pasted-text-1.txt` 42개 섹션을 현재 worktree, runtime, Git, 테스트와
운영 문서에 대조한 진행 audit다. `PASS`는 현재 epoch의 요구 범위를 직접 증명할 때만
사용한다. `PARTIAL`은 구현 또는 격리 테스트만 있고 물리 범위가 부족한 경우,
`MISSING`은 필수 증거가 없는 경우, `BLOCKED`는 readiness 또는 human approval 없이는
진행할 수 없는 경우다. 과거 epoch의 성공은 보존하지만 현재 production gate의 PASS로
승격하지 않는다.

## 현재 결론

> 2026-08-12 authority update: this 42-section table remains the preserved
> `STABLE` completion audit. It no longer makes every missing section a
> `PILOT_READY` blocker. The active Pilot rubric and evidence are in `goal.md`,
> `docs/STATE.md`, and protocol `pilot-v1-transition-20260812`.

- Goal status: `IN_PROGRESS`; `COMPLETE` 증거 없음.
- 개발 정적 baseline: Ruff format/check, strict mypy 49 source files,
  `1035 passed`, shell syntax, systemd verify, trace 67/67 complete.
- 현재 물리 runtime: gateway/loopback active, `/healthz` OK, `/readyz` HTTP 503;
  Reasoner만 ready이고 Executor/Planner/Reviewer/Judge는 stopped.
- production `main@396e0458` worktree는 기존부터 dirty이며 이 Goal이 수정하지 않았다.
- Git 정상화 미달: local branch 10개, remote 실험 branch 2개, 등록 worktree 7개와
  임시 long-horizon worktree가 남아 있다. Release/rollback 전 삭제 금지다.
- Execution Graph는 checked-in disabled, development `shadow`다. 실제 attempt와
  checkpoint를 소유하는 범위가 늘었지만 legacy API/Controller가 아직 최종 실행
  authority이므로 architecture completion은 `PARTIAL`이다.

Pilot delta: Candidate A is active and physically qualified; isolated OOM
containment and the authenticated Chat/Responses/stream/tool/continuation,
durable Graph, high-risk fail-closed, restart, and recovery contract passed.
The audit's old Executor `BLOCKED`, deployment ordering, and readiness snapshot
are historical for the 2026-08-08 completion rubric, not current runtime facts.
The Goal remains active in `DEVELOPMENT`, with release revision, installed
defaults/restart, rollback rehearsal, and limited canary still open.

## 42-section requirement audit

| § | 요구 | 상태 | 현재 authoritative evidence / 미달 이유 |
| ---: | --- | --- | --- |
| 1 | dev/main/worktree 정책과 최종 main/dev만 유지 | `PARTIAL` | 개발은 `dev`, production은 `main`; 다수 branch/worktree가 남아 있고 cleanup은 release 후 gate다. |
| 2 | preflight와 기존 증거 보존 | `PASS` | `DYNAMIC_MOA_EVIDENCE_PRESERVATION_20260808.md`, incident/model inventory, dirty/untracked/stash 보존 기록. |
| 3 | 계획·protocol epoch·SHA-256 동결 | `PASS` | 두 frozen plan hash가 `sha256sum -c`를 통과한다. |
| 4 | 목표 역할/model/provider topology | `PARTIAL` | config/routing/runtime policy 구현; target revisions/hashes와 실제 role quality gate가 미완료다. |
| 5 | fixed-revision Mistral backend 물리 gate | `BLOCKED` | 현재 Executor stopped, `/readyz` 503. 이전 isolated load failure 이후 승인 없는 start 금지. |
| 6 | 병렬 Tier 0–3 Dynamic MoA | `PARTIAL` | lifecycle admission 뒤 Reasoner/Planner/Frontier A synchronization-barrier 3-way fan-out와 독립 evidence 보존 PASS; 실제 provider 동시성/compute contention 미검증. |
| 7 | Frontier A App Server + stdin/E2BIG transport | `PARTIAL` | persistent daemon proxy/resume/compaction/interrupt tests PASS; primary/secondary socket 부재, existing default daemon 실제 turn은 300초 timeout으로 FAIL. |
| 8 | bounded active state와 compaction/checkpoint | `PARTIAL` | content-addressed compact checkpoint와 10,000-event resume 테스트 PASS; 실제 long-horizon continuation 미검증. |
| 9 | API-key ownership/privacy | `PARTIAL` | key isolation, hashes, owner/operator Dashboard tests PASS; current physical multi-key audit 미실행. |
| 10 | lease/queue/fairness/Flash/provider pinning | `PARTIAL` | scheduler unit/API tests와 graph scheduling snapshot PASS; actual local-busy Flash concurrency 미검증. |
| 11 | Codex/OpenCode/Hermes/raw common core | `PARTIAL` | Chat/Responses adapters와 과거 client evidence 보존; current epoch actual client matrix 미실행. |
| 12 | Dashboard는 runtime projection, inference 독립 | `PARTIAL` | direct persisted Graph projection과 failure isolation tests PASS; production flag/physical outage test 미실행. |
| 13 | API-key Dashboard scope와 audited raw access | `PARTIAL` | owner/operator scope, audit-reason tests PASS; physical multi-key browser/session 검증 미실행. |
| 14 | 7개 navigation surface | `PARTIAL` | runtime Dashboard 구현/isolated rendering tests; production UI 검증 미실행. |
| 15 | role lanes, parallel/join/state canvas | `PARTIAL` | Graph snapshot/attempt projection tests PASS; actual multi-provider live canvas 미검증. |
| 16 | Inspector SUMMARY/PROMPT/LIVE/OUTPUT/EVIDENCE/EXECUTION/LOGS | `PARTIAL` | endpoints/redaction/object refs 존재; physical prompt/tool/final live view 미검증. |
| 17 | REST snapshot + scoped WebSocket schema | `PARTIAL` | `/admin/runtime/snapshot`, `/admin/ws`, direct graph event tests PASS; production WebSocket 미검증. |
| 18 | output batching과 reliable terminal | `PARTIAL` | batching/terminal unit tests PASS; actual model/tool throughput와 slow network 미검증. |
| 19 | seq replay/RESYNC/backpressure/disconnect | `PARTIAL` | replay/backpressure tests PASS; production reconnect/restart/multiple subscriber gate 미실행. |
| 20 | owner prompt/final object storage와 no hidden reasoning | `PARTIAL` | redaction/content references/opt-out tests PASS; end-to-end retention/secret scan 물리 gate 미실행. |
| 21 | common core refactor와 codebase 순감축 | `PARTIAL` | 시작 epoch 대비 Controller `-159`줄이나 API `+1050`, 전체 gateway source `+4220`; Graph/review 중복, Discord/fake, legacy context tuner, 미참조 OpenAI API Frontier scaffold/Protocol, prompt wrapper, disconnected sanitized feed를 제거했지만 legacy authority가 남아 완료를 반박한다. |
| 22 | normalized SQLite 경계 | `PARTIAL` | graph/attempt/checkpoint/usage/training/audit tables 존재; SessionState serialized payload 의존이 여전히 크다. |
| 23 | recursive-improvement provenance logging | `PARTIAL` | trace/training/graph edge projection tests PASS; runtime improvement/promotion paths는 gate 전 disabled. |
| 24 | role별 gated training datasets | `PARTIAL` | candidate schema, privacy/license/opt-out/review transitions tests PASS; external terms와 physical export gate 미완료. |
| 25 | weekly 7z atomic package | `PARTIAL` | weekly/package/integrity tests와 과거 evidence 존재; current epoch 실제 7-day package 미생성. |
| 26 | cache semantics와 per-invocation usage 합산 | `PASS` | `cached_tokens=null` vs `0`, repeated role accounting, trace/training/CSV/Graph tests PASS. |
| 27 | GB10/mathcat telemetry 격리 | `PARTIAL` | telemetry stores/providers와 failure isolation tests; current physical mathcat/GB10 coverage 미실행. |
| 28 | 90-day retention/rollup/deletion audit | `PARTIAL` | retention logic/tests 존재, apply 기본 disabled/dry-run; physical retention job 미실행. |
| 29 | blind real-use non-inferiority evaluation | `MISSING` | current epoch 30 paired samples/comparator/client strata 없음. |
| 30 | frozen paired-bootstrap statistical contract | `PARTIAL` | stdlib evaluator가 margin `-0.10`, 10,000회/seed `20260808`, 30쌍·coverage·missing/mismatch/telemetry fail-closed를 검증; current matched dataset와 CI 결과 없음. |
| 31 | Reasoner ablation A/B/C/D decision | `MISSING` | current epoch paired ablation과 최종 decision 없음; Reasoner production default 근거 없음. |
| 32 | natural long-horizon stability | `MISSING` | 임시 worktree/과거 runs는 보존됐지만 current target topology의 complete long-horizon gate 없음. |
| 33 | Dashboard physical validation matrix | `MISSING` | feature는 production physical gate 전 disabled; current production readiness도 실패. |
| 34 | model inventory/cleanup/retirement | `PARTIAL` | inventory와 retain/delete candidates 기록; canary/rollback 전 legacy 삭제 금지, target hashes 일부 missing. |
| 35 | static + integration test matrix | `PARTIAL` | static gate PASS; required actual providers/clients/Dashboard/weekly integration 미완료. |
| 36 | ordered dev→PR→main→production release | `BLOCKED` | blind/ablation/dashboard/model gates와 human approval 미충족; merge/deploy 금지. |
| 37 | production canary | `MISSING` | target release가 없고 readiness 503. |
| 38 | rollback rehearsal | `MISSING` | target release rollback source/commands/duration/data-preservation physical evidence 없음. |
| 39 | final branch/worktree cleanup | `BLOCKED` | release+rollback 이전 삭제 금지; 현재 branch/worktree 수가 완료 조건을 반박한다. |
| 40 | 모든 completion condition | `NOT_MET` | MISSING/BLOCKED/INCONCLUSIVE 필수 항목 다수; Goal COMPLETE 금지. |
| 41 | 최종 한국어 evidence report | `PARTIAL` | STATE/OPERATIONS/VALIDATION은 갱신 중; ending release/canary/rollback metrics 없음. |
| 42 | 24-step ordered execution | `IN_PROGRESS` | preflight/plan/hotfix/refactor/scheduler/Dashboard/data/cache 개발은 진행; physical step 7 이후 gate들이 열려 있다. |

## Execution Graph engineering audit

현재 직접 증명된 범위:

- Runtime Policy 소유 deterministic templates, provider/model pins, deadline/budget,
  bounded retry/repair/fallback/no-progress와 terminal status.
- Reasoner/Planner/Frontier A가 서로 기다리지 않고 시작하는 실제 mock task fan-out,
  executor-preparation join, sibling 실패 시 완료 evidence 보존.
- primary Executor, Reviewer, Judge, Frontier B, tool/test, failed tool, hard rejection,
  streaming tool continuation과 compact checkpoint.
- nonce/allowlist 기반 operator approval가 `HUMAN_APPROVAL(WAITING_APPROVAL)`을
  `ON_APPROVAL` Evidence로 재개하는 개발 경로.
- node-type lookup, observed token/cache/cost/latency 정규화와 role failure fingerprint를
  `ExecutionGraphRuntime` 공통 메서드가 소유하며 API/Controller 중복을 제거했다.
- Graph shadow persistence 실패 stage/class 기록도 단일 runtime helper가 소유한다.
- Execution node가 generated/validated/contradicted Evidence node ID를 참조하고,
  Dashboard/training projection이 persisted graph/attempt를 직접 소비한다.

남은 architecture gap:

- `execution_graph.mode`는 `disabled|shadow`뿐이고 legacy API/Controller가 authority다.
- graph runtime이 provider/tool dispatch를 단독 소유하지 않아 일부 stage boundary는 API의
  start/finish adapter에 의존한다.
- post-stream Reviewer/Judge는 이미 client output이 전달되므로 deferred이며, high-risk stream은
  non-stream retry gate를 사용한다.
- production 승격에 필요한 physical parallelism, partial restart, long-horizon resume,
  provider/client/Dashboard comparison과 source/branch normalization이 없다.

## 다음 허용 순서

1. development에서 Graph-owned stage adapters를 공통 execution core로 이동하고 legacy
   orchestration branch/source delta를 다시 측정한다.
2. dirty production tree와 stopped model services를 변경하지 않은 채 isolated provider/model
   readiness plan을 준비한다.
3. explicit approval 후 Mistral/remote roles/Frontier transports/client/Dashboard physical gates를
   같은 epoch에서 실행한다.
4. blind evaluation, Reasoner ablation, long-horizon, dev release validation을 통과한 뒤에만
   PR/merge/deploy/canary/rollback/retirement/branch cleanup을 순서대로 수행한다.

## Pilot delta — 2026-08-12

- Production gateway PID `3107456` and Pilot attempt-10 PID `3704865` are
  active with zero restarts; the Pilot runs release `ed9f3d943` under 1/2/0.5
  GiB caps.
- The exhausted TOOL-graph projection defect passed clean validation and
  physical reprojection with zero post-fix shadow failures.
- Explicit Codex catalog pinning exposes `apply_patch`, but compatibility and
  primary repository-write probes left the isolated worktree unchanged. The
  quality gate remains open.
- vLLM native NVFP4 remains candidate A; SGLang candidate B v66/v98 evidence is
  preserved for this epoch; MARLIN remains rollback only.
- Goal status remains active `PILOT_ACTIVE`; neither terminal `blocked` nor
  `complete` is authorized.
