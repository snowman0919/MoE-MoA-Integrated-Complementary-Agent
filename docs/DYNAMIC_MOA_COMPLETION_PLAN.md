# Dynamic MoA Completion Plan

동결일: 2026-07-27 KST
작업 브랜치: `auto/runtime/sglang-gemma4-v1`
계획 hash: `docs/DYNAMIC_MOA_COMPLETION_PLAN.sha256`에 별도 기록

이 문서는 구현·평가·branch 복구·release 순서를 사전 등록한다. 이 파일을
변경하면 기존 hash 이후의 결과는 진단 자료로만 남기고, 새 계획 revision과
새 protocol/run ID를 동결한 뒤 평가를 처음부터 다시 시작한다.

## 1. 불변 안전 경계

- production worktree, `main`, `dev`의 기존 dirty 변경을 덮어쓰거나
  destructive reset하지 않는다.
- 실험 구현은 `dev`에서 분기한 `auto/<layer>/<proposal-id>`에서만 한다.
- production 모델 endpoint는 loopback-only로 유지하고 인증된 gateway만
  tailnet에 노출한다.
- Executor만 host 도구 실행과 client-visible 최종 합성을 소유한다.
  Frontier는 schema-validated client tool call을 제안할 수 있지만 host를
  직접 변조하지 않는다.
- provider dispatch 후 전환하거나 local/remote 부분 결과를 혼합하지 않는다.
- prompt, hidden reasoning, credential, cookie, authorization, raw provider
  output, request ID, repository 이름을 metric label이나 평가 archive에 넣지
  않는다.
- 기존 vLLM Executor/North Reviewer rollback은 새 rollback이 같은 범위에서
  물리 검증될 때까지 제거하지 않는다.
- 실패, 누락, `INCONCLUSIVE`, 불완전 telemetry는 PASS가 아니다.

## 2. 동결 전 상태 스냅샷

### 2.1 공유 clone

| 항목 | 상태 |
|---|---|
| canonical remote | `https://github.com/snowman0919/MoE-MoA-Integrated-Complementary-Agent.git` |
| `dev` | `e6c6b512e02dda6a3f267fc4c17704d09dc4fb10`, `origin/dev`와 일치, dirty 45 |
| 실험 branch | `020105c5ec4443af2585b7c3cb795d843befed0d`, upstream보다 22 commits ahead, dirty 51 |
| local `main` | `c0947cd52ba5b10b9e08c6c09857adb3f6c9b522`, local tracking 기준 1 ahead/254 behind |
| `main`–`dev` merge base | `589e71b2357085d21ea2d79e5c78dd584506abaa` |
| `dev`–실험 merge base | `e6c6b512e02dda6a3f267fc4c17704d09dc4fb10` |
| `dev`–실험 차이 | `dev` only 0, experiment only 29 commits |

연결된 worktree:

- `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent`
  (`dev`, dirty 45)
- `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent-observability-eval`
  (`auto/validation/all-model-observability-eval`, dirty 6)
- `/home/kotori9/code/MoE-MoA-sglang-gemma4`
  (`auto/runtime/sglang-gemma4-v1`, dirty 51)
- `/home/kotori9/code/dgx-moa-imp-2026-0001`
  (`auto/controller/IMP-2026-0001`, dirty 4)

### 2.2 production clone과 실행 상태

| 항목 | 상태 |
|---|---|
| worktree | `/home/kotori9/dgx-moa-agent` |
| branch/HEAD | `main@396e0458f25977293281b953d2c804cf5b689970` |
| `origin/main` | production clone에서 HEAD와 일치 |
| dirty | `config/models.yaml` 수정, `data/state/backups/` 미추적 |
| 실행 gateway | active/running, PID는 가변값이라 계획 hash에 사용하지 않음 |
| 실행 source cwd | `/home/kotori9/dgx-moa-agent` |
| runtime channel/origin | `main` / `production` |
| 환경의 controller commit | `45192c136d6690d2f1115f72c1023131798d98da` |

`45192c1`은 production HEAD `396e045`의 조상이다. 따라서 실행 환경이 보고한
controller commit과 현재 worktree HEAD가 다르다. release 전에 binary/source/
environment provenance를 하나의 commit으로 일치시켜야 하며, 지금 상태를
검증된 clean production으로 가정하지 않는다.

### 2.3 현재 진단 증거

- dual-SGLang soak `20260727-performance-c6-overlap-fix`는 계속 실행 중이며
  완료 전 PASS가 아니다.
