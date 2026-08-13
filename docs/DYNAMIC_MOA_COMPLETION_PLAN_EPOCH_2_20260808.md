# Dynamic MoA Production Completion Plan

이 문서는 `protocol_epoch=dynamic-moa-v2-20260808`의 동결 실행 계약이다.
이전 Qwen/Gemma/AvatarForge epoch와 결과를 혼합하지 않는다. exact file SHA-256은
self-reference를 피하기 위해 `docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256`에만 기록한다.
실질적 계획·평가 protocol 변경은 새 epoch와 새 sidecar를 만든다.

## 1. Freeze metadata

```yaml
protocol_epoch: dynamic-moa-v2-20260808
created_at: 2026-08-08T15:49:10+09:00
starting_dev_commit: f2c20a78d814ef9cd59424f372fa42d503874054
starting_main_commit: 396e0458f25977293281b953d2c804cf5b689970
starting_production_commit: 396e0458f25977293281b953d2c804cf5b689970
plan_hash_algorithm: SHA-256 over exact bytes of this file
plan_hash_location: docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256
source_goal: /home/kotori9/.codex/attachments/b509d274-1917-40d4-98a1-052adb7ed6d5/pasted-text-1.txt
```

`COMPLETE`는 모든 필수 물리 gate가 같은 epoch에서 통과한 경우에만 허용한다.
`FAILED`, `MISSING`, `INCONCLUSIVE`, `TELEMETRY_INCOMPLETE`가 하나라도 남으면
merge, production deploy, old model 삭제와 `COMPLETE` 선언을 금지한다.

## 2. Preflight snapshot

### Git과 worktree

- 개발: `dev@f2c20a78d814ef9cd59424f372fa42d503874054`, `origin/dev`와 동일.
- 기준: `main=origin/main@396e0458f25977293281b953d2c804cf5b689970`.
- `merge-base(dev,main)=396e0458...`; `dev`는 `main`보다 2 commits 앞서며 분기 없음.
- remote branches 4개: `main`, `dev`, `auto/evaluation/frontier-noninferiority-v1`,
  `auto/runtime/sglang-gemma4-v1`.
- local branches 11개, worktrees 8개, stashes 4개. 고유 commit 또는 dirty state가
  있는 branch/worktree는 evidence manifest와 patch-equivalence 판정 전 삭제하지 않는다.
- `dev` dirty preflight: 기존 plan/index/sidecar 변경과
  `docs/GOAL_BRANCH_RECOVERY_CHECKPOINT_20260807.md`가 존재했다.
- 기존 plan worktree SHA `d21912c5...`, index SHA `280fe273...`, 기록 sidecar
  `3348801f...`는 불일치했다. exact 복구 정보는
  `docs/DYNAMIC_MOA_COMPLETION_PLAN_EPOCH_1_RECOVERY.md`에 보존한다.
- ignored evidence: `data/` 약 140 MiB, `.superpowers/sdd/` 약 3 MiB, 총 1,283 files.
  여기에는 production/validation/benchmark traces, runtime DB, datasets,
  training staging과 실험 보고서가 포함된다.

### Production runtime

- production checkout: `/home/kotori9/dgx-moa-agent`, `main@396e0458...`.
- production worktree는 tracked 7 files `+361/-66`와 untracked runtime/backup files로
  dirty다. 실행 코드와 rollback 관계를 판정하기 전 수정·reset하지 않는다.
- gateway active PID `3725086`, planner active PID `2206057`.
- executor/reviewer/reasoner/judge units inactive; loopback proxy socket active.
- authenticated gateway listener `100.125.239.72:9000`, loopback proxy
  `127.0.0.1:9000`, Planner `127.0.0.1:8102`; Executor `8101` listener 없음.
- effective runtime: `runtime_channel=main`, `trace_origin=production`, admin/Frontier enabled,
  lifecycle disabled with empty unit map. model endpoints는 loopback-only를 유지한다.
