# Phase 2 Task 3 Report: Usage Integration and Protected Report

Date: 2026-07-18
Branch: `dev`
Base: `66af95c3baba2665492ec82a2f9fc1ebab266812`

## Scope completed

- The gateway lifespan creates `UsageStore` on the configured state database
  with the configured bounded statistics limits.
- Each accepted request receives a server UUIDv4 request ID and a process-private
  UUIDv5 session correlation. Raw client session IDs are not passed to usage
  storage.
- User-Agent is reduced to one of six allowlisted client classes and does not
  affect routing or request behavior.
- The Task 1 terminal finalizer now finalizes usage once for non-stream and
  stream success, disconnect/cancellation, stage timeout, post-state validation
  failure, and expected or unexpected backend failure.
- Non-stream and stream token counts are copied only from bounded reported
  integer usage fields. Messages, responses, tools, raw User-Agent, raw session
  IDs, authorization, and secrets are not copied into usage rows or reports.
- `GET /v1/admin/runtime-status` is disabled with 404 before authentication
  unless `admin_api_enabled=true`, then uses the existing bearer or auth-disabled
  loopback policy. The same flag-first dependency protects every admin route.
- Runtime status includes the safe last request, active count, request
  statistics, observed role states, null Task 7 adaptive timeout, cold starts,
  loading failures, and bounded lifecycle duration/memory samples.
- No lifecycle control, loading response, scheduler, or production configuration
  was added.

## TDD evidence

Baseline before Task 3 tests:

```text
uv run pytest tests/test_api.py tests/test_usage.py tests/test_streaming.py tests/test_trace_v2.py -q
105 passed, 1 warning
```

Initial RED command:

```text
uv run pytest tests/test_api.py tests/test_runtime_status.py tests/test_usage.py tests/test_streaming.py -q
```

The run produced 13 expected missing-feature failures before it was interrupted
for the safety incident below. After all admin tests were guarded against
profile execution, the same RED command completed with 35 failed and 79 passed.
Failures were the intended missing behaviors: no application usage store, no
client classifier, no stream token observation, no runtime usage report, and
admin flag ordering that returned 401/200 instead of disabled 404.

GREEN after the minimum implementation and one existing-stream-test root fix:

```text
uv run pytest tests/test_api.py tests/test_runtime_status.py tests/test_usage.py tests/test_streaming.py -q
114 passed, 1 warning
```

The intermediate GREEN run exposed that direct endpoint tests omit the ASGI
`headers` scope key. Six existing streaming tests failed because the new
User-Agent read raised before streaming setup. Guarding the header read made the
same focused suite pass without changing streaming behavior.

## Final seven gates

1. Focused pytest: 114 passed, one pre-existing Starlette/httpx deprecation
   warning.
2. MyPy: success, 27 source files checked.
3. Ruff format check: 51 files already formatted.
4. Ruff check: all checks passed.
5. Full pytest: 230 passed, one pre-existing Starlette/httpx deprecation
   warning.
6. Trace audit: 10 total, 10 complete, 0 incomplete, 0 legacy, 100.0% mandatory
   completeness.
7. `git diff --check`: clean.

## Content and security audit

- Integration sent unique prompt, response, tool, raw User-Agent, raw session,
  metadata-secret, and bearer sentinels. `SELECT * FROM request_usage`, the
  materialized usage record, and the admin report contained none of them.
- Existing UsageStore-only SQLite/WAL sentinel tests remain green and reject
  non-allowlisted category values before persistence.
- Runtime report omits the opaque session correlation as well as paths, unit
  names, commands, and credentials.
- Every admin endpoint is tested disabled with missing and valid bearer tokens.
  Admin tests monkeypatch `ProfileManager.switch`, `ProfileManager.transition`,
  and profile subprocess execution to raise before any external action. Runtime
  status command probes are faked.
- User-Agent is used only by `classify_client`; route classification still uses
  model, messages, tools, and public metadata exactly as before.

## Safety incident and restoration

The initial RED command inadvertently invoked the existing admin profile
handler because the test supplied valid authentication while demonstrating that
`admin_api_enabled=false` was bypassed. Gateway and executor were started. Main
stopped the exact DGX units and reset the executor failed marker. Final state was
restored inactive and clean. No later test was run until main explicitly cleared
the workspace; all subsequent admin tests used the profile-control tripwires
described above.

## Concerns

- The test environment emits the existing Starlette `TestClient` deprecation
  warning about httpx2; no new warning was introduced.
- Adaptive timeout and lifecycle actions intentionally remain absent until
  Tasks 4-8.
