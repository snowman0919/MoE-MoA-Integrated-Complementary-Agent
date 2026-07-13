# Validation

## Environment

- `docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L`: exit `0`; detected NVIDIA GB10.
- `hf auth whoami`: exit `0`; authenticated.
- Required ports are unoccupied.

Gateway, resident systemd, model, integration, and profile evidence is recorded
below. Heavy-judge validation is appended after its first isolated startup.

## Executor Runtime

- vLLM startup: `435` seconds; readiness and `/v1/models` passed.
- Model memory: `44.31 GiB` reported by vLLM; measured available-memory drop
  `53276835840` bytes; remaining available memory `67773710336` bytes.
- Completion: `READY`; warm latency `0.103836927` seconds; `2` output tokens.
- Tool call: valid `read_file` call; ID `chatcmpl-tool-95e68c30eba02ec8`;
  arguments decoded to `/tmp/example.txt`; latency `0.828135645` seconds.
- Clean stop restored available memory to `122827276288` bytes.

## Reviewer Runtime

- First startup attempt failed: `Value error, The checkpoint you are trying to
  load has model type cohere2_moe but Transformers does not recognize this architecture.`
- vLLM `0.22.1` contains native `Cohere2MoeForCausalLM`; compatible HF config
  alias loaded all original MoE fields. `cohere_melody 0.10.0` installed per model card.
- Startup: `213` seconds; readiness and `/v1/models` passed.
- Structured result: `{"status":"approved","findings":[]}`; reasoning parsed separately.
- Latency: `4.041933448` seconds; `125` completion tokens; measured decode
  rate `30.925793709406964` tokens/second.
- Measured available-memory drop: `26989322240` bytes; remaining available
  memory `95837954048` bytes.
- Clean stop restored available memory to `121841950720` bytes.

## Planner Runtime

- Startup: `131` seconds; readiness and `/v1/models` passed.
- Strict plan JSON passed with one plan step, one acceptance criterion, and no tool call.
- A `256` token trial ended `finish_reason=length`; configured planner budget
  `1500` avoids that measured lower bound. `512` token trial completed in
  `6.963814218` seconds with `271` tokens.
- Measured decode rate: `38.91545516816371` tokens/second.
- Measured available-memory drop: `25925709824` bytes; remaining available
  memory `95916240896` bytes.
- Clean stop restored available memory to `122724655104` bytes.

## Resident Profile

- Executor + reviewer first passed with `45066366976` bytes available.
- Initial second-process trial failed before load because vLLM defaulted to
  `gpu_memory_utilization=0.92`; calibrated per-role values fixed the guard.
- First low-KV trial proved reviewer needs `0.66 GiB` for 8192 tokens; final
  reviewer and planner reservations are `750000000` bytes.
- Executor + planner + reviewer passed concurrently with all required context
  limits and `25814450176` bytes initially available.
- Final benchmark after integration: `25148334080` bytes available, exceeding
  required `20000000000` by `5148334080` bytes.
- `scripts/start-judge.sh` while resident active: exit `73`, exact output
  `resident role executor is running`.
- Current systemd resident target: executor, planner, and reviewer all active;
  final `/proc/meminfo` `MemAvailable` was `22406086656` bytes.
- Executor vLLM reported `17829` KV tokens at `16384` context; planner reported
  `59392` at `8192`; reviewer reported `8649` at `8192`.

## Gateway

- User systemd service active on `127.0.0.1:9000`.
- `/healthz`, `/readyz`, `/v1/models`, non-streaming, and streaming passed.
- Real gateway tool call ID `chatcmpl-tool-9f4743372a9de247` and JSON arguments
  survived planner/executor round trip.
- Real gateway tool-call latency: `11.151994731` seconds.
- Session `integration-tool` remained in SQLite after service restart.
- Measured gateway `/healthz` overhead: `0.000731` seconds.
- Bearer rejection, malformed tool call, timeout, HTTP 500, replay blocking,
  no-progress blocking, planner/reviewer/judge routing, rollback, redaction,
  compression, integrity, capacity, and completion gates have automated tests.