- Codex 진단 `d11`은 기능 5/5이나 baseline 부재로 확증 자료가 아니다.
- Hermes 진단 `20260727-hermes-five-sglang-isolated-d1`은 계획 hash 전에
  시작했으므로 진단 전용이다. 결과는 3/5 PASS이며 `dag-runner`는 tool
  evidence/취소 invocation, `webhook-verifier`는 무수정으로 실패했다.
- gateway `d13`은 local streaming zero-cache를 `cached_tokens=0`으로
  기록하는 것을 물리 확인했다.

## 3. Branch와 history 정상화

1. 모든 ref, worktree HEAD, dirty path 목록, production 환경 commit을 JSON
   manifest로 저장하고 SHA-256을 기록한다.
2. canonical remote를 fetch하되 어떤 worktree도 checkout/reset하지 않는다.
   fetch 전후 remote ref를 모두 manifest에 남긴다.
3. 각 dirty worktree의 변경을 소유 목적별로 분류한다. 다른 실험의 변경은
   복사·수정하지 않고 해당 branch 증거로만 기록한다.
4. 현재 실험 변경은 다음 단위로 분리 검토한다.
   - dual-SGLang topology와 rollback
   - provider/routing/cache telemetry
   - quality/long-horizon harness
   - 코드 삭제와 systemd 정리
   - 문서와 검증 증거
5. 보존 bundle과 hash가 만들어지기 전에는 rebase, cherry-pick, branch
   삭제, force push를 금지한다.
6. 정리된 기능 commit은 새 `dev` 기반 `auto/*` branch에서 재현한다.
   현 실험 branch를 억지로 rebase하거나 전체 diff를 한 번에 이식하지 않는다.
7. 각 기능 branch가 독립 전체 회귀를 통과한 뒤 reviewed PR로 `dev`에
   통합한다.
8. `dev` 통합 결과로 release candidate를 만들고 동일한 평가·rollback을
   재실행한다.
9. 모든 gate와 별도 승인 후에만 `dev -> main` reviewed PR을 사용한다.
   production은 reviewed `main` fast-forward만 받는다.

정상화 완료 판정:

- production `main`, integration `dev`, experiment `auto/*`의 역할이 실제
  ref와 worktree에서 일치한다.
- 모든 기존 commit/dirty diff가 bundle 또는 해당 branch에서 복구 가능하다.
- `main` 직접 개발 commit이 새로 생기지 않는다.
- production 실행 commit, worktree HEAD, controller provenance가 일치한다.

## 4. 코드베이스 정리와 모듈 경계

현재 가장 큰 파일은 `api.py` 4,572 lines, `controller.py` 4,370 lines다.
평가 도구는 여러 `runpy`/동적 import와 전역 객체를 공유한다. 다음 순서로
의존성을 줄이되 framework, ORM, DI container, 범용 plugin abstraction은
추가하지 않는다.

### 4.1 평가 도구

1. `run-client-quality-matrix.py`의 순수 데이터·fixture·runner·scorer 함수를
   import 가능한 작은 stdlib package로 옮긴다.
2. long-horizon, breadth, seal, blind scorer, non-inferiority 분석이 그 package를
   정상 import하게 바꾸고 `runpy`와 import-time 전역 변경을 제거한다.
3. 기존 script 파일은 argument parsing과 exit code만 담당하는 얇은 CLI로
   남긴다.
4. fixture hash, prompt hash, image digest, attempt order, scorer blindness와
   기존 command line은 보존한다.
5. tests도 `runpy` 대신 정상 import를 사용한다.

### 4.2 Chat/Responses 공통 실행 core

1. Chat와 Responses adapter의 입력 정규화와 출력 serialization은 각 router에
   남긴다.
2. role selection, provider pinning, loop budget, tool continuation, review,
   final synthesis, timing/usage 기록은 하나의 공통 실행 core를 사용한다.
3. 공통 core는 protocol별 SSE/Responses event를 알지 않으며 구조화된 실행
   event만 반환한다.
4. Chat과 Responses의 terminal, disconnect, cancellation, tool-call 의미가
   기존과 동일한지 paired contract test로 검증한다.

### 4.3 Router

- inference router: health/readiness/models/model-status, Chat, Responses,
  Judge endpoint
- admin router: runtime/drain/session/Codex/API key/Frontier auth/workflow
- training router: training, weekly, replay, retention

`create_app`은 설정, store, lifecycle, provider, 공용 HTTP client를 lifespan에서
만들고 router에 명시적으로 전달한다. route decorator를 옮기는 것 외의 동작
변경은 같은 commit에 섞지 않는다.

### 4.4 Controller

