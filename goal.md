# Dynamic MoA Production Completion

## 0. 문서의 지위

이 파일은 프로젝트 루트에서 현재 Goal의 방향, 현재 검증 상태, 다음 실행 순서와 완료 조건을 빠르게 확인하기 위한 최상위 실행 헌장이다.

이 파일은 기존의 동결 계획과 증거를 대체하지 않는다. 다음 문서가 더 구체적이거나 충돌하는 경우에는 최신 protocol epoch에 속한 동결 계획과 물리 검증 증거를 우선한다.

- `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`
- `docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256`
- `docs/STATE.md`
- `docs/VALIDATION.md`
- `docs/OPERATIONS.md`
- `docs/DYNAMIC_MOA_COMPLETION_AUDIT_20260808.md`
- 관련 incident, benchmark, model inventory, rollback manifest

기존 성공과 실패, protocol epoch, trace, runtime DB, benchmark artifact, branch와 worktree history를 삭제하거나 유리한 결과로 덮어쓰지 않는다.

모든 사용자 가시 진행 보고, 오류 설명, 판단, 승인 요청과 최종 보고는 한국어로 작성한다. 코드, model ID, API field, schema identifier, command와 로그 식별자는 원래 표기를 유지한다.

### 0.1 Pilot-first 현재 권위

2026-08-12 `pilot-v1-transition-20260812`부터 직접 Goal은 모든 장기 gate를 먼저
끝내는 `COMPLETE`가 아니라 최소 안전 배포 경계인 `PILOT_READY`, 제한된 개발자
canary인 `PILOT_ACTIVE` 순서다. 이 절은 아래의 completion-first release 순서와
충돌할 때 우선하며, 동결 계획·hash·과거 성공/실패를 수정하거나 삭제하지 않는다.

단계는 `DEVELOPMENT -> PILOT_READY -> PILOT_ACTIVE -> PRODUCTION_BETA -> STABLE`이다.
현재 단계는 `DEVELOPMENT`다. `BLOCKED`는 같은 막힘이 반복되고 안전한 검증 경로가
모두 소진된 경우에만 사용한다.

`PILOT_READY`의 최소 계약은 다음과 같다.

- 고정 revision의 vLLM Blackwell native NVFP4 Candidate A
- Chat, Responses, streaming, native tool, tool-result continuation
- 인증과 API-key 격리, DeepSeek V4 Flash
- durable request/event/Evidence/ExecutionGraph projection
- secret 및 hidden reasoning 비수집·비노출
- model/qualification OOM이 gateway, user manager, SSH/control plane을 죽이지 않는 격리
- destructive/high-risk operation의 approval 또는 fail-closed
- 고정 release revision과 실제 rollback 절차

SGLang은 `DEFERRED/REJECTED_THIS_EPOCH`다. fresh 20/20 matrix, blind
non-inferiority, Reasoner ablation, long-horizon, 전체 Dashboard/training 및 최종
branch cleanup은 `POST_PILOT_VALIDATION` 또는 `STABLE` gate이며 Pilot 배포 선행조건이
아니다.

---

## 1. 최종 목표

단일 강력한 로컬 Executor를 중심으로 원격 Planner, Reviewer, Judge, Frontier와 fallback Executor를 병렬 및 조건부로 연결하는 Dynamic MoA를 완성한다.

완성된 시스템은 다음을 만족해야 한다.

1. Codex, OpenCode, Hermes 및 일반 OpenAI-compatible client에서 실제 tool loop와 장기 작업을 안정적으로 수행한다.
2. GPT-5.6-sol High와 Claude Opus 5-class agent를 상대로 사전 동결한 블라인드 실사용 평가에서 비열등성을 신뢰구간으로 입증한다.
3. API Key별 요청, prompt, output, evidence와 Dashboard stream을 격리한다.
4. ExecutionGraph가 fan-out, fan-in, retry, fallback, tool/test continuation, bounded repair, checkpoint와 human approval을 명시적으로 소유한다.
5. 장기 세션에서 전체 history를 반복 직렬화하지 않고 compact active state와 durable evidence를 사용한다.
6. 코드베이스와 Git history를 정리하고 최종 장기 branch는 `dev`와 `main`만 남긴다.
7. 운영 로그와 학습 후보를 분리한 재귀 개선 및 주간 fine-tuning dataset 생산 체계를 확립한다.
8. 모든 release gate를 통과한 뒤에만 `dev -> main -> production` 순서로 병합하고 배포한다.