## Build And Tests

- `uv run ruff format --check .`: passed.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 18 source files.
- `uv run pytest -q`: `17 passed`, one third-party TestClient deprecation warning.
- `docker compose config -q`: passed.
- `docker compose build gateway`: passed; image
  `sha256:2a1f97eb4c54c6b5644621a3ace80ac15b9259410dcbb06cf5702b869fc3742b`.
- Targeted post-change tests: `11 passed`; Ruff and mypy passed after strict
  judge and context-tuner additions.
- Final `scripts/verify-models.sh executor reviewer planner`: all verified.
- Final incomplete-file scan under model root: zero files.

## Development Branch Validation

- Frontier foundation on `dev`: `codex --version` returned `codex-cli 0.144.1`.
  `codex exec --help` confirmed structured `--json`, `--output-schema`, and
  `workspace-write` sandbox support; App Server is experimental, so the bounded
  JSONL runner is selected. Official model documentation identifies GPT-5.6 Sol as
  `gpt-5.6-sol`; installed Codex configuration confirms
  `model_reasoning_effort = "high"`. Account entitlement remains unverified until
  a separate OAuth profile runs its smoke test.
  `scripts/codex-profile.sh status` reported `primary` and `secondary` as
  `authenticated=no`, `state=not_configured`; no OAuth profile directory or
  credential was created. Frontier provider, profile, worktree, immutable-baseline,
  human-approval, and cycle-limit tests passed locally; full suite was
  `78 passed` with one third-party TestClient warning.
- Primary OAuth smoke on `2026-07-11`: Codex started a `gpt-5.6-sol` High request
  from isolated `frontier/phase8-smoke` worktree. CLI returned its explicit usage
  limit before work began; this is `FRONTIER_USAGE_LIMIT`, not a profile failover.
- Secondary OAuth smoke first reached Codex schema validation and exposed an invalid
  `const`-only property in `frontier-result-v1.json`; corrected schemas now include
  required property types before retrying.
- Secondary OAuth retry authenticated `gpt-5.6-sol` with High reasoning and returned
  valid `frontier-result-v1` JSON from `frontier/phase8-smoke`, with no changed files.
  Status was `blocked`: Codex sandbox bubblewrap could not configure loopback
  (`RTM_NEWADDR: Operation not permitted`) before task inspection. Recorded as
  `FRONTIER_VALIDATION_FAILURE`; no profile rotation, merge, or deployment occurred.
- `uv run pytest -q`: exit `0`; `74 passed`, one third-party TestClient warning.
- `uv run ruff check gateway/src tests`: exit `0`.
- `uv run mypy`: exit `0`; `23` source files.
- `scripts/run-mvp-benchmark.sh`: exit `0`; `10/10` synthetic fixture tasks
  passed. Input/output token metrics are explicitly unknown (`null`); fixture
  repository identities are recorded in emitted traces.
- `scripts/validate-opencode-synthetic.sh`: OpenCode-compatible HTTP client
  covers read-only, one-file, multi-file, failure/recovery, reviewer correction,
  gateway restart persistence, tool-call identity, usage, and streaming. Physical
  remote OpenCode remains separately unverified.
- `scripts/mine-improvements.sh`, `scripts/evaluate-improvement.sh`,
  `scripts/build-training-dataset.sh`, and `scripts/export-agentic-traces.sh`:
  exit `0`.
- Re-run on `2026-07-11`: mining produced `IMP-2026-0001`; candidate comparison
  remained `not_recommended` with automatic merge false. Dataset build emitted
  10 Silver executor-SFT samples with train/validation/test split `3/5/2`.
- `systemd-analyze --user verify systemd/*`: exit `0`.
- Read-only user-service check on `2026-07-11`: gateway `/healthz` returned
  `200` on configured tailnet address `100.125.239.72:9000`; loopback is not
  configured for this gateway. `/readyz` returned `503` because profile state
  was `failed` after judge startup hit the 16 GiB headroom gate (`exit 70`).
  Rollback completed without intervention: executor, reviewer, and planner
  returned ready; gateway `/readyz` returned `200`; available memory was
  `23037333504` bytes.
