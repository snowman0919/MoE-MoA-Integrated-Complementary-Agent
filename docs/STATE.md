# State

Updated: 2026-07-18

## Branch and deployment

- `main` is the reviewed production target and stable recursive control plane.
- `dev` is the integration branch; recursive experiments must use isolated
  `auto/<layer>/<proposal-id>` worktrees created from `dev`.
- The production runtime worktree is `/home/kotori9/dgx-moa-agent` on `main`.
  Development stays in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent`
  on `dev`.
- Promotion remains `dev` -> reviewed PR -> `main` fast-forward pull -> controlled
  gateway restart. Runtime services never execute from the development worktree.

## Runtime

- Gateway: authenticated direct tailnet TCP at `100.125.239.72:9000`.
- Model endpoints: loopback-only executor `8101`, planner `8102`, reviewer `8103`.
- Context limits are executor, planner, and reviewer `65536`.
- Development phase one exposes `dgx-moa-chat`, `dgx-moa-agent`, and
  `dgx-moa-orchestrated` through `/v1/models`. Chat and agent are executor-only;
  orchestration roles are selected deterministically.
- Complete SSE events are forwarded as they arrive with a single DONE. Streaming
  review is deferred; it does not buffer executor output. Capture and individual
  event bounds are each 1,000,000 bytes.
- Executor output defaults to `4096` tokens with a server cap of `16384`.
  `finish_reason=length` is preserved and recorded as truncation, not completion.
- Standard OpenAI request fields suffice. Project metadata and provenance headers
  remain optional, and errors use the typed OpenAI envelope.
- KV reservations, model selection, unit topology, and memory gates are unchanged.
- A configurable 10-second prestart memory-settle delay prevents reloads from
  racing unified-memory reclamation. The final resident restoration passed.
- These contracts are implemented on `dev` and passed isolated physical curl,
  OpenAI Python, HTTPX, OpenCode `1.17.18`, and Hermes Agent `0.18.2` checks in
  Task 9. The post-fix stream reached the client before executor completion and
  used no planner or reviewer. Production was not deployed or restarted.

## Validation baseline

- Current phase-one suite: `180 passed`, with the existing FastAPI TestClient
  deprecation warning; Ruff format/check, MyPy, shell syntax, and systemd unit
  verification pass. The repository trace-corpus audit is separately red:
  `4/10` sessions complete because six ignored legacy-v1 records shadow their
  v2 session IDs. This is recorded evidence, not a green all-gates claim.
- Isolated post-fix API validation advertised all three aliases at `65536`,
  preserved native tool-call identity and continuation, returned typed auth,
  model, request, and backend errors, and kept ordinary chat/agent state
  executor-only.
- For the exact Task 0 twenty-line prompt, downstream first byte arrived
  `0.213156919` seconds after acceptance and `6.693879185` seconds before
  executor completion, with HTTP `200` and one `[DONE]`. The corresponding
  direct-agent state recorded only the executor role.
- Fixed synthetic benchmark: `10/10`, success rate `1.0`, routes `3/6/1`
  fast/standard/escalation, tool calls per success `1.2`.
- Required real OpenCode staging: 10 sessions covering read `3`, small edit `3`,
  multi-file `2`, failure recovery `1`, bounded engineering `1`.
- Required-session outcomes: 6 completed and 4 explicitly failed on bounded
  timeout/validation. One earlier calibration failure is retained.
- Staging trajectories: 11/11 complete; review/blocked validation trajectories:
  2/2 complete; applicable mandatory trace completeness is `100%`.
- Updated reviewer boundary passed a full in-process API run against the real
  planner, executor, and reviewer: HTTP 200, structured rejection, phase
  `correction`, completion blocked.

## Stability evidence

- Bounded soak: `26867` seconds (`7h 27m 47s`), 5370 memory samples.
- Minimum observed `MemAvailable`: `20783300608` bytes; maximum
  `123198304256` bytes. Resident startup uses the operator-approved 5 GiB
  (`5368709120` bytes) gate as of 2026-07-13. The 64K resident profile runs
  executor, reviewer, and planner; VibeThinker remains optional and stopped.
- Soak exercised real OpenCode requests, idle intervals, gateway and resident
  restarts, tool continuation, review, explicit block, and trace archival.
- SQLite state errors: 0. Trace archive errors/degradations: 0.
- This is not a 24-hour stability result; 24-hour observation remains pending.

## Heavy Judge and Frontier

- Heavy Judge remains validated with its unchanged model, `4000000000`-byte KV
  reservation, 8192 context, structured accept verdict, and resident restoration.
  It was not rerun because Judge code/configuration did not change.
- Frontier Codex is enabled through separate OAuth profiles (`primary` and
  `secondary`). Each can be invoked independently with
  `scripts/codex-profile.sh test <profile>` or the existing
  `dgx-moa-codex-frontier@<profile>.service` template; its read-only sandbox
  and systemd hardening remain unchanged. Both stored OAuth refresh tokens
  were rejected on 2026-07-13, so each profile needs interactive re-login
  before it can run work.

## Known limitations

- The isolated Task 9 trace audit found `0/13` sessions complete: every trace
  lacked `session_ended` and `workspace_identity`, and most lacked task IDs.
  Phase-one client/stream behavior passed, but formal all-gates completion is
  not claimed while the repository and isolated trace audits exit nonzero.
- Multi-file and bounded-engineering staging tasks exceeded the 180-second
  harness bound; their failed traces are retained for later analysis.
- The 7.5-hour soak includes classified startup rollback incidents before the
  memory-settle fix; the final resident state is healthy with no active loop.
- Promotion still requires human review of PR #2 and a later main deployment.
- The overall runtime-reliability Goal also still requires usage statistics,
  lifecycle/adaptive unloading, loading progress, memory-mechanism study, a
  near-limit 64K request, extended client matrices, soak, remaining docs, push,
  and PR work.