1. orchestration decision과 loop admission
2. review/revision/Frontier disagreement
3. evidence graph와 completion gate
4. session state와 persistence coordination

위 네 책임을 caller graph 기준으로 분리한다. 이미 있는 `evidence.py`,
`loop_engineering.py`, `routing.py`를 우선 재사용하고 동일 기능의 새
interface/factory는 만들지 않는다. 각 단계는 기존 Controller public contract를
유지하며 별도 commit과 전체 회귀를 가진다.

### 4.5 HTTP client와 SQLite

- application lifespan이 외부 provider용 `httpx.AsyncClient`를 소유하고
  shutdown에서 닫는다. 요청마다 새 client를 만들지 않는다.
- SQLite DDL/migration은 schema 경계, request/token/admin quota 계산은 quota
  경계, domain store는 query/update만 소유한다.
- WAL, busy timeout, transaction, `0600`, 원문 key storage의 기존 보안 의미를
  유지한다.
- schema migration은 downgrade가 아니라 additive/read-compatible migration과
  rollback snapshot으로 검증한다.

### 4.6 삭제 후보

다음은 `rg`, import graph, unit/systemd 참조, runtime process, rollback에서
모두 미참조임을 증명한 뒤에만 삭제한다.

- `fake_model.py`와 fake model launcher
- Discord provider/config/metrics/tests/docs
- 중복 start/stop/resident wrapper
- 완료된 일회성 계획과 context tuning 잔재
- 같은 설정을 중복 표현하는 adapter/wrapper
- 현재 trace/API 호환성에 필요하지 않은 legacy 변환

trace v1 읽기, 기존 API token ID `legacy`, production rollback asset처럼 실제
호환성 계약이 남은 항목은 이름만 보고 삭제하지 않는다.

정리 완료 gate:

- 총 runtime/source LOC와 중복 함수 수가 시작점보다 감소한다.
- `runpy`/동적 script import가 production 평가 도구에서 0이다.
- strict mypy 오류 0, Ruff check/format, `git diff --check`, 전체 pytest PASS.
- 공개 API schema, 인증, SSE/Responses terminal, tool continuation 결과가
  golden contract와 동일하다.

## 5. Prefix/cache 계약

### 5.1 Prefix 순서

다음 고정 prefix를 각 provider 요청 앞에 안정적으로 배치한다.

1. 고정 역할·보안·tool ownership 정책
2. 대화/작업의 immutable identity와 acceptance criteria
3. 동적 plan
4. tool evidence
5. review context
6. 현재 사용자 turn

동적·큰 evidence를 고정 정책 앞에 넣지 않는다. provider prompt cache와
SGLang Radix cache는 별도 필드와 별도 판정으로 기록한다.

### 5.2 Usage 의미

- provider가 explicit zero를 보고하면 `0`
- provider가 cache detail을 생략했으나 local SGLang prompt usage가 있으면
  물리 contract에 따라 `0`
- remote/provider 미보고는 `null`, 절대 0으로 대체하지 않음
- Planner/Reviewer 다중 호출 usage는 invocation별 원본과 합계를 모두 보존
- prompt, cached prompt, completion, reasoning, total 사이의 산술 일관성을 검사

### 5.3 물리 검증

Executor와 Specialist 각각에서 동일한 65K 이하 prefix를 두 번 실행한다.

- 첫 요청과 반복 요청의 TTFT, total latency, cached tokens, output/tool 동등성
- gateway-level 반복 prefix와 직접 SGLang 반복 prefix
- Radix hit, provider prompt-cache hit, cache miss를 별도 표시
- GPU memory, host memory, swap, queue delay, cancellation
- reconnect 후 prefix 재사용과 provider pinning

cache 최적화는 출력/tool 의미가 바뀌거나 메모리/OOM gate를 악화시키면
폐기한다.

## 6. 관리자 workflow 관측

기본값은 비활성이다. 기존 인증 gateway에만 다음 기능을 추가한다.

- authenticated WebSocket workflow canvas
- queue, warm-up, dispatch, fallback, retry, failure 상태
- 실제 provider/model과 content-free latency/cost/cache/memory
- 요청 상세 로그와 별도 AI 요약 보고서
- operator 전용 명시적 원문 조회
- 원문 조회 감사 기록과 90일 retention
- local GPU/전력/메모리/시간대별 요청량
- `ssh mathcat` Ollama host의 같은 aggregate 관측

보안 규칙:

- hidden reasoning과 credential은 operator 원문에도 표시하지 않는다.
- 원문 조회는 admin session, 명시적 action, `no-store`, 감사 event를 요구한다.
- WebSocket은 기존 admin 인증과 origin 정책을 재사용한다.
- browser reconnect cursor, bounded queue, backpressure, slow-client drop를
  구현하고 prompt/raw payload를 broadcast하지 않는다.
- SSH는 고정 host와 read-only allowlisted 관측 명령만 허용한다.
- 90일 삭제는 dry-run과 authenticated apply를 분리한다.

활성화 전 물리 gate:

- 정상 reconnect와 event cursor 복구
- 느린 client가 gateway/model 요청을 막지 않음
- bounded queue overflow가 명시적 drop metric을 남김
- local 또는 mathcat 한쪽 장애 시 다른 쪽 관측과 inference가 계속됨
- 원문 권한 우회, secret leak, hidden reasoning 노출 0
- feature disabled 시 route가 404 또는 명시된 비활성 응답

## 7. SGLang 물리 topology gate

고정 대상:

- Executor: `Cirrascale/Qwen3-Coder-Next-NVFP4`,
  revision `15c399c8189eccc9c47d17dcf8adf3c16e8bb3f8`
- Planner/Reviewer: `nvidia/Gemma-4-26B-A4B-NVFP4`,
  revision `a19cfe00be84568a6867111c9a68c9c44fdcffe6`
- image:
  `lmsysorg/sglang:dev-cu13@sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0`

필수 설정:

- 두 독립 loopback-only instance
- context 65,536, max running requests 1, max total tokens 65,536
- Executor Radix cache, Mamba cache 5 slots, 검증된 63–65 GB 목표 점유
- Gemma ModelOpt NVFP4, `gemma4` reasoning/tool parser, streaming, structured output
- 실제 inference probe 이후에만 READY

검증:

- 두 모델 동시 상주와 revision/image digest
- near-limit prompt, prefix reuse, Executor tool call
- Planner plan/migration, Reviewer security/concurrency finding
- 다중 client queue와 BUSY remote fallback
- provider pinning, no mixed output, fail-closed high-risk path
- 장기 Goal 부하 중 OOM/restart 0, memory/swap pressure와 recovery

Gemma SGLang의 위 물리 계약이 실패한 경우에만 동일 revision Gemma vLLM
fallback epoch를 시작한다.

## 8. 평가 protocol과 epoch

`docs/QUALITY_EVALUATION.md`의 현재 margin, sample, seed, blindness, 실패 기준을
변경하지 않는다.

### 8.1 Coding panel

- variants: native GPT-5.6 Sol baseline, MoA Codex, OpenCode, installed Hermes
- five tasks × ten repeats × four variants = 200 attempts
- 모든 candidate attempt의 기능·hidden·도구·terminal·telemetry gate PASS
- quality: task-stratified paired bootstrap 10,000, seed `56052026`,
  one-sided 95% lower bound > -5
- speed: log ratio의 one-sided 95% upper bound < 1.50
- ordinary OpenRouter variable spend $0

### 8.2 Breadth panel

- Scientific Reasoning 2 tasks, General 2 tasks
- four variants × four tasks × ten repeats = 160 attempts
- bootstrap 10,000, seed `56052027`
- 두 category가 각각 reliability/quality/speed/cost를 통과

### 8.3 Blind judge

- primary: Codex OAuth `gpt-5.6-sol`, high reasoning
- secondary: OpenRouter `anthropic/claude-opus-5`, Amazon Bedrock only,
  fallbacks disabled
- scorer는 opaque artifact만 보고 provider/model/route/timing/final response를
  보지 않는다.
- dual-score agreement가 80% 미만이면 Opus 5를 전체 panel로 확대한다.

### 8.4 Change control

코드, model, revision, image, prompt, fixture, tool policy, scorer, threshold,
runner가 바뀌면 해당 epoch는 진단으로 봉인하고 새 protocol/run ID로 전체
확증 평가를 다시 시작한다.

## 9. 장기 Goal 연속성 gate

- 목적은 모델 endpoint를 10시간 점유하는 것이 아니라 최적화된 MoA API를
  통해 실제 장기 Goal의 계획·구현·검토·복구를 끝까지 유지하는 능력이다.
- 경과 시간은 관측값일 뿐 단독 완료 조건이나 품질 대용 지표가 아니다.
- 실제 장기 Goal은 Codex/OpenCode/Hermes→인증 Gateway→Dynamic MoA→host tool
  경로로 의존 순서가 있는 다섯 단계를 수행하고, 최소 1회 intentional
  reconnect 뒤 같은 작업을 정확히 재개해야 한다.