기능 존재, mock test 통과 또는 단발성 completion만으로 완료를 선언하지 않는다.

---

## 2. 작업 위치와 Git 규칙

개발 저장소:

```text
/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent
```

프로덕션 배포 디렉터리:

```text
/home/kotori9/dgx-moa-agent
```

장기 branch 역할:

```text
dev
  모든 개발, 통합, release validation

main
  검증 완료된 production revision
```

직접 `main` 개발, production worktree 직접 수정, destructive reset, force push, history replacement, 전체 tree 덮어쓰기를 금지한다.

임시 branch와 worktree는 허용하지만 다음을 확인한 뒤 최종 정리한다.

- commit 도달 가능성
- 실패와 성공 증거 보존
- candidate verdict 기록
- `dev` 통합 여부 확인
- 재현 명령 보존
- rollback 의존성 제거 여부 확인

최종 완료 시 local과 remote에 장기 branch는 `main`과 `dev`만 남긴다.

---

## 3. 목표 모델 토폴로지

### 3.1 Executor

```text
Role: Executor
Model: mistralai/Mistral-Small-4-119B-2603-NVFP4
Revision: b1a9048590131d38491bd23a7c9f6ed0962f0358
Location: local GB10
Context: 131072
max_num_seqs: 1
KV budget: 3.4 GB
Quantization: NVFP4
Dense backend: FlashInfer B12x native NVFP4 (`VLLM_NVFP4_GEMM_BACKEND=flashinfer-b12x`)
MoE backend: `flashinfer_b12x`
Attention: TRITON_MLA
CUDA Graph: FULL_DECODE_ONLY
```

Executor는 다음을 단독 소유한다.

- client-visible native tool calls
- repository modification
- implementation과 debugging
- tool/test evidence 해석
- bounded engineering loop
- specialist 의견의 수용 또는 거부
- 최종 synthesis와 client-visible response

### 3.2 Reasoner

```text
Role: Reasoner
Model: empero-ai/Qwythos-9B-v2
Status: experimental
```

Reasoner는 현재 Goal의 고정 전제가 아니다. 다음 ablation 결과로 결정한다.

- `Mistral only`
- `Qwythos -> Mistral`
- `Qwythos + Frontier A -> Mistral`
- `Qwythos + Planner + Frontier A -> Mistral`

최종 상태는 다음 중 하나다.

```text
KEEP_ALWAYS
KEEP_COMPLEX_ONLY
MOVE_TO_MATHCAT
REMOVE
INCONCLUSIVE
```

`INCONCLUSIVE`이면 production 기본 경로에 넣지 않는다.

### 3.3 Planner

```text
Role: Planner
Provider: OpenCode Go
Primary model: deepseek-v4-pro
```

Planner는 scope, assumptions, dependencies, ordered plan, risk, validation, rollback만 제공한다. Tool을 실행하거나 working tree를 수정하지 않는다.

### 3.4 Reviewer

Reviewer는 실제 diff, tests, build, tool evidence와 completion claim이 존재할 때만 실행한다.

GLM-5.2의 reasoning-only 또는 빈 public output 실패 증거는 보존한다. 현재 production candidate는 물리 검증에서 구조화 review를 안정적으로 통과한 OpenCode Go 모델로 pin하며, 최신 `config`, `STATE`, `VALIDATION`을 권위로 삼는다. 동일 모델이 Planner와 Reviewer 양쪽에 배치되더라도 역할 prompt, schema, metrics와 invocation provenance는 분리한다.

### 3.5 Judge

```text
Role: Judge
Provider: OpenCode Go
Primary candidate: kimi-k3
```

