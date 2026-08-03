# Dynamic MoA 개발자 아키텍처 및 실행 계획

## 0. 문서 상태

| 항목 | 값 |
|---|---|
| 작성일 | 2026-07-31 |
| 통합 기준 branch | `dev` |
| 최신 후보 참조 branch | `auto/runtime/sglang-gemma4-v1` |
| 최신 후보 참조 commit | `05a729ecfc4bf5f5d7fd903ba234a0081db2ee10` |
| production branch | `main` |
| 현재 물리 검증 epoch | `V162`, protocol v64 |
| 문서 목적 | 개발자가 기존 경계를 보존하면서 독립 작업을 시작할 수 있는 구조·순서·검증 계약 제공 |

이 문서는 코드 구조와 앞으로의 구현 순서를 설명한다. 운영 상태의 최종
권위는 `docs/STATE.md`, 운영 절차는 `docs/OPERATIONS.md`, 측정 증거는
`docs/VALIDATION.md`, trace 계약은 `docs/TRACE_SCHEMA.md`가 가진다.

현재 `dev` worktree에는 아직 통합되지 않은 미커밋 변경이 존재한다.
따라서 새 개발은 `dev` 파일을 직접 수정하지 않고 별도 `auto/*`
worktree에서 수행한다. 실행 중인 `auto/runtime/sglang-gemma4-v1`도
V162 평가 대상이므로 직접 수정하지 않는다.

## 1. 시스템 불변 조건

1. 외부 클라이언트는 인증된 Gateway만 호출한다.
2. Executor, Planner, Reviewer inference endpoint는 loopback-only다.
3. Executor만 도구 호출, 라우팅 최종 권한, 수정 검증, 사용자 최종
   synthesis를 소유한다.
4. Reasoner는 모든 기본 Executor turn 전에 호출된다.
   `dgx-moa-fast`만 의도적으로 Reasoner를 우회한다.
5. Planner, Reviewer, Frontier, Judge는 구조화 artifact만 반환한다.
6. provider dispatch 이후 현재 호출의 provider를 전환하거나 local/remote
   결과를 섞지 않는다.
7. hidden reasoning, credential, authorization, cookie, prompt 원문은
   observation, metric label, trace, training archive에 저장하지 않는다.
8. SQLite state 저장 실패는 fail closed다. 보조 JSONL trace 실패는
   observability degraded로 기록할 수 있지만 안전한 요청 결과를 버리지 않는다.
9. 모델 READY는 실제 inference readiness probe 성공 후에만 허용한다.
10. production `main`, integration `dev`, 실험 `auto/*` 역할을 바꾸지 않는다.

## 2. 실행 토폴로지

```text
Codex / OpenCode / Hermes / OpenAI-compatible client
                         |
                         | authenticated tailnet / loopback
                         v
                  FastAPI Gateway
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
Ollama Reasoner   Specialist Router   Codex OAuth Frontier
100.90.167.128     Planner/Reviewer       GPT-5.6-sol
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
              Qwen3-Coder-Next Executor
                SGLang, loopback-only
                         |
                tools / final synthesis
                         |
                         v
                      Client
```

최신 후보 모델:

| 역할 | 모델 | revision | endpoint |
|---|---|---|---|
| Executor | `Cirrascale/Qwen3-Coder-Next-NVFP4` | `15c399c8189eccc9c47d17dcf8adf3c16e8bb3f8` | `127.0.0.1:18101` |
| Planner·Reviewer | `nvidia/Gemma-4-26B-A4B-NVFP4` | `a19cfe00be84568a6867111c9a68c9c44fdcffe6` | `127.0.0.1:18102` |
| Reasoner | 외부 Ollama 모델 | 운영 manifest 권위 | `100.90.167.128:11434` |
| Frontier | Codex OAuth `gpt-5.6-sol` | provider 관리 | 별도 Codex process |
| Judge | local Heavy Judge 또는 별도 Remote Judge | 역할별 manifest | Executor/Planner fallback과 분리 |

