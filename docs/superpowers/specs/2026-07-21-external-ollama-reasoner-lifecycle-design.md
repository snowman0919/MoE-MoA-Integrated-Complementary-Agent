# External Ollama Reasoner and Lifecycle Recovery Design

Date: 2026-07-21
Status: pending user approval for implementation
Starting dev commit: `6204a1d`
Production reference commit: `c2a9af0`

## Goal

Enable a 실동 실행 전용 MoA reasoner on the already-open remote Ollama endpoint `http://192.168.0.197:11434` (model `Qwythos-v2-9B:Q5`) while keeping lifecycle-managed local models for `executor`, `planner`, and `reviewer`.

This must keep the existing `adaptive/fixed/observe` behavior for on-demand memory control:

- `planner`/`reviewer` should be lifecycle-managed.
- `reasoner` should be checked via the external Ollama health path and should not be started/stopped by local systemd.

## Why this change

The previous full lifecycle path required every required role to exist in `lifecycle_unit_map`; with an unmapped required role it returned `model_unavailable`, not matching the requirement to support external reasoner calls.

Systemd startup races were also observed when roles were already in `start-post` state, because `SystemdLifecycleDriver.start()` blocked and `status()` could only parse `active/inactive/failed`, so warm-start reconciliation could misclassify valid in-progress loads.

## Scope

In-scope:

- 한 개 신규 설정 필드의 도입: `lifecycle_control` for `ModelConfig` (`systemd` default, `external` optional).
- API lifecycle preflight logic:
  - fixed/adaptive 경로에서 관리 정책을 `systemd`/`external`으로 분기
  - `external` roles는 시스템드라이버 대신 헬스 체크로 준비 상태를 판정
  - required `external` role unavailable => HTTP 503 with 기존 `loading`/`unavailable` 메시지 형식으로 대응
- Systemd 드라이버 안정성 조치:
  - `status()`는 `activating`을 허용
  - `start()`는 non-blocking 호출(`systemctl --user start --no-block`)
  - 기존 로직의 `_load()`는 in-progress 상태를 즉시 `failed`로 바꾸지 않도록 재조정
- 모델/설정 반영:
  - `reasoner` 모델을 `Qwythos-v2-9B:Q5`로 교체
  - `planner`/`reviewer`는 기존 local role로 유지
- 테스트: 라이프사이클/모델/요청 경로 + 생성/운영 상태 보정

Out of scope:

- `systemd` 외 드라이버/스케줄러 아키텍처 재작성
- 신규 추론 파이프라인 규칙 전면 변경
- 모수(temperature/top_p 등) 튜닝

## Current-state assumptions

- `gateway` starts with `lifecycle_mode: adaptive` for production validation and `lifecycle_unit_map` containing `executor`, `planner`, `reviewer` only.
- `reasoner` is already defined in `config/models.yaml` and must remain optional for safety (or required only when orchestration asks for it).
- `192.168.0.197:11434/api/tags` currently returns `Qwythos-v2-9B:Q5`.

## Design

### 1) Model config: external-control intent

Add field to `ModelConfig`:

```python
lifecycle_control: Literal["systemd", "external"] = "systemd"
```

- default keeps existing behavior.
- `systemd` roles still require lifecycle-managed unit mapping.
- `external` roles are allowed to be absent from `lifecycle_unit_map`.

Validation rules:

- existing `validate_lifecycle_unit_map` remains unchanged for `systemd` roles.
- `Settings` validation remains unchanged; only additional checks are added for `ModelConfig` to keep backward compatibility.

### 2) Preflight role handling in fixed/adaptive request path

In request handling (`create_app` path), replace the current “all required roles must be in unit_map” assumption with per-role control policy:

- if role control is `systemd` and not in map -> unmanaged fallback (current behavior)
- if role control is `external`:
  - skip `ensure_ready()`.
  - run `lifecycle_health_probe(role)` to determine readiness.
  - if healthy and role is `required`, proceed as ready
  - if unhealthy:
    - required role → immediate `loading_response()`-style 503 path (model_loading), or unavailable path with proper code depending on health-state intent
    - optional role → degrade and continue