- current Planner: Gemma-4 path
  `/home/kotori9/models/experimental/gemma-4-26b-a4b-nvfp4-a19cfe00`.
- inactive current Executor unit: Qwen3-Coder-Next path
  `/home/kotori9/models/experimental/qwen3-coder-next-modelopt-nvfp4-15c399c8`.
- credential presence only: gateway API-key config, `OPENCODE_GO_API_KEY`, Codex OAuth
  profiles present; `OPENROUTER_API_KEY`, `HF_TOKEN` absent. secret values는 읽거나 기록하지 않았다.
- current DBs include `data/state/gateway.db` (125,280,256 bytes), weekly, evolution,
  knowledge, training DBs. gateway tables include sessions/events/usage/lifecycle/API-key state.
- canonical trace schema는 `schemas/agent-trace-v3.json`; Phase 3은 schema를 변경하지 않았다.
- 단일 authoritative deploy manifest는 발견되지 않았다. 현재 commit, backup config,
  service state와 `docs/VALIDATION.md`를 결합한 manifest를 release 전에 생성한다.

### Existing implementation gaps and reuse

- 재사용: Responses→Chat 공통 실행 실체, `Controller`, `ModelProvider`, specialist
  provider pinning, lifecycle guards, state event listeners, sanitized feed, observation batching,
  separate training DB/CAS, weekly 7z atomic packaging, trace v3와 usage tables.
- gap: `CodexOAuthCollaboration`은 최대 800,000자 evidence를 argv에 넣고
  `subprocess.run()`을 `asyncio.to_thread()`로 감싼다. App Server와 E2BIG 분류가 없다.
- 재사용 hotfix 기반: `admin_codex.py`의 `codex exec ... -`,
  `asyncio.create_subprocess_exec`, stdin/JSONL drain, timeout/cancellation cleanup.
- gap: raw API key가 DB에 저장되고 admin reveal이 존재한다.
- gap: same-key queue, cross-key Flash overflow, round-robin fairness, key-owned Executor lease 없음.
- gap: runtime snapshot/WebSocket/seq replay/backpressure/`RESYNC_REQUIRED` 없음.
- gap: `SessionState.payload`가 active state와 audit/history를 함께 직렬화한다.
- gap: cached-token missing/invalid가 `0`으로 정규화되어 `null`과 구분되지 않는다.

## 3. Evidence preservation contract

다음은 삭제·rewrite·epoch 혼합 금지다.

- `docs/VALIDATION.md`의 성공·실패·rejected benchmark 전부.
- protocol/benchmark epoch artifacts, production traces/session history/evaluation artifacts.
- model retirement/rollback/weekly package manifests와 provider failure evidence.
- 4 stashes, preservation refs, 고유 branch commits, dirty worktree files.
- production DBs, `data/traces`, `data/training-staging`, `.superpowers/sdd`.
- credential-bearing files는 hash/metadata만 다루고 내용은 Git/evidence에 넣지 않는다.

Branch 또는 worktree 제거 전 `commit reachable`, `patch-equivalence`, `evidence archived`,
`candidate verdict`, `dev integration status`, `reproduction command`를 manifest에 기록한다.
`git reset --hard`, force push, history replacement와 production tree overwrite를 금지한다.

## 4. Target topology

| Role | Provider/model | Policy |
| --- | --- | --- |
| Executor | local `mistralai/Mistral-Small-4-119B-2603-NVFP4` | normally resident, tools/routing/final synthesis의 유일한 owner |
| Reasoner | `empero-ai/Qwythos-9B-v2` | experimental; ablation 전 production default 금지 |
| Planner | OpenCode Go `deepseek-v4-pro` | nontrivial engineering에서 medium-high, structured plan only |
| Reviewer | OpenCode Go `glm-5.2` | 구현 evidence가 있을 때만 structured findings |
| Judge | OpenCode Go `kimi-k3` candidate | high-risk independent verdict; GLM/Kimi role swap 평가 후 확정 |
| Frontier A | Codex OAuth `gpt-5.6-sol`, effort `high` | active parallel collaborator; Reviewer보다 자주 사용 |
| Frontier B | OpenRouter Claude Opus 5-class | exceptional second opinion only; key/provider gate 실패 시 fail-closed |
| Overflow | OpenCode Go `deepseek-v4-flash` | low-risk Executor overflow/fallback only |

