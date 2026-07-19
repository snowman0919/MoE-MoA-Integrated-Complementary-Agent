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
- Production session `production-stream-review-1783915400` then recorded
  planner, executor, and reviewer decisions, an approved reviewer result with no
  findings, `finish_reason=stop`, and `stream_completed`. Resident readiness was
  HTTP `200` with executor, planner, and reviewer ready; reasoner and judge stayed
  stopped.

### Phase-one physical streaming-buffer baseline

- On 2026-07-18, clean development commit `0b83e18` was measured against the
  read-only production reference `c2a9af0`. Installed versions were vLLM
  `0.22.1`, OpenCode `1.17.18`, and Hermes Agent `0.18.2`. Production gateway,
  executor, planner, and reviewer user services were all inactive and their
  ports were unbound before the isolated run.
- Controlled foreground model processes used loopback ports `8101`, `8102`, and
  `8103`. The isolated gateway used `127.0.0.1:19000`, SQLite path
  `/tmp/dgx-moa-phase1.6roKBd/state/gateway.db`, trace root
  `/tmp/dgx-moa-phase1.6roKBd/traces`, and run root
  `/tmp/dgx-moa-phase1.6roKBd/data/run`. No production service or production
  worktree was changed.
- The first foreground model launch failed before model loading because the
  shared settings validator required a gateway API key. The retry used a new
  isolated validation credential supplied only through the process environment;
  no credential was written or recorded.
- The executor's default FlashInfer-CUTLASS path began a first-run SM121a build
  containing 96 object targets. After 9 targets, that diagnostic process was
  stopped because the kernel build was unrelated to gateway buffering. The same
  physical executor model was restarted with vLLM's supported `MARLIN` MoE
  backend, already exercised by the reviewer runtime. Its model load took
  `245.521061` seconds. This override is diagnostic evidence, not a production
  backend selection.
- One authenticated streaming request asked for twenty numbered lines with
  `max_tokens=1000`. Monotonic timestamps in nanoseconds were request accepted
  `1230195082686135`, planner start `1230195118466714`, planner complete
  `1230219591415785`, executor start `1230219596688357`, executor first byte
  `1230221185713404`, executor complete `1230228218239311`, reviewer start
  `1230228225083613`, reviewer complete `1230262583974904`, downstream first
  byte `1230262588265733`, and downstream completion `1230262595932885`.
- Derived durations were planner `24.472949071` seconds, executor first-byte
  latency `1.589025047` seconds, executor total `8.621550954` seconds, reviewer
  `34.358891291` seconds, and downstream first-byte latency `67.505579598`
  seconds from request acceptance. The downstream first byte followed the
  executor first byte by `41.402552329` seconds and followed reviewer completion
  by only `0.004290829` seconds. This proves full executor buffering behind the
  reviewer.
- Final client status was HTTP `200`; the response contained `62174` SSE bytes
  and exactly one `[DONE]`. This is a defect reproduction and timing baseline,
  not a throughput or quality benchmark.

### Phase-one isolated post-fix validation

- On 2026-07-18, development commit `0d95591` was validated against the
  unchanged production reference `c2a9af0`. The production worktree was clean
  on `main`; all production gateway/model units and targets were inactive, and
  ports `8101`, `8102`, `8103`, `8104`, `8110`, `9000`, and `19000` were
  unbound before the run.
- The pre-runtime gates reported `180 passed, 1 warning in 2.27s`, `48 files
  already formatted`, Ruff `All checks passed!`, MyPy success for 26 source
  files, clean systemd verification, clean shell syntax, and clean
  `git diff --check`. The warning was the existing Starlette TestClient
  deprecation. The repository trace audit exited `1`: 10 sessions, 4 complete,
  6 incomplete/legacy, and 40.0% mandatory-field completeness. The six missing
  records were `legacy_v1`; ignored root records with duplicate session IDs
  sort after and shadow the corresponding nested v2 records.
- The isolated root was `/tmp/dgx-moa-phase1-post.ahMvu6`, with separate
  `state/gateway.db`, `traces`, `data/run`, and `logs` paths. The gateway bound
  only `127.0.0.1:19000`; physical models bound only loopback `8101`, `8102`,
  and `8103`. A fresh API credential existed only in the supervisor process
  environment and was unset when that process exited.
- Controlled process groups were executor `3896715`, reviewer retry `3915544`,
  planner `3921619`, timed gateway `3973021`, and temporary tailnet relay
  `3985247`. The executor used the same diagnostic vLLM `MARLIN` MoE backend as
  Task 0. It advertised maximum model length `65536`; reviewer and planner also
  advertised `65536`.
- Executor checkpoint loading took `606.69` seconds. The first reviewer start
  failed before weight loading with CUDA `cudaMemGetInfo` out-of-memory; its
  log was retained, memory was allowed to settle, and the unchanged retry loaded
  four shards in `196.34` seconds and became ready. Planner then became ready.
  All three real model endpoints were concurrently healthy before client tests.

#### Generic OpenAI-compatible clients

- Authenticated `/v1/models` returned, in order, `dgx-moa-chat`,
  `dgx-moa-agent`, and `dgx-moa-orchestrated`, each with
  `context_length=65536`.
- Curl non-streaming chat session `physical-curl-nonstream` returned HTTP `200`,
  natural content `CHAT_OK`, completion ID `chatcmpl-9051f38c1b87592a`,
  `finish_reason=stop`, and usage `260/3/263`. Persisted policy was
  `chat/plain_chat`, requiring and recording only executor.
- Curl streaming agent session `physical-curl-stream` returned HTTP `200`,
  content `STREAM_OK`, `1029` bytes, completion ID
  `chatcmpl-9cacc35b31422f23`, and exactly one `[DONE]`. Persisted policy was
  `agent/native_agent_turn`, requiring and recording only executor.
- The official OpenAI Python client `2.6.1`, using no project metadata, returned
  HTTP `200`, `OPENAI_OK`, completion ID `chatcmpl-b55b4713f2a48802`, session
  header `99e087e8-2c49-4ce6-9699-adac639e2d74`, `finish_reason=stop`, and usage
  `260/4/264`. Its state was executor-only.
- A minimal HTTPX `0.28.1` streaming consumer, also without project metadata,
  returned HTTP `200`, `HTTPX_OK`, `1252` bytes, and exactly one `[DONE]` in
  session `2ad4d7f0-5e41-49fc-8af6-e649d8d01242`. Its first raw byte was at
  monotonic nanoseconds `1245245784681732`, completion was
  `1245245866156559`, and elapsed time was `285.885` milliseconds. Its state
  was `chat/plain_chat`, executor-only.
- Native tool session `physical-tool-loop` first returned exactly one
  `read_file` call with ID `chatcmpl-tool-b6f42439d220f9ab`, arguments
  `{"path":"/tmp/dgx-moa-physical.txt"}`, and `finish_reason=tool_calls`.
  A standard tool-result continuation preserved that ID and returned
  `PHYSICAL_TOOL_RESULT` in natural assistant content with
  `finish_reason=stop`. Both decisions were executor-only.
- Explicit orchestrated session `physical-orchestrated` returned HTTP `200`,
  `ORCHESTRATED_OK`, completion ID `chatcmpl-971a44e0da6ad77e`, and elapsed
  time `54.364` seconds. State recorded planner `14815.343` ms, executor
  `322.505` ms, reviewer `39178.55` ms, and an approved review. This is the
  explicit orchestration path, not an ordinary-client dependency.
- Negative requests returned these complete OpenAI error envelopes; the first
  three were re-captured against the CPU-only follow-up gateway and matched the
  original physical run:

  ```text
  HTTP 404 {"error":{"message":"unknown model","type":"invalid_request_error","code":"model_not_found","param":"model"}}
  HTTP 422 {"error":{"message":"tool_choice requires tools","type":"invalid_request_error","code":"invalid_request","param":null}}
  HTTP 401 {"error":{"message":"invalid bearer token","type":"authentication_error","code":"invalid_api_key","param":null}}
  HTTP 502 {"error":{"message":"All connection attempts failed","type":"backend_error","code":"backend_error","param":null}}
  ```

  The HTTP `502` was the retained orchestrated request after only the controlled
  planner group was stopped; it is distinct from the measured timeout below.

#### Exact post-fix streaming measurement

- The preserved Task 0 timing wrapper initially returned HTTP `500`, 21 bytes,
  and no DONE because Task 6 added `timeout_seconds` keywords to
  `Provider.stream()` after that wrapper was written. The retained exception was
  `TypeError`; an ignored validation-only wrapper was updated to forward the
  new keywords without changing gateway source.
