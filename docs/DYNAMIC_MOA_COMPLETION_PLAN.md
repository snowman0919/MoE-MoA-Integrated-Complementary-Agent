# Dynamic MoA Production Completion Plan

이 문서는 `protocol_epoch=dynamic-moa-v3-20260808`의 동결 실행 계약이다.
`dynamic-moa-v2-20260808`은
`docs/DYNAMIC_MOA_COMPLETION_PLAN_EPOCH_2_20260808.md`에 exact bytes로 보존하며,
그 문서의 topology, transport, scheduling, Dashboard, data, evaluation, release와 safety
계약을 모두 승계한다. 이 문서는 사용자 추가 목표인 `Execution Graph Engineering`에 따른
protocol delta와 재검증 범위를 정의한다. v1/v2/v3 결과를 같은 confidence interval이나
production gate에 혼합하지 않는다.

Exact file SHA-256은 self-reference를 피하기 위해
`docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256`에만 기록한다. 이 계획 또는 평가 protocol이
실질적으로 바뀌면 기존 결과를 보존한 채 새 epoch를 만든다.

## 1. Freeze metadata

```yaml
protocol_epoch: dynamic-moa-v3-20260808
created_at: 2026-08-08T16:00:00+09:00
starting_dev_commit: f2c20a78d814ef9cd59424f372fa42d503874054
starting_main_commit: 396e0458f25977293281b953d2c804cf5b689970
starting_production_commit: 396e0458f25977293281b953d2c804cf5b689970
parent_epoch: dynamic-moa-v2-20260808
parent_plan_hash: bd69063dbd20891349ea459b6ecff4a6cb53ac17f88359d1df47e1b6fb29a668
plan_hash_algorithm: SHA-256 over exact bytes of this file
plan_hash_location: docs/DYNAMIC_MOA_COMPLETION_PLAN.md.sha256
source_goal: /home/kotori9/.codex/attachments/b509d274-1917-40d4-98a1-052adb7ed6d5/pasted-text-1.txt plus user-added Execution Graph Engineering objective
```

Preflight, evidence preservation와 model cleanup은 parent epoch에서 완료됐고 새 목표에도
유효하다. 관련 authoritative artifacts:

- `docs/DYNAMIC_MOA_EVIDENCE_PRESERVATION_20260808.md`
- `docs/MODEL_INVENTORY_DYNAMIC_MOA_V2_20260808.md`
- `docs/DYNAMIC_MOA_COMPLETION_PLAN_EPOCH_1_RECOVERY.md`

## 2. Runtime ownership and non-goals

- Runtime Policy가 graph template, allowed mutation, budget, risk와 approval authority를 소유한다.
- LLM은 objective/plan/review artifact를 제안할 수 있으나 임의 graph structure, unbounded node,
  edge, cycle 또는 mutation 권한을 생성·변경하지 못한다.
- Executor만 tools, repository mutation, routing authority, loop control과 client-visible final
  synthesis를 소유한다.
- Execution Graph와 Evidence Graph를 합치지 않는다. execution node/attempt가 생성·검증·반박한
  Evidence node ID를 reference한다.
- LangGraph, workflow framework, message broker, distributed scheduler, ORM을 추가하지 않는다.
  stdlib, Pydantic, SQLite와 기존 event/state/provider primitives를 재사용한다.
- 공개 Chat/Responses API, tool semantics, streaming terminal contract, failure taxonomy,
  API-key isolation, audit provenance, trace v3 reader와 역사적 evidence를 보존한다.

## 3. Deterministic Graph Compiler

Compiler 입력은 request objective/class, policy version, complexity, risk, API-key scheduling
snapshot, role/provider readiness, budgets, deadlines, current active state와 checkpoint다.
출력은 allowlisted template와 typed nodes/edges로 구성된 immutable execution plan이다.

Compiler는 순수·결정론적이어야 한다. 동일 compiler version, normalized input와 policy version은
동일 graph hash를 만든다. graph record:

