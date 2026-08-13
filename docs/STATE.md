# State

Updated: 2026-08-12

## Current decision authority

Use this section for current engineering decisions. Later sections and frozen
protocol-epoch documents preserve historical evidence; when they conflict with
this section, they are not current implementation authority.

| Topic | Current decision | Superseded interpretation |
| --- | --- | --- |
| Executor target | Pinned Mistral Small 4 NVFP4 revision, context `131072`, `max_num_seqs=1`, 3.4 GB initial KV; explicit FlashInfer B12x is the qualified Blackwell-native candidate and MARLIN remains rollback evidence | The Phase 3 65K/1.7 GB profile is rollback and comparison evidence, not the production target |
| Memory | Approximately 96 GiB steady-state with sufficient system headroom is an optimization target | 96 GiB is not a hard acceptance limit and crossing a 96 GiB experiment watchdog is not, by itself, backend rejection |
| CUDA execution | Production qualification requires an active, physically measured CUDA Graph path and acceptable long-decode performance | `cudagraph_mode=NONE` proves memory/readiness/API compatibility only; it is not the final optimized NVFP4 runtime |
| Backend | Keep vLLM explicit B12x as production candidate A. SGLang native candidate B passed SM121 FP4 load, FlashInfer MLA, CUDA Graph, Chat/tools/stream/cancel, but failed verbatim tool continuation and standard Responses input semantics; MARLIN remains rollback only | Do not generalize either rejected auto-CUTLASS path or SGLang API regressions into a claim that MARLIN is optimal on Blackwell |
| Flash overflow | `deepseek-v4-flash` completion, native tool continuation, stream/cancel, provider pinning, cross-key overflow, same-key FIFO/fairness, recovery, and high-risk fail-closed gates passed | Checked-in scheduling remains disabled pending broader release gates |
| Client quality | Fresh v103 completed `18/20`: baseline/Hermes/OpenCode `5/5`, Codex `3/5`. Codex rate-limiter rejected the hidden constructor contract and Codex atomic-store accepted an invalid update. Preserve both failures and recover them in separately named epochs before another fresh full matrix | V103 does not pass the all-20 functional gate or authorize blind noninferiority, canary, or release promotion; the two Codex failures are not a Candidate-A backend verdict |
| Goal status | Continue remaining verifiable engineering gates; preserve failures and protocol epochs | Do not convert an unresolved engineering path into a terminal external-resource conclusion |

### Dashboard validation overlay — 2026-08-13

The development source now removes the information-level single-agent
bottleneck: one immutable Runtime-owned canonical evidence snapshot feeds
independent Reasoner, Planner, and Frontier A fan-out projections, then a
Runtime fan-in projection feeds the Executor. Reviewer, Kimi K3 Judge, and
Frontier B receive their own later-stage projections from the same snapshot
lineage rather than an Executor-authored evidence summary. Snapshot/projection
IDs, hashes, included categories, Evidence IDs, and source attempts are durable;
raw secrets and hidden reasoning are excluded. The Dashboard displays this
lineage together with live draft, final client output, and separate transport
versus task-completion state.

The fixed tailnet gateway currently runs the reviewed development Dashboard
overlay with `runtime_channel=dev`, `trace_origin=validation`, and Execution
Graph `shadow`. Its shadow state is isolated at
`data/diagnostics/runtime-overlays/dashboard-production-20260812/state/gateway.db`;
the production state database is no longer used by the Graph experiment.

Fresh exact-model inference probes report all seven requested roles available:
loopback Ollama Qwythos Reasoner, DeepSeek V4 Pro Planner, Codex OAuth
GPT-5.6-Sol `xhigh` Frontier A, local Mistral Small 4 Executor, DeepSeek V4
Flash Reviewer, OpenCode Go Kimi K3 Judge, and OpenRouter Claude Opus 5
Frontier B. Actual requests selected and persisted `simple-v1`,
`engineering-v1`, and `critical-v1`; the critical projection observed the
Executor, Reviewer, Judge, checkpoint, and final stages without a shadow
failure. This is runtime-created subgraph evidence, not Graph control-flow
authority.

The application passed a disposable loopback HTTPS/WSS gate. The operator then
selected authenticated access on the already connected tailnet and same trusted
LAN instead of a new TLS ingress, and corrected the repository policy to use a
single authenticated `0.0.0.0:9000` listener. The obsolete loopback/LAN socket
proxies were removed. Role-model endpoints remain loopback-only; Tailscale Serve
and Funnel remain prohibited. The fixed gateway and Candidate A remain healthy
with zero restarts.

### Pilot-first transition — 2026-08-12

The current operating stage is `PILOT_ACTIVE`. Release candidate
`40fddc0b2e05520117fdfc93d4247528ebe86406` is running as a limited
developer/operator own-key canary on the tailnet-only endpoint
`100.125.239.72:19000`. Fresh 20/20 client
quality, blind non-inferiority, Reasoner ablation, long-horizon, full Dashboard
and training qualification, SGLang reconsideration, and final branch cleanup are
post-Pilot gates. They remain preserved and required before later promotion,
but no longer block a safe limited Pilot.

Physical epoch `data/diagnostics/pilot/pilot-v1-transition-20260812` now proves:

- a 128 MiB qualification cgroup reached 120 MiB and was OOM-killed locally;
  320 production/validation health probes had zero failures and the user
  manager, production gateway, and Candidate A PIDs did not change;
- Candidate A remains active with live `MemoryHigh=12 GiB`, `MemoryMax=16 GiB`,
  `MemorySwapMax=4 GiB`, `OOMPolicy=stop`, and `KillMode=control-group`;
- an isolated single-key gateway passed Chat, Responses, streaming, native tool
  call, same-session tool-result continuation, durable restart, high-risk 403
  approval fail-closed, and post-failure recovery;
- its durable DB contains six graphs, 25 attempts, 57 checkpoints, six active
  states, and zero `execution_graph_shadow_failed` events;
- a stale scheduler-disabled `legacy_local_qwen` telemetry label was corrected
  at the shared projection boundary and physically rechecked as
  `local_mistral` for both selection and Executor node provider.

The checked-in Executor launcher now emits the qualified Candidate A defaults:
revision `b1a9048590131d38491bd23a7c9f6ed0962f0358`, context `131072`, seq1,
KV `3400000000`, FlashInfer B12x dense/MoE, TRITON_MLA, lazy safetensors, and
`FULL_DECODE_ONLY`; MARLIN/`NONE` remains an explicit environment-selected
rollback. The checked-in unit also contains the measured 12/16/4 GiB host
limits. These changes are not installed production state yet.

The canary passed unauthorized 401/authorized 200, Chat, Responses, completed
SSE, native tool call, semantic tool-result continuation, high-risk 403,
DeepSeek V4 Flash completion, exact gateway restart with graph durability, exact
stop rollback, and redeploy. Candidate A, the production gateway, and the user
manager retained their PIDs throughout. Bounded single-developer real-use
telemetry is active and has passed evidence-backed Codex, OpenCode, and Hermes
read-only canaries; broader sampling and failure-family review continue.
Standardized Candidate A
installation on port 8101 and a persistent reviewed unit are post-Pilot
hardening before `PRODUCTION_BETA`; the active Pilot deliberately uses the
preserved Candidate A endpoint on 19301. V105 is preserved as a policy-paused
post-Pilot matrix, not a Pilot blocker. The frozen completion-plan SHA-256 remains
`41e16b4f2fb8f442d8da3065ba53eacb317fc9a68333e63c02253784bcf1a4bd`.

After redeploy, an actual Candidate A completion returned
`PILOT_REDEPLOY_OK`; 120 paired Pilot/production health samples had zero
failures. Durable totals are now 11 graphs, 47 attempts, 108 checkpoints, 11
active states, and zero shadow failures. The active Pilot gateway peak is
59,916,288 bytes with zero restarts.

The approved production gateway recovery remains active and HTTP 200. Candidate
A and its isolated gateway are also active and healthy. The v80, v81, and v82
matrix transients are exactly stopped. These current facts supersede the historical v64 incident
paragraph below without deleting it.

### Recovered production incident and isolated challenger result — 2026-08-10/11