Executor만 runtime tool loop, mutation authority, loop control과 client-visible final response를
소유한다. specialist는 structured artifact만 반환하며 hidden reasoning을 요청·저장하지 않는다.
Frontier는 host를 직접 mutate하지 않고 recursive agent loop를 만들지 않는다.

Target model revision, weight hash, tokenizer revision, config hash는 현재 `MISSING`이다.
고정 upstream revision을 resolve하고 checksum manifest를 만든 뒤에만 model download/backend
검증을 시작한다. model weights와 secrets는 Git에 넣지 않는다.

## 5. Workflow and routing

- Tier 0 Simple: Executor → deterministic validation → final.
- Tier 1 Engineering: Planner + Frontier A + Executor read-only inspection 병렬 → join →
  Executor implementation/tools/tests → justified Reviewer.
- Tier 2 Complex/Research: selected Reasoner + Planner + Frontier A + read-only inspection 병렬 →
  join → Executor → tools/tests → optional Frontier evidence-delta → Reviewer.
- Tier 3 Critical: Planner + Frontier A + optional Reasoner → Executor → tests → Reviewer →
  repair → Judge → exceptional Frontier B → Executor final.
- specialist join 전에는 read-only evidence gathering만 허용하며 architecture mutation,
  migration, destructive tools와 deploy를 금지한다.
- Qwythos와 Mistral generation은 compute contention evidence 전에는 겹치지 않는다.

## 6. Local Executor backend gate

SGLang은 선호가 아니라 후보 1이다. 아래를 실제 고정 revision으로 통과해야 선택한다.

- NVFP4 load, `context=65536`, `max_num_seqs=1`, one sequence.
- streaming, native tool call/parser, Chat/Responses compatibility.
- long context, Radix/prefix cache, cancellation/restart, memory/swap.
- 기존 Phase 3 안전 baseline과 동등한 memory/quality contract:
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, MARLIN을 기준 비교한다.

Mistral에서 SGLang이 model-specific gate를 실패할 때만 vLLM fallback을 검증한다.
backend rejection evidence를 보존한다. rejected FP8 KV/eager/chunking/offload/sleep/cache-reset
실험을 production 설정으로 되살리지 않는다. unload fallback은 exact full service stop/start다.

## 7. Frontier transport contract

Primary는 persistent Codex App Server다: profile-specific `CODEX_HOME`, thread start/resume,
turn start, stream events, interrupt, compaction, bounded input, structured output을 검증한다.
검증 실패 시에만 `codex exec` + stdin fallback을 허용한다.

공통 subprocess 계약:

- argv에는 짧은 flags/path만; prompt/task package 금지.
- `asyncio.create_subprocess_exec`, stdin write, stdout/stderr concurrent bounded drain.
- bounded timeout, process-group cleanup, client cancellation cleanup.
- `errno.E2BIG` → `FRONTIER_INPUT_TRANSPORT_TOO_LARGE`; 동일 transport 재시도 금지.
- typed errors: `FRONTIER_PROCESS_SPAWN_FAILED`, `FRONTIER_INPUT_TRANSPORT_TOO_LARGE`,
  `FRONTIER_CONTEXT_PACKAGE_TOO_LARGE`, `FRONTIER_AUTH_ERROR`, `FRONTIER_USAGE_LIMIT`,
  `FRONTIER_RATE_LIMITED`, `FRONTIER_PROVIDER_TIMEOUT`, `FRONTIER_PROVIDER_UNAVAILABLE`,
  `FRONTIER_PROTOCOL_ERROR`.