- 직접 local endpoint 호출, 모델 공회전, backend soak는 이 gate의 증거가
  아니다.
- 전체 실행에서 Reasoner, Executor, Planner, Reviewer provenance가 모두
  관측되어야 하며 외부 fallback은 실제 routing policy가 요구할 때만 쓴다.
- checkpoint 맥락은 모델이 별도 파일 형식을 따르는지로 평가하지 않는다.
  실제 Gateway session state의 objective, acceptance, plan, phase, completed
  steps, tool, review 필드를 선택적으로 SHA-256 처리해 연속성을 판정하며 원문은
  평가 archive에 저장하지 않는다.
- 같은 session의 새 user turn은 이전 turn의 계획·증거를 맥락으로 보존하되,
  이전 turn에서 완료한 변경·검증·review를 현재 turn 완료 근거로 재사용하지
  않는다. tool continuation은 같은 user turn으로 유지한다.
- 필수 Frontier correction은 반환된 도구를 클라이언트가 실제 실행하지 않으면
  즉시 fail closed한다. 실행했지만 correction이 남은 경우에만 mutation을
  명시한 두 번째 retry를 허용하며, 두 번 후에는 반드시 fail closed한다.
- intentional reconnect 1회 이상
- positive cache read 1회 이상
- objective, acceptance criteria, plan, phase, next action, repository/branch/
  dirty identity, evidence hash, provider provenance 유지
- 실제 구현, 독립 review, 전체 validation 이후에만 final terminal
- 5xx, lost continuation, 반복 무의미 읽기, plan drift, premature completion,
  secret persistence, checkpoint 누락, provider error, unresolved critical 0

`scripts/analyze-long-horizon.py`의 기계적 판정은 장기 Goal 증거의 한
구성요소다. 짧은 backend soak나 단순 경과 시간으로 실제 작업 완결성,
reconnect, plan/context 보존을 대체하지 않는다.

### 9.1 AvatarForge active-work protocol

추가 장기 검증은 사용자 제공 계약
`avatarforge-10h-validation-goal.md`와 그 계약이 참조하는 AvatarForge Goal
원문을 byte-for-byte fixture로 사용한다. 동결 SHA-256은 각각
`6676ac077979fe305d96619c7cd2d6c42b40d7e3b361d28389e9eaa54609df83`와
`37878be8c6e67262e80b680cea5effa504ed3cafef55d886ae41e9bc35d507fa`다.

- Codex, OpenCode, installed Hermes는 같은 clean seed repository, 입력,
  provider manifest, 권한, 모델 topology에서 각각 독립 실행한다.
- 실제 client→인증 loopback Gateway→Dynamic MoA→host tool 경로만
  유효하다. direct model/idle soak/반복 추론은 제외한다.
- 필수 checkpoint는 AvatarForge Phase 0, 1, 2, 3이다. 각 checkpoint는
  계획 갱신, baseline-relative 실제 diff, 발견된 테스트 1개 이상, 고정
  validation 성공, 독립 Reviewer, clean commit, evidence를 요구한다.
- Phase 1 완료 뒤 client를 의도적으로 재접속하고 동일 Gateway session의
  plan, phase, unresolved item, tool/review evidence를 복구한다.
- Codex 내부 context compaction 요약 요청은 `:compact` 보조 세션에서
  tool 없이 처리하며 본 작업 session의 user turn, review, progress evidence를
  변경하지 않는다.
- 10시간은 active-work 상한이다. Phase 0–3이 통과하면 기다리지 않고
  종료할 수 있고, 시간이 남을 때만 마지막 통과 checkpoint에서 Phase 4
  이후를 순서대로 진행한다. 시간을 채우는 반복은 실패다.
- 장기 Goal 합격값은 경과시간이 아니다. 실제 Codex/OpenCode/Hermes
  client→인증 Gateway→Dynamic MoA→host tool 경로가 서로 의존하는 계획,
  수정, 테스트, 독립 검토, checkpoint, 재접속, context/cache 복구를
  terminal까지 완결해야 한다. direct local-model 반복이나 idle soak는
  실행 시간이 길어도 증거가 아니다.
- 이 상한은 전체 profile에 한 번만 적용한다. checkpoint마다 상한을 새로
  부여하거나 실제 도구·수정·검토 진척이 있는 실행을 30분에 자르지 않는다.
- 설치, 라이선스, credential, OS permission이 없으면 dependent 항목을
  `BLOCKED`로 기록하되 mock, schema, contract, state/revision 구현과 테스트는
  계속한다. `BLOCKED`를 PASS로 변환하지 않는다.