The v64 `auto` backend candidate selected
`FlashInferCutlassNvFp4LinearKernel` and `FLASHINFER_CUTLASS`. During initial
warmup, CUDA compiler children exhausted host/unified memory after the original
8 GiB guard fired. A global OOM killed unrelated user-session processes, the
production gateway, and the user systemd manager. The candidate process group
was then forcibly removed and memory recovered. Port 9000 is currently not
listening and `systemctl --user` cannot connect to the killed manager. No
production restart or deployment was attempted because that requires separate
human approval. Further memory-intensive backend runs are paused. Qualification
guards now use a 24 GiB host floor and immediate process-group `SIGKILL`.
The first guard implementation was itself defective: dash's `kill` builtin
rejected `-- -PGID`, and `|| true` hid the failure. Both qualification launchers
now use checked `/bin/kill`; the forced-floor process-group self-check passes.
The direct mechanism is uncapped FlashInfer ninja JIT parallelism: `MAX_JOBS`
was unset on a 20-CPU host and concurrent `cicc` processes consumed multi-GiB
RSS each. A serialized `MAX_JOBS=1` auto-CUTLASS retry remains technically
testable only after production recovery is approved. That single-variable retry
is preregistered as protocol epoch
`mistral-128k-v65-blackwell-auto-serialized-20260810`; it has not started.

The production user manager and `dgx-moa-gateway.service` recovered at
2026-08-11 07:16 KST before the explicit recovery approval was exercised.
Post-approval inspection found the gateway active with zero service restarts,
tailnet `/healthz` 200, and unauthenticated `/v1/models` 401; no redundant
restart was performed. Explicit FlashInfer B12x v64 is now frozen as known-good
production candidate A. SGLang native candidate B was run separately as
`mistral-128k-v66-sglang-native-auto-20260811`; it does not replace or mutate A.
The default Triton MLA attempt failed CUDA Graph compilation with a preserved
`256` versus `512` grouped-decode shape mismatch. Changing only attention to
FlashInfer loaded 64.42 GB of weights, allocated 147,568 BF16 MLA KV tokens
(reported 3.17 GB), built native `compute_121a/sm_121a` FlashInfer CUTLASS FP4
GEMM serially, captured batch-one CUDA Graph in 729.82 seconds using 1.19 GB,
and initialized RadixCache. Startup GPU peak was 72,556 MiB; production health
remained 200.

Candidate B passed exact Chat, single and parallel native tool generation,
Chat streaming, client cancellation, and recovery. It is not production
eligible: its own tool-call response uses `content:""`; verbatim continuation
then reissues the same tool, while changing only that field to `null` succeeds.
Standard `/v1/responses` string input also returns 400 on the Pixtral path with
`input_ids should be a list of lists for batch processing`. Official v0.5.17
source retains both relevant code paths, so no speculative runtime replacement
was run. The transient was stopped successfully and memory returned to normal.
Cold and agent-prefix performance matrices were intentionally not run after the
mandatory semantics gate failed. Candidate A remains selected.

The operator has now added a released-runtime SGLang retry ahead of the next
client-quality matrix. Protocol
`mistral-128k-v98-sglang-0.5.17-native-20260812` keeps candidate A immutable and
tests candidate B in a separate venv and transient loopback service. Source and
package resolution found SGLang `0.5.17` at tag commit
`b6a09f38fcc5e96574324b4acc19d421c539cfc6`, sglang-kernel `0.4.5`,
FlashInfer `0.6.15.post1`, torch `2.11.0+cu130`, and transformers `5.12.1`.
On SM121 its registry resolves dense FP4 auto to `flashinfer_cutlass`, NVFP4
MoE auto to `flashinfer_trtllm`, and MLA attention auto to `triton`. The old
Triton shape failure and both API regressions remain explicit first-class
gates. Correctness must pass before either cold or RadixAttention agent-prefix
performance is measured. This preregistration does not promote SGLang or alter
candidate A.
The v65 vLLM auto-CUTLASS retry remains preserved but is deferred behind the
completed SGLang challenger evidence.

Candidate-A-pinned protocol epoch
`mistral-128k-v67-b12x-full-matrix-20260811` then completed its immutable
20-cell client-quality schedule. Baseline, Codex, and OpenCode each passed
`5/5`; Hermes passed `4/5`. The sole failure was Hermes atomic-store at the
frozen 1,800-second limit. Its implementation changed only `atomic_store.py`,
and both public and hidden validation passed. The preserved Hermes state has 52
messages: 25 assistant responses all ended in tool calls, followed by 26 tool
results, with no terminal assistant response. It continued redundant audits and
rewrites after repeated passing tests; the last successful test result arrived
27.813 seconds before harness termination. Gateway chat calls in the interval
returned HTTP 200, candidate A remained at 72,428 MiB, all three isolated and
production services stayed healthy, and the next OpenCode cell passed. This is
a Hermes terminal-convergence quality regression, not a backend, memory, or
gateway outage. The frozen cell was not retried. Candidate A remains selected,
but the v67 functional gate is failed; blind noninferiority and later release
gates remain unstarted pending a new targeted terminal-convergence recovery
epoch.

Targeted epochs v68-v71 preserved four distinct failed controls: copied-config
turn limiting was ignored by oneshot, the top-level CLI rejected
`--max-turns`, the one-line oneshot turn fix reached an English fallback, and
the full-history `dgx-moa-fast` summary failed with `backend_error`. v72 retained
the one-line turn fix and fast-summary selection while bounding the summary
history. It completed Hermes atomic-store naturally after seven assistant
messages, exited zero in 389.044 seconds, changed only `atomic_store.py`, and
passed public validation, hidden validation, tool-evidence, Korean-terminal,
and isolation checks. All seven gateway requests completed and candidate A
remained healthy. Because Hermes converged before the 20-turn limit, the compact
fast-summary branch was not exercised; v72 is valid targeted recovery evidence,
not proof of that fallback path. The next authority is a fresh full matrix in a
new epoch; frozen v67 remains unchanged and later gates remain unstarted.

Fresh v73 then executed all 20 cells with the candidate-A backend and the
read-only Hermes recovery overlay. Baseline and OpenCode passed `5/5`, Codex
passed `3/5`, and Hermes passed `4/5`, for `17/20`. Codex log-report exited 139
before implementation despite three completed gateway requests. Codex
rate-limiter implemented and passed public/hidden validation plus tool evidence
but timed out without terminal output at 1,800.094 seconds; its interval had 31
completed and one cancelled gateway request. Hermes log-report implemented and
passed public/hidden validation but ended with the client fallback `API call
failed after 3 retries: remote Executor fallback unavailable`; its interval had
four completed and three cancelled gateway requests, with no gateway request
marked failed. The key Hermes atomic-store regression passed in 552.221 seconds.
All services remained active and HTTP 200, candidate A ended at 72,430 MiB, and
host headroom stayed above the guard. v73 is frozen failed functional evidence;
continue separate client recovery and do not start blind or release gates.

Fresh v80 executed all 20 scheduled cells after the v77/v79 gateway fixes.
Baseline passed `5/5`; Codex, Hermes, and OpenCode each passed `0/5`, totaling
`5/20`. This broad regression had a shared infrastructure cause: the isolated
gateway service inherited a systemd `PATH` without `/home/kotori9/.local/bin`,
while the configured Frontier command is the bare executable `codex`. Runtime
events record `FRONTIER_PROCESS_SPAWN_FAILED`, repeated remote-Executor fallback
failure, and client-visible `remote Executor fallback unavailable`. Candidate A
remained resident at 72,596 MiB, both persistent gateways and production stayed
HTTP 200, and host headroom remained above the guard. The v80 summary SHA-256 is
`e696e49c5eae60385b6b05160f53c646dffe30f85c4ff5229df2299ed9fc5d50`.
The transient gateway was exactly stopped and port 19312 released. v80 remains
failed evidence and is not a clean backend or client-quality comparison; the
next single variable is the isolated launcher `PATH`, followed by a direct
Frontier spawn probe before any fresh matrix rerun.

The separate v81 prerequisite epoch prepended only
`/home/kotori9/.local/bin` to the transient launcher `PATH`. The service
environment resolved `/home/kotori9/.local/bin/codex`, and an ordinary
orchestrated request completed Codex OAuth Frontier collaboration through the
`primary` profile with model `gpt-5.6-sol`: 28,873.862 ms, 19,551 prompt tokens,
and 1,048 completion tokens. No `FRONTIER_PROCESS_SPAWN_FAILED` event occurred.
Candidate A and production remained healthy; the v81 transient was exactly
stopped and port 19312 released. This passes the missing common prerequisite
and permits a separately named fresh full matrix without changing v80.

Fresh v82 executed that separately named 20-cell matrix with only the qualified
PATH change. Baseline and Hermes passed `5/5`, Codex passed `2/5`, and OpenCode
passed `3/5`, totaling `15/20`. The state DB contains zero
`FRONTIER_PROCESS_SPAWN_FAILED` events and zero `remote Executor fallback
unavailable` payloads, so the v80 transport prerequisite is closed. The five
preserved failures are Codex rate-limiter, atomic-store, and dag-runner
timeouts; OpenCode atomic-store timeout; and OpenCode dag-runner's non-Korean
final response. Candidate A remained at 72,776 MiB with all three gateways HTTP
200 before cleanup and 45,452,932 KiB host memory available. Only the v82
transient was stopped and port 19312 released. v82 is client/task quality and
convergence evidence, not an NVFP4 backend failure; targeted recoveries must
pass before another full matrix or any blind/release gate.