- Real gateway read-only request, session `runtime-readonly-1783700774`:
  HTTP `200`, response `READY`, usage `356` prompt / `2` completion / `358`
  total tokens.
- Real tool continuation, session `runtime-tool-1783700822`: first HTTP `200`
  response preserved tool ID `chatcmpl-tool-a8fafd00dce4b44d` for
  `read_file("/tmp/dgx-moa-validation.txt")`, usage `678` prompt / `35`
  completion / `713` total. A normalized synthetic tool observation continued
  in the same session with HTTP `200`, no additional tool call, and
  `{"output":"validation fixture"}`; usage `629` prompt / `7` completion /
  `636` total tokens.
- `scripts/validate-opencode-loop.sh` against recovered resident services:
  exit `0`; session `opencode-loop-1783701252`; authenticated discovery,
  tool-result continuation, and streaming passed.
- Repeated resident OpenCode-compatible validation on `2026-07-11`:
  `scripts/validate-opencode-loop.sh` exit `0`; session
  `opencode-loop-1783736024`; tool-result continuation and streaming passed.
  `MemAvailable` immediately after was `22945952 kB`.
- Physical remote OpenCode read-only validation on `2026-07-11`: SSH alias `win`
  reached Windows host `Pocket4`, OpenCode `1.17.18`, and tailnet gateway
  `100.125.239.72:9000`. A temporary read-only project config allowed only
  `read`, `glob`, and `grep`; OpenCode emitted a real tool event and returned
  `README_PRESENT`. Gateway credential was piped over SSH only and neither stored
  nor logged. A one-file test was not accepted: its noninteractive OpenCode child
  did not exit, so the test-created PID and temporary fixture were removed.
- Bounded one-file rerun invoked the Windows `opencode.exe` directly rather than
  its npm shim. It changed the isolated fixture (`changed=true`) but retained a
  worker process and provided no final completion within the bounded run; that PID
  and fixture were removed. This is edit-path evidence only, not a completed
  one-file scenario.
- OpenCode `serve`/`run --attach` diagnostic: a loopback-only server reached
  readiness on Pocket4, but the attach client exited without submitting the task
  or changing the fixture. Server, temporary config, and fixture were removed.
- Consolidated `scripts/smoke-test.sh`: exit `0`; session
  `opencode-loop-1783728287`; tool continuation and streaming passed. The
  streaming check captures output before matching `[DONE]`, avoiding a
  `pipefail` false failure from `grep -q` closing its input early.
- Final read-only resident check: `/readyz` returned `200` with executor,
  planner, and reviewer ready; `MemAvailable` was `23184121856` bytes.
- Heavy Judge maintenance on `2026-07-11`: Mistral judge loaded in `603.49`
  seconds with the unchanged `4000000000`-byte KV reservation. vLLM measured
  `22192` KV tokens and `2.71x` concurrency at `8192` context; profile
  readiness had `18105536512` available bytes, above the unchanged 16 GiB
  safety gate. A strict `JudgeVerdict` smoke passed with `accept`, `low` risk,
  `completion_allowed=true`, zero resolved disagreements, and zero mandatory
  changes. Judge then stopped and resident was restored; final gateway
  `/readyz` returned `200` with `23834812` KiB available. No model, unit,
  headroom, resident-context, or trace setting was changed.
- Raw SSE protocol capture on `2026-07-11`: real resident gateway normal,
  tool-call, and tool-result continuation streams each ended `data: [DONE]`
  followed by HTTP EOF. Their final finish reasons were respectively `stop`,
  `tool_calls`, and `stop`; no stale `tool_calls` finish reason or post-DONE
  usage was observed. Artifact: `data/diagnostics/opencode-completion/`
  `opencode-sse-48850860-c3a6-4a69-a5b2-9234f0758417.json`.