```text
graph_id
graph_schema_version
compiler_version
policy_version
request_id
api_key_id
template_id
input_hash
graph_hash
created_at
deadline
budgets
entry_nodes
terminal_nodes
```

허용 node type:

```text
CLASSIFY
REASONER
PLANNER
FRONTIER_A
EXECUTOR_SELECT
EXECUTOR
TOOL
TEST
REVIEWER
JUDGE
FRONTIER_B
JOIN
POLICY_GATE
HUMAN_APPROVAL
CHECKPOINT
FINALIZE
```

허용 edge type:

```text
DEPENDS_ON
ON_SUCCESS
ON_FAILURE
ON_RETRYABLE_FAILURE
ON_FINDING
ON_APPROVAL
ON_REJECTION
ON_BUDGET
ON_PROGRESS
ON_NO_PROGRESS
ON_FALLBACK
ON_CHECKPOINT
```

Tier templates는 parent plan을 graph로 정규화한다.

- Simple: `CLASSIFY → EXECUTOR_SELECT → EXECUTOR → optional TOOL/TEST → FINALIZE`.
- Engineering: `CLASSIFY → fan-out(PLANNER, FRONTIER_A, read-only EXECUTOR) → JOIN →
  EXECUTOR → TOOL/TEST → conditional REVIEWER → FINALIZE`.
- Complex/Research: optional REASONER + PLANNER + FRONTIER_A + read-only evidence fan-out → JOIN →
  EXECUTOR → TOOL/TEST → optional Frontier evidence-delta → REVIEWER → FINALIZE.
- Critical: Planner + Frontier A + optional Reasoner → JOIN → Executor → tools/tests → Reviewer →
  bounded repair cycle → Judge → exceptional Frontier B → Finalize.

`EXECUTOR_SELECT`는 lease/scheduling snapshot으로 local Mistral 또는 OpenCode Go
`deepseek-v4-flash`를 결정한다. 선택된 provider는 turn 중 고정한다.

## 4. Graph runtime

Runtime은 dependency가 충족된 ready nodes를 가능한 한 병렬 실행하고 fan-in JOIN을 명시한다.
각 attempt는 다음을 durable하게 기록한다.

```text
node_id
attempt_id
node_type
role
provider
model
state
parent_node_ids
parallel_group_id
selected_incoming_edge
available_outgoing_edges
started_at
ended_at
deadline
latency_ms
token_usage
cached_tokens
cost_usd
failure_code
failure_fingerprint
progress_evidence_ids
generated_evidence_ids
validated_evidence_ids
contradicted_evidence_ids
public_output_ref
checkpoint_id
```

Node state는 `QUEUED|DISPATCHING|RUNNING|STREAMING|WAITING_TOOL|WAITING_DEPENDENCY|
WAITING_APPROVAL|RETRYING|FALLBACK|SUCCEEDED|DEGRADED|FAILED|CANCELLED|SKIPPED`다.

- dependency, absolute deadline, provider pinning, per-role/request budgets와 cancellation을 보존한다.
- retry는 동일 node의 새 attempt이며 typed transient failure에만 parent plan 규칙대로 최대 2회.
- fallback은 새 provider attempt와 `ON_FALLBACK` edge로 기록하며 기존 attempt를 덮어쓰지 않는다.
- partial rerun은 invalidated node와 descendants만 재실행하고 unaffected successful node artifact를
  graph hash/artifact hash 검증 후 재사용한다.
- terminal event와 Finalize는 exactly once다.
- Dashboard/event consumer failure는 graph execution을 block하지 않는다.

## 5. Bounded cycles and repair

Cycle은 template에 선언된 repair subgraph만 허용한다.

```text
REVIEWER/JUDGE finding → EXECUTOR repair → TOOL/TEST → REVIEWER
```

