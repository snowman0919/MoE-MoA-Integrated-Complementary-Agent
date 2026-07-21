# State

Updated: 2026-07-22

## Dynamic MoA production status

| Capability | Designed | Implemented on `dev` | Unit-tested | Physically validated | Production-enabled |
| --- | --- | --- | --- | --- | --- |
| `dgx-moa` Reasoner + Executor core | yes | yes | yes | production yes | yes |
| Dynamic Planner/Reviewer routing | yes | yes | yes | Planner production; Reviewer isolated | yes |
| Codex OAuth Frontier modes/fallback | yes | yes | yes | production architecture yes | yes |
| Heavy Judge adjudication | yes | yes | yes | isolated exclusive-profile yes | deployed, operator-only |
| Evidence graph and per-agent trace | yes | yes | yes | production yes | yes |
| Multiple API tokens and per-token usage | yes | yes | yes | production yes | yes |
| Codex Responses text/function/custom tool loop | yes | yes | yes | production yes | yes |
| Runtime model invocation-rate CSV | yes | yes | yes | production live clients | yes |
| Bounded Loop Engineering Phase A + action-boundary B | yes | yes | yes | isolated success/no-progress/duplicate | no |
| Runtime Skills Phase C foundation | yes | yes | yes | isolated governed lifecycle | no |
| Declarative Policy Phase D foundation | yes | yes | yes | isolated redaction | no |
| Typed Evidence Graph Phase E foundation | yes | yes | yes | isolated replay validation | no |
| Discord/Telegram Live Observation Phase E | yes | yes | yes | unit only | no |
| Privacy-aware Training Collection Phase F | yes | yes | yes | isolated role/loop/preference archive | no |
| Weekly Skill/Data Packaging Phase G | yes | yes | yes | isolated real 7z; scheduler/provider pending | no |
| Execution Replay Phase H foundation | yes | yes | yes | isolated exact loop replay | no |
| Fixed label-free Goal metrics endpoint | yes | yes | yes | production yes | yes |

This table is the current authority. Later sections preserve historical Phase
1–4 evidence and must not be read as later production evidence. Checked-in safe
defaults still have lifecycle control and Frontier disabled with an empty unit
map. The production-only 0600 environment overrides authentication, Frontier,
and the reviewed adaptive Executor/Planner/Reviewer unit map.

## Branch and deployment

- `main` is the reviewed production target and stable recursive control plane.
- `dev` is the integration branch; recursive experiments must use isolated
  `auto/<layer>/<proposal-id>` worktrees created from `dev`.
- The production runtime worktree is `/home/kotori9/dgx-moa-agent` on `main`.
  Development stays in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent`
  on `dev`.
- Promotion remains `dev` -> reviewed PR -> `main` fast-forward pull -> controlled
  gateway restart. Runtime services never execute from the development worktree.

## Production enablement — 2026-07-22

- PRs 15, 16, and 17 were reviewed, merged to `main`, and fast-forwarded into
  the production worktree. The gateway was restarted under the reviewed
  production environment; model endpoints remained loopback-only and only the
  authenticated gateway remained on the tailnet address.
- Authentication is enabled with non-secret usage IDs `legacy`, `opencode`,
  `hermes`, and `operator`. New client secrets are held outside Git in a 0600
  operator file; the legacy value remains accepted for existing Codex clients.
  OpenCode and Hermes local configs use their distinct credentials.
- Codex OAuth Frontier is enabled with ordered `primary`, `secondary` profiles.
  Primary remained usage-limited, and a production architecture collaboration
  physically completed through `secondary` with the selected profile persisted
  in task evidence.
- Production lifecycle mode is `adaptive` for Executor, Planner, and Reviewer.
  Executor idle unload remains disabled. The external Ollama Reasoner reports
  `control=external`; Judge remains outside the adaptive unit map and available
  only through the separately controlled exclusive profile.
- The post-deployment state had automation enabled with zero retained failures,
  Executor and external Reasoner ready, Planner generation 10 ready after the
  architecture smoke, Reviewer cold/inactive, Judge inactive, and the resident
  target active. Planner remains subject to its normal minimum-residency and
  adaptive idle-unload policy.
- PR `#34` deployed the governed runtime foundations and production invocation
  CSV as `main@979a608`. Codex, OpenCode, Hermes, Chat tool continuation, Chat
  streaming, and Responses terminal streaming passed against production. The
  new autonomous/observation/training/weekly capabilities remain deployed but
  disabled; deployment did not authorize their gates.

## Runtime