Judge는 high-risk independent gate이며 tool을 실행하지 않는다. 출력 예산, strict schema와 provider-specific temperature 계약을 물리 검증된 값으로 유지한다.

Judge 사용 조건:

- security와 authentication
- production deployment
- destructive migration
- persistent schema change
- critical disagreement
- model retirement
- high-impact policy, routing, prompt 또는 Skill promotion

### 3.6 Frontier A

```text
Role: Frontier A
Model: gpt-5.6-sol
Reasoning effort: high
Frequency: high
```

Frontier A는 emergency fallback이 아니라 적극적인 공동 설계자다.

주요 용도:

- novel technology와 research implementation
- architecture와 large refactor
- unknown API/framework
- concurrency와 state machine
- complex debugging
- independent strategy와 code critique
- local plan invalidation

대형 prompt를 argv로 전달하지 않는다. Primary transport는 검증된 Codex App Server 또는 daemon/proxy path이며, 허용된 fallback은 `codex exec`와 stdin이다. `errno.E2BIG`는 `FRONTIER_INPUT_TRANSPORT_TOO_LARGE`로 분류하고 동일 transport를 재시도하지 않는다.

### 3.7 Frontier B

```text
Role: Frontier B
Model: Claude Opus 5-class
Provider: OpenRouter
Frequency: lower than Judge
```

Frontier B는 유료 독립 second opinion이며 다음에서만 사용한다.

- Judge와 Frontier A의 material disagreement
- critical security
- destructive production migration
- 매우 큰 architecture 결정
- Frontier A 반복 실패
- blind comparison sample

### 3.8 Overflow and fallback Executor

```text
Role: overflow/fallback Executor
Provider: OpenCode Go
Model: deepseek-v4-flash
```

DeepSeek V4 Flash의 China-hosted provider setting 문제와 과거 `403 RegionError`는 해결됐다. Completion, native tool call, tool-result continuation, stream/cancel, provider pinning, cross-key overflow, same-key FIFO/fairness, recovery와 high-risk fail-closed의 기존 물리 증거를 유지한다.

Flash는 다음에는 사용할 수 없다.

- critical Judge replacement
- security approval
- production deployment approval
- destructive migration approval
- model retirement approval

---

## 4. 현재 물리 검증 상태

이 절은 `goal.md` 생성 시점의 snapshot이며, 최신 `STATE.md`와 `VALIDATION.md`가 항상 우선한다.

### 완료 또는 해제된 핵심 blocker

1. Mistral NVFP4 정적 checkpoint와 KV가 120 GiB를 필수로 요구한다는 가설은 기각됐다.
2. MARLIN postprocess temporary block retention은 과거 100-120 GiB 증가의 원인으로
   분리됐고 compatibility rollback 증거로 보존됐다.
3. 별도 reclaim/allocator workaround가 없는 FlashInfer B12x native Candidate A에서
   다음이 반복 검증됐다.
   - startup GPU peak 약 72.6 GiB
   - stable GPU memory 약 72.4 GiB
   - 131072 context
   - KV 3.4 GB
   - `FULL_DECODE_ONLY` CUDA Graph
   - two cold starts
   - short and repeated decode
   - long prefill
   - native tool continuation
   - stream cancellation and recovery
   - exact stop/restart
4. Chat, Responses, streaming, tool call과 continuation의 128K live protocol matrix가 통과했다.
5. `deepseek-v4-flash`의 provider setting 문제는 해결됐고 overflow scheduling gate의 기존 물리 증거가 복구됐다.
6. Frontier argv/E2BIG 경로는 stdin 및 App Server 계열 transport로 교정됐고 typed failure taxonomy가 추가됐다.
7. ExecutionGraph, checkpoint, partial rerun, 10,000-event compact state, usage/cache `null` 대 `0`, API Key Dashboard WebSocket replay와 owner isolation이 구현 및 검증됐다.

### 현재 진행 중인 Pilot gate

이 snapshot 시점에서 graph-active 경로의 Codex canary는 다음까지 진행됐다.