- The successful session `physical-streaming-postfix-retry` used the exact Task
  0 prompt, `Write exactly twenty short numbered lines about reliable APIs.`
  Raw monotonic nanoseconds were request accepted `1245752311438712`, executor
  start `1245752342543874`, executor first byte `1245752523408335`, downstream
  headers `1245752524396351`, downstream first byte `1245752524595631`, executor
  complete `1245759218474816`, and downstream complete `1245759226444430`.
- Derived durations were executor start `0.031105162` seconds after acceptance,
  executor first-byte latency `0.180864461` seconds, executor first byte
  `0.211969623` seconds after acceptance, one-event transport overhead
  `0.001187296` seconds, executor total `6.875930942` seconds, downstream first
  byte `0.213156919` seconds after acceptance, and downstream total
  `6.915005718` seconds. The client received its first byte
  `6.693879185` seconds before executor completion; final forwarding finished
  `0.007969614` seconds after executor completion.
- Final status was HTTP `200`, `59652` bytes, and exactly one `[DONE]`.
  Persisted state was `agent/native_agent_turn`, with executor as the only
  required and recorded role, `finish_reason=stop`, and no truncation. Reviewer
  was absent from both state and the critical path.

#### Real HTTP executor-first-byte timeout

- A follow-up used no GPU model. A fresh root
  `/tmp/dgx-moa-timeout.uVbS91` contained state, trace, run, model-placeholder,
  and log paths. A real CPU-only OpenAI-compatible provider bound
  `127.0.0.1:19101`; the real gateway bound `127.0.0.1:19100` with
  `executor_first_byte_timeout_seconds=0.25` and the slow provider as its only
  executor. Production remained inactive and ports `9000`, `19100`, and
  `19101` were free before startup.
- The first gateway launcher, `uv run python -m dgx_moa.api`, exited without
  binding because `api.py` defines the console `main()` but no module
  `__main__` call; its empty log was retained. The retry used the declared
  `uv run dgx-moa` console entry point and bound normally. This failed harness
  attempt did not reach a request.
- Session `physical-executor-first-byte-timeout` sent an authenticated standard
  streaming request. The slow provider accepted the HTTP POST, returned HTTP
  `200` headers, and logged `stream=true`, model `timeout-executor`, and
  monotonic nanoseconds `1248155177768646`; it deliberately slept before its
  first SSE byte. The gateway cancelled that stream at `1248155425595592`,
  proving a first-byte timeout after connection and request acceptance rather
  than connection refusal.
- Client monotonic bounds were `1248154882995579` through
  `1248155487226164`. The gateway returned this complete HTTP response before
  starting SSE:

  ```text
  HTTP/1.1 504 Gateway Timeout
  date: Sat, 18 Jul 2026 03:40:28 GMT
  server: uvicorn
  content-length: 126
  content-type: application/json

  {"error":{"message":"executor_first_byte timed out","type":"timeout_error","code":"executor_first_byte_timeout","param":null}}
  ```

- SQLite state was `agent/native_agent_turn`, executor-only. Its single
  `request_timing` event recorded
  `stage_status={"executor_first_byte":"timed_out"}` and milliseconds
  `accepted=0.0`, `upstream_start=8.139`, `executor_total=257.988`,
  `first_downstream_byte=266.133`, and `completed=266.135`. The trace at
  `traces/dev/validation/2026-07-18/physical-executor-first-byte-timeout.jsonl`
  preserved the same timing metrics, task `TASK9-TIMEOUT`, workspace identity,
  executor decision, and `final_status=degraded`.
- The isolated one-session trace audit still exited `1`: its fields were
  complete, but `session_ended` was absent. Teardown stopped only gateway PGID
  `4026366` and provider PGID `4025162`; both ports were unbound, the
  environment-only credential was unset, memory was unchanged, production
  units remained inactive, and the production worktree remained clean.

#### Real OpenCode and Hermes clients

- Real OpenCode `1.17.18` ran through its documented `opencode run --pure
  --auto --format json --dir ... --model dgx-moa/dgx-moa-agent` interface from
  explicit isolated working directories. Its first normal attempt returned
  API HTTP `400` because a temporary config without a model `limit.output`
  caused the client to request more than the server cap of `16384`. Adding the
  documented temporary `limit: {context: 65536, output: 16384}` fixed the
  client configuration without changing repository source.
- OpenCode normal session `ses_08cd07ec3ffeHhZ6FnUz8r3GUQ` exited `0` with
  `OPENCODE_OK`, `finish_reason=stop`, and usage total/input/output
  `2824/2820/4`. Tool session `ses_08ccfe27effefpBnhcFEKpr03N` exited `0`,
  invoked native `read` call `call_ebb54446c04947f9bcfd77b4` on the isolated
  `FIXTURE.txt` with exact client input
  `{"filePath":"/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/FIXTURE.txt"}`,
  received `OPENCODE_PHYSICAL_FIXTURE`, and continued with
  `OPENCODE_TOOL_OK`. The gateway access log recorded HTTP `200` for both normal
  POSTs and all three tool-session POSTs. Normal state recorded request stream
  flags `[true,true]` and two `stream_completed` events; tool state recorded
  `[true,true,true]` and three `stream_completed` events, plus
  `tool_result_received`, `tool_execution_recorded`, and executor-only roles.
- Real Hermes Agent `0.18.2` (`2026.7.7.2`, upstream `d9ee3424`) used its
  documented one-shot CLI, `provider: custom`, environment-expanded
  `model.api_key`, model `dgx-moa-agent`, and the direct tailnet URL
  `http://100.125.239.72:9000/v1`. The environment reference prevented any
  credential from being stored. A controlled foreground TCP relay bound only
  `100.125.239.72:9000` after port 9000 and production inactivity were proved;
  it forwarded only to the isolated loopback gateway and was removed first at
  teardown. No Tailscale Serve, systemd, or production configuration changed.
- Hermes attempt one reached the endpoint but returned `HTTP 401: invalid bearer
  token`: version 0.18.2 deliberately host-gates `OPENAI_API_KEY` away from
  unrelated custom hosts and used its no-key placeholder. The retained retry
  used the documented `${DGX_MOA_API_KEY}` config reference. Normal session
  `20260718_121450_52e9b9` then exited `0` with `HERMES_OK`, one API call, and
  usage `3112/4/3116` input/output/total. Gateway state
  `7d5d40fd-f402-4a18-833f-c6caa9aaca2e` recorded `stream=true`, one
  `stream_completed`, and `finish_reason=stop`.
- Hermes tool session `20260718_121544_04de50` exited `0` with two API calls.
  Its exported transcript recorded native `read_file` call
  `call_b93806e12d814d80baa71f38` with arguments
  `{"path": "/tmp/dgx-moa-phase1-post.ahMvu6/hermes/work/FIXTURE.txt"}`,
  tool result `HERMES_PHYSICAL_FIXTURE`, `finish_reason=tool_calls`, and a
  continuation `HERMES_TOOL_OK` with `finish_reason=stop`. Gateway state IDs
  `063de118-5cc1-4d41-b606-19f8bd51b0c2` and
  `42087b8e-abaf-4893-87c3-0718a7199b4a` remained executor-only and recorded
  `stream=true` and one `stream_completed` each; the former finished
  `tool_calls`, while the continuation finished `stop` and recorded
  `tool_result_received` and `tool_execution_recorded`.

#### Exact retained failed-to-successful transitions

Only credential values are replaced by `[REDACTED]` below. All other paths,
ports, versions, flags, environment names, prompts, and output files are the
retained commands or configuration transitions.

The Task 0 baseline first started each role in its own foreground shell without
an API key. These three commands failed in the shared settings validator before
model loading:

```bash
cd /tmp/dgx-moa-phase1.6roKBd
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve planner
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve reviewer
```

The credential retry added only
`DGX_MOA_API_KEY='[REDACTED]'`. Its executor command did not pass a MoE-backend
override, so vLLM `0.22.1` selected FlashInfer-CUTLASS and began the first-run
SM121a build. After 9 of 96 objects, only that diagnostic executor was stopped;
the successful Task 0 executor retry added `DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN`:

```bash
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  DGX_MOA_API_KEY='[REDACTED]' XDG_CACHE_HOME=/home/kotori9/.cache \
  MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor

exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  DGX_MOA_API_KEY='[REDACTED]' DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor
```

Task 9 used the fresh root and environment established below. Its executor went
directly to MARLIN; the first reviewer command failed at CUDA
`cudaMemGetInfo` before weights, and the byte-for-byte same reviewer command
was retried after a 10-second memory-settle interval. Planner and the normal
gateway then started with the shown commands:

