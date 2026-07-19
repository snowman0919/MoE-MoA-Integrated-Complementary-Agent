# State

Updated: 2026-07-19

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
- Automated lifecycle contracts now cover persisted states, single-flight load,
  typed loading progress, content-free usage/decisions/samples, leases/guards,
  bounded idle policy, exact-unit full-stop unload, restart reconciliation,
  status filtering, and shutdown ownership. The canonical contract is
  `docs/MODEL_LIFECYCLE.md`.
- Checked-in lifecycle mode remains `disabled` with an empty unit map. Physical
  Task 10 used an isolated fixed-mode harness only; no production lifecycle
  setting changed. It physically passed cold single-flight, measured-shard
  progress, active/stream/continuation guards, ordered full-stop unload, memory
  return within host-snapshot noise, timeout, and one reload at 64K
  configuration.
- Phase 3 physically selected exact full transient-systemd stop/start and the
  unchanged executor baseline: context `65536`, `max_num_seqs=1`,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN. A later
  three-cycle run passed the complete short, long, native-tool, code, review,
  near-64K, teardown, and gateway-advertisement contract. This selection is not
  deployed or enabled in production.

## Phase 3 memory and topology decision

- Authoritative mechanism result:
  `/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms-resumed.json`, SHA-256
  `625b25afbadbb1e8ef42f95e836df627ec22e37c87e07301102eaaa6194b6af9`.
  Full stop was selected. Sleep level 1 returned only 47.12% of full-stop
  MemAvailable and failed PSS stability; sleep level 2 and live reset each
  failed their first exact post-wake/reset short check.
- Authoritative 64K candidate result:
  `/tmp/dgx-moa-phase3-7vfm7bzv/candidates-confirmed.json`, SHA-256
  `10f233b47acfb52e54ee41532963d68e38831e7337818d4335b57f3bc2eaad03`.
  Baseline was selected. FP8 and chunked prefill had no material PSS benefit,
  eager lost `612888576` bytes of matched MemAvailable beyond the noise band,
  CPU offload worsened PSS, KV offload was incompatible with the installed
  hybrid layout, and prefix-off was an exact no-op.
- Authoritative three-cycle result:
  `/tmp/dgx-moa-phase3-1vjxvw8w/selected.json`, SHA-256
  `fb2fc9261509acf4b51fad4b201b5210bd5a9bcb6c578006c45856e2692e7f9b`.
  Ready times were `938.3187154009938`, `270.0974161340855`, and
  `274.08552565216087` seconds. Each backend near-limit request reported
  `63786` prompt tokens; every exact PGID and unit-cgroup PSS/RSS was zero
  after stop.
- The contemporaneous checked-in record for the original three-role 64K
  resident ended with `18525147136` bytes MemAvailable after planner start; its
  raw artifact was unavailable to the final independent review. The isolated
  Task 10 executor-only row measured `65156329472` bytes warm-ready MemAvailable and
  `4532602880` bytes owned PSS; its initial cold snapshot was `120509042688`
  bytes and its best post-unload settle was `120564150272` bytes with owned
  PSS/RSS zero. These host snapshots are noisy comparisons, not GPU-byte
  measurements.
- The checked-in, undeployed resident target now requires gateway+executor only;
  planner, reviewer, and reasoner are optional and retain `PartOf` cleanup.
  On-demand loading still requires a separately reviewed fixed/adaptive
  deployment and validated unit map. Rollback restores the prior
  gateway+executor+planner+reviewer dependencies and prior readiness/stop
  arrays.
- The isolated five-minute Python gateway result is
  `/tmp/dgx-moa-phase3-gateway-nzacnu_v/gateway-probe.json`, SHA-256
  `4513ca3f6980f7fcfb81d7f7a360851325fcd7f90cddcb475f2612c17f2f6d62`.
  Peak PSS was `48741376` bytes, idle CPU `0.24998221036527596%`, and
  `/healthz` p99 `2.1657010074704885` ms. All Rust rejection gates passed, so
  no crate was created.

## Validation baseline

- Phase 3 serialized pre-commit publication gates: `533 passed`, one existing
  Starlette TestClient warning; Ruff format/check passed for 53 files; MyPy
  passed for 28 source files; user-unit verification and all shell syntax checks
  passed; the checked-in trace corpus remained 10/10 complete at 100.0%; and
  `git diff --check` passed.
- Earlier phase-two automated scheduling gate: `527 passed`; it remains the
  pre-physical historical baseline.
- Phase-two Task 10 gate after the tool-continuation compatibility fix:
  `531 passed`; Ruff format/check, MyPy for 28 source files, unit-file
  verification, shell syntax, checked-in trace audit 10/10, and
  `git diff --check` all passed.
- The isolated Task 10 physical matrix passed all required rows at dev commit
  `ee2d714`: 12/12 cold requests returned typed loading `503` with one start;
  measured-shard progress reached ready in about 944 seconds; real active,
  disconnected-stream, and forced-tool continuation guards blocked unload;
  optional stopped before the executor; reload reached ready in about 273
  seconds; success/disconnect/timeout trace roots each audited 1/1 complete.
  Sanitized retained traces contain placeholders rather than validation
  objectives, model output, or tool content. Production was not restarted,
  deployed, or modified.
- Current phase-one suite: `181 passed`, with the existing FastAPI TestClient
  deprecation warning. The final re-review gate matrix passed Ruff format/check,
  MyPy for 26 source files, shell syntax, systemd user-unit verification, and
  `git diff --check`. The repository trace-corpus command remained red at exit
  `1`: 4 of 10 sessions complete, with six `legacy_v1` records. The retained
  physical-client audit also exited `1` at 0 of 13 complete, and the CPU-only
  timeout audit exited `1` at 0 of 1 complete. This is recorded evidence, not a
  green all-gates claim.
- Final eight-command results were: pytest exit `0` with `181 passed, 1
  warning`; Ruff format exit `0` with 48 files already formatted; Ruff check
  exit `0`; MyPy exit `0` for 26 files; systemd verification exit `0`; all
  `scripts/*.sh` syntax checks exit `0`; repository trace audit exit `1` with
  the exact 4/10 result above; and `git diff --check` exit `0`.
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
  The later timeout trace had no missing fields but lacked `session_ended`, so
  its audit was `0/1`. Phase-one client/stream behavior passed, but formal
  Task 9 all-gates completion was not claimed. The current checked-in corpus and
  new Task 10 success/disconnect/timeout traces all audit at 100%; the retained
  historical Task 9 roots are unchanged evidence.
- Multi-file and bounded-engineering staging tasks exceeded the 180-second
  harness bound; their failed traces are retained for later analysis.
- The 7.5-hour soak includes classified startup rollback incidents before the
  memory-settle fix; the final resident state is healthy with no active loop.
- Promotion still requires human review of PR #2 and a later main deployment.
- The overall runtime-reliability Goal still requires the Phase 4 extended
  client matrices and soak, followed by the separately approved push/PR
  workflow. Phase 3 evidence does not authorize deployment.