- Gateway: authenticated direct tailnet TCP at `100.125.239.72:9000`.
- Model endpoints: loopback-only executor `8101`, planner `8102`, reviewer `8103`.
- Context limits are executor, planner, and reviewer `65536`.
- The deployed `main` runtime exposes `dgx-moa`, `dgx-moa-fast`,
  `dgx-moa-agent`, and `dgx-moa-orchestrated`. `dgx-moa` is the primary
  Reasoner + Executor core; `dgx-moa-fast` is the explicitly Executor-only
  compatibility alias. The orchestrated profile combines deterministic safety
  policy with a structured Executor routing decision.
- Codex utility requests using the measured `gpt-5.6-luna` slug are accepted as
  unadvertised `dgx-moa-fast` compatibility traffic. They never invoke Frontier;
  Frontier remains the separate Codex OAuth collaboration path.
- Chat SSE forwarding preserves complete events and a single DONE. The Responses
  adapter buffers at most 1,000,000 characters until it can distinguish a final
  answer from a tool-call preamble; tool preambles and failed streams are never
  exposed. A valid upstream terminal marker is required before completion.
- Deployed source resolves a failed MCP local-path observation after a later
  successful native file/shell observation, retries genuine optional-role
  loading within the existing Responses stream, and writes atomic all-time and
  trailing-hour model invocation rates to
  `<gateway.run_dir>/model-invocation-rates.csv`. Generic HTTP, Codex, OpenCode,
  and Hermes plus the primary Reasoner path physically produced six Executor
  records and one exact `Qwythos-v2-9B:Q4` Reasoner record through an isolated
  development gateway. Production clients now physically update the same CSV.
- Deployed source contains disabled Phase A state and Phase B action
  admission. Evidence-linked criteria, iterations, role/tool/token/known-cost/
  wall-time budgets, progress evidence allowlisting, stable repeated-failure
  policy, and explicit termination reasons are unit-tested. An isolated physical
  run exercised success, no-progress, and duplicate-failure termination;
  production stays disabled.
- Deployed source also contains a disabled runtime Skill registry with
  immutable versions, bounded active-only retrieval, Executor-only activation,
  structured recurring-pattern drafts, isolated multi-gate candidate evaluation,
  Executor-evidenced canaries, governed versioned lifecycle changes, separate
  metrics, evidence-gated promotion/rollback, and verified pack hashes. An
  isolated physical run exercised draft generation, every evaluation gate, an
  Executor-evidenced helpful canary, explicit promotion, and rollback. No
  production registry or canary was created.
- A disabled declarative policy engine records versioned, hashed decisions and
  enforces request denial, approval requirements, role requirements, loop
  limits, and per-tool deny globs. Policy field redaction covers evidence,
  decisions, tool results, normalized executions, and persisted Reasoner,
  Planner, Reviewer, Frontier, and Judge artifacts while preserving container
  schemas.
- Task evidence now records canonical node types and trust classes without
  changing the existing edge serialization. Deterministic trust precedence and
  graph consistency passed an isolated exact replay.
- A bounded internal event bus, Discord/Telegram senders, safe event projection,
  batching, drop/error metrics, and optional authenticated control commands are
  implemented but disabled. No platform message has been sent physically.
- A separate training event/candidate store, content-addressed objects,
  sanitization, repository/opt-out/license gates, role-specific candidates,
  deduplication, transactional review audit, request/repository exclusion, and
  candidate revocation, hashed user opt-out, quality consistency gates,
  integrity/backup, holds, and dry-run-first retention are implemented but
  disabled. Isolated physical packaging retained role-specific loop-transition
  and evidence-grounded failed-repair preference candidates.
- Weekly Skill reports and atomic verified-archive logic are implemented and
  disabled. An in-process Seoul scheduler, aggregate reports, safe observation
  summaries, authenticated verify/revoke/regenerate, holds, and archive
  retention exist. A user-local 7-Zip 23.01 binary physically passed archive
  creation, `7z t`, checksum, idempotency, revocation/regeneration, empty-week,
  corruption, archiver-failure, late-arrival, and capacity-isolation checks on
  synthetic data. No scheduled or production run exists.
- Hash-protected replay snapshots and exact/mock versus live/comparative replay
  modes plus an exact/audit admin API are implemented. An isolated exact replay
  reproduced the persisted loop state and validated the non-empty Evidence
  Graph; no live-provider or production replay has been exercised.
- The authenticated development `/metrics` endpoint exposes the fixed Goal
  metric names without labels or event content. Loop events and current
  Skill/observer/training aggregates are connected; scheduler/package and some
  approval timeout counters remain zero until their runtime paths exist.
- The external Ollama Reasoner is exactly `Qwythos-v2-9B:Q4`; it remains external
  to the local lifecycle unit map and is never silently replaced by fast mode.
