# Dynamic MoA Pilot Context Epoch — 2026-08-13

## 계보와 범위

- 부모 runtime epoch: `pilot-v1-transition-20260812`
- 동결 계획 SHA-256: `41e16b4f2fb8f442d8da3065ba53eacb317fc9a68333e63c02253784bcf1a4bd`
- 병합 전 production 계보: `6f879428913a5bf50bb469f81349b8ee56f2c18f`
- 배포 release: `ffdf006a4deb429d7902c42bb9165d9b83729ab0`
- 상태: `PILOT_ACTIVE`; 아래 장기 high-risk 종료 결함 때문에 `COMPLETE`가 아니다.

이 epoch는 동결 계획을 수정하지 않는다. Runtime-owned Role Context Package v1,
역할별 budget, 실제 production 배포, 7역할 availability, Graph fan-out/fan-in,
rollback/redeploy를 추가 검증한다.

## Git 및 증거 보존

`dev`와 production checkout은 모두 clean이며 같은 release를 가리킨다. 병합 전
dirty 상태는 `stash@{0}`의 `goal-normalization-preserve-20260813-pre-rc-ff`로
보존했다. 충돌 가능 JSON 5개는 삭제하지 않고
`/home/kotori9/code/.moa-evidence-preservation/20260813-pre-rc-ff`에 보존했다.

남은 worktree는 삭제 대상이 아니다. `observability-eval`은 관측 검증,
`sglang-gemma4`와 `sglang-topology-integration`은 candidate-B 반증,
`IMP-2026-0001`은 controller 실험, `pilot-v1-release-candidate`와 detached
write/long-run worktree는 재현 가능한 Pilot 증거다. 소유자는 operator이며 새
production 변경의 source로 사용하지 않는다.

## Role Context Package v1

Reasoner, Planner, Frontier A는 동일 immutable pre-dispatch snapshot hash
`5d8f1936346b87f8db27b816a3f8bfb832579ba292edad1bd6418119a08283b2`에서
서로의 출력을 보지 않고 fan-out했다. 각각 3,153/3,150/3,160 bytes를 받았고
budget은 98,304/81,920/196,608 bytes였다. 세 기여가 끝난 뒤 Runtime은 별도
fan-in snapshot `d21cb8a0c94f9f95ef48bf23322cc3027d1814df066bd3ac9d08a50538b04db1`을
만들어 Executor에 12,401/536,576 bytes를 투영했다. 원 objective, 요청,
constraints, acceptance는 immutable이며 초과 시 discretionary evidence와 기여를
결정적으로 제외하고 excluded ID를 기록한다.

직접 증거 A/B의 authoritative artifact는
`data/diagnostics/role-context-ab/20260813-v4/result.json`, SHA-256
`71fe99be0368154400af606d02b51743d4827ebf39e98385100b9c35faa5a829`다.
direct package는 Planner correction 1→2, Reviewer critical recall false→true,
missed criteria 3→1, completion approval/verified completion false→true를 기록했다.
양쪽 repair iteration은 1이었다. Frontier criterion recall은 2→1로 악화되어
후속 품질 항목으로 남긴다. v1은 초기 측정, v2/v3는 scoring assertion 결함으로
비권위 보존하고 v4만 qualification 판정에 사용한다.

## Production 배포와 물리 증거

validation drop-in은 `.disabled-20260813`으로 복구 가능하게 보존했고 실제
`main` checkout의 fixed `dgx-moa-gateway.service`를 실행한다. gateway만
`0.0.0.0:9000`에 bind하며 Candidate A는 `127.0.0.1:19301`에만 남는다.
인증 없는 Chat은 401, 같은 요청의 유효 key 호출은 200이었다. 응답 content
SHA-256은 `3b0e25379afadc20a946147df5203e736ff6a47d2ff954df1e5b5c5fd6609f74`이고
내부 `provider_provenance`는 client에 노출되지 않았다.

첫 실요청은 production DB의 stale local Planner `READY` 때문에 502를 냈다.
`ffdf006a4`는 local context/readiness probe를 증명하지 못하면 dispatch 전에
remote로 route하고 stale lifecycle state를 failed로 전환한다. 같은 요청 재시도는
Reasoner Qwythos, Planner DeepSeek V4 Pro, Frontier A GPT-5.6-Sol을 fan-out하고
HTTP 200으로 완료됐다. Frontier A는 Codex OAuth `primary`, prompt 15,819,
completion 966, latency 24,569.716 ms였다.

Graph `graph_d63241f082b8f72ecadf820e`는 `complex-v1` 10 nodes/26 edges이며
Reasoner `local_qwythos`, Planner `opencode_go`, Frontier A `codex_oauth`,
Executor `local_mistral`, JOIN/CHECKPOINT/FINALIZE를 포함한 10 attempts가 모두
`SUCCEEDED`, checkpoint 21개였다.

fresh 7-role probe는 Reasoner `Qwythos-v2-9B:Q4`, Planner
`deepseek-v4-pro`, Frontier A `gpt-5.6-sol`/`xhigh`, Executor pinned Mistral
NVFP4, Reviewer `deepseek-v4-flash`, Judge `kimi-k3`, Frontier B
`anthropic/claude-opus-5`를 모두 available로 확인했다. remote 5-role artifact는
`/home/kotori9/dgx-moa-agent/data/diagnostics/runtime-roles/production-20260813-v2.json`,
SHA-256 `06abb808412bcb446f016ee7c4a37b1da2b2963931a83338acab68025e2c8fe3`다.
Dashboard는 shadow mode, 네 static template, deterministic compiler,
`runtime_mutation=false`를 보고했다.

## Rollback과 미통과 항목

서비스를 drain한 뒤 이전 release `88f553dec8245d3456270f912b6bf79b0f3ec071`로
실제 checkout/restart했다. rollback PID `2985632`에서 인증 fast canary가
통과했고, 다시 `ffdf006a4`로 redeploy한 PID `2985816`에서도 같은 11-byte
응답 SHA-256 `c15847368d9312ee04095d81d111ea546353f5f5da1448befc39942ad4085e30`을
반환했다. 현재 service는 active, restart 0이다.

의도적으로 불충분한 high-risk 인증 변경안은 Reviewer가 거부했다. Judge
`kimi-k3`와 Frontier B 호출은 완료됐지만 correction/re-review가 300초 client
제한을 넘었고 최종 Graph는 `execution_graph_shadow_failed(stage=finalize)`와
`session_ended(status=failed)`로 닫혔다. false approval은 없었으나 장기
non-stream 종료/latency 계약은 미통과다. 따라서 일반 Pilot은 active지만
`PRODUCTION_BETA`, `STABLE`, Goal `complete`는 선언하지 않는다.

전체 source gate는 Ruff/format, strict mypy 50 files, pytest `1087 passed`를
통과했다.