- `max_traversals`와 wall/token/tool/role-call budgets를 compile time에 고정한다.
- 각 traversal은 이전 traversal 이후의 새로운 test result, diff hash, finding resolution 또는
  Evidence node를 `progress_evidence_ids`로 증명해야 한다.
- 동일 failure fingerprint가 configured limit에 도달하거나 progress가 없으면
  `ON_NO_PROGRESS`로 fail-closed terminal/checkpoint를 선택한다.
- LLM output만으로 progress를 인정하지 않는다.
- recursive agent-to-agent cycle과 runtime graph mutation은 구조적으로 거부한다.

기존 Loop Engineering의 budget, duplicate fingerprint, no-progress, approval과 termination
semantics를 Graph Runtime의 단일 cycle mechanism으로 이전한다. parity evidence가 확보되기 전
기존 경로를 삭제하지 않는다.

## 6. Checkpoint and compact active state

장기 작업은 전체 history를 매 turn 직렬화하지 않는다. CHECKPOINT node는 parent plan의
active/durable state 분리를 graph 수준으로 확장한다.

```text
checkpoint_id
graph_id
graph_hash
parent_checkpoint_id
completed_node_ids
active_node_ids
pending_node_ids
selected_edges
available_edges
provider_pins
remaining_budgets
failure_fingerprints
progress_evidence_ids
active_state_object_ref
event_cursor
snapshot_hash
size_before
size_after
reason
```

Resume은 compiler/schema/policy/artifact hashes를 검증하고 pending graph에서 이어간다.
불일치하면 silent resume하지 않고 typed incompatibility로 fail-closed/recompile decision을
기록한다. durable history와 이전 checkpoint는 삭제하지 않는다.

## 7. Evidence Graph boundary

Evidence Graph는 claim/evidence trust와 support/contradiction 관계의 authority를 유지한다.
Execution Graph는 control flow authority다. 결합은 ID reference뿐이다.

- Execution node가 Evidence node를 생성할 때 `generated_evidence_ids`를 기록한다.
- TEST/REVIEWER/JUDGE가 검증·반박한 ID를 별도 field에 기록한다.
- Evidence Graph edge semantics나 trace v3 reader를 execution edge로 재사용하지 않는다.
- graph completion은 acceptance criteria에 연결된 verified Evidence node가 없으면 final success를
  선언할 수 없다.

## 8. API-key scheduling graph input

Parent plan의 same-key queue/cross-key Flash/fairness/high-risk policy는 Graph Compiler 입력과
`EXECUTOR_SELECT`/`POLICY_GATE` node로 구현한다.

- scheduling snapshot에는 raw key가 아닌 `api_key_id`, lease owner, queue position,
  round-robin epoch, risk와 readiness만 포함한다.
- local/Flash 선택, queue/fallback reason과 provider pin은 graph/node provenance에 남긴다.
- high-risk overflow는 explicit policy path가 없으면 `HUMAN_APPROVAL` 또는 fail-closed다.
- continuation은 기존 turn provider pin과 graph identity를 검증한다.

## 9. Dashboard projection

Dashboard는 별도 workflow를 추론하지 않고 persisted Execution Graph와 node attempts를 직접
REST snapshot/`WS /admin/ws`로 투영한다.

- graph topology, fan-out/fan-in, ready/running/join, retry/fallback/cycle/checkpoint를 표시한다.
- node Inspector는 owner-scoped prompt, public live output, tool/test stream, final output,
  Evidence references, latency/cost/usage/failure를 표시한다.
- WebSocket event는 `graph_id`, `node_id`, `attempt_id`, `edge_id`, `parallel_group_id`,
  `parent_node_ids`를 포함한다.
- monotonic seq/replay/`RESYNC_REQUIRED`, reliable workflow terminal, lossy telemetry,
  batching/backpressure/slow-client disconnect는 parent plan을 따른다.
- raw key/credential/hidden reasoning/private other-key content를 저장·전송하지 않는다.

## 10. Logging, training, and Skill candidates