Executor와 Specialist는 각각 context 65,536, sequence 1을 유지한다.
현재 Goal 원문 일부에는 Gemma 31B가 남아 있지만 실제 후보와 최신 사용자
결정은 26B-A4B다. 확증 평가 전에 계획, model manifest, seal을 같은 모델
revision으로 다시 일치시켜야 한다.

## 3. 저장소 구조

```text
repository/
├── gateway/src/dgx_moa/  Python runtime package
├── tests/                unit, integration, contract tests
├── config/               checked-in safe configuration
├── scripts/              operator and evaluation commands
├── systemd/              production unit and target definitions
├── docs/                 architecture, state, operations, evidence
├── schemas/              external JSON schemas
├── data/                 local state, traces, datasets, evidence
├── training/             role-specific training assets
└── compat/               narrowly scoped runtime compatibility
```

`data/validation/`, 모델 weight, API key, OAuth credential은 Git에 추가하지
않는다.

## 4. Gateway 조립과 API 경계

### 4.1 `api.py`

`dgx_moa.api:create_app()`가 runtime object를 조립하고 FastAPI route를
등록한다.

주요 route:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `GET /v1/models`
- `GET /v1/model-status`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/responses`
- `POST /v1/judge/adjudications/{session_id}`

`api.py`는 조립, dependency wiring, HTTP transport 경계를 담당해야 한다.
다음 책임을 새로 추가하지 않는다.

- OpenAI message 변환
- orchestration policy
- SQLite DDL
- admin HTML
- training retention

이 책임들은 아래 전용 모듈로 보낸다.

### 4.2 `inference.py`

Chat Completions와 Responses API 공통 실행 경계다.

- Responses input을 내부 message로 변환
- Responses tool schema 변환
- tool call ID 재사용 보정
- Chat 결과를 Responses 결과로 변환
- tool result와 tool call 연결 검증
- response-owned iterator와 HTTP response 수명 관리

OpenAI 호환 필드를 추가하거나 수정할 때 이 파일을 먼저 변경한다.

### 4.3 `schemas.py`

외부 입력과 역할별 구조화 출력의 신뢰 경계다.

- Chat/Responses request
- Reasoner contribution
- Executor orchestration decision
- Planner plan
- Reviewer finding
- tool call

길이, enum, extra field, 위험한 조합은 Pydantic schema에서 거부한다.
route별 임시 `dict` validation을 만들지 않는다.

### 4.4 `security.py`

- bearer 인증
- 일반 key와 admin key 분리
- API key 생성·회전·폐기·quota
- admin session
- 민감 필드 재귀 마스킹

인증 우회나 raw key 출력은 route가 아니라 이 공통 경계에서 차단한다.

## 5. 요청 실행 흐름

```text
1. API 인증과 schema 검증
2. model alias → runtime mode
3. request class와 필수 역할 계산
4. request/session/role usage 시작
5. Reasoner 호출 또는 dgx-moa-fast 우회
6. Executor orchestration decision
7. deterministic safety policy 보정
8. Planner/Reviewer/Frontier/Judge dispatch
9. Executor context에 구조화 evidence 삽입
10. Executor tool call 또는 final synthesis
11. tool result 정규화
12. 실패·진척·review·completion gate 갱신
13. 필요하면 correction/replanning loop
14. usage, trace, observation 종료
15. Chat/Responses 형식으로 client 응답
```

### 5.1 `routing.py`

- model alias 해석
- request class 분류
- required/optional role 계산
- Planner·Reviewer 필요 조건
- 고위험 fail-closed 조건

### 5.2 `controller.py`

현재 orchestration의 중심이지만 책임이 너무 많다.

현재 책임:

- loop admission과 budget
- Reasoner context fingerprint
- orchestration decision
- Planner/Reviewer/Frontier 호출 순서
- tool result 정규화
- review correction
- evidence 기록
- completion gate

목표 분리 경계:

```text
controller.py             thin coordinator
orchestration.py          role selection and deterministic overrides
review.py                 reviewer/frontier/judge correction flow
tool_evidence.py          tool result normalization and validation evidence
completion.py             terminal completion and fail-closed gate
```

한 번에 전부 분리하지 않는다. 각 단계는 호출자를 모두 검색하고, 한 책임,
한 회귀 테스트, 전체 테스트 통과 단위로 이동한다.

### 5.3 `policy.py`, `loop_engineering.py`, `evidence.py`

- `policy.py`: declarative safety decision
- `loop_engineering.py`: iteration/action/token/cost/time budget
- `evidence.py`: 모델 주장과 실제 tool evidence의 구분

모델 출력은 policy authority가 아니다. deterministic policy가 모델 결정을
보강하거나 거부할 수 있다.

## 6. 모델 provider와 specialist routing

### 6.1 `providers.py`

로컬 OpenAI-compatible provider 공통 구현:

- request body 정리
- context-fit token count
- timeout
- streaming/non-streaming
- structured response parse
- prompt/completion/cached token 정규화
- Gemma reasoning + final JSON 2단계

`cached_tokens=None`은 provider가 보고하지 않았다는 뜻이고, `0`은 실제
보고된 zero다. 두 값을 합치지 않는다.

### 6.2 `specialists.py`

```text
PlannerProvider
├── LocalPlannerProvider
├── RemotePlannerProvider
└── MockPlannerProvider