The first targeted recovery, v83, exact-replayed OpenCode dag-runner without
changing the backend, client, prompt, task, timeout, or scoring contract. It
passed 10/10 in 204.123 seconds, including the Korean terminal check. The v82
English-only final was not reproduced, so no prompt or gateway change is
authorized from that single failure; preserve both observations and continue
the remaining v82 targeted recoveries.

Targeted v84 then exact-replayed OpenCode atomic-store with repetition as the
only variable. It passed 10/10 in 489.769 seconds, including public/hidden
validation, tool evidence, and Korean terminal output. The v82 1,800-second
timeout was not reproduced. Together v83 and v84 close deterministic OpenCode
failure as the current hypothesis without erasing either v82 observation; no
OpenCode prompt, client, or gateway change is authorized before a fresh matrix.

Codex atomic-store exact replay v85 reproduced the 1,800-second timeout with
public/hidden validation passing but no terminal. Its 36 gateway requests
contained 18 Frontier correction-tool retries because bounded review evidence
retained initial stub/deadlock failures beside current passes. v86 changed only
that selection to the latest eight results and passed 339/339 focused tests.
Physical replay removed the stale Frontier correction loop entirely (zero
correction retries), but still timed out: the eight-result window retained two
superseded failing test runs until two newer passes arrived after the final
Reviewer rejection. Preserve v85/v86; the next single variable is the latest
four review results, with contract documents still carried separately.

v87 changed only that window from latest eight to latest four after another
339/339 focused pass. The isolated Codex atomic-store replay completed in
1,058.352 seconds and passed 10/10. It retained real review assurance: one
Frontier rejection led to four bounded correction-tool calls, one file change,
and a recorded `frontier_correction_verified` event before the Korean terminal.
Thus latest-four is the current client-recovery candidate, not a deployment;
the remaining Codex rate-limiter and dag-runner cells must pass isolated
targeted epochs before a fresh full matrix.

v88 applied latest-four to Codex rate-limiter. Terminal convergence recovered:
the client exited zero in 457.669 seconds and passed public tests, tool, scope,
and Korean-final checks. Hidden validation still failed because the
implementation rejected valid positive float `window_seconds=2.5`. The clean
local Reviewer approval could not receive Frontier assurance: four repeated
architecture collaborations had exhausted the per-task Frontier budget and
seven later paths recorded `FRONTIER_INVOCATION_LIMIT`. Preserve v88 at 9/10;
the next single variable is reuse of the first architecture artifact so review
budget remains available.

v89 exact-replayed Codex rate-limiter and passed 10/10 in 742.760 seconds,
including hidden validation and verified Frontier correction. The
preregistered architecture-reuse branch was not exercised: all three Frontier
calls were code review and no architecture reuse event occurred. Retain the
pass as replay evidence, not proof that architecture reuse caused recovery or
is ready to deploy. Candidate A remains unchanged; Codex dag-runner and a fresh
full matrix remain open.

Fresh matrix v91 is frozen after two failed cells with its original latest-four runtime. Its first
Codex rate-limiter cell failed only harness-exit and terminal at 1,800.213
seconds; public and hidden validation passed. Direct session evidence shows
that path extraction converted `empty/non-string` into a false `/non-string`
changed path. The OpenCode atomic-store cell similarly treated a
temporary validation `state.json` as a repository change. Candidate A remains
stable. The separate v92 new-process replay physically recovered OpenCode
atomic-store at 10/10 in 231.803 seconds and recovered the Codex timeout/terminal
path, but Codex rate-limiter failed hidden validation at 9/10 because its
implementation rejected valid non-integer `window_seconds`. V92 also exposed
Python `-> bool:`/`-> int:` as false redirect targets. The shared matcher
correction passes 341 focused tests plus Ruff but remains unqualified until a
new-process rate-limiter replay. No full matrix is yet authorized.

V93 recovered Codex rate-limiter task quality at 10/10 in 1,137.327 seconds,
but did not qualify the parser: raw state retained false `/remaining(` and
`cutoff` targets. The root candidate now recognizes redirects only in explicit
shell write commands and excludes parenthesized slash prose. Its 341 focused
tests, Ruff, and direct regression pass are source evidence only; a new-process
replay remains the next gate.

V94 physically passed that gate: Codex rate-limiter completed 10/10 in
714.089 seconds with verified Frontier correction, and all implementation
target paths were exactly `rate_limiter.py`. The conservative parser is now the
qualified client-recovery candidate. A separately named fresh 20-cell matrix is
the next gate; blind and release gates remain unstarted.

V95 is frozen as an interrupted, inadmissible matrix. Its schedule SHA-256 is
`9b63d1ce3883e06debd2794358856c776fbfb2fcff580ac4f38e4f08396a081c`;
Hermes atomic-store passed 10/10 in 303.809 seconds. Codex log-report failed
hidden bool-limit validation and bad-terminal after the isolated gateway
interruption; OpenCode log-report was started then stopped without a score.
During cell 02 the initial cleanup monitor briefly stopped only the isolated
gateway after misreading `activating`; the gateway was restored and the monitor
fixed. Preserve v95 and do not accept it as a clean matrix. The source-only
quality-contract candidate explicitly names `limit` and `*_limit`; its 341
focused tests and Ruff pass require a new-process targeted replay.

V96 is frozen at 8/10 after a 1,800.145-second timeout. Its hidden validation
passed, qualifying the `limit`/`*_limit` contract, but terminal convergence did
not. Four architecture calls preempted code-review escalation and were followed
by 18 unavailable events. The source-only candidate defers architecture during
implementation review; 341 focused tests and Ruff pass, but a new-process
convergence replay is still required.

V97 completed that new-process replay. Its first launcher attempt failed before
any model request because the runner workspace had not been prepared; the
failure remains in `execution.log`. Attempt 2 added only the missing prepare
action and passed 10/10 in 329.680 seconds. It emitted zero architecture calls,
two code-review calls, no Frontier-unavailable event, one rejected review, one
applied correction, and one verified correction. Hidden and public validation,
terminal, source scope, tool evidence, Docker isolation, and Korean final checks
all passed. The review-before-architecture convergence correction is physically
qualified. Operator priority now places frozen SGLang v98 before the next clean
client matrix.

V98 has now exhausted the installed SGLang `0.5.17` native MLA paths under the
pinned 131072/seq1/BF16-KV/CUDA-Graph contract. Auto selected native SM121 dense
and fused-MoE FP4 but Triton MLA failed graph capture at the preserved 256/512
shape mismatch. Explicit FlashInfer reached readiness and passed Chat,
Responses, tools, continuation, streaming, cancel, and recovery, but selected
non-native FA2 attention. Explicit TRTLLM-Gen reached its kernel after a
one-line isolated compatibility probe and rejected SM121 as `Unsupported
architecture`; stock `cutlass_mla`, despite an installed `sm_121a` image,
failed its model-shape assertion `D_q_nope == D_latent`. Native candidate B is
therefore rejected for this pinned epoch without running or mixing cold and
Radix-prefix performance lanes. Candidate A remains selected; MARLIN remains
rollback only. Candidate A exact recovery passed on loopback port 19301: 66.09
GiB weights in 393.77 seconds, fixed 3.4 GB KV, 11.92-second decode graph
capture, 72,430 MiB startup peak, direct API recovery checks, and the
authenticated validation gateway all passed. The production gateway is active
with `NRestarts=0` and `/healthz` 200; its pre-existing stopped production roles
keep `/readyz` at 503.

v90 then tested the remaining Codex dag-runner cell with latest-four alone.
It passed 10/10 in 864.933 seconds, including hidden validation, after 33
tool-result continuations. Four architecture calls exhausted Frontier budget
and 20 later paths recorded unavailable assurance, so efficiency remains an
observation even though task quality recovered. All five v82 failed cells now
have passing targeted replays; a fresh full matrix is the next client gate.

CUDA Graph optimization is an explicit Executor promotion gate. A candidate
must enable graph capture without eager mode, retain the pinned NVFP4/MARLIN and
128K contracts, report peak and steady allocator/GPU/system memory, and pass a
long-output decode benchmark plus Chat, Responses, streaming, tools,
continuation, cancellation, restart, soak, and gateway-isolation checks. A
watchdog may still protect the host during experiments, but its threshold is a
run-specific safety control chosen from current host headroom, not the 96 GiB
product target encoded as a universal hard limit.