Training provenance에 다음을 추가한다.

```text
graph_schema_version
compiler_version
template_id
graph_state_before
available_edges
selected_edge
node_attempt_result
failure_fingerprint
progress_evidence_ids
latency
cost
quality_delta
checkpoint_resume_result
partial_rerun_result
```

반복 성공 subgraph는 자동 promotion authority가 아니라 governed Skill candidate 입력이다.
candidate는 bounded connected subgraph, success count, task/risk scope, failure distribution,
quality/cost delta, privacy/license/opt-out와 source graph IDs를 가진다. 기존 isolated evaluation,
Executor-evidenced helpful canary와 explicit promotion approval 없이는 Skill로 승격하지 않는다.

## 11. Refactor and deletion gate

첫 구현은 기존 Controller orchestration을 감싸는 별도 duplicate framework가 아니라,
Controller의 실제 routing/parallel/fallback/retry/loop/checkpoint 분기를 한 개씩 Graph Compiler와
Runtime으로 이전한다. migration 동안 public API와 provider helpers는 재사용한다.

기존 branch 제거 조건:

- graph/non-graph contract parity tests.
- same request의 selected roles/providers/tools/terminal semantics parity.
- fault injection에서 retry/fallback/cancellation/approval parity.
- Controller source/branch count의 measured 순감축.
- no hidden duplicate execution path.
- rollback flag로 기존 validated path 복구 가능.

이 조건 전에는 기존 분기를 삭제하지 않고 Graph Engine을 production default로 만들지 않는다.

## 12. Validation delta

Parent epoch의 모든 static/integration/client/evaluation/canary/rollback gate를 v3에서 다시
통과해야 한다. 추가 필수 gate:

- deterministic compilation: same input/policy → same graph hash.
- allowlisted nodes/edges only; arbitrary/cyclic LLM graph rejection.
- fan-out concurrency와 JOIN dependency correctness.
- provider pinning, deadline, budgets와 cancellation propagation.
- transient retry와 conditional fallback attempt provenance.
- repair `max_traversals`, duplicate fingerprint, no-progress termination.
- human approval pause/resume/audit.
- graph checkpoint, compaction, process restart resume.
- partial rerun은 invalidated descendants만 실행.
- Execution/Evidence Graph ID boundary and acceptance-proof gate.
- API-key fairness/cross-key overflow/high-risk path under concurrent clients.
- Dashboard topology/node attempt WebSocket truth, reconnect/backpressure/owner scope.
- training record graph state/edges/results and Skill-candidate governance.
- Controller before/after lines, branches, wrappers와 execution-path count 순감축.

Physical comparison은 legacy Controller baseline과 Graph Engine candidate를 동일 request/client/
failure injection에서 paired 실행해 task success, false completion, duplicate calls, verified
completion time, repair count, checkpoint resume, observability completeness와 resource overhead를
기록한다. Graph Engine이 병렬성·부분 재실행·장기 안정성·관측성·재현성을 개선했다는 evidence가
없으면 production 승격하지 않는다.

## 13. Execution order delta

1. v3 plan/hash freeze.
2. Frontier argv/E2BIG hotfix.
3. immutable graph schema와 deterministic compiler.
4. graph runtime, attempt persistence와 bounded cycles.
5. Controller branch migration + common execution core 순감축.
6. checkpoint/compaction/partial rerun.
7. API-key scheduler/lease/Flash를 graph input으로 연결.
8. Dashboard direct projection.
9. graph training/Skill-candidate provenance.
10. parent epoch의 model/provider/client/evaluation/long-horizon/release gates 전체 재실행.

Merge/deploy/security/systemd topology/training export/model retirement/branch deletion은 parent
계획과 `AGENTS.md`의 human approval gate를 그대로 따른다. 최종 상태는 모든 parent+v3 필수
gate가 같은 epoch에서 통과한 경우 `COMPLETE`, 아니면 `BLOCKED`다.
