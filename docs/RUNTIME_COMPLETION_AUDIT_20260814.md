# Runtime Completion Audit — 2026-08-14

이 문서는 과거 completion 표시가 아니라 `dev@43826ccee`, candidate
`auto/audit/runtime-completion-20260814`, production `main@59bcb54e5`의 source,
test, SQLite와 실제 listener를 기준으로 한다. 세부 물리 수치와 실패 로그 분류는
`docs/VALIDATION.md`의 `Runtime completion 재감사 기준선` 이후 절이 권위다.

## 판정 기준

- `PHYSICALLY_VERIFIED`: 현재 production 또는 격리 candidate에서 전체 경로가 실제 요청으로 관측됨
- `IMPLEMENTED_NOT_DEPLOYED`: source/test와 격리 물리 증거는 있으나 main/production에 없음
- `PARTIALLY_WIRED`: 일부 단계가 빠졌거나 deterministic client gate가 실패함
- `DISABLED_BY_POLICY`: 구현은 있으나 현재 권위가 활성화를 금지함
- `DOCUMENT_ONLY`: 문서 계약만 있고 실행 경로 또는 자동 검사가 없음
- `DEAD_OR_SUPERSEDED`: 현재 public topology가 사용하지 않는 역사/호환 경로

한 기능에 여러 성격이 있으면 release를 막는 더 낮은 상태를 대표값으로 사용한다.

## 구현 matrix

| 기능 | 시작 상태 | candidate 상태 | route → runtime → provider/tool → persistence → client → test 근거와 남은 경계 |
| --- | --- | --- | --- |
| Chat/Responses common execution | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | `/v1/responses`가 동일 `chat()` core로 변환된다. Production authenticated Chat/Responses와 격리 raw/Codex smoke가 성공했고 protocol/tool/stream tests가 존재한다. |
| Codex/OpenCode/Hermes compatibility | `PARTIALLY_WIRED` | `PARTIALLY_WIRED` | 네 client smoke와 canonical launcher 정리는 성공했다. v6 OpenCode는 public/terminal/protocol gate를 회복했지만 hidden float validator가 실패했다. Codex의 유효한 post-fix replay, Hermes 3~5 task batch와 broader client matrix는 미실행이다. |
| ExecutionGraph | `PARTIALLY_WIRED` | `PARTIALLY_WIRED` | Compiler/runtime/store가 fan-out/join/retry/fallback/tool continuation/approval/checkpoint를 구현하고 production DB에 graph `164`, attempt `797`, checkpoint `1998`이 있다. Checked-in default는 `disabled`, production은 `shadow`; client control authority가 아니므로 완료가 아니다. |
| Role Context projection | `PARTIALLY_WIRED` | `IMPLEMENTED_NOT_DEPLOYED` | 시작 production invocation은 explicit provider token/drop reason이 없었다. Candidate는 deterministic priority selector와 byte/token/drop telemetry를 구현했다. v6 최종 candidate에서 Executor/Reasoner/Reviewer projection `10/1/4`, provider token 기록 `10/1/5`, drop `0`을 실제 호출까지 확인했다. |
| Canonical evidence persistence | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | Runtime snapshot/projection, session/event, tool execution과 Graph state가 SQLite에 durable 저장된다. Candidate는 기존 schema 안에서 context 전달량을 보강했지만 아직 production에는 없다. |
| Planner/Reviewer/Judge/Frontier routing | `PARTIALLY_WIRED` | `PARTIALLY_WIRED` | Production DB와 과거 canary에 모든 role이 있다. v6 remote Reviewer 5회와 rejection→Executor tool handoff 3회가 완료됐지만 마지막 Reviewer가 hidden defect를 놓친 코드를 잘못 승인했다. Checked-in specialist/Judge는 disabled이고 provider별 quality gate는 닫히지 않았다. |
| API-key isolation | `PARTIALLY_WIRED` | `IMPLEMENTED_NOT_DEPLOYED` | General/admin hash-only store와 cross-key isolation은 production 증거가 있다. Candidate는 short-TTL `evaluation` kind와 inference-only allowlist를 추가했다. Smoke 네 key와 v3/v6 key 모두 revoke 후 `401`, plaintext `0`, hash `64`를 확인했으나 main/production에는 없다. |
| Overflow Executor | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | OpenCode Go `deepseek-v4-flash` completion/tool continuation/stream/cancel/fairness/recovery/high-risk fail-closed 증거와 scheduler tests가 있다. Checked-in default는 정책상 disabled이고 production override만 enabled다. |
| Tool call과 continuation | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | Chat/Responses native function/custom tool, matching call/session, continuation lease, expiry와 bounded budget이 source/test/production canary에 연결된다. Executor만 client-visible tool authority를 가진다. |
| Streaming/cancellation/recovery | `PARTIALLY_WIRED` | `PARTIALLY_WIRED` | Core SSE translation, cancellation, partial EOF, loading wait와 session recovery가 test된다. v6 required-tool buffer는 stream complete/abort `10/0`, retry `3/3`, reconnect `0`으로 v3 protocol failure를 회복했지만 task hidden gate는 실패했고 다른 client replay는 남았다. |
| Dashboard/WebSocket | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | Cookie-scoped HTTP/WebSocket, cross-key redaction, Graph event/snapshot과 topology tests가 있다. 현재 production private session `204`, snapshot/runtime `200`, role `7`, Graph `shadow`, session delete `204`를 재확인했다. |
| Logging/trace | `PHYSICALLY_VERIFIED` | `PHYSICALLY_VERIFIED` | Production request/event/tool/stream/review/Judge 집계가 존재하고 raw secret/hidden reasoning 제외 계약이 test된다. Candidate context telemetry는 `IMPLEMENTED_NOT_DEPLOYED` 하위 항목이다. |
| Training candidate/weekly/retention | `DISABLED_BY_POLICY` | `DISABLED_BY_POLICY` | Separate store, sanitization, opt-out/tombstone/hold, dry-run retention과 packaging code/tests는 있다. 현재 권위는 physical gates 전 disable이다. Production override가 training/weekly를 enable한 것은 policy finding이며 현재 권위로 인정하지 않는다. |
| Deployment/rollback | `PHYSICALLY_VERIFIED` | `IMPLEMENTED_NOT_DEPLOYED` | Production은 clean `main@59bcb54e5`, gateway health `200`, rollback commit/script와 과거 rehearsal 증거가 있다. Candidate는 dev/main에 통합·배포되지 않았고 bounded canary/rollback rehearsal도 미실행이다. |
| CI/branch protection | `DOCUMENT_ONLY` | `IMPLEMENTED_NOT_DEPLOYED` | 시작 revision에는 workflow가 없었다. Candidate는 format/Ruff/strict mypy/full pytest/schema workflow를 추가했다. GitHub main/dev는 현재 모두 unprotected이고 workflow가 main/dev에 없으므로 protection 변경은 보류한다. |
| Retired model/client path | `DEAD_OR_SUPERSEDED` | `DEAD_OR_SUPERSEDED` | Public catalog는 `dgx-moa`, `dgx-moa-fast`만 노출한다. 실행 가능한 OpenCode validation launcher 세 개는 정리됐다. 내부 `MODEL_MODES`, schema와 historical tests에는 hidden `dgx-moa-agent`/`dgx-moa-orchestrated`가 남아 있어 참조·rollback 의존성 분류 후 제거가 필요하다. |
| Git/worktree normalization | `PARTIALLY_WIRED` | `PARTIALLY_WIRED` | 시작 branch `13`, worktree `10`, stash `5`; 고유 commit을 가진 branch가 있어 삭제하지 않았다. Candidate는 dev 기반 별도 worktree에서 clean commit으로 진행 중이다. 통합/폐기 판정과 human approval 전 장기 branch 두 개 상태가 아니다. |