## 8. Session and storage contract

Active state는 objective, constraints, current plan/working set, unresolved criteria,
recent relevant evidence, open failures/findings, remaining budget만 가진다.
한도를 넘으면 immutable checkpoint와 successor compact state를 만들고 parent/session,
snapshot hash, event cursor, reason, before/after size, open state를 기록한다.
durable audit history는 삭제하지 않는다.

SQLite 경계는 existing schema를 migration-safe하게 확장한다: active sessions,
workflow runs/stages/events, provider invocations, tool executions, failure fingerprints,
evidence, prompt/output object refs, telemetry, training candidates, admin audit, retention jobs.
새 ORM/message broker/workflow framework/distributed scheduler는 추가하지 않는다.

## 9. API-key scheduling and privacy

- raw key는 DB/log/Dashboard/WebSocket에 저장하지 않는다. `api_key_id`, one-way hash,
  operator label만 유지한다. legacy plaintext migration은 rollback-safe하고 reveal을 제거한다.
- request/session/event/object ownership은 authenticated principal의 `api_key_id`로 결정한다.
- local Executor lease: owner key/request/acquired time/state.
- same key: local queue max 3, 그 이후 Flash overflow 가능.
- cross key: local busy면 즉시 Flash overflow.
- local queue는 key별 round-robin. 한 turn은 시작 provider에 고정하고 다음 turn에서만 재평가.
- security/deploy/destructive/auth/persistent schema/model retirement는 Mistral queue,
  Flash + Frontier A + Reviewer + Judge, 또는 fail-closed 중 명시 정책을 사용한다.
- 일반 key는 자기 raw content만 본다. Operator cross-key raw access는 explicit reason과
  request-scoped audit event가 필수다.

## 10. Dashboard and WebSocket

Dashboard는 runtime event/evidence의 projection이며 inference 실패 원인이 될 수 없다.
물리 gate 전 feature flag는 disabled다. 메뉴는 `LIVE`, `REQUESTS`, `MODELS`, `SYSTEM`,
`INCIDENTS`, `EVALUATION`, `AUDIT`만 둔다.

Snapshot: `GET /admin/runtime/snapshot`; delta: `WS /admin/ws`.

```json
{"seq":1,"timestamp":"...","api_key_id":"key_...","request_id":"req_...","stage_id":"stage_...","parent_stage_ids":[],"type":"output.delta","channel":"model","role":"frontier_a","provider":"codex","model":"gpt-5.6-sol","state":"STREAMING","payload":{}}
```

- state: `QUEUED|DISPATCHING|RUNNING|STREAMING|WAITING_TOOL|WAITING_DEPENDENCY|RETRYING|FALLBACK|SUCCEEDED|DEGRADED|FAILED|CANCELLED`.
- model delta: 50 ms 또는 256 chars; tool output: 50 ms 또는 4 KiB.
- workflow terminal event reliable; telemetry lossy latest-value.
- monotonic `seq`, reconnect `last_seq`, buffer miss `RESYNC_REQUIRED` + REST resnapshot.
- bounded per-connection queue; slow client disconnect. Dashboard off에서도 inference 지속.
- auth scope는 principal에서만 결정하고 URL/payload raw key를 금지한다.

Inspector는 `SUMMARY|PROMPT|LIVE|OUTPUT|EVIDENCE|EXECUTION|LOGS`를 제공한다.
Authorization/API key/OAuth/cookie/private key/secret env/hidden reasoning을 저장·전송하지 않는다.
prompt와 final output은 owner에게만, content-addressed object reference와 retention/privacy/
opt-out/redaction/content hash metadata로 저장한다.

## 11. Logging, training, weekly, cache

request→decision→role/provider/model→prompt/policy version→tool/result→failure/repair→criteria→
review→outcome→feedback provenance를 연결한다. 운영 log는 자동 training data가 아니다.
candidate는 source request/event, baseline/candidate commit, role, quality/privacy/license/
eligibility를 가진다.