- Physical OpenCode completion differential on `2026-07-11`: direct Windows
  `opencode.exe` `1.17.18` invocation with an explicit isolated `--dir` completed
  the one-file scenario against both the resident gateway and a temporary
  loopback-only fake server. Both runs emitted `write`, `tool-calls`, continuation
  text `WORKER_DONE`, final `stop`, created `COMPLETION.txt` with `DONE`, and
  exited `0`. The fake B server was stopped and all temporary processes and
  fixtures were removed. This does not reproduce a gateway protocol or OpenCode
  completion-lifecycle defect. Artifact:
  `data/diagnostics/opencode-completion/opencode-physical-20260711.json`.
- Completion lifecycle re-validation on `2026-07-12`: after deploy fast-forward
  and resident restoration, raw gateway normal, tool-call, and continuation SSE
  streams recorded `stop`, `tool_calls`, and `stop` respectively, each followed
  by `[DONE]`, HTTP EOF, and a matching `stream_completed` gateway timestamp.
  Artifact: `data/diagnostics/opencode-completion/`
  `opencode-sse-d656ffdc-ca38-4340-b9eb-d2b79445ae4f.json`.
- Bounded physical OpenCode acceptance on `2026-07-12`: Pocket4 OpenCode
  `1.17.18` ran direct `opencode.exe` with explicit isolated `--dir`; PowerShell
  parent PID `3544` started run-owned OpenCode PID `35868`. It emitted
  `tool-calls`, then continuation final `stop` in session
  `ses_0ae328bf5ffeCrrWy7hFprQjIN`, wrote `COMPLETION.txt` as `DONE`, and
  exited `0`. Child snapshots observed `opencode.exe` and `conhost.exe` during
  the run; after final SSE the run-owned child list was empty. The fixture and
  all run-owned processes were removed. Artifact:
  `data/diagnostics/opencode-completion/`
  `opencode-physical-59a5d08a-e1d0-4b56-aacf-53801cb86471.json`.
- Final live loop checks on `2026-07-12`: `scripts/validate-opencode-loop.sh`
  passed session `opencode-loop-1783783547`; `scripts/smoke-test.sh` passed
  session `opencode-loop-1783783550`; gateway `/readyz` returned `200` with
  executor, planner, and reviewer ready.
- Post-resolution fixed ten-task benchmark: `scripts/run-mvp-benchmark.sh`
  passed `10/10`, task success rate `1.0`, route distribution `3/6/1`
  fast/standard/escalation, tool calls per successful task `1.2`, and time per
  successful task `0.0311096` seconds. Its trace inspection found `10` JSONL
  files with `24` indexed `failure_classified` events. The bounded improvement
  evaluation again selected `REPEATED_ACTION` (one fixture) but returned
  `not_recommended`, `0.0%` reduction, and automatic merge `false`; no candidate
  was applied.

## Tailscale

- Attempted `tailscale serve --bg http://127.0.0.1:9000`.
- Blocker: `Serve is not enabled on your tailnet.`
- Enable URL: `https://login.tailscale.com/f/serve?node=ngaf9Ptc8f11CNTRL`.
- Funnel was never enabled or used.

## Production Baseline Stabilization — 2026-07-12

- Starting `dev` commit: `5760c6bab0c48766441e6245e13401b69569bfb8`.
- Logging semantics v2 adds strict runtime provenance, durable session
  trajectories, linked agent decisions/tool executions/evaluations, typed failure
  attribution and resolution, explicit training eligibility, date-partitioned
  JSONL, SQLite trace indexing, and primary/secondary persistence policy tests.
- Legacy v1 remains readable and classified `legacy`; it is excluded from
  completeness claims and automatic training export.
- Final automated run before documentation: `96 passed`, one upstream
  Starlette/httpx deprecation warning. Ruff format/check and MyPy passed.
- Fixed synthetic benchmark passed `10/10`, task success `1.0`, routes
  fast/standard/escalation `3/6/1`, tool calls per success `1.2`. Its ten v2
  traces audited `10/10`, `100%`, with no missing fields or lifecycle events.
- Improvement mining excluded the benchmark's synthetic injected failures and
  returned `no_actionable_failure`; no candidate cycle was started.