## Dynamic MoA production status

| Capability | Designed | Implemented on `dev` | Unit-tested | Physically validated | Production-enabled |
| --- | --- | --- | --- | --- | --- |
| `dgx-moa` Reasoner + Executor core | yes | yes | yes | production yes | yes |
| Dynamic Planner/Reviewer routing | yes | yes | yes | Planner and Reviewer production | yes |
| Codex OAuth Frontier modes/fallback | yes | yes | yes | production architecture yes | yes |
| Heavy Judge adjudication | yes | yes | yes | isolated exclusive-profile yes | deployed, operator-only |
| Evidence graph and per-agent trace | yes | yes | yes | production yes | yes |
| Multiple API tokens and per-token usage | yes | yes | yes | production yes | yes |
| Codex Responses text/function/custom tool loop | yes | yes | yes | production yes | yes |
| Runtime model invocation-rate CSV | yes | yes | yes | production live clients | yes |
| Bounded Loop Engineering Phase A + action-boundary B | yes | yes | yes | live production success/correction | yes |
| Runtime Skills Phase C foundation | yes | yes | yes | live selection; production empty registry | yes |
| Runtime Knowledge Phase C foundation | yes | yes | yes | live retrieval; production integrity | yes |
| Declarative Policy Phase D foundation | yes | yes | yes | production approval fail-closed | yes |
| OpenCode Go GLM-5.2 Remote Judge | yes | yes | yes | live matrix and production readiness | yes |
| Local-first Planner/Reviewer cold fallback | yes | yes | yes | live OpenCode Go + production local/cold routing | yes |
| Typed Evidence Graph Phase E foundation | yes | yes | yes | production graph and isolated replay | yes |
| Telegram Live Observation Phase E | yes | yes | yes | Korean deterministic cards; production Telegram | Telegram yes; controls no |
| Privacy-aware Training Collection Phase F | yes | yes | yes | production eligible candidate + integrity | yes |
| Weekly Skill/Knowledge/Data Packaging Phase G | yes | yes | yes | real 7z + wall-clock scheduler | yes |
| Execution Replay Phase H foundation | yes | yes | yes | production exact mock replay and fail-closed boundary | yes, operator-only |
| Prompt/Policy/Routing evolution registry | yes | yes | yes | production empty-registry integrity; isolated lifecycle | yes, empty registry |
| Fixed label-free Goal metrics endpoint | yes | yes | yes | production yes | yes |
| Execution Graph v1 + compact checkpoint/training projection | yes | dev worktree only | yes | 10,000-event resume + partial rerun PASS | no; checked-in mode disabled |
| Codex App Server Frontier A transport | yes | dev worktree only | yes | one-shot PASS; persistent default daemon TIMEOUT | no; Frontier gateway gate disabled |
| Claude Opus 5 Frontier B | yes | dev worktree only | yes | isolated structured call PASS | no; paid fallback disabled outside gated use |
| v3 remote Planner/Reviewer/Judge mapping | yes | dev worktree only | yes | Planner/Reviewer/Judge PASS | no; role gates disabled |
| API-key fair local queue + DeepSeek Flash pinning | yes | dev worktree only | yes | Flash direct matrix + authenticated HTTP fairness/overflow/fail-closed PASS | no; checked-in scheduler disabled pending release gates |
| API-key scoped ExecutionGraph Dashboard | yes | dev worktree only | yes | graph snapshot/delta/replay TCP PASS | no; checked-in Dashboard disabled |
| API-key plaintext-free credential store | yes | dev worktree only | yes | legacy scrub/auth byte test PASS | no; migration not deployed |
| Cache null/zero + multi-invocation usage accounting | yes | dev worktree only | yes | isolated SQLite/Responses PASS | no deployment required yet |

The development candidate centralizes Executor provider priority in the
existing routing module and separates bounded review-evidence assembly from
Controller orchestration. Against the pre-v3 `dev` source, Controller is 144
lines and 29 AST branches smaller. This is static/shadow parity evidence, not
authorization to enable Graph execution or deploy it.

The v3 Frontier candidate now uses the native profile-specific persistent App
Server daemon through a short-lived stdio proxy. It resumes bounded read-only
threads, compacts them after a calibrated turn count, and interrupts the active
daemon turn before proxy cleanup on timeout or cancellation. Stdin `codex exec`
remains only for typed App Server unavailability. A prior one-shot primary OAuth
architecture turn physically passed. The primary and secondary daemon sockets
are absent; one existing default-daemon turn reached the exact 300-second
provider timeout, interrupted its turn, and removed only its proxy process.
Persistence/resume/compaction therefore remain failed physical gates. A later
bounded primary-profile turn passed through the validated read-only stdin
`codex exec` fallback, not the persistent App Server path. Frontier B passed one
paid structured Opus 5 call after removing an unnecessary sampling parameter
that excluded eight of nine current provider endpoints. GLM-5.2 Reviewer did
not reliably produce public structured output even with thinking disabled and
two bounded attempts. The disabled development mapping now uses the physically
validated DeepSeek V4 Pro replacement for Reviewer; Planner, Reviewer, and Kimi
K3 Judge all pass their isolated structured gates. Kimi Judge required a
measured 4,096-token output ceiling; hidden reasoning was discarded. External
Qwythos structured output passed its standalone smoke, but ablation remains
unrun. Basic Mistral readiness is no longer its blocker; run the comparison only
after the CUDA Graph and sustained-performance target is fixed so the ablation
does not benchmark the diagnostic no-graph runtime as the production candidate.

The API-key scheduler candidate enforces one local owner, a three-request
same-key queue, per-key round-robin promotion, immediate cross-key Flash
selection, and high-risk local-only fail-closed handling. Its provider choice
is pinned for the turn and projected into the Execution Graph. After the
operator enabled China-hosted models, the exact Flash model completed a minimal
request, native tool call and continuation, complete stream, and client cancel
through the same endpoint and credential identity. This isolates the prior 403
to workspace policy. Physical same-key queue, cross-key overflow, and recovery
validation passed in direct scheduler/provider integration. Authenticated HTTP
cross-key overflow, high-risk local queuing, depth-three fairness, and fourth
request fail-closed also passed with the live Flash provider. The repository
default remains disabled pending broader release gates.

The v40 targeted Docker rerun isolated a Codex Responses continuity defect.
Physical fake-server probes proved Codex 0.146 accepts named `event: ping`
frames, but v42 then exposed that the gateway buffered inner translated ping
frames together with terminal events. Dag-runner and log-report disconnected
after five reconnects at 1,271.799 and 1,245.751 seconds. The minimal fix lets
only comments and named ping frames bypass that terminal-validation buffer.
Fresh v44 Docker reruns passed dag-runner in 151.850 seconds and log-report in
505.383 seconds with all ten checks true and zero reconnects. The v42 full
matrix still records baseline `4/5`, Codex `1/5`, Hermes `4/5`, and OpenCode
`5/5`; targeted recovery does not rewrite that epoch or yet clear full-matrix
noninferiority.

A fresh v45 randomized full matrix on the same revision and 131K no-graph
profile measured baseline `4/5`, Codex `1/5`, Hermes `5/5`, and OpenCode `5/5`.
The common Codex defect was a compatibility rewrite that turned invalid or
invented `write_stdin` session IDs into a successful `exec_command` printing a
no-op message. Preserving `write_stdin` and replacing only its invalid ID with
sentinel `0` makes the client observe the real tool failure. In v46,
rate-limiter, dag-runner, and log-report passed all ten checks in 155.862,
817.715, and 629.233 seconds. Webhook-verifier still passed both validations
but timed out at 1,800.101 seconds without a terminal response, so the targeted
fix is accepted while Codex webhook termination and full-matrix
noninferiority remain open.

The v47 completion-aware progress retry distinguishes missing implementation
evidence from an already completed tool/test record. It retains the existing
tool requirement for the former and asks only for a concrete final result for
the latter. A regression test exercises that branch. Physical Codex webhook
runs then passed all ten checks in 588.653 seconds (v47) and 609.751 seconds
(v48), replacing the v46 1,800.101-second timeout.

The fresh randomized v48 matrix used seed
`ac5cd8d40cccb13a2f3bfa59fd381bca835b569839b6d2144df6052220e480fb`.
Nineteen cells produced valid scores: baseline, Hermes, and OpenCode each
passed `5/5`; Codex passed rate-limiter, webhook-verifier, and log-report but
atomic-store timed out at 1,800.102 seconds after both validations passed. The
outer orchestration process received SIGTERM during the final Codex dag-runner
cell, so that cell is recorded as externally interrupted and is not scored.
Both long Codex traces show repeated reviewer/correction cycles after tests
passed because shell-based writes did not project trustworthy changed paths and
the Docker image lacked `git`. This is now a separate review-evidence blocker;
v48 is not a complete noninferiority epoch.