For request metrics, `role_states`, `degraded_roles`, `role_ready_at` should receive explicit values for `external` roles so usage rows and `/v1/model-status/{role}` remain consistent and redacted.

### 3) 모델 상태 저장소에 대한 외부 역할 표현

Add minimal API-facing semantics for `external` roles:

- store remains single source of role state and readiness timestamps.
- external roles use existing `LifecycleRecord` fields; state transitions are set via `reconcile` and probe checks (no systemd mutation).
- `model_status` should still report role rows even when not in `lifecycle_unit_map`, but control field should reflect non-local management.

### 4) Reconcile and scheduler behavior

Startup reconcile remains focused on managed roles only (`lifecycle_unit_map`) for mutation.

For `external` roles:

- `LifecycleCoordinator` may perform a non-mutating reconcile check (optional): probe health at startup and set record to `ready`/`cold`/`failed` for observability.
- no start/stop/lease mutation from scheduler/driver calls.

### 5) Systemd correctness for start-post race

In `SystemdLifecycleDriver` and lifecycle load loop:

- expand `DriverStatus` to include `activating` and map the `show` output accordingly.
- update load loop to treat `active` or `activating` as valid warm-up states before health check succeeds.
- change `start()` command from blocking start to `systemctl --user start --no-block ...`.

### 6) External reasoner runtime config

Update `config/models.yaml`:

- `reasoner`:
  - `base_url: http://192.168.0.197:11434`
  - `served_name: Qwythos-v2-9B:Q5`
  - `classification: external`
  - `revision: Q5`
  - keep `repository` and local `destination` placeholder to satisfy schema validation
  - add `lifecycle_control: external`

`planner`/`reviewer` remain unchanged except lifecycle unit map entries in deployment environment.

## Test and rollout plan

### Dev tests (repo)

- `test_lifecycle.py`
  - `SystemdLifecycleDriver` accepts `activating` in status.
  - `start()` emits `--no-block`.
  - reconcile and ensure-ready path with active->activating does not enter failed state.
- `test_api.py`
  - `reasoner` external required path returns 503 with load-style response when Ollama endpoint unreachable.
  - optional reasoner degrades correctly.
  - `/v1/model-status` includes external role with control metadata.
  - non-reasoner behavior unchanged.
- `test_config` + typing/build checks for new enum/default/backward compatibility.

### Production user-systemd validation path

After dev verification:

1. keep checked-in lifecycle mode disabled and `lifecycle_unit_map` empty in repository.
2. apply `.env.local` in production user-systemd worktree:
   - `DGX_MOA_LIFECYCLE_MODE=adaptive`
   - `DGX_MOA_LIFECYCLE_UNIT_MAP='{"executor":"dgx-moa-executor.service","planner":"dgx-moa-planner.service","reviewer":"dgx-moa-reviewer.service"}'`
3. restart gateway with role map and external reasoner.
4. run matrix:
   - generic/stream/orchestration request flow
   - planner/reviewer lifecycle load/unload
   - reasoner required path with external Ollama up/down
   - cold model unload/reload and load progress headers

## Acceptance gates

1. required `reasoner_mode: required` request succeeds only when Ollama health is good; otherwise returns deterministic retryable structured 503.
2. `planner`/`reviewer` can be lifecycle loaded/unloaded with non-drifted state.
3. `test_api` and `test_lifecycle` targeted coverage passes; no new public API behavior change for unmanaged non-external roles.
4. production cold-start and recovery do not fail due to `start-post` status mismatch.
5. 모든 요청은 sensitive 정보 없이 리턴되고, 기존 로그/trace redaction 룰을 유지.

## Rollback

- Roll back config by setting reasoner `lifecycle_control` to `systemd` and removing remote base/served_name override, then revert `.env.local` lifecycle env + restart gateway.