```bash
export TASK_RUN_ROOT=/tmp/dgx-moa-phase1-post.ahMvu6
export DGX_MOA_CONFIG="$TASK_RUN_ROOT/config.yaml"
export DGX_MOA_STATE_DB="$TASK_RUN_ROOT/state/gateway.db"
export DGX_MOA_BIND_HOST=127.0.0.1
export DGX_MOA_BIND_PORT=19000
export DGX_MOA_AUTH_ENABLED=true
export DGX_MOA_API_KEY='[REDACTED]'
export DGX_MOA_RUNTIME_CHANNEL=dev
export DGX_MOA_TRACE_ORIGIN=validation
export DGX_MOA_CONTROLLER_COMMIT=0d95591c86a81d6fcea290261a93917a3896d90e
export DGX_MOA_VLLM_VERSION=0.22.1
export DGX_MOA_PROJECT_ROOT=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent
export PYTHONPATH=/home/kotori9/dgx-moa-agent/compat
export VLLM_BIN=/home/kotori9/.pyenv/shims/vllm
export XDG_CACHE_HOME=/home/kotori9/.cache
export MAX_JOBS=1
export CMAKE_BUILD_PARALLEL_LEVEL=1

DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN setsid uv run python -m dgx_moa.serve executor \
  >"$TASK_RUN_ROOT/logs/executor.log" 2>&1 &
setsid uv run python -m dgx_moa.serve reviewer \
  >"$TASK_RUN_ROOT/logs/reviewer.log" 2>&1 &
sleep 10
setsid uv run python -m dgx_moa.serve reviewer \
  >"$TASK_RUN_ROOT/logs/reviewer-retry.log" 2>&1 &
setsid uv run python -m dgx_moa.serve planner \
  >"$TASK_RUN_ROOT/logs/planner.log" 2>&1 &
setsid uv run dgx-moa >"$TASK_RUN_ROOT/logs/gateway.log" 2>&1 &
```

The retained vLLM `0.22.1` argv confirms the executable flags and ports. The
executor had `--moe-backend MARLIN`; the unchanged reviewer retry did not pass
a backend override and vLLM selected MARLIN automatically:

```bash
/home/kotori9/.pyenv/shims/vllm serve /home/kotori9/models/dgx-moa/executor \
  --host 127.0.0.1 --port 8101 --served-model-name dgx-moa-executor \
  --max-model-len 65536 --max-num-seqs 1 --kv-cache-memory-bytes 1700000000 \
  --gpu-memory-utilization 0.5 --moe-backend MARLIN \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder

/home/kotori9/.pyenv/shims/vllm serve /home/kotori9/models/dgx-moa/reviewer \
  --host 127.0.0.1 --port 8103 --served-model-name dgx-moa-reviewer \
  --max-model-len 65536 --max-num-seqs 1 --kv-cache-memory-bytes 2300000000 \
  --gpu-memory-utilization 0.25 \
  --hf-config-path /tmp/dgx-moa-phase1-post.ahMvu6/data/run/reviewer-hf-config \
  --reasoning-parser cohere_command4
```

The old timing wrapper was launched exactly as follows and its request returned
HTTP `500`, 21 bytes, no DONE, and
`TypeError: TimedProvider.stream() got an unexpected keyword argument
'timeout_seconds'`:

```bash
setsid uv run python /tmp/dgx-moa-phase1.6roKBd/timed_gateway.py \
  >"$TASK_RUN_ROOT/logs/timed-gateway.log" 2>&1 &
```

The validation-only adaptation added the new keyword-only parameters and
forwarded them upstream:

```python
async def stream(
    self,
    role: str,
    model: ModelConfig,
    request: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
    stage: str | None = None,
) -> AsyncIterator[bytes]:
    upstream = await super().stream(
        role, model, request, timeout_seconds=timeout_seconds, stage=stage
    )
```

The retry command used the adapted ignored file and produced the retained HTTP
`200` measurement:

```bash
setsid uv run python .superpowers/sdd/task-9-timed-gateway.py \
  >"$TASK_RUN_ROOT/logs/timed-gateway-retry.log" 2>&1 &
```

OpenCode `1.17.18` first created its temporary configuration without a model
limit and ran the following exact bounded command:

```bash
sed 's#http://<DGX_TAILSCALE_IP>:9000/v1#http://127.0.0.1:19000/v1#' \
  config/opencode.example.json | \
  jq '. + {permission:{"*":"deny",read:"allow"}}' \
  >"$TASK_RUN_ROOT/opencode/normal/opencode.json"

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir "$TASK_RUN_ROOT/opencode/normal" --model dgx-moa/dgx-moa-agent \
  'Reply exactly OPENCODE_OK.' \
  >"$TASK_RUN_ROOT/opencode/normal/stdout.jsonl" \
  2>"$TASK_RUN_ROOT/opencode/normal/stderr.log"
```

It exited with API HTTP `400` and complete body
`{"error":{"message":"max_tokens exceeds server maximum
16384","type":"invalid_request_error","code":"invalid_request","param":"max_tokens"}}`.
The exact configuration transition and otherwise unchanged retry were:

```bash
jq '.provider["dgx-moa"].models["dgx-moa-agent"].limit={context:65536,output:16384}' \
  "$TASK_RUN_ROOT/opencode/normal/opencode.json" \
  >"$TASK_RUN_ROOT/opencode/normal/opencode.json.tmp"
mv "$TASK_RUN_ROOT/opencode/normal/opencode.json.tmp" \
  "$TASK_RUN_ROOT/opencode/normal/opencode.json"

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir "$TASK_RUN_ROOT/opencode/normal" --model dgx-moa/dgx-moa-agent \
  'Reply exactly OPENCODE_OK.' \
  >"$TASK_RUN_ROOT/opencode/normal/retry.stdout.jsonl" \
  2>"$TASK_RUN_ROOT/opencode/normal/retry.stderr.log"
```

Hermes Agent `0.18.2` attempt one used a config with no `model.api_key`:

```yaml
model:
  default: dgx-moa-agent
  provider: custom
  base_url: http://100.125.239.72:9000/v1
  context_length: 65536
  max_tokens: 16384

platform_toolsets:
  cli:
    - file
```

Its exact invocation supplied only the host-gated generic environment variable:

```bash
cd /tmp/dgx-moa-phase1-post.ahMvu6/hermes/work
HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes \
  OPENAI_API_KEY="$DGX_MOA_API_KEY" NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal.stderr
```

It reached `100.125.239.72:9000` but returned `HTTP 401: invalid bearer token`.
The only config transition was adding the environment reference beneath
`model`:

```yaml
  api_key: ${DGX_MOA_API_KEY}
```

The retry removed the ineffective `OPENAI_API_KEY` assignment, retained
`DGX_MOA_API_KEY='[REDACTED]'` in the supervisor environment, and used the same
Hermes interface:

```bash
HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stderr
```

Finally, the CPU-only timeout harness provider started normally, but the first
real-gateway launcher exited without binding because the module has no
`__main__` call. The console-entry-point retry was the only launcher change:

```bash
TIMEOUT_ROOT=/tmp/dgx-moa-timeout.uVbS91
DGX_MOA_API_KEY='[REDACTED]'
export DGX_MOA_API_KEY
setsid uv run python .superpowers/sdd/task-9-timeout-provider.py \
  >"$TIMEOUT_ROOT/logs/provider.log" 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run python -m dgx_moa.api \
  >"$TIMEOUT_ROOT/logs/gateway.log" 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run dgx-moa \
  >"$TIMEOUT_ROOT/logs/gateway-retry.log" 2>&1 &
```

#### Safely redacted physical commands

The following are the exact successful client and follow-up harness commands.
Only the credential value is replaced by `[REDACTED]`; temporary paths, output
redirections, models, prompts, headers, and options are retained. Failed and
successful launch/configuration transitions are recorded immediately above.