The v49-v53 CUDA Graph isolation established that installed alternative MLA
backends reject GB10 capability 12.1, tuned native allocation still dies during
MARLIN packing, and cudaMallocAsync capture pointers remain inaccessible to both
static and dynamic Triton launchers even after upstream MLA workspace
preallocation. No active-graph candidate reached readiness. This is an active
runtime engineering gate, not a model-size requirement or an external-resource
terminal condition.

The Dashboard candidate now projects actual StateStore events over a bounded
WebSocket instead of deriving a second execution flow. General keys see only
their own live/history scope; operators see aggregate metadata unless they
provide an audited reason for a request-scoped raw view. A real loopback TCP
WebSocket gate passed. API-key plaintext persistence and reveal were removed in
the development store, but that irreversible production DB migration and its
rollback compatibility have not been approved or deployed.

Execution Graph checkpoints now link a content-addressed compact active state
to the durable event cursor while leaving normalized session events intact.
Each model-relevant field is redacted and byte-bounded; an oversized field is
replaced by its SHA-256 plus bounded JSON summary. Trace v3 remains unchanged:
its existing `metrics` object carries graph/checkpoint references, and the
disabled-by-default training collector resolves and integrity-checks those
references only after repository, privacy, opt-out, and license eligibility
passes. A 10,000-event isolated restart preserved every event and reduced a
26,485,228-byte working state to 93,367 bytes. This is long-session storage
evidence, not Graph execution parity or production authorization.

Usage accounting now preserves an unreported prompt-cache measurement as
`null` and an explicitly measured zero as `0` across Responses output,
per-invocation SQLite, trace/training records, and Execution Graph attempts.
Repeated calls append and aggregate instead of replacing the last role call.
The isolated Planner check retained two rows and summed 30 prompt, 12
completion, and 42 total tokens. This validates accounting semantics only; the
Mistral 128K Responses probe physically reported 16 cached input tokens. Broader
prefix-cache performance and eviction behavior remain part of the pending
optimized-runtime matrix.

The Dashboard now subscribes directly to committed `ExecutionGraphStore`
graph, node-attempt, and checkpoint writes. Private scope receives full redacted
topology and attempts; operator scope receives only aggregate counts and
allowlisted role/provider/state/latency/cost metadata. Each scope has its own
monotonic sequence and bounded replay window; stale or future `last_seq` returns
`RESYNC_REQUIRED`, after which the client reloads the persisted REST snapshot.
An actual loopback TCP WebSocket passed disconnect/replay at seq 3 -> 4/5 and
returned the same succeeded attempt from REST. Graph execution itself remains
shadow/non-authoritative.

This table is the current authority. Later sections preserve historical Phase
1–4 evidence and must not be read as later production evidence. Checked-in safe
defaults still have lifecycle control and Frontier disabled with an empty unit
map. The production-only 0600 environment overrides authentication, Frontier,
and the reviewed adaptive Executor/Planner/Reviewer unit map.

The next Executor runtime is fixed at
`mistralai/Mistral-Small-4-119B-2603-NVFP4@b1a9048590131d38491bd23a7c9f6ed0962f0358`
with vLLM as the selected first backend. This is a runtime decision, not a claim
of completed deployment. The canonical cache passed `23/23` verification.
Watchdog-bounded physical comparison now attributes the historical 120,052 MiB
growth to native allocator retention during vLLM's NVFP4-to-MARLIN post-load
packing, not the approximately 66 GiB checkpoint or fixed KV budget.
`cudaMallocAsync` held the packed model near 71,671 MiB; native expandable
segments still crossed 100,868 MiB. SGLang retained about 44 GB headroom after
its 1.41 GB KV allocation but failed attention warmup and did not exercise true
MARLIN MoE. vLLM's CUDA-graph path remains incompatible with cudaMallocAsync on
this measured stack, while its compiled `cudagraph_mode=NONE` path passed 65K
readiness and API gates. That result is diagnostic compatibility evidence, not
the final production runtime. The identical dense/MoE MARLIN path then passed 128K twice with a
fixed 3.4 GB KV budget: 147,568 KV tokens, 1.13x full-context concurrency,
74,714 MiB steady GPU allocation, a 125,026-token prompt, cancellation recovery,
and an exact stop/start completion. This clears only the abnormal-memory and
basic readiness questions; CUDA Graph optimization and sustained decode
performance remain open engineering blockers. An isolated authenticated live protocol matrix
also passed raw generic/primary requests plus installed Codex, OpenCode, and
Hermes clients against this 128K backend. Production remains disabled pending
the separate CUDA Graph, long-horizon, coding-task client quality matrix,
performance/noninferiority, canary, rollback, and human promotion gates.

## Branch and deployment

- `dev` declares package/runtime version `2.0.0`. The OpenCode Go Judge and
  cold-routing gates passed and were promoted through reviewed PRs `#44`-`#48`.
  The operator explicitly removed Discord from the release scope on 2026-07-22;
  Telegram is the selected production observation provider.
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
- PR `#36` deployed the audited policy-persistence and role-specific loop/
  preference data paths as `main@40fce08`. The gateway restart performed the
  selected exact Executor stop/start and restored the unchanged Phase 3 65,536
  baseline. Codex, OpenCode, Hermes, Responses/Chat streaming, function-tool
  continuation, metrics, and invocation CSV checks passed. Loop Engineering,
  Skills, policy, observation, training, and weekly-job production gates remain
  disabled.
- Telegram observation was subsequently enabled through the protected production
  environment after a real Bot API identity, target, safe-payload, and send
  validation. A production `dgx-moa` request emitted three observer events with
  zero Telegram errors or drops. Discord is intentionally unconfigured and is
  not a release gate; observation controls remain disabled.
- PRs `#44`-`#48` replaced NVIDIA NIM with OpenCode Go, enabled the separate
  GLM-5.2 Remote Judge and DeepSeek V4 Pro/Flash specialist providers, corrected
  real readiness-probe and structured-output limits, and documented production
  cold/warm routing. The production worktree is `main@29bd904`; Planner and
  Reviewer remain local models, with remote execution used only by routing
  policy while a cold local specialist warms independently.
- PRs `#50` and `#51` closed live-provider Loop completion and specialist
  warm-up/review guard races. Loop Engineering is enabled in the protected
  production environment; the remaining Skills, Knowledge, evolution, policy,
  training, weekly, replay-admin, retention-apply, and observation-control gates
  remain disabled.
- Runtime Skills, Runtime Knowledge, and declarative Policy were enabled after a
  live shadow request selected an approved Skill and Knowledge entry and applied
  a matched budget rule. Production starts with empty governed registries and a
  single `production-v1` rule requiring explicit approval for requests marked
  destructive; no candidate was automatically promoted.
- PR `#54` records the exact active Prompt artifact/version in session and trace
  metrics for replay. Production enabled the authenticated operator Replay API
  and an empty Evolution registry as `main@cbcb011`; Training and Weekly remain
  disabled. Exact mock replay passed deterministically, live comparative replay
  remained fail-closed, and no evolution artifact was promoted.
- On 2026-07-23, explicit operator approval enabled Training Collection and the
  bounded in-process Weekly scheduler in the protected production override.
  Only stable workspace ID `moa-production` is `training_allowed`; the shared
  `external-api` identity remains unknown, external-provider output remains
  ineligible, and retention apply/export remain disabled. The first eligible
  production probe created one candidate after the storage reserve was restored.

## Runtime

- Gateway: authenticated direct tailnet TCP at `100.125.239.72:9000`, with
  `127.0.0.1:9000` and local-LAN `192.168.0.42:9000` proxied to the same gateway
  by address-specific systemd sockets. Role-model endpoints remain loopback-only.
- Model endpoints: loopback-only executor `8101`, planner `8102`, reviewer `8103`.
- The currently deployed production baseline uses Executor `65536`, Planner
  `8192`, and Reviewer `8192`. This describes deployed historical state; the
  undeployed Executor qualification target is `131072` as defined above.
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
- Deployed source contains production-enabled Phase A state and Phase B action
  admission. Evidence-linked criteria, iterations, role/tool/token/known-cost/
  wall-time budgets, progress evidence allowlisting, stable repeated-failure
  policy, and explicit termination reasons are unit-tested. An isolated physical
  run exercised success, no-progress, and duplicate-failure termination. Live
  production subsequently exercised evidence-backed success and correction
  without weakening the Reviewer gate.