### Real OpenCode staging

- Local OpenCode `1.17.18` ran against the direct tailnet gateway using disposable
  Git fixtures. The required ten-session distribution was read/repository analysis
  `3`, small edit `3`, multi-file `2`, failure recovery `1`, and bounded engineering
  `1`.
- Required-session outcomes were 6 completed and 4 failed. The failed read,
  two multi-file tasks, and bounded-engineering task reached the explicit
  180-second harness bound and/or failed fixture validation; none was deleted or
  reclassified as successful.
- An earlier calibration task completed in OpenCode but failed harness finalization
  because OpenCode supplied its own `ses_*` gateway ID. The failure was retained;
  the harness now discovers that real ID from OpenCode JSONL. A stream-finalizer
  race and bytes-on-timeout path were also fixed and regression-tested.
- Validation partitions audited 11/11 staging/calibration sessions and 2/2
  review/blocked sessions at `100%` applicable mandatory completeness, including
  completed, failed, and blocked terminal records.
- Controlled no-progress session `blocked-soak-1783826633` returned HTTP
  `200`, `200`, then `502`; it was finalized `blocked` with expected
  `NO_PROGRESS` attribution so it cannot pollute active mining.

### Review and runtime behavior

- A real reviewer flow first returned HTTP `502` because North followed raw task
  or observation text (`READY`) rather than the structured verdict schema. The
  diagnostic failure was preserved with context attribution and resolving commit.
- The fixed prompt removes raw objectives from reviewer/judge contexts and ends
  with a literal JSON-only output boundary. Exact real-model replay returned
  `{"status":"approved","findings":[]}`. A full updated FastAPI path using the
  real planner, executor, and reviewer returned HTTP `200`, a structured rejected
  verdict, phase `correction`, and blocked completion. Its trace audited `1/1`,
  `100%`.
- Controlled resident restart exposed reviewer CUDA initialization failures and a
  planner readiness sample below the unchanged 20 GiB startup gate. Rollback was
  preserved. A configurable 10-second unified-memory settle delay was added;
  clean prestart measured `123138887680` bytes and the final resident restoration
  succeeded without changing models, KV, contexts, units, or headroom criteria.
- Gateway was failure-restarted to load validation code; SQLite continuation state
  remained available. The final resident target/profile is ready and gateway
  `/readyz` returns `200`.

### Bounded soak

- Memory monitor window: epoch `1783799804` through `1783826671`, duration
  `26867` seconds (`7h 27m 47s`), `5370` samples.
- Minimum observed `MemAvailable`: `20783300608` bytes; maximum:
  `123198304256` bytes.
- The window covered actual OpenCode work, idle periods, gateway restart,
  resident restart and rollback/recovery, real tool continuation, review flow,
  one explicit block, and trace archive reads/writes.
- SQLite state errors: `0`; trace archive errors: `0`; observability degradation:
  `0`. Startup/backend and profile rollback incidents remain visible in journald
  and runtime status rather than being erased.
- This is a bounded soak, not a 24-hour stability claim. The 24-hour observation
  state is pending.

### Deferred physical checks

- Heavy Judge was not reloaded: Judge code, model, KV reservation, context, and
  profile architecture did not change; the prior physical structured-verdict and
  resident-restoration evidence remains authoritative.
- Pocket4 physical completion was not rerun: OpenAI serialization and tool-result
  continuation behavior did not change; the prior OpenCode `1.17.18` completion
  baseline remains authoritative.
- Frontier remains connected but disabled for the recorded host bubblewrap
  capability failure. No AppArmor, networking, sandbox, or OAuth rotation change
  was made.

### Final command pass

- `uv run pytest -q`: `96 passed`, one upstream deprecation warning.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
  `systemd-analyze --user verify systemd/*`, and shell syntax checks: exit `0`.
- `scripts/validate-opencode-loop.sh`: session `opencode-loop-1783828819`,
  tool continuation and streaming passed.