Role datasets: Executor SFT/preference, Planner decomposition, Reviewer findings, Judge verdict,
Frontier routing, tool selection/arguments/recovery, failure/repair/loop transition/termination,
API-key scheduling, local-vs-overflow, Reasoner ablation.
secret/privacy/repository/opt-out/license/schema/quality/dedup gates를 모두 통과한 candidate만
포함한다. external raw output은 provider terms가 명시적으로 허용할 때만 eligible이다.

Weekly package는 이전 완전 7-day window, 7z LZMA2, SHA-256, manifest와 schema/model/prompt/
policy/routing snapshots, quality/privacy/dedup reports, atomic publication, `7z t`, quota
fail-closed를 유지한다. inference는 packaging failure와 분리한다.

Cache는 stable prefix를 role/tool/runtime policy/conversation prefix 순으로 앞에 두고 dynamic
plan/evidence/review/observation을 뒤에 둔다. provider prompt cache, runtime prefix/Radix cache,
gateway reuse를 구분한다. `cached_tokens=null`과 `0`을 구분하고 모든 specialist/Frontier
호출 usage를 누계한다.

## 12. Refactor boundary

기존 Responses→Chat core를 추출·재사용하고 별도 orchestration을 만들지 않는다.
최소 응집 경계는 protocol adapters, execution core, inference/admin/training routers,
Controller, evidence builder, session state, provider transport, event bus/WebSocket,
telemetry, SQLite schema/quota다.

reference scan + runtime evidence 전에는 fake model, Discord, lifecycle, wrappers를 삭제하지
않는다. 순 source/중복 path/config key/service unit/wrapper layer의 before/after를 측정한다.
Gateway는 Python으로 유지한다. Rust는 `docs/RUST_EVALUATION.md` gate를 새로 넘고 별도 승인을
받기 전에는 만들지 않는다.

## 13. Evaluation protocol

Dynamic MoA를 동일 task/repo/environment/tool/network/timeout/retry/criteria/hidden tests/cost
조건에서 `GPT-5.6-sol High`와 Claude Opus 5-class에 비교한다. client strata는 Codex,
OpenCode, Hermes, raw OpenAI-compatible client다.

### Frozen statistics

- primary quality metric: paired task success (`0/1`), hidden tests와 false-completion gate 포함.
- secondary: verified-completion time, TTFT, first useful tool, tool-call accuracy/failure/repair,
  reliability, cost, context retention, GPU memory/TTFT/tok/s impact.
- blind assignment: implementation identity를 무작위 opaque label로 바꾸고 evaluator와
  hidden-test runner에 provider/model identity를 숨긴다; mapping은 결과 freeze 후 해제한다.
- unit: 동일 task/client/seed의 paired run. 최소 30 completed pairs per frontier comparator,
  task category와 client strata를 모두 포함한다.
- non-inferiority margin: Dynamic MoA minus comparator task-success rate `>-0.10`.
- CI: paired bootstrap, 10,000 resamples, fixed seed `20260808`, two-sided 95% percentile CI.
- pass: 각 comparator에 대한 CI lower bound가 `-0.10`보다 크고 reliability gate를 통과.
- failed run은 success `0`, missing/mismatched/telemetry-incomplete pair는 통계에서 임의
  제외하지 않고 protocol violation으로 전체 결과를 `INCONCLUSIVE` 처리한다.
- epoch 혼합, sample 부족, CI 미통과, 조건 불일치도 `INCONCLUSIVE`다.

Reasoner ablation은 `Mistral only`, `Qwythos→Mistral`, `Qwythos+Frontier A→Mistral`,
`Qwythos+Planner+Frontier A→Mistral`을 동일 paired protocol로 비교한다. 결론은
`KEEP_ALWAYS|KEEP_COMPLEX_ONLY|MOVE_TO_MATHCAT|REMOVE|INCONCLUSIVE`; `INCONCLUSIVE`는
production default에서 제외한다.