## 현재 정책과 실제 runtime의 차이

Checked-in default는 Graph, specialist routing, remote Judge, scheduling, Loop Engineering,
Runtime Skills/Knowledge/Evolution, training, weekly, Dashboard와 lifecycle을 disabled로 둔다.
실제 production은 인증과 Dashboard를 포함해 Graph `shadow`, specialist/Judge/scheduling,
Loop Engineering, Runtime Skills/Knowledge/Evolution, training과 weekly를 enable한다.
이는 current repository policy와 충돌하며 배포 상태를 source 권위로 소급하지 않는다.

실제 production lifecycle은 현재 `disabled`와 empty unit map이다. 따라서 optional role의
fixed/adaptive on-demand loading이 현재 활성이라는 주장은 이번 물리 inspection으로 확인되지
않았다. Executor/Planner/Reviewer/Judge endpoint는 loopback 설정이지만 external Reasoner는
`100.90.167.128:11434`를 사용한다. 이 또한 loopback-only 문구와의 topology 차이로 보존하며
별도 승인 없이 network/systemd 구성을 변경하지 않는다.

## 크기와 정리 상태

동일한 tracked-file 기준으로 Python source는 시작/현재 모두 `50`, config `6`, script `53`이다.
Gateway Python LOC는 `35177 → 35505`로 `328` 증가했다. Candidate 전체 diff는 CI, tests와
물리 증거 문서를 포함하므로 아직 실질 순감축 조건을 만족하지 않는다. 새 framework, ORM,
broker, orchestration dependency는 추가하지 않았다.

## 현재 release 판정

`IN_PROGRESS`다. OpenCode v6는 review-correction protocol을 회복했지만 hidden validator와
Reviewer quality gate가 실패했다. Codex/Hermes/raw의 3~5 task batch, Graph control authority 여부, policy override 정리,
전체 회귀, dev integration, protected CI, bounded production canary와 rollback rehearsal이 남았다.
Merge, deploy, systemd/security topology 변경은 승인 전 수행하지 않는다.