- `scripts/smoke-test.sh`: session `opencode-loop-1783828822`, tool continuation
  and streaming passed.
- Final fixed benchmark: `10/10`, success `1.0`, routes `3/6/1`, tool calls per
  success `1.2`, time per success `0.0420419` seconds; trace audit `10/10`, `100%`.
- Final direct tailnet `/healthz`, `/readyz`, and authenticated `/v1/models`
  passed; only `dgx-moa-agent` is exposed. Resident target/profile and all three
  role services are ready. tmux `dgx-opencode` remains active on OpenCode `1.17.18`.
- Post-finalizer regression: `opencode-loop-1783829101` and
  `opencode-loop-1783829104` both passed continuation and streaming; their main
  and stream sessions finalized completed. The full July 12 validation partition
  then audited `10/10`, `100%`, with zero missing fields or events.

### Multiple tool-call regression

- Gateway regression tests preserve two valid executor tool calls and attribute
  each tool result to its matching call ID.
- OpenCode `1.17.18` session `ses_0ab465307ffetVHiBQf40HnwFn` completed against
  the updated gateway with two `read` calls in one assistant message. Gateway
  state recorded one structured decision containing both calls; OpenCode exited
  `0`, fixture validation exited `0`, and finalization exited `0`.
- `uv run pytest -q`: `98 passed`, one upstream Starlette/httpx deprecation
  warning. Ruff format/check and MyPy passed.

### Context overflow regression

- OpenCode `1.17.18` session `ses_0ab2dda76ffeKbk9p2yiJ2SSmY` exposed the
  executor limit: at least `15385` input plus `1000` requested output tokens
  exceeded the configured `16384` context. The streaming gateway had already
  returned HTTP `200`, so the upstream `400` surfaced as a connection reset.
- The gateway now bounds structured tool content and reused stdout/stderr across
  the retained window, and opens the upstream stream before returning HTTP
  headers. Successful stdout containing words such as `failed` is no longer
  classified as a failed action.
- OpenCode session `ses_0ab28024effe7ILeEx30RyB72q` read eight 353-line files,
  then completed the same conversation with `CONTEXT_DONE`, `12426` input and
  `22` output tokens, `finish_reason=stop`, and HTTP `200` without a reset.
- `uv run pytest -q`: `102 passed`, one upstream Starlette/httpx deprecation
  warning. Ruff format/check and MyPy passed.

### Runtime context calibration

- Executor candidates `24576/750000000`, `20480/600000000`, and
  `18432/525000000` each had enough measured KV tokens but failed the required
  three-cycle resident startup criterion when reviewer or planner CUDA context
  allocation returned OOM. The stable selection remains `16384/500000000`.
- Runtime `main@d8b4708` was cleanly restarted with the selected baseline. All
  resident roles became ready with `23362560000` bytes available; executor
  five-request and near-limit probes passed in `5.863` seconds.
- OpenCode `1.17.18` continued large-history session
  `ses_0ab28024effe7ILeEx30RyB72q` against the deployed gateway and returned
  `RUNTIME_DONE`, `12636` input and `23` output tokens, `finish_reason=stop`,
  and HTTP `200`.

### OpenCode title-request isolation

- OpenCode session `ses_0aab526deffeBz5wMjmBm3MPmd` first sent the automatic
  `Generate a title for this conversation` request with the work session ID.
  Gateway state consequently retained that title request as the objective, and
  later work requests stopped after title-oriented tool loops despite HTTP `200`
  and `finish_reason=stop`.
- Title requests now use an internal `<session-id>:title` state key while the
  client continues to receive its original session ID. The API regression sends
  a title request followed by `Create AGENTS.md` with the same client session ID
  and verifies their objectives remain isolated.
- `uv run pytest`: `103 passed`, one upstream Starlette/httpx deprecation
  warning. `uv run ruff check gateway/src tests` and `git diff --check` passed.
- A temporary loopback staging gateway using the resident executor received a
  title request and then `Create AGENTS.md` with client session
  `physical-title-isolation`. Its SQLite state recorded
  `physical-title-isolation:title` with the title objective and
  `physical-title-isolation` with `Create AGENTS.md`; the title response stopped
  normally. The staging process was then stopped and its temporary state removed.