```bash
export DGX_MOA_API_KEY='[REDACTED]'

curl --fail --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  http://127.0.0.1:19000/v1/models

curl --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-curl-nonstream' \
  --data '{"model":"dgx-moa-chat","messages":[{"role":"user","content":"Reply exactly CHAT_OK."}]}' \
  http://127.0.0.1:19000/v1/chat/completions

curl --no-buffer --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-curl-stream' \
  --data '{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Reply exactly STREAM_OK."}],"stream":true}' \
  http://127.0.0.1:19000/v1/chat/completions

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir /tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal \
  --model dgx-moa/dgx-moa-agent 'Reply exactly OPENCODE_OK.' \
  >/tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal/retry.stdout.jsonl \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal/retry.stderr.log

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir /tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool \
  --model dgx-moa/dgx-moa-agent \
  'Use the read tool exactly once to read FIXTURE.txt, then reply OPENCODE_TOOL_OK followed by its content.' \
  >/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/stdout.jsonl \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/stderr.log

HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stderr

HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Use the read_file tool to read /tmp/dgx-moa-phase1-post.ahMvu6/hermes/work/FIXTURE.txt. Do not answer before using the tool. After the tool returns HERMES_PHYSICAL_FIXTURE, reply with exactly HERMES_TOOL_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool.stderr

setsid uv run python .superpowers/sdd/task-9-timeout-provider.py \
  >/tmp/dgx-moa-timeout.uVbS91/logs/provider.log 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run dgx-moa \
  >/tmp/dgx-moa-timeout.uVbS91/logs/gateway-retry.log 2>&1 &

curl --silent --show-error --max-time 10 \
  --dump-header /tmp/dgx-moa-timeout.uVbS91/timeout.headers \
  --output /tmp/dgx-moa-timeout.uVbS91/timeout.body.json \
  --write-out '%{http_code}' \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-executor-first-byte-timeout' \
  -H 'X-Runtime-Channel: dev' \
  -H 'X-Trace-Origin: validation' \
  -H 'X-Task-ID: TASK9-TIMEOUT' \
  -H "X-Workspace-Path: $PWD" \
  -H 'X-Workspace-ID: task9-timeout' \
  -H 'X-Repository-Branch: dev' \
  -H 'X-Repository-Commit: 391f968' \
  -H 'X-Dirty-State: clean' \
  --data '{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Reply exactly TIMEOUT_UNEXPECTED."}],"stream":true,"max_tokens":64}' \
  http://127.0.0.1:19100/v1/chat/completions
```

#### Trace audit, teardown, and acceptance boundary

- The isolated trace audit exited `1`: 13 sessions, 0 complete, 0 legacy, and
  0.0% mandatory-field completeness. All 13 lacked `session_ended` and
  `workspace_identity`; 12 lacked `task_id`; decision task IDs were also
  missing. The client/stream checks passed, but this is a real phase-one
  observability gap and prevents an all-gates completion claim.
- The original Task 9 post-documentation gate run reported `180 passed, 1
  warning in 1.93s`, `48 files already formatted`, Ruff success, MyPy success
  for 26 source files, clean systemd verification, clean shell syntax, and
  clean `git diff --check`. The repository trace audit was the only nonzero
  command: exit `1`, 10 total, 4 complete, 6 incomplete/legacy, 40.0%
  mandatory-field completeness, with `legacy_v1` missing for six sessions.
- Teardown stopped only the verified controlled groups: tailnet relay first,
  then isolated gateway, reviewer, and executor; planner had already been
  stopped for the backend-error check. Ports `8101`, `8102`, `8103`, `8104`,
  `8110`, `9000`, and `19000` were unbound afterward, the owned PIDs were
  absent, no NVIDIA compute process remained, and `MemAvailable` returned to
  `120329036` kB. All production units/targets remained inactive and the
  production `main` worktree remained clean.
- The phase-one design audit finds the intended public aliases, executor
  contract, field preservation, typed errors, bounded immediate streaming,
  native tool ownership, reviewer policy, output limits, truncation, timing,
  and explicit context override covered by direct files and the current
  181-test suite; the physical matrix proves the principal client and latency
  contracts.
  Formal Task 9 completion remains blocked by all three nonzero trace audits. The
  overall runtime-reliability Goal remains active for usage statistics,
  lifecycle and adaptive unloading, loading progress, memory-mechanism study,
  near-limit 64K validation, extended client matrices, soak, remaining docs,
  push, and PR work.

#### Final re-review gate matrix

After adding the Hermes contract test and the retained command transitions, the
complete eight-command matrix was rerun. Earlier `180`-test pre-runtime and
original Task 9 post-documentation results above remain chronological evidence;
the current suite contains `181` tests.

1. `uv run pytest -q`: exit `0`, `181 passed, 1 warning`.
2. `uv run ruff format --check .`: exit `0`, `48 files already formatted`.
3. `uv run ruff check .`: exit `0`, `All checks passed!`.
4. `uv run mypy`: exit `0`, no issues in 26 source files.
5. `systemd-analyze --user verify systemd/*`: exit `0`, no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: exit `0`, no output.
7. `scripts/audit-trace-completeness.sh data/traces`: exit `1`, 10 total,
   4 complete, 6 incomplete, 6 legacy, 40.0% mandatory completeness, and
   `missing_fields={"legacy_v1":6}`.
8. `git diff --check`: exit `0`, no output.

The two retained isolated audits were also rerun after the same edit:

- `/tmp/dgx-moa-phase1-post.ahMvu6/traces`: exit `1`, 13 total and 0 complete;
  all 13 lack `session_ended` and `workspace_identity`, 12 lack top-level and
  first-decision task IDs, 4 lack the second-decision task ID, and 2 lack the
  third-decision task ID.
- `/tmp/dgx-moa-timeout.uVbS91/traces`: exit `1`, 1 total and 0 complete; the
  sole gap is one missing `session_ended` event, with no missing fields.

## 2026-07-18 — Isolated physical lifecycle matrix (Task 10)

Task 10 ran only foreground development processes from commit
`ee2d714a1b7a4cac7fca4655fa035535da94c727`. The production worktree remained
read-only at clean `main` commit
`c2a9af0d6b5db8dd940842c56a7236ac867061ff`; no service manager, profile,
deployment, AppArmor, or Frontier command was used. The successful raw root is
`/tmp/dgx-moa-task10-yhs6_hr8`; it ran from
`2026-07-18T15:03:58.596447+00:00` through
`2026-07-18T15:24:34.850669+00:00`. Its API key existed only in the harness
environment and is redacted from the manifest and results.

### Retained failure transitions

The following failed attempts remain as evidence and were not converted into
passes:

- `/tmp/dgx-moa-task10-f7w_eqsb` stopped before starting any process because
  this GPU reports `0, [N/A], [N/A]` for memory fields. The root contains only
  empty directories, so it is an observed failed attempt, not retained raw
  result evidence. The parser now preserves those fields as JSON null with
  `memory_metrics_available=false`; its regression test passes.
- `/tmp/dgx-moa-task10-xofa35a1` observed a transient empty `/proc` argv while
  capturing the optional process identity. The harness failed closed. The
  retained result itself ends with `RuntimeProcessLeak` and a running planner.
  That exact planner identity was revalidated and stopped afterward, and
  current read-only checks find none of its processes or ports, but no retained
  artifact attests that later cleanup. Identity capture now retries only the
  transient empty-argv state and has a regression test.
- `/tmp/dgx-moa-task10-53voozpd` reached real model health after about 1,034
  seconds, but the initial 3,600-second lifecycle poll interval could not
  observe it before the 1,200-second load timeout. Exact teardown passed. Load
  polling is now 2 seconds while automatic idle/residency thresholds remain
  independently fixed at 7,200 seconds.
- `/tmp/dgx-moa-task10-wv_g_4bp` reached ready in about 1,026 seconds and proved
  12 typed loading responses, one start, monotonic measured-shard progress,
  retry success, and an active-request guard. Its stream assertion sampled
  after the real stream had already closed. The harness now requires a fresh
  blocked scheduler decision while the stream lease is open and then requires
  a cancelled terminal state with `stream_aborted` and without
  `stream_completed`.
- `/tmp/dgx-moa-task10-uv1pt8ub` passed that stricter stream-disconnect proof,
  then exposed a real compatibility defect: vLLM returned a non-empty
  `message.tool_calls` with `finish_reason=stop`, so the gateway did not create
  a continuation lease. The run stopped only its exact owned groups and
  returned memory. The broader reliability goal authorized the separate source
  remediation commit `ee2d714`, made between validation attempts: the gateway
  now treats a validated non-empty tool-call payload as continuation evidence
  while preserving the provider's original finish reason. The new regression
  first failed, then the relevant three tests and the full 531-test suite
  passed. Task 10's final tracked change remains documentation-only.
- `/tmp/dgx-moa-task10-d36rm7e7` was the first result with all physical rows
  marked passed, but independent evidence review rejected it as final proof:
  traces retained raw objective/model/tool content, the v1 manifest overwrote
  the first executor identity on reload, and final host `MemAvailable` was
  `767856640` bytes below its initial snapshot after 120.19 seconds. Its rows
  remain useful diagnostic evidence, but the run is superseded by the final
  root above.