## 14. Timeout, retry, and stability

- role별 timeout은 isolated latency pilot의 p99와 상한을 기록한 뒤 freeze한다. pilot 전
  arbitrary production timeout 변경 금지.
- retry는 typed transient failure만 exponential backoff+jitter로 최대 2회; auth, protocol,
  context-too-large, E2BIG와 destructive-policy failure는 동일 경로 재시도 금지.
- cancellation은 child process group/lease/queue/stream을 정리하고 terminal event는 exactly once.
- long-horizon gate는 실제 긴 engineering Goal에서 plan revisions, many tools, code mutation,
  failed test+repair, specialist/follow-up, compaction, reconnect, fallback이 자연 발생해야 한다.
- 시간 자체는 gate가 아니다. context corruption/E2BIG/unbounded session/duplicate loop/
  disconnect/orphan/cache corruption/runaway memory/false completion이 0이고 checkpoint continuation,
  failure recovery가 성공해야 한다.

## 15. Model inventory and cleanup

모든 model path에 ID/path/revision/hash/size/service/config/test/rollback reference/last-used/
decision을 기록한다. rejected experiment, production/rollback/service/config reference 0,
pinned upstream 복구 가능 조건을 모두 만족한 후보만 manifest 후 삭제할 수 있다.

기존 Qwen Executor, Gemma Planner/Reviewer, Qwythos는 Mistral canary, remote roles,
Frontier transport, client matrix, rollback rehearsal, replacement rollback path와 reference 0을
통과하기 전 유지한다. model retirement와 실제 삭제는 explicit human approval 후 수행한다.

## 16. Release, canary, rollback

순서: `dev full validation → blind evaluation → Reasoner ablation → Dashboard validation →
model canary preparation → reviewed PR dev→main → main merge → approved production deploy →
production canary → rollback rehearsal → post-deploy validation → approved retirement → cleanup`.

`main` 직접 개발과 production worktree 개발을 금지한다. merge/deploy/security/systemd topology/
training export/model deletion은 별도 human approval 없이는 실행하지 않는다.

Canary는 health/ready/auth, Chat/Responses/stream/heartbeat/tools, Codex/OpenCode/Hermes/raw,
Mistral/Flash/Planner/Reviewer/Frontier/Judge/Frontier-B gate, Dashboard/telemetry/memory/cache를
검증한다. 실패하면 main을 자동 수정하지 않고 승인된 rollback source로 복구한다.

Rollback manifest는 source commit/model/config/commands/duration/service/health/data preservation을
포함한다. 삭제 weight 의존 rollback은 불인정이다. lifecycle rollback은 승인된 한 config에만
`scripts/rollback-lifecycle.sh <one-config>`를 사용하고 exact full stop/start로 resident를 복구한다.

## 17. Validation matrix and completion

정적 gate: strict mypy 0, Ruff format/check, full pytest, systemd verify, shell syntax, schema
migration, trace completeness. Integration gate: App Server + stdin fallback + E2BIG, OpenCode,
Hermes, Chat, Responses, tool continuation, heartbeat/terminal, key isolation/queue/fairness/overflow/
pinning/high-risk, Dashboard stream/reconnect/backpressure/retention, training candidate, weekly 7z.

최종 branch cleanup은 release+rollback 이후 local/remote `main`, `dev`만 남기는 작업이다.
각 삭제는 reachability/evidence manifest 후 수행하며 remote 삭제도 human approval gate로 본다.

최종 보고는 한국어로 시작/종료 commits, plan hash/epoch, branch/worktree/code line counts,
model inventory와 role별 measured metrics, scheduling/clients/Dashboard/logging/evaluation/
long-horizon/static/canary/rollback/post-deploy evidence, limitations를 포함한다.
최종 상태는 `COMPLETE` 또는 `BLOCKED`만 사용한다.