- Deployed source also contains a production-enabled runtime Skill registry with
  immutable versions, bounded active-only retrieval, Executor-only activation,
  structured recurring-pattern drafts, isolated multi-gate candidate evaluation,
  Executor-evidenced canaries, governed versioned lifecycle changes, separate
  metrics, evidence-gated promotion/rollback, and verified pack hashes. An
  isolated physical run exercised draft generation, every evaluation gate, an
  Executor-evidenced helpful canary, explicit promotion, and rollback. The
  production registry is empty; no production Skill or canary was created.
- A production-enabled declarative policy engine records versioned, hashed
  decisions and enforces request denial, approval requirements, role requirements, loop
  limits, and per-tool deny globs. Policy field redaction covers evidence,
  decisions, tool results, normalized executions, and persisted Reasoner,
  Planner, Reviewer, Frontier, and Judge artifacts while preserving container
  schemas.
- Task evidence now records canonical node types and trust classes without
  changing the existing edge serialization. Deterministic trust precedence and
  graph consistency passed an isolated exact replay.
- A bounded internal event bus, Telegram sender, safe event projection, batching,
  drop/error metrics, and optional authenticated control commands are
  implemented. Telegram observation is production-enabled; the excluded Discord
  compatibility source is removed from `dev`, while controls remain disabled.
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
  retention exist. Archive staging enforces its own configurable free-space
  reserve; jobs fingerprint exact registry/configuration state and populate
  measured candidate analytics. A user-local 7-Zip 23.01 binary physically passed archive
  creation, `7z t`, checksum, idempotency, revocation/regeneration, empty-week,
  corruption, archiver-failure, late-arrival, and capacity-isolation checks on
  synthetic data. No scheduled or production run exists.
- Hash-protected replay snapshots and exact/mock versus live/comparative replay
  modes plus an exact/audit admin API are implemented. Isolated replay restored
  loop state and a non-empty Evidence Graph; production exact mock replay passed
  through the operator-only API. Live comparative replay remains isolated from
  the admin surface and fails closed there.
- The authenticated development `/metrics` endpoint exposes the fixed Goal
  metric names without labels or event content. Loop events and current
  Skill/observer/training aggregates are connected; scheduler/package and some
  approval timeout counters remain zero until their runtime paths exist.
- The Ollama Reasoner is exactly `Qwythos-v2-9B:Q4`, served only on
  `127.0.0.1:11435`; it remains outside the adaptive lifecycle unit map and is
  never silently replaced by fast mode.
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

## Execution Graph live-attempt boundary (development only, 2026-08-08)

- The Graph feature remains checked-in disabled and non-authoritative.
- Executor-only requests with no tool, validation, approval, or downstream
  review nodes now persist their actual control, provider, and terminal
  attempts from the common Chat/Responses path.
- Successful unvalidated output terminates as `degraded`; an injected Executor
  timeout retained HTTP `504` and terminated the Graph as `failed`.
- At this checkpoint, collaboration and continuation graphs were projections
  only and no stage already completed inside `prepare_executor()` was
  synthesized as a live attempt. Production promotion remains blocked on real
  stage ownership,
  Mistral/Flash/Reviewer/Judge/client gates, blind evaluation, soak, canary, and
  rollback evidence.
- Current development regression baseline: `1032 passed`, one existing
  Starlette warning; Ruff, strict mypy, both frozen plan hashes, and diff check
  pass.

## Runtime Policy role authority (development only, 2026-08-08)

- Executor model output no longer selects orchestration roles or graph shape.
  The former structured `orchestration_decision` provider call and retry were
  removed.
- Runtime Policy deterministically selects Planner, Reviewer, Frontier, and
  Judge from route, request class, risk, explicit signals, bounded evidence,
  and active failures before any role model call. Cold/unmanaged selected roles
  therefore fail before spending a Reasoner request. Reasoner recommendations
  are advisory only.
- Compatible trace schema/version and decision roles are unchanged; persisted
  orchestration evidence and events identify `runtime_policy` authority.
- A multi-file orchestrated request now uses three model calls
  (`reasoner -> planner -> executor`) instead of four. Review-only requests no
  longer load Planner.
- Current development regression baseline is `1031 passed`, one existing
  Starlette warning. Production remains untouched and Graph promotion remains
  blocked on actual collaboration/tool/review attempt ownership and all
  physical provider/client/reliability gates.

## Scheduled collaborator Graph boundary (development only, 2026-08-08)

- Scheduler-enabled requests compile after Runtime Policy role selection and
  before Reasoner dispatch, using the pinned API-key admission snapshot.
- Reasoner, Planner, `FRONTIER_A`, executor preparation, primary Executor,
  control, checkpoint, and terminal stages now persist actual attempts when
  their compiled dependencies match the live request.
- The multi-file success path is terminal `degraded`, not verified completed;
  generated Evidence is not independent validation.
- Straight-through Reviewer/Judge approval and same-session tool/test
  continuation stages are now runtime-owned. Correction/rejection and failed
  tool recovery remain incomplete. Physical Mistral/Flash/Codex OAuth/client
  gates remain unchanged and production is untouched.
- Current development regression baseline: `1031 passed`, one existing
  Starlette warning; Ruff, strict mypy over 51 source files, frozen hashes, and
  diff check pass.

## Tool/test continuation and approval Graph boundary (development only, 2026-08-08)

- Primary Executor output is persisted before downstream Reviewer/Judge
  dispatch. Dual approval validates the referenced Executor Evidence and may
  terminate `completed`; unvalidated output remains `degraded`.
- Client tool calls pause as `WAITING_TOOL` and resume the same Graph/checkpoint
  on an authenticated matching continuation. Observed validation commands add
  a separate `TEST` attempt before the same primary node retries.
- Tool/test cycles are bounded to two traversals and then select `ON_BUDGET`.
- Current regression baseline: `1033 passed`, one existing Starlette warning.
  Production remains untouched; hard rejection, Frontier B, streaming
  continuation, physical providers, client matrix, blind evaluation, soak,
  canary, and rollback gates remain open.

## Bounded correction/fallback Graph boundary (development only, 2026-08-08)

- Remote Judge `revise` can open attempt two of the same pinned primary
  Executor, followed by targeted Reviewer and optional Judge recheck attempts.
- A no-recheck approved correction uses Reviewer `ON_APPROVAL`; a rechecked
  correction closes only after the second Judge approves corrected Evidence.
- Failed tool Evidence selects bounded `ON_FALLBACK` to the primary Executor.
  Tool/test/failure cycles stop after two traversals.
- Hard Judge rejection selects `ON_REJECTION` directly to failed terminal;
  `revise` remains the only correction class.
- Conditional `FRONTIER_B` records an actual configured OpenRouter disagreement
  attempt and opens bounded primary repair. Disabled/missing provider access
  fails closed; Frontier A remains Codex OAuth.
- Streaming tool calls persist `TOOL` as `WAITING_TOOL` and reuse the same
  authenticated continuation resume path. Post-stream review remains deferred.
- All shadow requests now compile before collaborator dispatch, not only
  scheduler-enabled requests. Policy-gated requests persist
  `HUMAN_APPROVAL(WAITING_APPROVAL)` and resume the same Graph only after the
  scoped operator command records approval Evidence.
- Runtime-owned common adapters now replace duplicate API/Controller node
  lookup, metrics/failure fingerprints, tool/test continuation, approval
  continuation, external wait detection, checkpoint, and terminal transitions.
- That consolidation reduced `api.py` from 5,728 to 5,564 lines. Controller now
  starts Reasoner, Planner, and Frontier A in one in-process fan-out after
  lifecycle admission and joins their independent public artifacts; duplicate
  post-Reasoner launch/deferred paths were removed. Mock synchronization proves
  three-way overlap, not physical provider concurrency.
- Graph shadow start/finish/resume/approval/tool/finalize errors now use one
  runtime-owned event boundary instead of 18 API/Controller constructions.
- Internal-only review-evidence forwarding methods were removed; public
  Controller compatibility methods remain where API/tests consume them.
- Discord observation compatibility code/config/tests were removed after a zero
  config-reference scan; the zero-reference 80-line OpenCode fake launcher was
  removed with prior experiment evidence retained at `681f1dd`. Telegram and
  its approval-control contract remain.
- The zero-runtime-reference legacy context tuner and launcher were removed with
  retirement evidence retained at `ce2f212`; historical measurements remain in
  `docs/CONTEXT_TUNING.md` and benchmark data.