### Preflight, runtime, and immutable inputs

Immediately before the successful run, all eight non-mutating gates exited
zero: `uv run pytest -q` reported `531 passed, 1 warning`; Ruff format reported
53 files; Ruff check and MyPy for 28 source files passed; unit-file verification,
all shell syntax checks, and `git diff --check` were clean; the checked-in trace
audit reported 10/10 complete and 100.0% mandatory-field completeness. The
ignored harness also passed 9 tests, Ruff format/check, Python compilation, and
its dry run.

Preflight `MemAvailable` was `120673374208` bytes against the 80-GiB start gate
and 40-GiB continuous floor. Loopback ports were gateway `19200`, executor
`19201`, and optional `19202`; production ports `9000`, `8101`-`8104`, and
`8110` were unbound. There was no unowned DGX MoA/vLLM runtime. The exact
executor command retained `--max-model-len 65536`, `--max-num-seqs 1`,
`--kv-cache-memory-bytes 1700000000`, `--gpu-memory-utilization 0.5`,
`--moe-backend MARLIN`, automatic tool choice, and the `qwen3_coder` parser on
`127.0.0.1:19201`. Installed versions were vLLM `0.22.1`, OpenCode `1.17.18`,
and Hermes Agent `0.18.2`.

The model path metadata fingerprint was unchanged before and after: revision
`27a8f16f463b9a13c91c332c40cf93e09717347e`, metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
82 files, 4 directories, `47613238658` total bytes, and the same newest mtime.
This is a path/count/size/mtime/revision fingerprint, not a content hash or a
byte-for-byte model comparison.

The final run seeded only `cache` and `home/.cache/flashinfer` from the earlier
isolated root `/tmp/dgx-moa-task10-d36rm7e7`; provenance is recorded in
`cache-seed.json` and preflight. Root-dependent cache keys still caused the
first engine to rebuild much of its initialization path, so the seed is not
claimed as a complete cold-start cache hit.

### Successful physical rows

- Cold/single-flight: 12 concurrent real loopback requests all returned HTTP
  `503` with typed code `model_loading` in `0.14082865789532661` seconds, and
  the manifest recorded exactly one executor start.
- Progress/ready: observations followed `process_starting` ->
  `loading_weights` -> `initializing_engine` -> `warming_up` -> `ready`.
  Measured shard progress was monotonic and reached 100% without treating later
  initialization or warmup as ready. The lifecycle measured load duration was
  `942.7537190914154` seconds and the status wait was
  `944.0529136529658` seconds. vLLM separately logged weight loading in
  `238.88` seconds, model loading in `249.978614` seconds using 44.31 GiB, and
  initial profiling/warmup in `580.42` seconds. It reported a 67,121-token KV
  cache and 1.02x maximum concurrency for a 65,536-token request. The real retry
  returned HTTP `200` with `finish_reason=stop`.
- Guards: a real non-stream request held `active_request_count=1`; a real stream
  held `active_request_count=1` and `open_stream_count=1`, produced a fresh
  `reason=blocked` idle decision, and after downstream close ended
  `cancelled` with `stream_aborted` and no `stream_completed`; a real forced
  tool call held `continuation_lease_count=1`, and its matching real tool-result
  continuation released it. Each scheduler check left the executor ready.
- Timeout: a real request under the controlled 0.001-second executor total
  limit returned HTTP `504` with typed code `executor_total_timeout`.
- Ordered unload: after three manual hysteresis checks, the optional process
  stopped before the executor. The optional sample took
  `0.29537057876586914` seconds; the single executor unload sample took
  `1.361647605895996` seconds and ended in `cold`. Memory settlement took
  `6.216998043004423` seconds and there was no rapid retry.
- Reload: the next real request returned typed loading HTTP `503`, the manifest
  recorded exactly the second executor start, ready returned in
  `273.00104479002766` seconds, and the retry returned HTTP `200`. vLLM logged
  the second weight load at `237.30` seconds, model load at `248.278115`
  seconds, and profile/KV/warmup at `9.22` seconds including `2.86` seconds of
  compilation.
- Traces: the isolated success, disconnect/cancellation, and timeout roots each
  audited 1/1 complete with 100.0% mandatory-field completeness. The checked-in
  corpus independently audited 10/10 complete at 100.0%. Before final artifact
  capture, all six isolated trace files were atomically sanitized; objectives
  and model decisions use explicit placeholders, tool-event payloads retain
  only `content_redacted=true`, and raw tool/evidence fields are empty. A
  structural check over the seven root records plus three audit copies found
  zero violations, the three copies match their sanitized roots by SHA-256,
  and a known-sensitive-string scan found no match. These audits prove
  structural completeness, not semantic success: the named success trace has a
  completed `session_ended` event but top-level `final_status=degraded`. The
  separately reviewed sanitizer code and tests require a final teardown pass
  and make the harness fail closed if sanitization cannot complete.

### Memory and exact teardown

`nvidia-smi` was available but this unified-memory GPU exposed neither used nor
free byte fields, so every GPU byte value is null and no GPU percentage is
inferred. Host and exact-owned-process measurements were:

| Point | MemAvailable bytes | owned PSS bytes | owned RSS bytes |
| --- | ---: | ---: | ---: |
| initial | 120509042688 | 0 | 0 |
| warm ready | 65156329472 | 4532602880 | 4947398656 |
| immediately before ordered unload | 65325219840 | 4655138816 | 5070721024 |
| immediately after unload | 120379711488 | 0 | 0 |
| best bounded unload settle | 120564150272 | 0 | 0 |
| final after reload teardown | 120676032512 | 0 | 0 |

The final snapshot exceeded the initial snapshot by `166989824` bytes, while
exact-owned PSS/RSS were zero. This supports full process-memory return within
host `MemAvailable` snapshot noise; it does not establish a GPU-byte result
because those metrics were unavailable. The earlier `d36rm7e7` shortfall is
retained above rather than generalized away.

The v2 manifest preserves full history rather than only the latest role entry:
planner PID/PGID/session `1249683`, first executor `1249697`, and reloaded
executor `1274552`, each with start ticks, cwd, requested and observed argv,
start time, stop time, and `state=stopped`. It records planner start once and
executor start exactly twice, then planner stop, first executor stop, and final
executor stop. Each kill was limited to a recorded PID=PGID=session group after
leader and group-member identity revalidation.

The point-in-time, scoped final fingerprint found loopback ports
`19200`-`19202` and production ports
`9000`, `8101`-`8104`, and `8110` unbound, no DGX MoA/vLLM runtime process,
clean unchanged production, clean dev at `ee2d714`, and the unchanged metadata
fingerprint. The successful physical result contains no failures and reports
`passed=true`.

### Final post-documentation gates

An earlier post-documentation attempt launched all eight commands concurrently.
It found one real documentation-contract mismatch because the historical `527
passed` baseline had been replaced rather than retained, and one asynchronous
progress test missed its bounded scheduler-yield observation while CPU-heavy
gates ran beside it (`529 passed, 2 failed`). The historical line was restored
alongside the current baseline. The progress test then passed 10 of 10 isolated
repetitions, matching the earlier green full-suite runs; no lifecycle code
changed for that transient scheduling failure.

After the evidence correction, the first serialized gate run exited zero for
all eight commands. A verification rerun after recording that result then
reproduced the same test race even without concurrent gates: 530 passed and
`test_coordinator_preserves_prior_progress_when_new_logs_are_invalid` failed
while its background load was still `process_starting`. The isolated test
reproduced on repetition 12. Its bounded loop of 100 `asyncio.sleep(0)` yields
did not guarantee completion of the coordinator's `to_thread` calls.

Separate test-only commit `8cd8117` replaced yield counting with an event set
on entry to the second poll sleep. Runtime code did not change. The corrected
test passed 100/100 isolated repetitions, the full suite passed 531/531, and an
independent review confirmed that `coordinator.close()` still cancels and
collects the blocked task. Task 10's final tracked commit remains limited to
this documentation.

The final serialized gate run after that test stabilization exited zero for all
eight commands:

1. `uv run pytest -q`: `531 passed, 1 warning`.
2. `uv run ruff format --check .`: `53 files already formatted`.
3. `uv run ruff check .`: `All checks passed!`.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, 0
   incomplete, 0 legacy, and 100.0% mandatory-field completeness.
8. `git diff --check`: no output.

## Role-Aware Lifecycle Gap Closure — 2026-07-20

The implementation commits add strict role policies, persisted generations and
unload queues, content-free per-role usage statistics, the complete cold 503
progress contract, a bounded global automation circuit, and atomic rollback.
The first full regression after implementation passed `567` tests with the one
existing third-party Starlette TestClient deprecation warning.