- After PR `#6` merged, production `main@eeb4484` was restarted and resident
  readiness returned `200`. The authenticated production sequence
  `production-title-isolation-1783844401` recorded the title objective only in
  its `:title` state and `Create AGENTS.md` in the work state; both requests
  returned HTTP `200`.

### Resident guard recovery and Hermes compatibility

- On 2026-07-12, planner completed model startup but its post-start guard
  rejected `21415972864` available bytes against a `21474836480`-byte threshold.
  The planner stopped and OpenCode received gateway `502` responses. PR `#8`
  aligned role and resident guards with the documented `20000000000`-byte
  requirement; planner then started successfully and `/readyz` returned `200`.
- An authenticated Hermes-compatible OpenAI streaming request without a custom
  session header returned content chunks, `finish_reason=stop`, and `[DONE]`.
- Live read-only routing audit on 2026-07-12: no configured or locally present
  model matched `VibeThinker` or `Hermes`. The resident 21,562 MiB GPU process
  was the planner, `cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit`; the executor
  and reviewer used 47,009 MiB and 19,753 MiB respectively. Since the current
  resident startup, 34 planner requests returned HTTP 200, while 3 executor
  requests returned HTTP 200 and 30 returned HTTP 400. Every inspected session
  selected the standard route and recorded planner then executor; reviewer had
  no chat-completion request. The executor failures measured 15,385 prompt
  tokens plus the configured 1,000 output tokens, exceeding its 16,384-token
  limit. This is an operational observation, not a benchmark.

### VibeThinker reasoner integration preparation

- On 2026-07-12, the development worktree downloaded and verified
  `WeiboAI/VibeThinker-3B@77bd2cced09193c8b9a59a32bd8577bbd1f3e01c` at
  `/home/kotori9/models/dgx-moa/reasoner`: two safetensors shards,
  `6188996125` bytes, valid tokenizer/chat template, and no incomplete files.
  This is a model-integrity check only; the production services were not
  restarted and no resident 65,536-context readiness or capacity result is
  claimed.

### 65,536-context resident candidate rejection

- On 2026-07-12, candidate `9929115` ran from the production runtime worktree
  with `runtime_channel=dev` and `trace_origin=validation`; it was not merged.
  Executor, reviewer, and planner each started at `65536` and reported,
  respectively, `78748`, `175790`, and `140174` GPU KV tokens. Their measured
  maximum 65,536-token concurrency values were `1.20x`, `2.68x`, and `2.14x`.
- The resident profile was rejected before VibeThinker could start: planner's
  post-start guard measured `17965121536` available bytes, below the then-current
  `20000000000`-byte safety minimum, and exited `70`. The guard was not
  weakened. Stable `main` was restored with executor `16384`, planner/reviewer
  `8192`, authenticated tailnet health, model discovery, and `/readyz` all
  returning success. This is a failed capacity validation, not a performance
  benchmark.

- On 2026-07-13, explicit operator approval changed the resident startup floor
  to `10737418240` bytes (10 GiB). The 65,536-context candidate is retested
  under that floor; kernel OOM or a lower measured value remains a rejection.

### 65,536-context 10-GiB-floor retry rejection

- On 2026-07-13, candidate `41bfba1` started all four resident roles at
  `65536`: executor `67121`, reviewer `67383`, planner `83740`, and
  VibeThinker reasoner `66448` GPU-KV tokens (each at least `65536`). The
  post-start guards recorded, in role order, `67721474048`, `46267162624`,
  `22638268416`, and `12540280832` available host-memory bytes. The initial
  full start therefore passed the explicit `10737418240`-byte floor.
- A required dependency recycle exposed an unstable result: the reviewer's
  first CUDA initialization returned `torch.AcceleratorError: CUDA error: out
  of memory` and systemd retried it successfully, but the reasoner's next
  post-start guard measured `10208575488` bytes, below the 10-GiB floor by
  `528842752` bytes. Its guard stopped the service before accepting the
  profile. No kernel panic, host restart, or host-OOM event was observed;
  direct kernel-log access was unavailable to the unprivileged service user.