ReviewerProvider
├── LocalReviewerProvider
├── RemoteReviewerProvider
└── MockReviewerProvider
```

`SpecialistRouter`는 READY/health, queue, 예상 완료시간, cost margin,
circuit breaker, local-only policy로 provider를 선택한다.

Cold local model을 현재 요청이 기다리지 않는다. remote를 즉시 선택하고
local warm-up은 singleflight로 별도 진행한다. 현재 호출은 dispatch한
provider에 pin한다.

### 6.3 `frontier.py`

Codex OAuth collaboration:

- architecture
- code review
- disagreement
- Executor fallback

Frontier에는 bounded sanitized evidence만 전달한다. Codex OAuth primary는
일반 OpenAI API key를 요구하지 않는다. OpenRouter는 드문 마지막 fallback다.

### 6.4 `remote_judge.py`

JudgeProvider는 Planner·Reviewer remote fallback과 분리한다. Judge 결과는
고위험 disagreement/correction에만 권위를 가진다.

## 7. Streaming과 tool continuation

### 7.1 `streaming.py`

- 완전한 SSE event 단위 forwarding
- native delta 보존
- duplicate `[DONE]` 제거
- clean EOF에서 `[DONE]` 보장
- Chat → Responses SSE 변환
- keepalive
- tool progress 표시
- apply_patch compatibility
- repeated goal prerequisite read batching

Streaming 경로는 Reviewer 전체 출력 buffer가 아니다. streaming review는
후속 evidence 단계로 미룬다.

### 7.2 tool evidence

tool result에서 보존할 것:

- 실제 exit code
- stdout/stderr의 bounded sanitized form
- duration
- truncation
- filesystem effect
- failure class
- argument fingerprint

검증 성공은 exit code 0만으로 인정하지 않는다.

- pytest: nonzero `N passed`
- unittest: nonzero `Ran N tests`와 `OK`
- pipe, redirect, output filter가 사용된 검증: evidence 거부

## 8. State, SQLite, usage, trace

### 8.1 `state.py`

`SessionState`가 논리 작업 상태를 보존한다.

- phase
- objective
- plan
- roles
- tool results
- failures
- review status
- orchestration decisions
- invocations
- completion evidence
- termination reason

`StateStore`는 `sessions`, `events`를 관리한다.

### 8.2 `database.py`

SQLite 연결과 WAL/busy-timeout 같은 공통 연결 정책만 둔다.

목표 schema 경계:

```text
database.py / schema module
  DDL, migration, connection