- Executor output defaults to `4096` tokens with a server cap of `16384`.
  `finish_reason=length` is preserved and recorded as truncation, not completion.
- Standard OpenAI request fields suffice. Project metadata and provenance headers
  remain optional, and errors use the typed OpenAI envelope.
- `/v1/models` preserves the standard OpenAI `data` list and also publishes the
  Codex model metadata required by CLI `0.144.6`. Responses streaming requests
  include upstream usage and return official `input_tokens`, `output_tokens`,
  cached-token, and reasoning-token fields. Production Codex physically passed
  both shell-command and freeform `apply_patch` execution.
- KV reservations, model selection, unit topology, and memory gates are unchanged.
- A configurable 10-second prestart memory-settle delay prevents reloads from
  racing unified-memory reclamation. The final resident restoration passed.
- These contracts first passed isolated physical curl,
  OpenAI Python, HTTPX, OpenCode `1.17.18`, and Hermes Agent `0.18.2` checks in
  Task 9. The post-fix stream reached the client before executor completion and
  used no planner or reviewer. Task 9 itself did not deploy production; the
  later production enablement above supersedes that historical boundary.
- Current dynamic OpenCode evidence additionally passes architecture with
  Planner + Codex OAuth Frontier in parallel and an evidence-bearing review
  continuation with local Reviewer + Frontier in parallel. Its automatic title
  request is isolated to a separate session and forced to the fast Executor-only
  path. Hermes architecture also passes with Planner + Frontier, and its real
  four-turn failure recovery preserves one token-scoped state, reinvokes
  Reasoner, and selects Frontier after two failures. A 2026-07-21 rerun returned
  the exact required recovery marker with four Reasoner rounds and two Frontier
  rounds. Hermes evidence-bearing review also selects local Reviewer + Frontier
  after its read continuation; its rerun returned the exact review marker with
  two Reasoner, two Reviewer, and two Frontier invocations. OpenCode multi-file/
  recovery and Hermes multi-file/recovery/review now pass with exact output.
- A controlled real-weight seven-key security task now covers Executor-only,
  core, Planner, Reviewer, Codex OAuth Frontier, and full relevant-agent
  variants. All successful final answers scored 7/7, but specialists added
  latency/tokens and showed no final-answer quality gain on this one task. The
  latest full row passed strict pre/post review in 125.950 seconds; the latest
  Reviewer-only row returned 7/7 but its pre-review artifact failed schema
  validation and therefore remained observability-degraded with confidence
  `low`. This controlled same-task evidence is paired with real simple,
  architecture, multi-file, recovery, review, and security task coverage in
  `docs/VALIDATION.md`; it is not a full variant-by-task cross-product.
- Automated lifecycle contracts now cover persisted states, single-flight load,
  typed loading progress, content-free usage/decisions/samples, leases/guards,
  bounded idle policy, exact-unit full-stop unload, restart reconciliation,
  status filtering, and shutdown ownership. The canonical contract is
  `docs/MODEL_LIFECYCLE.md`.
- Safe checked-in lifecycle mode remains `disabled` with an empty unit map;
  production uses the reviewed ignored adaptive override described above.
  Historical Task 10 used an isolated fixed-mode harness and physically passed
  cold single-flight, measured-shard
  progress, active/stream/continuation guards, ordered full-stop unload, memory
  return within host-snapshot noise, timeout, and one reload at 64K
  configuration.
- Phase 3 physically selected exact full transient-systemd stop/start and the
  unchanged executor baseline: context `65536`, `max_num_seqs=1`,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN. A later
  three-cycle run passed the complete short, long, native-tool, code, review,
  near-64K, teardown, and gateway-advertisement contract. The selected baseline
  and exact full-stop mechanism are now deployed; recent gateway restarts
  physically exercised the same full service stop/start.

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
- The historical Phase 3 checked-in resident target required gateway+executor
  only. The current dynamic MoA design instead treats the externally managed
  Ollama Reasoner as normally resident and not subject to local idle unload;
  Planner and Reviewer remain optional local services with `PartOf` cleanup.
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

## Phase 4 draft-PR gate

- The ignored summary at `/tmp/dgx-moa-phase4-s5gy6ydh/summary.json`, SHA-256
  `5249dd396c4ac8b6ed85e4474fb7c631f504055685138be90791999f03928a8f`,
  reports `passed=true` with no blockers.
- Generic non-stream/stream/long counts are `5/10/3`; native
  tool/continuation/multi-step counts are `5/3/1`; OpenCode
  read/small-edit/multi-file/bounded-engineering counts are `2/2/1/1`; Hermes
  normal/stream/tool/multi-step counts are `2/1/1/1`.