- Executor command construction now explicitly defaults to the fixed MARLIN
  baseline while preserving its environment calibration override; dry-run argv
  also pins context 65,536, one sequence, 1.7 GB KV, and utilization 0.5.
- Against the starting epoch, API is `+1050`, Controller is `-291`, and all
  gateway Python source is `+4089`; required net reduction is not met. The
  unreferenced disabled OpenAI API Frontier scaffold, its one-implementation
  Protocol, an unused prompt-registry wrapper, and the disconnected sanitized
  event-feed prototype were removed; Frontier remains Codex OAuth-only.
- Current regression baseline: `1034 passed`, one existing Starlette warning;
  Ruff and strict mypy pass over 49 source files. Production is untouched.

## Physical promotion readiness (read-only audit, 2026-08-08)

- Static development gates pass: Ruff format/check, strict mypy, `1034` tests,
  shell syntax, systemd unit verification, and 67/67 complete trace audits.
- The active production gateway is healthy but not ready: `/readyz` is HTTP
  `503`; only Reasoner is ready and Executor/Planner/Reviewer/Judge are stopped.
- The production `main` worktree at commit `396e0458` is already dirty and was
  not changed. No service was started or restarted.
- Isolated provider validation was approved on 2026-08-09; production mutation,
  deployment, canary, and rollback rehearsal were not. Mistral readiness,
  Flash, current client matrix, evaluation, ablation, and long-horizon gates
  remain open and keep production promotion blocked.
- The development config now uses the official OpenRouter target
  `anthropic/claude-opus-5` with the published `$5/$25` per-million-token
  accounting. One bounded structured Opus 5 call passed with 3,380 total tokens,
  43.616-second latency, and calculated cost `$0.06798`. Production remains on
  `anthropic/claude-sonnet-4.6` with fallback disabled; no production config
  switch was made.
- The frozen paired non-inferiority analyzer now enforces 30-pair minimum,
  complete client/category coverage, matched conditions/epochs, failed-run zero,
  telemetry/reliability/blinding gates, margin `-0.10`, and deterministic
  10,000-resample seed `20260808`. No current physical comparator matrix exists,
  so this is not a non-inferiority result.
- A read-only 2026-08-09 recheck found the same production state: `/readyz`
  HTTP `503`, Reasoner ready, Executor/Planner/Reviewer/Judge stopped, gateway
  active, and production still dirty at `main@396e0458f259`. Nothing was started
  or changed.
- The credentialed specialist validator now uses measured DeepSeek V4 Pro for
  both remote roles. Planner passed in 11.919 seconds with 1,032 tokens and
  Reviewer passed in 4.071 seconds with 516 tokens. The 4,096-token Kimi Judge
  matrix passed all six judgment/correction rows plus the two-call limit.

## Graph-active Executor qualification (isolated, 2026-08-10)

- v54 clears the 131K CUDA Graph blocker with native allocation and one
  layer-wise cache reclamation after each quantized MARLIN post-process.
- Two cold starts held the post-MARLIN model at 66.06 GiB, allocated the fixed
  3.4 GB KV cache, captured `FULL_DECODE_ONLY`, and reached loopback readiness.
- Short, repeated, 48K-token prefill, native tool continuation, streaming
  cancellation recovery, and exact restart passed without abnormal growth or
  CUDA allocator/launcher errors. The isolated runtime remains on port 19301;
  production and the installed vLLM package are unchanged.
- A targeted gateway on port 19310 reused that runtime for client convergence.
  Codex atomic-store v57, rate-limiter v59, webhook-verifier v60, and dag-runner
  v61 passed all ten public/hidden/isolation/terminal/tool-evidence checks. The
  earlier v58 DAG hidden-validation failure remains retained. These are targeted
  rows, not a completed full client matrix or remote-role qualification.

## Candidate-A post-SGLang client matrix v99 — 2026-08-12

V99 completed `18/20`: Hermes/OpenCode `5/5`, baseline/Codex `4/5`. Codex
log-report rejected valid `sample_limit=0`; baseline atomic-store accepted an
invalid boolean expected version. The other three clients passed each affected
task, so neither failure is a Candidate-A backend verdict. V99 transient units
are inactive after exact cleanup; Candidate A and the production gateway remain
active with zero restarts. Recover both cells in separately named epochs, then
run a fresh full matrix. Blind noninferiority and later gates remain unstarted.

V100 physically recovered Codex log-report at `10/10` in 1,482.571 seconds.
Baseline atomic-store remained failed because invalid `expected_version=True`
raised `VersionConflict` instead of an input-validation exception. The v100
transient gateway is stopped. A new baseline-only recovery epoch is next; no
full matrix or later gate is authorized yet.

V101 reproduced the baseline atomic-store hidden failure at unchanged `high`.
V102 then changed only baseline reasoning effort to `xhigh` and passed `10/10`
in 190.610 seconds. Baseline xhigh is the new matrix candidate; a fresh 20-cell
epoch is required before blind noninferiority or later gates.

V103 pinned baseline `xhigh` and left every other harness contract unchanged.
It completed all 20 cells at `18/20`: baseline, Hermes, and OpenCode passed
`5/5`; Codex passed `3/5`. Codex rate-limiter failed hidden validation because
its constructor rejected the exercised `window_seconds` input with `TypeError`.
Codex atomic-store passed public validation but failed hidden validation with
`AssertionError: invalid update accepted`. Baseline and OpenCode passed
rate-limiter, while baseline, Hermes, and OpenCode passed atomic-store, so these
are Codex trajectory regressions rather than Candidate-A backend failures.
Exact cleanup stopped all three v103 transient units with result `success` and
zero restarts; Candidate A and the production gateway remain active. Recover
both Codex cells in separately named epochs, then require another fresh matrix.

V104 exact-replayed both Codex failures in fresh workspaces. Attempt 1 stopped
before any request because the launcher omitted the runner's required
`prepare`; that setup failure is preserved. Attempt 2 changed only that setup
step. Codex rate-limiter passed `10/10` in 302.828 seconds and Codex
atomic-store passed `10/10` in 386.212 seconds. Exact cleanup stopped the three
v104 transients with zero restarts while Candidate A and production stayed
active. The targeted recovery passes; another fresh 20-cell matrix is required.

## Pilot real-use graph recovery — 2026-08-12

The first bounded Codex real-use audit did not converge and was cancelled after
five completed streaming turns and one active turn. Its failed client sandbox
commands and five Graph shadow `ValueError` events are preserved under
`real-use-codex-01`; Candidate A and both gateways remained healthy. The common
cause was a projection/runtime mismatch: a failed TOOL continuation resumed its
old Graph while orchestration re-entered completed collaborator nodes, and a
configuration-disabled Frontier role could still be compiled into a mandatory
join branch.

Release candidate `c96ace60` preserves the failed TOOL attempt but compiles
a new Graph before collaborator re-entry, and graph compilation excludes
Frontier when `frontier_enabled=false`. The clean release gate passed Ruff,
strict mypy on 49 source files, and pytest `1061/1061`. Attempt 05 preserved a
credential-expression launch failure; attempt 06 recovered with the verified
escaped launch contract. A physical tool-failure continuation
compiled two graphs, resumed once, retained one failed TOOL attempt, contained
zero Frontier nodes and zero shadow failures, and returned a normal second
completion.

Codex canary 02 then proved that the explicit Korean read-only audit was still
misclassified as implementation and repeated successful reads until bounded
cancel. Canary 03 removed that loop but exposed false completion: no requested
command ran before PASS. Commit `0f170c02` now forces one requested
`exec_command` evidence cycle while keeping explicit read-only work outside the
change/validation/review gate. Canary 04 exited zero after exactly three
successful commands and an evidence-backed PASS, with one Graph compile, one
resume, and zero shadow failures. Attempt 08 is active at that commit with PID
`3597082`, zero restarts, and unchanged 1/2/0.5 GiB limits. Production PID
`3107456` and Candidate A PID `2383374` remained unchanged. The Goal stays
active in `PILOT_ACTIVE`; broader bounded real-use sampling is next.

The same release then passed bounded OpenCode and Hermes read-only audits.
OpenCode executed two `bash` commands, returned `PASS`, and exited zero; Hermes
executed two `terminal` commands, returned exactly `PASS`, and exited zero.
Each durable session compiled once, resumed once, and recorded zero shadow
failures. OpenCode exposed a host inotify `ENOSPC` warning while still passing;
that warning is an operating-resource observation, not backend failure.
Read-only `/proc` accounting found `zed-remote-serv` PID `3393658` owns 65,448
of the 65,536 allowed user watches; Codex owns 35. No process was stopped and no
sysctl was changed. Pilot attempt 08 remained healthy through this observation.