- `atomic-store`: recovery PASS
- `rate-limiter`: 10/10 PASS
- `webhook-verifier`: 10/10 PASS
- `dag-runner`: v58 hidden-validation FAIL 보존, fresh v61 10/10 PASS

이 결과를 전체 matrix 또는 비열등성 결과로 확대 해석하지 않는다. v105의 추가
quality cell은 결과를 보존한 채 `POST_PILOT_VALIDATION`으로 일시 중단했다. 현재 다음
gate는 reviewed Pilot release revision, checked-in cgroup/native launch defaults의 설치
및 exact restart, rollback rehearsal과 제한된 developer canary다.

### 아직 완료되지 않은 Pilot gate

- reviewed Pilot release revision
- checked-in Candidate A memory/native defaults 설치와 exact restart
- rollback rehearsal
- developer-key-only limited canary와 recovery

다음 항목은 여전히 필요하지만 Pilot 선행조건이 아니라 post-Pilot 또는 `STABLE` gate다.

- fresh client quality matrix 전체 완료
- Codex, OpenCode, Hermes 각 경로의 품질 수렴
- Reasoner ablation
- 30-pair blind non-inferiority evaluation
- 자연스러운 long-horizon engineering Goal 안정성
- Dashboard 전체 physical gate와 production enable
- codebase 순감축 완료
- branch/worktree 최종 정리
- `dev` release validation
- production canary
- rollback rehearsal
- old production model retirement
- 최종 merge와 production deployment

---

## 5. Dynamic MoA 실행 흐름

### Simple

```text
Request
  -> Executor
  -> deterministic validation
  -> final
```

### Engineering

```text
Request classification
  ├─ Planner
  ├─ Frontier A
  └─ Executor read-only evidence gathering
        |
        v
Context join
        |
        v
Executor implementation
        |
        v
Tools and tests
        |
        v
Reviewer when justified
```

### Complex or Research

```text
Request classification
  ├─ optional Reasoner
  ├─ Planner
  ├─ Frontier A
  └─ Executor read-only inspection
        |
        v
Evidence join
        |
        v
Executor implementation
        |
        ├─ tools
        ├─ tests
        └─ Frontier A evidence-delta follow-up
        |
        v
Reviewer
```

### Critical

```text
Planner + Frontier A + optional Reasoner
        |
        v
Executor
        |
        v
Tools/tests
        |
        v
Reviewer
        |
        v
Executor repair
        |
        v
Judge
        |
        v
Frontier B only when exceptional independent opinion is required
        |
        v
Executor final
```

독립 역할은 가능한 한 병렬 실행한다. Qwythos와 remote roles는 병렬화할 수 있으나, Qwythos와 Mistral의 동시 local inference는 실제 자원 경합 결과로 결정한다.

---

## 6. ExecutionGraph

Runtime Policy가 허용된 node와 conditional edge template에서 request별 ExecutionGraph를 결정론적으로 컴파일한다.

Node 종류:

```text
CLASSIFY
REASONER
PLANNER
FRONTIER_A
EXECUTOR
TOOL
TEST
REVIEWER
JUDGE
FRONTIER_B
CHECKPOINT
HUMAN_APPROVAL
FINALIZE
```

Graph는 다음을 소유한다.

- fan-out과 fan-in
- provider pinning
- retry와 fallback
- bounded tool/test continuation
- repair cycle
- failure fingerprint
- progress requirement
- max traversal과 wall-clock budget
- checkpoint와 partial rerun
- operator approval

LLM은 허용되지 않은 node나 무제한 cycle을 임의로 생성하지 못한다.

ExecutionGraph와 Evidence Graph를 합치지 않는다. Execution node가 생성, 검증 또는 반박한 Evidence node ID를 참조한다.

---

## 7. API Key scheduling

모든 요청은 raw key가 아닌 `api_key_id`에 귀속된다.

Local Mistral은 기본적으로 sequence 1과 lease를 사용한다.