- The candidate is rejected because it cannot consistently meet the approved
  10-GiB guard. It was not merged or deployed. The production worktree was
  returned to `main`; baseline resident recovery is in progress. This is a
  capacity/safety validation result, not a benchmark.

### Codex multi-agent activation check

- On 2026-07-13, `primary` and `secondary` Codex OAuth profiles were present
  and the installed CLI was `0.144.1`. The profile test was updated for that
  CLI by removing its unsupported `--ask-for-approval` argument and requiring
  a JSON `turn.completed` event.
- Both real read-only test invocations returned HTTP `401` with
  `token_invalidated` / revoked refresh-token errors. No task was accepted or
  changed. Frontier configuration is enabled and retains independent profile
  workers, but interactive OAuth re-login is required before either agent is
  usable.

### 64K three-role resident validation

- On 2026-07-13, candidate `4b2fe2b` excluded VibeThinker from the resident
  target while retaining it as an optional configured model. Executor,
  reviewer, and planner started at `65536` and reported `67121`, `67383`, and
  `83740` GPU-KV tokens. Their post-start host-memory measurements were
  `68723949568`, `42841587712`, and `18525147136` bytes, above the approved
  5-GiB floor.
- The authenticated gateway request `resident64k-no-reasoner-*` returned HTTP
  `200` and `finish_reason=stop`. Its decision events were planner then
  executor; no `reasoner_completed` event was written. The reviewer required
  one systemd CUDA-OOM retry before becoming ready; no kernel panic or host-OOM
  event was observed.

### OpenCode title-history recovery

- OpenCode can send its automatic title prompt after the work-message history.
  The former single-user-message detection stored that title as the work-session
  objective, causing the model to complete a title and exit its loop.
- Production sequence `title-history-1783851856` confirmed that a trailing title
  prompt now uses only `:title` state while `Create AGENTS.md` remains the work
  objective. All resident roles and `/readyz` were active after deployment.

### Codex multi-agent activation

- On 2026-07-13, interactive OAuth re-login was followed by separate read-only
  `primary` and `secondary` Codex calls using `gpt-5.6-sol`. Both returned an
  agent message of `READY` and a JSON `turn.completed` event. The profile test
  now requires that completion event, so an expired token cannot be reported
  as healthy. No sandbox or systemd hardening was weakened.

### Hermes current-objective and context discovery regression

- A live Telegram turn on 2026-07-13 sent 124 history messages without a stable
  gateway session header. The gateway created a new state for each provider
  call and selected the oldest user message, `모델 변경완료`, as every objective.
  Hermes made at least 24 provider calls in that turn and issued three unrelated
  model-change clarification calls. The reviewer endpoint received zero chat
  completions during the observed streaming turn.
- The gateway model-discovery response omitted a context field, so Hermes logged
  a 256,000-token fallback despite the deployed 65,536-token limit.
- `uv run pytest -q` passed `110` tests; Ruff and MyPy passed. A loopback staging
  request containing an old model-change message and the latest context-analysis
  request returned HTTP `200`, `finish_reason=stop`, advertised `65536`, and
  persisted the latest context-analysis request as its objective. Its measured
  decision roles were planner then executor.
- The first streaming-review candidate invoked reviewer EngineCore PID `1459380`
  but passed raw SSE as evidence; the reviewer exhausted its structured response
  path and recorded `review_failed: ValueError`. The executor stream still ended
  normally. Passing only the reconstructed assistant content removed that noise.
- The corrected physical streaming request returned HTTP `200`, preserved
  `STREAM_REVIEW_OK` and `[DONE]` in its 1,484-byte SSE response, and recorded
  planner, executor, then reviewer decisions followed by `review_completed` and
  `stream_completed`. The reviewer rejected this synthetic response with the
  route's three missing-metadata findings; this validates invocation and protocol
  completion, not review quality.