After the never-started-unit fix and documentation contract update, the final
serialized gates all exited zero: `572 passed` with the same warning; 55 files
Ruff-formatted; Ruff lint clean; MyPy clean for 29 source files; user-systemd
unit verification clean; every `scripts/*.sh` syntax check clean; checked-in
trace audit 10/10, zero legacy/incomplete and 100%; and `git diff --check` clean.

The physical control-plane harness used a fresh `/tmp` root, random loopback
ports, a separate config/state/run tree, and PID-unique runtime-linked user
systemd units for gateway, executor, planner, reviewer, and reasoner. It used
the real gateway/lifecycle/systemd/journal path with fake model weights; no
production unit was a command target.

Two retained failed attempts improved the validation itself:

- `/tmp/dgx-moa-systemd-control-20bt5iys` queried nonexistent `/health` instead
  of `/healthz`; the gateway was healthy and cleanup/production equality passed.
- `/tmp/dgx-moa-systemd-control-rvw5v3od` found a real fresh-install defect:
  a never-started unit had no unit journal cursor and failed with
  `cursor_malformed_output`. Commit `9fa2801` added a tested global
  user-journal cursor fallback while keeping subsequent reads exact-unit scoped.
- `/tmp/dgx-moa-systemd-control-9947ve4w` passed cold, MoA, unload, and reload;
  its circuit fixture incorrectly expected three retries from one role despite
  the role-local retry cap of two. The final fixture injected two reasoner and
  one reviewer failures to test the actual global circuit contract.

The authoritative result is
`/tmp/dgx-moa-systemd-control-wbakbkm9/physical-result.json`, SHA-256
`83ecea14eec43543f22bddf00dccff0e208d45e2e84609820891d54a939c8fdf`,
with `passed=true`:

- initial executor/planner/reviewer/reasoner states were all `cold`;
- five concurrent cold requests all returned JSON 503, generation 1 and
  unavailable honest weight progress, with exactly one executor start;
- all four roles reached `ready`, each with one start, and orchestration returned
  HTTP 200;
- all four roles idled to systemd `inactive` under the accelerated isolated
  policy;
- executor request/retry produced generation 2, exactly two cumulative starts,
  and HTTP 200;
- three cross-role start failures opened the circuit; the fourth request returned
  `lifecycle_automation_disabled`, performed zero mutation, and ready executor
  traffic still returned HTTP 200;
- rollback passed twice, removed the unit map, reset the latch, restarted the
  isolated gateway, and reported lifecycle disabled;
- production commit `e63fa6f`, clean state, gateway/executor PIDs, and listeners
  9000/8101 were byte-for-byte equal before and after; all dev runtime units were
  removed.

This result adds no real-weight memory or load-time claim. Duplicating the active
45G production executor would have violated the safety floor, and production was
not stopped or altered. Phase 3 remains authoritative for real executor
full-stop memory recovery.

Independent review then identified that the adaptive scheduler read the newest
overall role rows before filtering successes. A sufficiently large burst of 503
or failed rows could therefore displace valid successful gaps despite the
required “recent successful requests” window. Commit `87f45e3` moved the
`success=1` predicate into SQLite before the policy limit and added a regression
with newer failures hiding older successes. The post-fix full suite passed 569
tests with the same third-party warning; Ruff and MyPy were clean.

The next review pass found two more Important contract gaps. Observe mode had
kept managed records cold without reading actual service state, so it could only
record `state_not_ready`; it now performs exact-unit status and health reads but
still cannot start, stop, or sample unload memory. A separate parser gap allowed
nonfinite journal counters or an unexpected parser exception to fail the load;
numeric counters now require finite values and all parser exceptions preserve
prior progress or `unavailable` while readiness continues. Focused red/green
tests cover both paths. The post-fix full suite passed 572 tests with the same
warning; Ruff and MyPy were clean.

## Phase 4 Physical Client and PR Gate — 2026-07-19

The content-free summary is
`/tmp/dgx-moa-phase4-s5gy6ydh/summary.json`, SHA-256
`5249dd396c4ac8b6ed85e4474fb7c631f504055685138be90791999f03928a8f`.
It has schema `phase4-pr-gate-summary-v1`, `passed=true`, and no blockers.
Source SHA-256 values are:

- client matrix:
  `a805eba3314ef3dee96646eea687def52238a40184543e38fc15c8e715e74cdc`;
- lifecycle result:
  `9f2412e59641a667bacc475b22d1bc90fa0f616becb2fb45ee4b34509154c9f3`;
- retained-root sanitization:
  `e4561c6620bf6607d52b77149a63e3c87ee9ad363c3a76c40718dcfad76147e4`.

| Contract | Physical pass count |
| --- | ---: |
| Generic non-stream / stream / >1,000-token long | `5` / `10` / `3` |
| Native forced tools / continuations / multi-step loops | `5` / `3` / `1` |
| OpenCode read / small edit / multi-file / bounded engineering | `2` / `2` / `1` / `1` |
| Hermes normal / stream / tool / multi-step | `2` / `1` / `1` / `1` |

All ten Generic streams recorded `malformed=0`, exactly one `[DONE]`, and the
first event before completion. Each long case used `max_tokens=5000`, returned
`4393` completion tokens, and parsed 1,100 finite numeric items. The linked
near-limit authority remained the Phase 3 selected result: three HTTP 200
cycles at 63,786 prompt tokens and executor context 65,536.

OpenCode `1.17.18` ran six physical cases with isolated HOME/XDG/TMP roots.
Read cases had no effects; edit cases matched exact allowed paths and hashes;
the bounded task modified only `calc.py` plus known test cache artifacts and
passed independent pytest. Hermes Agent `0.18.2` ran five cases with isolated
HOME/XDG/TMP and `HERMES_HOME`. Gateway observation proved the designated
stream case sent `stream=true`; file-tool effects and API-call counts matched.
Other measured clients were curl 8.5.0, HTTPX 0.28.1, and OpenAI Python 2.6.1.

The final lifecycle run returned twelve typed loading 503 responses with one
executor start, reached ready with nondecreasing progress in
`269.0157511299476` seconds, and retried with 200. Active-request, stream, and
continuation leases blocked unload. Idle policy stopped planner before executor,
returned the executor to cold, and raised MemAvailable from `66538033152` to
`121120661504` bytes. The next request returned 503, produced exactly the
second executor start, reached ready in `270.9573212391697` seconds, and
retried with 200. Success/disconnect/timeout traces were each 1/1 complete and
the checked-in corpus remained 10/10 complete at 100% mandatory fields.

The explicit serial validation window was `3064.0628089904785` seconds
(`51m 4.063s`) and included chat, stream, tool, OpenCode, Hermes, idle, unload,
and reload. It is not a continuous-load or 24-hour soak claim. Production
pre/post Git/index, tracked-file metadata, unit, port, and runtime snapshots
were equal. Production mutation and leaked process/listener counts were zero.

After evidence extraction, retained client stores, DBs, logs, forbidden
fields/values, unparseable JSON, and raw DB/log files all audited to zero.
Independent review concluded `Critical=0`, `Important=0`. The gate authorizes
only a draft `dev`-to-`main` PR; it does not authorize merge, deployment, unit
changes, or production restart.

### Final publication verification

The publication gate requires the following results on the final committed
tree; they were rerun after this record was committed and before push:

1. `uv run pytest -q`: `533 passed`, one existing deprecation warning.
2. `uv run ruff format --check .`: `53 files already formatted`.
3. `uv run ruff check .`: all checks passed.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: exit zero, no output. This is the
   repository's existing systemd gate; the plan's named
   `scripts/validate-systemd.sh` does not exist.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: exit zero, no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, zero
   incomplete/legacy, 100% mandatory-field completeness.
8. `git diff --check origin/main...HEAD`: exit zero, no output.
9. Ignored Phase 4 harness: `16 passed`; Ruff format/check and MyPy passed.
10. Retained-root audit: summary passed with no blockers; source validator
    errors, forbidden fields/values, JSON parse errors, raw DB/log files,
    production mutation, leaked ports/processes, Critical findings, and
    Important findings were all zero. The current production full snapshot
    equaled the lifecycle post-snapshot.

## Phase 3 Unload Mechanism Study — 2026-07-19

### Pre-execution gates and scope