- 같은 API Key의 후속 요청은 bounded queue를 사용한다.
- 다른 API Key가 local lease 점유 중 요청하면 DeepSeek V4 Flash overflow Executor를 사용한다.
- 같은 Key의 queue limit 이후 요청도 정책에 따라 overflow할 수 있다.
- Local queue는 API Key별 round-robin fairness를 사용한다.
- 한 turn이 local 또는 overflow provider로 시작되면 해당 turn에 provider pinning을 유지한다.
- high-risk overflow는 Frontier A, Reviewer, Judge 또는 Mistral queue와 fail-closed 정책을 적용한다.

---

## 8. Dashboard

Dashboard는 Runtime의 별도 진실 공급원이 아니라 ExecutionGraph, Evidence, invocation, tool, telemetry의 projection이다.

주요 메뉴:

```text
LIVE
REQUESTS
MODELS
SYSTEM
INCIDENTS
EVALUATION
AUDIT
```

Inspector:

```text
SUMMARY
PROMPT
LIVE
OUTPUT
EVIDENCE
EXECUTION
LOGS
```

Dashboard는 다음을 지원한다.

- API Key owner별 자기 요청만 조회
- operator global aggregate
- audited cross-key raw-safe access
- prompt display
- client-visible live model output
- tool stdout/stderr
- current draft와 final output
- model/provider/role provenance
- timeline과 workflow canvas
- WebSocket sequence replay
- `RESYNC_REQUIRED`
- bounded per-client backpressure
- local GB10과 `ssh mathcat` telemetry
- 90-day observability retention

Hidden chain-of-thought, credential, raw API key, OAuth token, private key와 secret-bearing environment는 저장하거나 전송하지 않는다.

---

## 9. 장기 context

Stable prefix 순서:

```text
fixed role contract
fixed tool definitions
stable runtime and repository policy
stable conversation constraints
dynamic plan
dynamic evidence
dynamic review
latest observations
```

장기 작업에서 semantic summary를 반복 생성하기 전에 다음을 우선한다.

- 오래된 대형 tool output externalization
- 완료된 diff reference화
- 해결된 evidence와 finding의 durable reference
- compact active state
- immutable checkpoint와 parent lineage

전체 durable history는 보존한다.

---

## 10. 코드베이스 정리

주요 책임 경계:

- common Chat/Responses execution core
- protocol adapters
- inference router
- admin router
- training router
- ExecutionGraph compiler/runtime
- Controller orchestration policy
- review evidence builder
- provider transport
- state and persistence
- WebSocket event hub
- telemetry
- training data and quota

제거 대상은 실제 reference, runtime, test, rollback evidence가 있는 경우에만 삭제한다.

- duplicate adapter/wrapper/config
- obsolete local Planner/Reviewer path
- completed plan scaffolding
- Discord
- unused fake model/launcher
- legacy lifecycle path
- `runpy`와 global mutation evaluation coupling
- dead tests

새 ORM, broker, workflow framework, scheduler framework나 별도 graph framework를 추가하지 않는다.

완료에는 단순 책임 이동이 아니라 source, branch, wrapper와 configuration의 실질 순감축 증거가 필요하다.

---

## 11. 재귀 개선과 training data

Operational logs, audit logs, analytics, training candidates와 approved training data를 분리한다.

최소 dataset target:

- Executor SFT and preference
- Planner decomposition
- Reviewer findings
- Judge verdict
- Frontier routing
- tool selection and arguments
- tool-result interpretation
- failure classification
- repair strategy
- loop transition and termination
- ExecutionGraph edge selection
- API Key scheduling
- local versus overflow routing
- Reasoner ablation

Training eligibility 전에 다음을 적용한다.

- secret scan
- privacy classification
- repository policy
- request/API Key opt-out
- license policy
- schema validation
- quality labeling
- exact and near deduplication

주간 complete window는 manifest, schema/model/prompt/policy/routing snapshot, reports, SHA-256과 검증된 7z archive로 원자적 publish한다.

---

## 12. 평가와 release gate

블라인드 비교 대상:

```text
Dynamic MoA
GPT-5.6-sol High
Claude Opus 5-class
```