- candidate Loop ceiling은 `iterations=256`, `tool_calls=1000`,
  `reasoner_reentries=256`, `planner_calls=32`, `reviewer_calls=64`,
  `frontier_calls=128`, `tokens=8000000`, `external_cost_usd=10`,
  `wall_clock_seconds=36000`이다. 이는 작업 목표가 아니라 fail-safe다.
- 코드, prompt, fixture, model, scorer, threshold가 바뀌면 진행 중 결과를
  진단으로 봉인하고 새 protocol/run ID와 clean seed에서 다시 시작한다.
- 기존 long-horizon runner와 analyzer를 profile-driven으로 최소 확장한다.
  별도 중복 runner나 AvatarForge 전용 orchestration framework는 만들지 않는다.
- protocol v2부터 필수 Frontier correction 재시도에는 클라이언트가 제공한
  도구 중 repository mutation 도구만 전달한다. 계획·Goal·이미지·조회
  도구로 correction retry를 소비하지 않으며 기존 2회 fail-closed 상한은
  유지한다.
- protocol v3 candidate Gateway는 `DGX_MOA_MAX_STEPS=1000`을 사용해
  long-Goal의 독립 step ceiling과 Loop Engineering 예산을 일치시킨다.
  `tool_calls=1000` fail-safe와 session step 상한을 정합시킨다. production
  기본 100은 변경하지 않는다. step 상한 도달은 retryable backend 장애가
  아니라 비재시도 `409 loop_budget_exhausted`로 종료한다.
- protocol v4는 Codex OAuth structured-output validation 실패 시 같은
  provider의 secondary·tertiary profile을 먼저 순서대로 시도한다. 필수
  Executor 요청에서 모든 OAuth profile이 실패한 경우에만 기존 OpenRouter
  최후 fallback을 허용하며 malformed tool arguments 자체는 계속 fail
  closed한다.
- protocol v5는 Frontier review의 semantic output만 fingerprint로 사용해
  동일 finding 세 번째 반복을 기존 `DUPLICATE_FAILURE_LIMIT`로 fail
  closed한다. token, cost, profile 메타데이터 변화나 무효 correction
  호출은 새 review progress로 인정하지 않는다.
- protocol v17은 모든 harness가 실제 host tool로 쓸 수 있는 정확한
  `<workspace>/state/long-review.json`을 최종 review artifact 경로로 쓴다.
  이 파일은 baseline 이후 clean commit에 포함되어야 하고
  `status`, `unresolved_critical_findings`, `evidence_sha256`만 허용한다.
  free-form review 원문, prompt, hidden reasoning, credential은 저장하지 않으며
  missing, unchanged, malformed artifact는 fail closed한다.
- protocol v18은 Frontier correction을 repository mutation과 그 뒤의 성공한
  bounded validation이 모두 관측된 뒤에만 재검토한다. correction 중에는
  Reviewer와 Frontier를 재호출하지 않고, mutation 뒤에는 command tool만
  노출해 validation을 먼저 수행한다.
- protocol v19는 post-mutation validation 실패 시 correction을 완료하거나
  같은 validation을 반복하지 않고 mutation 단계로 되돌린다. 성공한
  validation만 Reviewer와 Frontier 재검토를 허용한다.
- protocol v20은 stream 종료 시 명시적 Reviewer rejection을 `deferred`로
  덮지 않는다. rejected snapshot은 실제 성공한 repository mutation 전까지
  재검토할 수 없다.
- protocol v21은 Frontier `apply_patch`의 `input`, `patch`, `diff` 별칭을
  Codex custom-tool `input`으로 단일 정규화하고, 실행 가능한 patch envelope와
  file operation이 없는 correction을 완료로 기록하지 않는다.
- protocol v22는 실사용 장기 Goal이 100 request에서 중단되지 않도록 candidate
  session step 상한을 bounded 1000으로 늘린다. 시간 경과가 아니라 실제
  checkpoint, reconnect, review, 최종 artifact gate는 그대로 유지한다.
- protocol v23은 local Reviewer의 `status+findings` semantic fingerprint를
  기존 engineering-loop duplicate failure budget에 등록하고, 세 번째 동일
  finding set에서 fail closed한다.
- protocol v24는 고정 정책·schema·목표·제약을 동적 plan·evidence보다 먼저
  배치하고, cache 미보고를 실제 0과 구분하며 검증된 cache만 Loop token
  예산에서 차감한다.
- protocol v25는 Planner·Reviewer의 analysis와 final 두 호출이 모두 cache를
  보고한 경우에만 합계를 기록한다. 하나라도 미보고면 부분값 대신 unknown을
  보존한다.