Before any model process started, the serialized repository gates passed:
`uv run pytest -q` reported `531 passed, 1 warning`; Ruff format/check, MyPy for
28 source files, user-unit verification, all shell syntax checks, and
`git diff --check` exited zero; the checked-in trace audit remained 10/10
complete at 100.0%. The ignored phase-three harness passed 21 tests before the
first physical attempt and 26 tests after the retained tokenizer, systemd
collection, request-timeout, and resume corrections. Its ignore-aware Ruff,
Python compilation, and direct installed-Python dry run passed.

Trials used only fresh paths under `/tmp/dgx-moa-phase3-*`, loopback port
`19301`, and exact transient units matching
`dgx-moa-dev-phase3-[a-f0-9]{8}.service` or exact Task 10-style owned
PID/PGID/SID groups. Production remained read-only `main` at `c2a9af0`; no
production service or port was acted on.

### Retained attempts

- `/tmp/dgx-moa-phase3-52ffwbov` failed before process start because
  Transformers 5.8 returned `BatchEncoding` while the runner counted mapping
  fields instead of `input_ids`. A failing regression was added; the real
  tokenizer then produced `63786` tokens.
- `/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms.json`, SHA-256
  `6a5ce3ba6055f265f93e6f7a06752bbd883002bcbabf65512ab109db3e440994`,
  preserves the first complete A-D attempt. A finished short/tool/near-limit
  HTTP 200 requests and stopped cleanly, but `systemctl show` represented its
  collected unit as `LoadState=not-found` with an empty working directory; the
  runner misclassified that as a mismatched live unit. B reached ready in
  `938.83` seconds but its sleep call exceeded httpx's five-second default.
  C was deliberately interrupted and exactly torn down rather than spending a
  full cold load on the known timeout bug. D reached ready in `952.86` seconds,
  completed live reset HTTP 200, and then failed its first exact post-reset
  short quality check.
- Tests first fixed `LoadState=not-found` normalization and physical endpoint
  timeout propagation. Resume did not rewrite the original. The authoritative
  `/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms-resumed.json`, SHA-256
  `625b25afbadbb1e8ef42f95e836df627ec22e37c87e07301102eaaa6194b6af9`,
  links the original SHA and retains its per-row failure summaries.

### Final physical result

The resumed result reports `passed=true`, no harness failures, and selection
`A_full_systemd_stop_start` with the same mechanism preserved as fallback.

- A passed two exact transient-unit cycles. Cold/warm ready times were
  `946.3586723739281` and `272.0807015961036` seconds; stop times were
  `1.146820979192853` and `1.118467804044485` seconds. MemAvailable deltas were
  `55227699200` and `54869725184` bytes. Short and forced native-tool checks
  passed. Backend prompt usage was `63786` tokens twice, with near-limit
  latencies `17.792744473088533` and `17.567367010051385` seconds.
- B level-1 sleep was natively supported and completed two cycles. Sleep times
  were `21.733480336144567` and `2.1252455201465636` seconds; wake times were
  `38.78946190699935` and `7.454574962845072` seconds. Its median
  `25938081792`-byte return was 47.12% of A, below the required 90%, and owned
  PSS did not remain stable. Short/tool checks and backend `63786`-token quality
  still passed, so the rejection is memory/stability-based rather than a
  capacity failure.
- C level-2 sleep and wake routes returned HTTP 200 after a
  `941.2777812271379`-second ready. Pre-sleep short/tool checks passed; the first
  post-wake exact short check failed, so no second-cycle, memory-selection, or
  near-limit claim is made.
- D's live reset route returned HTTP 200 after a `952.8551460539456`-second
  ready. Two identical-prefix probes passed with 1560 prompt tokens and
  `0.701514609856531`/`0.4988313359208405` seconds latency. The first exact
  post-reset short check failed, so reset is a rejected cache-clear result, not
  an unload mechanism.

The final point-in-time fingerprint found phase-three and production ports
unbound, runtime process count zero, unchanged clean dev/production commits,
and the unchanged model metadata fingerprint. GPU used/free byte metrics were
null, and no GPU percentage is inferred. Result JSON passed the recursive
content-free scan; retained manifests contain only the literal
`redacted-environment-only` API-key descriptor, not a credential. Detailed
selection math and limitations are in `docs/MEMORY_OPTIMIZATION.md`.

Independent read-only raw-evidence review passed with no blocker. It matched the
original SHA link, prior-attempt summaries, A identities and cgroups, all A/B
quality/timing/memory values, deterministic 90% calculation, C/D route success
followed by generic quality rejection, and the final fingerprint. It also
confirmed result/log redaction. Review limits are retained rather than promoted
away: A's systemd identities exist in resumed JSON while its generic foreground
manifests/events are empty; C/D failed text is intentionally unavailable; two
samples do not form a robust distribution; MemAvailable is noisy, GPU bytes are
null, and model equality is metadata-only. One vLLM shutdown log reports
`resource_tracker` semaphore cleanup, with no surviving process, port, PSS, or
RSS in the final checks.

## Phase 3 65,536-Token Candidate Study — 2026-07-19

The authoritative content-free result is
`/tmp/dgx-moa-phase3-7vfm7bzv/candidates-confirmed.json`, SHA-256
`10f233b47acfb52e54ee41532963d68e38831e7337818d4335b57f3bc2eaad03`.
It reports `passed=true`, no failures, and selection `baseline`. The final
fingerprint records clean dev `eb165d3`, clean production `main` at `c2a9af0`,
unchanged model revision `27a8f16` and metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
all scoped phase-three/production ports unbound, and runtime process count zero.

All physical candidates kept `--max-model-len 65536` and
`--max-num-seqs 1`. Baseline, FP8, eager, chunked-8K, and CPU-offload screening
reported exactly 63,786 backend prompt tokens with the expected needle and
`finish_reason=stop`. KV offload failed during startup because the installed
hybrid layout required a GPU block size divisible by its hash block size;
teardown still left PSS/RSS zero. Prefix-off was rejected without process start
because the installed baseline already disabled prefix caching.

The final baseline and eager trials passed the complete contract:

| Check | Baseline | Eager |
| --- | ---: | ---: |
| cold ready | `934.9303155951202s` | `912.4722288539633s` |
| near-64K latency / reported prompt tokens | `17.774531355826184s` / `63786` | `20.046998847974464s` / `63786` |
| five short cases / forced native tools | 5/5 / 3/3 | 5/5 / 3/3 |
| long numeric items / completion tokens / latency | `1100` / `4393` / `113.90377882798202s` | `1100` / `4394` / `203.29746027011424s` |
| restricted code / strict reviewer JSON | pass / pass | pass / pass |
| warm owned PSS | `4545508352` | `3859753984` bytes |
| warm MemAvailable | `66737324032` | `66124435456` bytes |
| owned-memory growth | `512000` | `385024` bytes |
| post-stop owned PSS/RSS | `0` / `0` | `0` / `0` |