An additional Codex review canary returned plain-text `FAIL` instead of its
requested JSON schema. Its Graph concern was rejected because it contradicted
the focused test and physical continuation canary; both the invalid review and
rejection are preserved. Independent inspection found a real shared-boundary
bug: any earlier successful tool in a session could satisfy a later explicit
tool instruction. Release `40fddc0b2e05520117fdfc93d4247528ebe86406`
stores the explicit instruction hash and a durable tool-evidence cursor, so
only success after the current instruction counts. The clean gate passed Ruff,
strict mypy on 49 source files, and pytest `1061/1061`.

Physical same-session validation first completed an unrelated `noop`, then
issued a new explicit `exec_command` instruction. The gateway still required
and completed the requested `printf SCOPED_OK`; its durable cursor was `1`, two
tool executions were retained, and four requests used 6,105 tokens over 14.497
active seconds with zero Graph shadow failures. Codex canary 05 then executed
exactly two requested repository reads and returned `PASS`: two Gateway
requests used 12,157 tokens over 21.640 active seconds, with one Graph compile,
one resume, and zero shadow failures. Attempt 09 is active at this release with
PID `3628923`, zero restarts, and unchanged 1/2/0.5 GiB limits. Production PID
`3107456` and Candidate A PID `2383374` remain active; the tailnet-bound Pilot
`/healthz` is HTTP 200 and Candidate A remains loopback-only. The Goal remains
active in `PILOT_ACTIVE`.

## Pilot write canary and Graph reprojection — 2026-08-12

`dgx-moa-gateway.service` is recovered and remains `active/running` at PID
`3107456` with zero restarts. The authenticated production gateway was not
restarted during the isolated Pilot recovery. Pilot attempt 10 runs controller
`ed9f3d943d8f3c8b6877293472cef2d6c6db4140` at PID `3704865`, zero restarts,
with the preserved 1/2/0.5 GiB cgroup limits.

The bounded Codex repository-write canary reproduced a shared Graph defect:
after successful non-validation TOOL cycles exhausted the single repair edge,
the immutable Graph was returned and later resumed although no ready node
remained. Release `ed9f3d943` now records
`execution_graph_shadow_reprojected(reason=tool_cycle_budget_exhausted)` and
compiles a fresh Graph instead of widening the two-repair bound. The clean gate
passed Ruff, strict mypy on 49 source files, and pytest `1062/1062`. Physical
attempts after deployment recorded reprojections with zero shadow failures.

The Graph failure family is closed, but the repository-write canary is not.
With an explicitly pinned Codex model catalog, `apply_patch` was advertised;
`dgx-moa-fast` still repeated reads and the primary `dgx-moa` path attempted two
unsuccessful shell rewrites before bounded cancellation. The isolated worktree
remained unchanged. This is an open client/Executor quality gate, not a vLLM
Candidate-A kernel, CUDA Graph, or memory failure. Exact session counters and
hashes are frozen in `real-use-codex-write-01/result.json`.

Blackwell qualification ordering remains evidence-based: vLLM explicit native
NVFP4 B12x is preserved as known-good production candidate A; SGLang native was
evaluated as isolated candidate B in v66 and the released-runtime v98 retry;
MARLIN remains compatibility rollback only. The pinned SGLang runtime failed
its native MLA/model-shape and API/tool semantic gates, so it is rejected for
this epoch without generalizing that result to SGLang or claiming MARLIN is
optimal on Blackwell.

## Primary Codex write recovery — 2026-08-12

Epoch 02 proved that a Codex `apply_patch verification failed:` payload without
a numeric exit code was normalized as success. Commit `b6912a119` maps that
envelope to nonzero; epoch 03 physically recorded every malformed patch as
`TEST_FAILURE`. Epoch 03 then exposed a distinct classifier defect: `Do not
modify any other file` was treated as global read-only intent.

Commit `2a3afdce826b7fbc4e5cf3d682085b427ebcfa22` preserves that scoped write
intent. Ruff, strict mypy on 49 source files, and pytest `1062/1062` passed.
Pilot attempt 12 runs it at PID `3790208`, restart 0, under 1/2/0.5 GiB limits.

Epoch 04 passed the same primary `dgx-moa` task: two malformed patches remained
failures, the third patch produced exactly two requested insertions in one
file, pytest reported `103 passed`, Reviewer approved with no findings, and
Graph shadow failures remained zero. The targeted write gate is recovered; a
fresh client-quality matrix is next.

## Client-quality v106 and scoped-validation recovery v107 — 2026-08-12

The frozen v106 matrix completed all 20 cells without gateway restart:
baseline `5/5`, OpenCode `5/5`, Codex `0/5`, and Hermes `0/5`. Hermes passed
visible and hidden validation in every task but failed native unittest tool
evidence `5/5`; Codex recorded writes in every task but failed visible and
hidden validation `5/5`. Blind and later gates remain unopened.

State evidence exposed a Korean scoped-write classifier gap. The objective
`webhook.py만 구현하라. 테스트나 요구사항 파일은 수정하지 마라` was treated as
globally read-only, allowing completion after mutation without a later
successful test. `write_stdin failed: Unknown process id 0` was also normalized
as success. Commit `60f7a236e` adds only those two common guards. Ruff, strict
mypy on 49 source files, and pytest `1062/1062` passed.

Isolated v107 passed the same Codex webhook cell in 434.176 seconds. Two native
unittest failures were retained, the third native unittest call exited zero,
and all scoring checks passed. Attempt 01 failed before readiness because the
transient unit omitted `WorkingDirectory`; attempt 02 changed only that launch
variable and passed. Production, Pilot attempt 12, and Candidate A remained
HTTP 200; v107 services cleaned up successfully. A fresh post-recovery matrix
is still required before blind non-inferiority.

Hermes targeted v108 passed the identical webhook task in 343.912 seconds
with one native unittest call and one successful result. All ten checks passed;
cleanup succeeded; production, Pilot, and Candidate A returned HTTP 200. Both
failed v106 client families now have targeted recovery evidence at `60f7a236e`.

## Production Role Context epoch — 2026-08-13

`main`과 production checkout은 `ffdf006a4`로 정렬됐고 fixed gateway가
`0.0.0.0:9000`에서 active/restart 0으로 실행 중이다. Candidate A만
`127.0.0.1:19301`에 남는다. Dashboard는 일곱 역할 모두 available,
ExecutionGraph `shadow`, `static_skeleton+runtime_created_request_subgraph`,
네 static template, `runtime_mutation=false`를 보고한다.

인증된 실제 architecture 요청은 HTTP 200이었고 `complex-v1` 10-node/26-edge
Graph의 모든 attempt가 성공했다. Frontier A는 GPT-5.6-Sol `xhigh`, Codex OAuth
`primary`, 15,819/966 tokens, 24,569.716 ms였다. 이전 release checkout과 현
release redeploy canary도 동일 해시로 통과했다. 단, high-risk correction 경로는
Judge/Frontier B 호출 후 300초를 넘고 fail-closed됐으므로 상태는 계속
`PILOT_ACTIVE`이며 `COMPLETE`가 아니다. 세부 증거는
`docs/DYNAMIC_MOA_PILOT_CONTEXT_EPOCH_20260813.md`가 우선한다.

## Pilot feedback epoch — 2026-08-13

Production is `PILOT_ACTIVE` on runtime code `fd658a1e8`; the fixed gateway is
authenticated on `0.0.0.0:9000` with restart count zero. Candidate A alone
listens on loopback `127.0.0.1:19301`; Reasoner remains external at
`100.90.167.128`. The seven-role Static Graph Skeleton plus runtime-created
request subgraph was exercised by a final authenticated high-risk request.
Post-Pilot beta/stable, training, weekly, and retention gates remain deferred.

## Authoritative role correction — 2026-08-13

Reviewer is OpenCode Go `glm-5.2`. DeepSeek V4 Flash is Executor-only overflow
or fallback when the local Executor is busy or explicitly disabled by the
operator; it is not Reviewer. This mapping supersedes older experimental and
Pilot prose that names a DeepSeek model as Reviewer.

Runtime code `a1ea6d7b2` is deployed with that mapping. A fresh Dashboard
snapshot reports all seven roles available and names Reviewer `glm-5.2` through
`opencode_go`; Executor remains local Mistral. The same high-risk request
recorded one successful GLM Reviewer invocation and one local Executor
invocation, keeping the roles distinct.

Runtime code `269313420` also restores the intended Executor fallback: a
non-high-risk request selects DeepSeek V4 Flash when local Executor lifecycle
is unavailable or explicitly disabled. High-risk work remains local-only and
fails closed. The resident local Executor policy itself is unchanged.