- protocol v26은 Frontier가 세션 안에서 이미 실행된 tool call ID를 재사용하면
  provider dispatch 단위의 deterministic ID로 remap한다. ID 재사용 때문에
  성공한 host mutation 결과가 duplicate로 누락되어 correction retry가
  고갈되는 것을 막되, provider pinning과 안전한 tool-call 검증은 유지한다.
- protocol v27은 `long-horizon` workspace에서 마지막 파일 변경 뒤 clean
  `git status` 증거가 없으면 완료를 허용하지 않고 commit·artifact 정리·
  `git status --porcelain` 확인을 계속 요구한다.
- protocol v28은 장기 correction에서 최근 mutation 4개와 최근 도구 6개를
  Reviewer evidence에 함께 유지하고, implementation evidence를 8개 및
  redacted reviewer 입력을 24k 문자로 제한해 전체 구현 맥락 유실을 줄인다.
- protocol v29는 local Reviewer 중복 fingerprint를 원문 문구가 아니라
  finding ID·severity·category·affected location·required 여부로 정규화해,
  같은 결함을 바꿔 말하는 반복 correction이 duplicate fail-closed를
  우회하지 못하게 한다.
- protocol v30은 OpenCode 장기 실행에 고정된 비민감 `--title`을 전달한다.
  제목 생성을 위한 별도 모델 호출은 Goal 구현·도구 실행 증거가 아니며,
  V100에서 첫 Gateway 응답 후 네트워크·파일·checkpoint 진척 없이
  OpenCode 프로세스만 계속 실행되는 정체를 만들었다. 기존 v29 실행은
  진단으로 보존하고 v30부터 제목 생성 경로를 평가 대상에서 제외한다.
- protocol v31은 OpenCode의 기본 외부 경로 deny를 유지하면서 동결
  objective·acceptance·plan 세 파일만 정확한 경로 allowlist로 허용한다.
  workspace 밖의 다른 경로와 비밀 파일은 계속 거부한다.
- protocol v32는 격리 OpenCode의 native experimental filewatcher를 끈다.
  host tool 완료 뒤 네트워크 요청 없이 event loop가 대기하는 V102 정체를
  제거하되, runner의 Git diff·clean commit·checkpoint 검증은 유지한다.
- protocol v33은 OpenCode SDK가 configured `X-Session-ID` 대신 자체 session
  ID를 Gateway에 보내는 동작을 계측 계약에 반영한다. OpenCode 출력에서
  확인된 client session으로 Gateway state와 provider telemetry를 조회하며,
  Codex·Hermes의 configured session 계약은 변경하지 않는다.
- protocol v34는 Gemma batch-one decode에 full CUDA Graph를 사용하고
  prefill Graph는 비활성으로 유지한다. Gemma context count는 멀티모달
  placeholder ID를 직렬화하는 `/tokenize` 대신 SGLang의 native
  `/v1/messages/count_tokens`를 사용한다. V105에서 측정한 255.24초 Planner
  호출과 고정 two-pass token budget에 따라 ordinary routing의 local latency
  기본값을 Planner 260초, Reviewer 340초로 사용한다. V105는 중단 진단으로
  보존하며 v34는 새 clean seed와 새 run ID에서 시작한다.
- protocol v35는 Planner/Reviewer candidate를
  `nvidia/Gemma-4-26B-A4B-NVFP4` revision
  `a19cfe00be84568a6867111c9a68c9c44fdcffe6`로 교체한다. v34의 31B
  latency와 품질 결과는 새 모델의 증거로 재사용하지 않는다. V113 물리
  gate에서 Planner 39.730초, Reviewer 30.554초를 측정했으므로 ordinary
  routing의 보수적 local latency 기본값은 각각 45/35초로 사용한다.
- protocol v36은 OpenCode에 전체 호스트가 아닌 격리 workspace 루트만
  `external_directory` 예외로 허용한다. v35 실행은 진단 자료로만
  보존하고 새 clean seed와 새 run ID에서 다시 시작한다.
- protocol v37은 client 비정상 종료의 원문을 보존하지 않고 고정된
  payload-free 오류 분류만 failure sidecar에 기록한다. v36 결과는 진단
  자료로만 보존하고 새 clean seed와 새 run ID에서 다시 시작한다.
- protocol v38은 OpenCode의 디렉터리 단위 외부 접근 계약에 맞춰 동결
  입력 각각의 부모 디렉터리만 허용한다. 전체 attachments와 그 밖의 외부
  경로는 계속 deny하며 v37 결과는 진단 자료로만 보존한다.