Although eager lowered owned PSS by `685754368` bytes, its warm MemAvailable
was `612888576` bytes lower than baseline. The fixed `268435456`-byte noise
band therefore rejected eager before the lowest-PSS tie-breaker. The selected
baseline settings are the existing `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN; Task 4 requires no source change.

FP8 used `--kv-cache-dtype fp8 --calculate-kv-scales` with `900000000` KV
bytes, reached capacity 68,560 tokens, and required no capacity retry. The
installed hybrid path disabled calculated dynamic scales and checkpoint scales
were absent. Its warm PSS was `4537163776`, only `8344576` bytes below the final
baseline and far inside the noise band. Its retained full-contract failure was
from the superseded long fixture. FP8 is noncompetitive on memory; that retained
failure cannot be attributed to model quality.

The runner retained each correction rather than rewriting evidence. The
diagnostic result at `/tmp/dgx-moa-phase3-dktd_9pv/long-diagnostic.json`, SHA-256
`e165f0d227cfe2713a8bee901567eee23fe3931c2cfd960ca5a209ddf9cc0340`,
proved that the first long request parsed finite numbers but exhausted its
1,400-token cap after 700 items. The 2,400-token repeat still did not
self-terminate. The confirmed request enumerated 1 through 1100 and used an
`END` stop with a 5,000-token cap. A later `ENOSPC` attempt is preserved in
`candidates-verified.partial.json`: baseline's log records nvcc failing to write
a generated C file, then eager cache seeding also failed. Only derived
experiment cache directories were removed. The current harness now gates on 10
GiB free disk, but the confirmed artifact predates and did not exercise that
gate.

The ignored harness finished with 60 passing tests plus ignore-aware Ruff and
Python compilation. No prompt, model output, native tool argument value,
Authorization header, API key, or model weight is present in result JSON;
normalized output SHA-256 and content-free usage metadata are retained instead.
GPU used/free byte fields remained null, so no GPU percentage is claimed. This
remains undeployed development evidence; production was not started, stopped,
restarted, edited, or deployed.

## Phase 3 Selected Full-Stop Repetition and Resident Handoff — 2026-07-19

The authoritative independently reviewed result is
`/tmp/dgx-moa-phase3-1vjxvw8w/selected.json`, SHA-256
`fb2fc9261509acf4b51fad4b201b5210bd5a9bcb6c578006c45856e2692e7f9b`.
It has schema `phase3-selected-systemd-v1`, `passed=true`, no failures, selected
candidate `baseline`, and mechanism `A_full_systemd_stop_start`. The earlier
direct-process repetition at `/tmp/dgx-moa-phase3-kp3gj7ms/selected.json`,
SHA-256 `09fc8090771c4f665b8943c9e410b5e21595dc03bf422be833866f637b79655e`,
is retained as non-authoritative failed evidence: it proved exact process
teardown but did not execute the selected transient-systemd mechanism.

All three authoritative cycles used transient unit
`dgx-moa-dev-phase3-e6a0d509.service` with distinct invocations and PIDs
`2368754`, `2395854`, and `2442335`. In every row PID, PGID, and session ID were
equal; cwd, exact baseline argv, and unit-named cgroup were recorded; identity
revalidation passed immediately before stop; and the collected unit was absent.

| Cycle | ready | near-64K latency / backend tokens | PSS growth | post PGID PSS/RSS | post cgroup PSS/RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `938.3187154009938s` | `17.752001809887588s` / `63786` | `45056` bytes | `0` / `0` | `0` / `0` |
| 2 | `270.0974161340855s` | `17.56501955492422s` / `63786` | `2690048` bytes | `0` / `0` | `0` / `0` |
| 3 | `274.08552565216087s` | `17.564852259820327s` / `63786` | `2891776` bytes | `0` / `0` | `0` / `0` |

Each cycle passed five short cases, the expected near-limit needle,
the 1,100-item ascending numeric response, three native tool calls, restricted
code validation, and strict reviewer JSON. Port 19301 was unbound after every
stop. The post-third-cycle isolated gateway request on port 19300 returned 200
and advertised context length 65,536 for all three public aliases; only status
and configuration metadata were retained.

The final fingerprint records dev `6f8ab4d`, clean production `main` at
`c2a9af0`, unchanged model revision `27a8f16` and metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
all scoped ports unbound, and runtime count zero. The transient unit currently
has `LoadState=not-found` and MainPID zero. Results are content-free; the
independent review passed after rejecting and preserving the first mechanism
mismatch.

The tracked resident target change is undeployed. It requires only gateway and
executor, waits only for executor readiness, and verifies all optional resident
services/ports stopped on profile stop. Optional services retain `PartOf` for
cleanup. Lifecycle remains disabled with an empty unit map; a later
human-reviewed deployment is required for fixed/adaptive on-demand loading and
typed cold-role `503` behavior. Rollback restores the previous gateway,
executor, planner, and reviewer target requirements plus the prior script
arrays. No production process, unit, worktree, or deployment was mutated.

## Phase 3 Python Gateway Residency and Rust Decision — 2026-07-19

The authoritative five-minute content-free result is
`/tmp/dgx-moa-phase3-gateway-nzacnu_v/gateway-probe.json`, SHA-256
`4513ca3f6980f7fcfb81d7f7a360851325fcd7f90cddcb475f2612c17f2f6d62`.
It reports `passed=true`, no failures, 600 samples at 500 ms intervals, and
`300.02134908083826` seconds measured. The isolated gateway became ready in
`0.20371862896718085` seconds.

Peak process-group PSS/RSS was `48741376` / `56139776` bytes. Idle CPU was
`0.24998221036527596%` of one core. Loopback `/healthz` latency
p50/p95/p99/max was `1.5531240496784449` / `1.894660061225295` /
`2.1657010074704885` / `2.8134610038250685` ms. Schedule-drift
p50/p95/p99/max was `0.16089505515992641` / `0.685602892190218` /
`0.7837000302970409` / `1.084138872101903` ms.

The predeclared Rust rejection thresholds were PSS at most 256 MiB, CPU at most
1%, p99 at most 50 ms, and no remaining Python-attributable correctness gap.
The focused lifecycle/API/runtime-status recovery run passed `360` tests with
only the existing Starlette TestClient deprecation warning. All conditions
therefore reject a Rust rewrite for Phase 3; no crate or improvised prototype
was created. The gateway peak PSS is about 1.07% of the selected executor's
`4545508352`-byte warm owned PSS.

PID, PGID, and session were all `2478575`; identity was revalidated before the
exact group stop. Post-stop owned member count, PSS, and RSS were zero, the port
was unbound, and runtime process count was zero. Production stayed clean and
unchanged at `c2a9af0d6b5db8dd940842c56a7236ac867061ff`.

The first executable smoke root,
`/tmp/dgx-moa-phase3-gateway-r8uzjlp_`, is retained as non-authoritative failed
evidence: a probe-only log-directory ordering defect occurred before child
start, with the port still unbound. The corrected three-second smoke passed at
`/tmp/dgx-moa-phase3-gateway-rf8b296y/gateway-probe.json`, SHA-256
`4cdcf0f40e124818236d52175c9dd29a9e47880017a697d796752a260405d1da`.
Detailed responsibilities and limitations are in `docs/RUST_EVALUATION.md`.

## Phase 3 Publication Cross-check — 2026-07-19

The published topology comparison preserves the earlier measured rows rather
than substituting the later candidate run. The contemporaneous checked-in
validation record says the older three-role 64K resident profile recorded
`18525147136` bytes MemAvailable after planner start. No retained raw artifact
was available to the final independent review for that historical row. Task 10's
isolated executor-only lifecycle row recorded `65156329472` bytes warm-ready
MemAvailable, `4532602880` bytes owned PSS, and `4947398656` bytes owned RSS.
Its initial cold snapshot was `120509042688` bytes; the best post-unload settle
was `120564150272` bytes with owned PSS/RSS zero. Cold load, warm reload, and
executor unload were `942.7537190914154`, `273.00104479002766`, and
`1.361647605895996` seconds. The separate full-stop mechanism stops were
`1.146820979192853` and `1.118467804044485` seconds. Sleep-level-1 sleep/wake
times were `21.733480336144567` / `38.78946190699935` and
`2.1252455201465636` / `7.454574962845072` seconds; speed could not overcome
its memory/stability rejection.

Retained Phase 3 roots and their roles are explicit:

- `/tmp/dgx-moa-phase3-52ffwbov`: empty retained path from the pre-process
  tokenizer-count failure. Its cause comes from the contemporaneous run record
  and cannot be independently reconstructed from this raw root.
- `/tmp/dgx-moa-phase3-9l7a3ayp`: original mechanism failures plus the linked
  authoritative resumed result; the original was not rewritten.
- `/tmp/dgx-moa-phase3-dktd_9pv`: content-free long-fixture diagnostic.
- `/tmp/dgx-moa-phase3-7vfm7bzv`: candidate generations and partials, including
  the retained `ENOSPC` attempt, plus the authoritative confirmed selection.
- `/tmp/dgx-moa-phase3-kp3gj7ms`: quality-passing direct-process repetition
  rejected as non-authoritative because it did not run the selected transient
  systemd mechanism.
- `/tmp/dgx-moa-phase3-1vjxvw8w`: authoritative three-cycle transient-systemd
  repetition and gateway advertisement probe.
- `/tmp/dgx-moa-phase3-gateway-r8uzjlp_`: probe-only directory-order failure
  before child process start.
- `/tmp/dgx-moa-phase3-gateway-rf8b296y`: corrected three-second probe smoke.
- `/tmp/dgx-moa-phase3-gateway-nzacnu_v`: authoritative five-minute Python
  residency measurement.

Every selected physical result is content-free and reports exact teardown. Host
MemAvailable remains system-wide and noisy; GPU used/free bytes remain null;
the executor equality check is revision plus path/count/size/mtime metadata,
not a model-content hash. The checked-in resident target and lifecycle contract
are undeployed, and Phase 3 made no tracked trace-schema change.

### Serialized pre-commit publication gates

All eight commands ran sequentially and exited zero:

1. `uv run pytest -q`: `533 passed`, one existing third-party Starlette
   TestClient deprecation warning.
2. `uv run ruff format --check .`: 53 files already formatted.
3. `uv run ruff check .`: all checks passed.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, zero
   incomplete/legacy, 100.0% mandatory-field completeness.
8. `git diff --check`: no output.