평가 경로:

```text
Codex
OpenCode
Hermes
raw OpenAI-compatible client
```

평가 strata:

- deterministic small engineering
- multi-file implementation
- debugging and recovery
- architecture-sensitive refactor
- novel technology integration
- research implementation
- long-horizon engineering Goal

사전 고정:

- task and repository revision
- tool/network permission
- timeout and retry
- scoring and hidden tests
- quality, speed, cost, reliability and context-retention metrics
- non-inferiority margins
- sample size
- paired bootstrap confidence interval
- missing and failed run policy

CI가 margin을 통과하지 못하거나 telemetry가 불완전하면 비열등성을 선언하지 않는다.

고정 10시간 idle test를 요구하지 않는다. 자연스러운 장기 engineering Goal에서 planning revision, tools, failures, repair, checkpoint, reconnect, fallback, cache와 memory stability를 입증한다.

---

## 13. Release 순서

현재 Pilot-first 순서:

```text
1. isolated Pilot contract와 OOM containment
2. reviewed release revision
3. Candidate A native defaults/cgroup caps 설치와 exact restart
4. rollback rehearsal
5. developer/operator own-key limited canary
6. PILOT_ACTIVE telemetry review
7. post-Pilot client matrix, blind, ablation, long-horizon와 later gates
```

아래 completion-first 순서는 `PRODUCTION_BETA -> STABLE` backlog로 보존한다.

```text
1. 최신 canary와 client quality gate 완료
2. fresh full client matrix
3. Reasoner ablation
4. blind non-inferiority evaluation
5. long-horizon stability
6. Dashboard physical gate
7. codebase and branch cleanup
8. full dev release validation
9. PR dev -> main
10. independent/human review
11. main merge
12. production deployment
13. production canary
14. rollback rehearsal
15. post-deploy validation
16. old model retirement
17. final branch/worktree cleanup
18. final evidence report
```

해당 단계의 필수 gate가 실패, 누락, 불확정 또는 telemetry 불완전 상태이면 다음
단계 승격과 model deletion을 금지한다. Post-Pilot gate 미완료만으로 안전한 제한
Pilot을 금지하지 않는다.

---

## 14. 단계별 완료 조건

현재 Goal은 `PILOT_READY`와 제한된 `PILOT_ACTIVE`까지다. 아래의 기존 전체 목록은
`STABLE` 조건으로 보존하며 Pilot 조건으로 소급하지 않는다.

다음을 모두 높은 신뢰도로 통과한 경우에만 `STABLE`을 선언한다.

- historical evidence와 protocol epoch 보존
- `main`/`dev` 역할 회복
- 장기 branch가 `main`과 `dev`만 남음
- codebase 책임 분리와 실질 순감축
- fixed-revision Mistral 128K Executor physical qualification
- Planner, Reviewer, Judge, Frontier A/B physical qualification
- E2BIG recurrence 0
- bounded active state와 checkpoint/partial rerun
- Codex, OpenCode, Hermes, raw client matrix
- API Key isolation, overflow, fairness, pinning
- Dashboard prompt/live/final output와 reconnect/backpressure
- hidden reasoning 미수집과 미노출
- logging, training candidate, weekly 7z
- cache and usage accounting
- Reasoner ablation final verdict
- blind non-inferiority CI gate
- long-horizon stability
- strict mypy 0 errors
- Ruff and full tests
- production canary
- rollback rehearsal
- complete telemetry

운영 단계와 Goal terminal status를 혼동하지 않는다. 현재 운영 단계는 위의 5단계를
사용하고, Goal은 검증 가능한 경로가 남아 있는 동안 active로 유지한다.

```text
PILOT_READY
PILOT_ACTIVE
PRODUCTION_BETA
STABLE
BLOCKED
```

검증 가능한 다음 경로가 남아 있는 단일 실험 실패는 즉시 외부 자원 부족이나 영구 `BLOCKED`로 단정하지 않는다. 반대로 mandatory release gate가 실제로 충족되지 않았는데 `COMPLETE`를 선언하지 않는다.