- protocol v39는 OpenCode 공식 permission glob 계약에 따라 각 신뢰
  디렉터리 허용 패턴에 `/**`를 붙인다. v38 결과는 진단 자료로만 보존한다.
- protocol v40은 non-default Codex OAuth profile의 `HOME`과
  `CODEX_HOME`을 동일한 writable 격리 profile로 고정한다. v39 결과는
  진단 자료로만 보존한다.
- protocol v41은 Codex subprocess 원문을 저장하지 않고 고정된
  payload-free protocol-error detail만 관측 이벤트에 기록한다. v40
  결과는 진단 자료로만 보존한다.
- protocol v42는 redacted Frontier evidence를 process argv가 아니라
  Codex 공식 stdin 모드로 전달한다. v41 결과는 진단 자료로만 보존한다.
- protocol v43은 raw output 없이 Codex JSON event 실패와 stderr-only
  실패를 구분하고 고정된 CLI 오류 범주를 확장한다. v42 결과는 진단
  자료로만 보존한다.
- protocol v44는 stderr 문장을 저장하지 않고 사전 승인된 일반 진단
  단어의 교집합만 sanitized failure event에 기록한다. v43 결과는 진단
  자료로만 보존한다.
- protocol v84는 V179에서 확인된 평가 계약 모호성을 제거한다. 새
  AvatarForge 실행은 모든 산출물을 `<workspace>/avatarforge/`, 테스트를
  `avatarforge/tests/`, phase 보고서를 `avatarforge/docs/status/`의 고정
  5개 파일에만 둔다. 기존 MoA runtime·script·config·test·pyproject와
  top-level `source`/`src`/`tests` 변경은 prompt와 checkpoint changed-path
  gate에서 모두 거부한다. commit과 clean 상태는 runner가 수집하므로
  최신 commit hash를 다시 기록하는 self-referential evidence 문서는
  금지한다. 공개 evidence header와 private control은 첫 client 호출 전에
  fsync하고, 안정 session hash는 처음부터 알려진 gateway session으로
  계산한다. v76/V179는 진단 자료로만 보존하며 새 clean seed와 새 run ID를
  사용한다.
- protocol v85는 Codex stream이 session event를 내보내기 전에 단절되더라도
  격리 `state_*.sqlite`에 활성 thread가 정확히 하나일 때만 그 ID를 복구해
  동일 provider·gateway session으로 한 번 resume한다. 둘 이상이거나 재시도도
  실패하면 fail closed하며 raw client output과 thread ID는 evidence에 저장하지
  않는다. 첫 시도의 tool/cache/usage 관측은 성공한 resume와 합산한다.

## 10. Release, rollback, 배포

1. 정리된 기능 branch들을 `dev`에 reviewed integration
2. clean release candidate에서 전체 unit/Ruff/mypy/trace/API contract
3. sealed coding/breadth/장기 Goal 결과와 confidence interval PASS
4. dual-SGLang stop/start와 기존 baseline rollback rehearsal
5. 별도 승인 후 `dev -> main` reviewed PR
6. production worktree fast-forward, source/environment commit 일치
7. gateway-only listener와 인증 확인
8. canary: Chat, Responses, Codex, OpenCode, Hermes, tool continuation,
   admin-disabled contract, telemetry completeness
9. 배포 후 rollback 재확인

기존 model 삭제 조건:

- service, config, docs, install, status, rollback에서 참조 0
- 대체 rollback이 물리 검증됨
- model ID/revision/hash와 폐기 판정 증거 보존
- 삭제 대상 경로를 정확히 재검증
- 위 조건과 별도 승인 후 해당 weights만 삭제

## 11. 최종 완료 판정

다음이 모두 증거로 PASS일 때만 merge·배포·정리와 Goal 완료를 선언한다.

- branch/worktree 보존 및 `main`/`dev`/`auto/*` 역할 복구
- 코드 정리, 순감축, strict mypy 0, Ruff/전체 pytest/API contract PASS
- Codex/OpenCode/Hermes coding·breadth 비열등성과 신뢰구간 PASS
- dual-SGLang readiness/cache/tool/structured-output/load/OOM gate PASS
- 실제 장기 Goal의 계획·맥락·reconnect·cache·memory gate PASS
- 관리자 workflow 기능의 보안·reconnect·backpressure·장애 gate PASS
- production canary, gateway-only 보안, rollback rehearsal/배포 후 검증 PASS
- 누락, 실패, `INCONCLUSIVE`, 불완전 telemetry 0