- SSE malformed and duplicate-DONE counts are zero. Cold 503/single-load,
  progress, ready retry, guard, idle unload, memory return, next cold 503,
  reload, and retry contracts all passed.
- The explicit serial validation window was `3064.0628089904785` seconds
  (`51m 4.063s`), not a continuous-load or 24-hour soak claim.
- Production mutation, listener leak, process leak, Critical review, and
  Important review counts are all zero.
- This result permits only a draft PR. It does not activate lifecycle mode,
  merge, deploy, restart production, or make the resident target active.

## Validation baseline

### Role-aware lifecycle gap closure

- Final pre-commit gates passed: `572 passed` with one existing third-party
  warning; Ruff format/check, MyPy for 29 source files, user-systemd unit verify,
  every shell syntax check, trace audit 10/10 at 100%, and `git diff --check`.
- `dev` now persists generation-aware role lifecycle state, role-specific
  request usage and gaps, UTC hourly/weekday-hour counts, EWMA and percentiles,
  cold/load/unload samples, bounded failure events, and the automation circuit.
- Recommended defaults keep executor resident with idle unload disabled.
  Planner and reviewer use 600/1200/3600-second minimum/fallback/maximum idle
  thresholds and 600-second minimum residency; reasoner uses
  300/600/1800 and 300 seconds. Judge lifecycle automation is disabled.
- A cold request returns JSON `503`, `Retry-After`, role, state, generation, and
  honest weight progress. The body also carries monotonic overall progress,
  readiness, and ETA. Concurrent cold requests share one generation/load.
- The isolated user-systemd control result is
  `/tmp/dgx-moa-systemd-control-wbakbkm9/physical-result.json`, SHA-256
  `83ecea14eec43543f22bddf00dccff0e208d45e2e84609820891d54a939c8fdf`.
  Four cold roles each reached ready, all four idled to inactive, executor
  reloaded once at generation 2, three cross-role failures opened the circuit,
  the fourth mutation count was zero, ready executor traffic stayed HTTP 200,
  and two rollback invocations ended disabled with an empty unit map.
- That run used loopback fake weights with the real gateway and real user-systemd
  lifecycle driver. It validates the control path, not real-weight memory return
  or load duration. Earlier selected full-stop executor trials remain the only
  real-weight memory evidence.
- Production stayed at clean `e63fa6f` with gateway PID `3352392`, executor PID
  `3323765`, and listeners 9000/8101 identical before and after. No production
  unit, file, process, listener, or configuration was mutated.
- Independent review found three Important defects and each now has a regression:
  adaptive policy filters `success=1` before limiting the recent window; Observe
  reconciles status/health read-only so it can calculate candidates; and journal
  parser overflow/exception degrades progress without failing a healthy load.
  Final independent re-review of `f7d90cf..9508e97` reported Critical 0,
  Important 0, and Minor 0.

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

- A 2026-07-21 Heavy Judge rerun first found configuration drift to a
  `12000000000`-byte KV reservation. It loaded weights but left only
  `6796004` KiB available during KV initialization, so it was rejected and
  stopped. The first approved `4000000000`-byte retry was conservatively
  interrupted before the repository's readiness-time memory gate.
- The authoritative 4-GB retry then reached HTTP readiness at context `8192`,
  one sequence, `gpu_memory_utilization=0.85`, and ModelOpt FP4 with
  `18073493504` available bytes, above the 16-GiB minimum. An isolated
  authenticated gateway returned the expected `409`, `404`, and `409` guard
  errors, then completed a real pending adjudication in 39 seconds with
  `accept`, low risk, `completion_allowed=true`, and `resume_profile=resident`.
  Persisted state cleared pending evidence, recorded 1149 Judge tokens, and
  completed the task. Judge teardown closed both temporary ports; the fixed
  resident Executor was restored with `69124612096` available bytes.
- Frontier Codex uses separate OAuth profiles (`primary` and `secondary`) with
  automatic fallback from primary on authentication, usage-limit, or rate-limit
  failures. Each can also be invoked independently with
  `scripts/codex-profile.sh test <profile>` or the existing
  `dgx-moa-codex-frontier@<profile>.service` template; its read-only sandbox
  and systemd hardening remain unchanged. Both profiles were reauthenticated on
  2026-07-21. Primary is currently usage-limited until 2026-07-25 16:25; a real
  adapter call fell back to secondary, completed architecture mode, and recorded
  `profile=secondary` with `13613` total tokens.

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
- Phase 4 does not replace a longer continuous reliability soak.
- Promotion still requires draft-PR review, a separate merge decision, and a
  later separately approved production deployment. Phase 4 evidence does not
  authorize deployment.