usage.py / quota module
  request/token/admin quota calculation

state.py
  session and event persistence

lifecycle.py
  residency, lease, lifecycle decisions
```

### 8.3 `usage.py`

- request usage
- role request usage
- model invocation usage
- provider/model provenance
- latency, token, cache, cost
- API key별 quota와 dashboard aggregation

비용 누락을 0으로 처리하지 않는다.

### 8.4 `trace.py`

- runtime channel과 trace origin 검증
- session state → trace record
- append-only JSONL export
- SQLite trace index
- completeness audit

SQLite state 실패는 fail closed다. JSONL export 실패는 별도 degraded event로
기록한다.

## 9. Lifecycle

`lifecycle.py`의 주요 구성:

- `LifecycleStore`
- `LifecycleCoordinator`
- `SystemdLifecycleDriver`

상태:

```text
UNLOADED
LOAD_REQUESTED
LOADING
READY
BUSY
DEGRADED
EVICTING
FAILED
COOLDOWN
```

주요 불변 조건:

- READY는 inference probe 성공 이후
- role/revision/runtime instance별 active load 1개
- Executor와 Reasoner는 eviction 보호
- Planner·Reviewer idle gap은 역할 자체 성공 요청으로 계산
- 세 번의 lifecycle mutation failure가 automation latch를 비활성화
- rollback은 disabled + empty unit map으로 복귀

목표 분리:

```text
lifecycle_state.py     state, transition, lease
lifecycle_policy.py    idle/residency decision
lifecycle_driver.py    systemd execution
lifecycle.py           compatibility facade during migration
```

## 10. 관리자와 관측

### 10.1 현재 모듈

- `admin_routes.py`: admin API
- `admin_dashboard.py`: runtime dashboard HTML
- `key_dashboard.py`: API key dashboard HTML
- `admin_codex.py`: admin Codex execution
- `runtime_status.py`: service/model status
- `observation.py`: sanitized live events와 command nonce
- `metrics.py`: Prometheus

### 10.2 목표 workflow canvas

표시할 상태:

```text
intake → queue → warm-up → dispatch → running
       → fallback → retry → review → complete/failure
```

필수 보안:

- 기존 admin session 인증 재사용
- origin 검사
- hidden reasoning과 credential 제외
- raw 조회는 operator의 명시적 action
- `Cache-Control: no-store`
- raw reveal 감사 event
- 90일 retention
- reconnect cursor
- bounded queue와 slow-client backpressure
- 기능 기본 비활성

구현 권장:

```text
admin_workflow.py          WebSocket/API router
admin_workflow_store.py    bounded event query and retention
admin_workflow.js          canvas rendering
```

새 frontend framework나 별도 listener는 추가하지 않는다.

## 11. 평가 시스템

| 모듈 | 책임 |
|---|---|
| `quality_matrix.py` | Codex/OpenCode/Hermes 실작업 실행 |
| `blind_quality.py` | blind scoring |
| `breadth_quality.py` | coding 외 범주 panel |
| `breadth_noninferiority.py` | paired non-inferiority 통계 |
| `confirmation_seal.py` | protocol/model/scorer/fixture 봉인 |
| `long_horizon_client.py` | 장기 client 실행 |
| `long_horizon_analysis.py` | reconnect/context/cache 분석 |
| `isolated_sglang_validation.py` | 물리 topology 검증 |
| `isolated_sglang_soak.py` | sustained load |
| `frontier_noninferiority.py` | Frontier 기준 비교 |

평가 epoch가 시작된 뒤 code, prompt, model, fixture, scorer 중 하나라도
바뀌면 기존 결과를 진단 자료로 보존하고 새 protocol/run ID로 다시 봉인한다.

확증 PASS에 필요한 최소 증거:

- 고정 sample과 bootstrap seed
- blind scorer
- paired quality CI
- paired speed CI
- 비용 완전성
- reliability hard gate
- provider pinning
- tool-use 품질
- Coding, Scientific Reasoning, General, 장기 Goal 범주
- Codex, OpenCode, Hermes 모두 별도 판정

## 12. 테스트 구조

구현 파일과 동일 이름의 테스트를 우선 사용한다.

| 구현 | 테스트 |
|---|---|
| `api.py`, `inference.py` | `test_api.py` |
| `controller.py` | `test_controller.py` |
| `providers.py` | `test_providers.py` |
| `specialists.py` | `test_specialists.py` |
| `streaming.py` | `test_streaming.py` |
| `lifecycle.py` | `test_lifecycle.py` |
| `usage.py` | `test_usage.py` |
| admin | `test_admin_dashboard.py`, `test_api_keys.py` |
| evaluation | `test_*quality*`, `test_*noninferiority*` |
| SGLang | `test_isolated_sglang_*` |

표준 검증:

```bash
python -m pytest -q <focused test>
python -m pytest -q
python -m ruff check gateway/src tests scripts
python -m mypy --strict gateway/src
```

물리 검증은 별도 immutable run ID와 기존 결과 보존을 요구한다.

## 13. 안전한 개발 workflow

### 13.1 worktree 생성

```bash
cd /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent

git worktree add \
  -b auto/<layer>/<proposal-id> \
  /home/kotori9/code/MoE-MoA-<proposal-id> \
  dev
```

권장 layer:

- `api`
- `controller`
- `admin`
- `runtime`
- `evaluation`
- `storage`
- `observability`

### 13.2 한 작업의 순서

1. `AGENTS.md`와 관련 권위 문서를 읽는다.
2. 변경 대상 함수의 모든 caller를 `rg`로 찾는다.
3. 기존 공통 helper가 있는지 확인한다.
4. 한 책임의 최소 diff를 구현한다.
5. focused test를 실행한다.
6. 전체 pytest, Ruff, strict mypy를 실행한다.
7. 실제 측정이 필요한 경우 새 immutable epoch를 만든다.
8. `docs/VALIDATION.md`에 측정 사실만 기록한다.
9. auto branch를 review한다.
10. 검증된 commit만 dev에 통합한다.

### 13.3 수정 금지 대상

- 실행 중인 candidate worktree
- production worktree
- `main` 직접 개발
- 기존 validation result 덮어쓰기
- `data/validation/`
- 모델 weight
- credential 파일
- 승인 없는 systemd/production 변경

## 14. 병렬 개발 충돌 지도

| 작업 | 주요 파일 | 동시에 피할 작업 |
|---|---|---|
| Chat/Responses core | `api.py`, `inference.py`, `streaming.py` | API router 대규모 분리 |
| Controller orchestration | `controller.py`, `routing.py` | review/evidence 동시 분리 |
| Review/evidence | `controller.py`, `evidence.py` | orchestration 수정 |
| Specialist routing | `specialists.py`, `providers.py` | cache provider 수정 |
| Cache 계약 | `providers.py`, `controller.py`, `usage.py` | specialist routing |
| Admin canvas | 새 admin module, `admin_routes.py` | key dashboard 대규모 변경 |
| SQLite 경계 | `database.py`, `usage.py`, `state.py` | quota 기능 변경 |
| Evaluation refactor | `quality_matrix.py`, scripts | confirmatory run 실행 |
| Lifecycle 분리 | `lifecycle.py` | production lifecycle 변경 |

같은 행의 충돌 작업은 하나의 branch에서 순차 수행하거나 선행 branch가
dev에 통합된 뒤 시작한다.

## 15. 최신 단계별 실행 계획

### Phase A — 현재 runtime epoch 안정화

목표:

- v64/V162 end-to-end completion
- orchestration truncation/retry 0
- terminal validation evidence
- clean phase commit
- provider pinning과 usage 완전성

완료 증거:

- immutable V162 database와 workspace
- 전체 테스트 terminal verdict
- retry/failure 0
- local Executor structured output 분포

### Phase B — branch 및 baseline 정규화

1. 모든 branch/worktree/dirty diff snapshot 갱신
2. production deployed commit 재확인
3. 기능별 commit dependency graph 작성
4. 검증 완료 commit만 dev에 통합
5. release candidate를 dev에서 분기
6. main은 release 검증 이후 fast-forward 또는 reviewed merge

destructive reset과 전체 덮어쓰기는 금지한다.

### Phase C — 코드베이스 경계 회복

순서:

1. 평가 도구의 `runpy`와 전역 변경 제거
2. Chat/Responses 공통 core 완료
3. inference/admin/training router 분리
4. Controller orchestration 분리
5. Controller review/evidence/completion 분리
6. lifespan-owned HTTP client 통일
7. SQLite schema/quota 경계 분리
8. 실제 참조가 없는 legacy 삭제

각 단계는 순감축 또는 책임 이동이어야 하며 새 framework를 도입하지 않는다.

### Phase D — Prefix/cache

1. 고정 role policy
2. 고정 conversation history
3. 동적 plan
4. 동적 tool evidence
5. 동적 review context

위 순서로 message prefix를 구성한다.

측정:

- Executor/Specialist 각각 cold/warm TTFT
- gateway 반복 prefix
- runtime Radix hit
- provider cached token
- output/tool 동일성
- GPU/host memory/swap

### Phase E — 관리자 workflow

1. disabled WebSocket router
2. authenticated snapshot
3. cursor reconnect
4. bounded queue/backpressure
5. provider/model/routing provenance
6. 별도 AI summary
7. operator raw reveal와 감사
8. 90일 dry-run/apply retention
9. local/remote Ollama resource telemetry
10. 장애·느린 client 검증 후에만 활성화 승인

### Phase F — client 기능 panel

각 client에 신규 실작업 5개:

- atomic persistence
- DAG/concurrency
- webhook/security
- report/log processing
- rate limiting

기능 PASS와 Frontier 비열등성은 별도 판정한다.

### Phase G — sealed blind confirmation

1. protocol/model/fixture/scorer hash 봉인
2. blind repeated attempts
3. paired quality/speed bootstrap CI
4. cost와 reliability 판정
5. Coding 외 범주 평가
6. telemetry completeness audit

INCONCLUSIVE는 PASS가 아니다.

### Phase H — 장기·다중 client

- 실제 장기 Goal
- 계획 checkpoint
- reconnect
- context compaction
- cache 유지
- host/GPU memory와 swap
- Codex/OpenCode/Hermes 동시 요청
- local BUSY 시 remote fallback
- provider switch 없음

최종 계약에 10시간이 명시돼 있으므로 5시간 결과만으로 완료하지 않는다.

### Phase I — release와 production

1. release candidate 생성
2. isolated release 검증
3. rollback rehearsal
4. gateway-only exposure 검사
5. production canary
6. 배포 후 API/stream/tool/admin 검증
7. 별도 승인된 경우에만 legacy model 참조 감사
8. rollback 경로가 존재하는 미참조 모델만 삭제

## 16. 현재 알려진 미완료 항목

- Goal의 Gemma 31B 문구와 실제 26B 후보 불일치
- V162 최종 결과 미확정
- dev의 미커밋 통합 변경 정리 미완료
- Controller/API/lifecycle/quality matrix 대형 모듈 분리 미완료
- cache physical equivalence 미완료
- admin WebSocket 장애 게이트 미완료
- Codex/OpenCode/Hermes sealed 비열등성 미완료
- 200회 확증 평가 미완료
- 10시간 장기 작업 미완료
- release/canary/rollback 미완료

이 항목이 하나라도 남으면 merge, production 배포, 기존 모델 삭제, Goal
완료 선언을 하지 않는다.

