# Unload Mechanism and 64K Memory Study Design

Date: 2026-07-19
Status: approved by the in-thread continuation directive
Starting dev commit: `193b3afa7ab803f0979e890c20b22c24b48297f0`
Production reference commit: `c2a9af0d6b5db8dd940842c56a7236ac867061ff`

## Scope and Priority

This is phase three of the runtime-reliability Goal. It selects an executor
unload mechanism and 65,536-token runtime configuration from physical evidence,
redesigns the undeployed resident profile, and decides whether a small Rust
supervisor is justified. Actual system-memory recovery and reliability outrank
reload speed or feature count.

Phase three does not deploy, restart production, edit the production worktree,
merge to `main`, change AppArmor, enable Frontier, upgrade production vLLM, or
run the final client-count matrix and soak. Phase four retains those tasks.

## Verified Starting State

- `dev` is clean at `193b3af`; production is clean read-only `main` at
  `c2a9af0`.
- Installed vLLM is `0.22.1`. Its local CLI supports sleep mode, explicit KV
  bytes and dtype, prefix caching, chunked prefill, batched-token limits,
  eager mode, CPU weight offload, and native KV offload.
- Sleep control exists only when `VLLM_SERVER_DEV_MODE=1`; its loopback routes
  are `POST /sleep`, `POST /wake_up`, and `GET /is_sleeping`.
- The executor is Qwen3 Next NVFP4 with 65,536 configured context,
  `max_num_seqs=1`, an explicit 1,700,000,000-byte KV cache, and no checkpoint
  `kv_cache_scheme`. Local vLLM disables dynamic KV-scale calculation for this
  hybrid model.
- Task 10 physically proved full exact process stop, host-memory return,
  executor reload, 67,121 KV tokens, and 1.02x capacity for a 65,536-token
  request. It did not compare sleep, KV eviction, FP8 KV, or offload.
- Checked-in lifecycle mode remains `disabled`; the only implemented lifecycle
  action is exact-unit full stop.

## Design Principles

1. Reuse the Task 10 exact-ownership, memory, teardown, and evidence patterns.
2. Change one runtime variable at a time; do not run a factorial sweep.
3. Use foreground processes except the one required isolated transient
   `dgx-moa-dev-*` systemd stop/start trial.
4. Bind every inference and sleep endpoint to unused loopback ports under one
   fresh `/tmp/dgx-moa-phase3-*` root.
5. Fail closed on dirty repositories, bound ports, insufficient memory,
   ownership mismatch, raw-content retention, or incomplete teardown.
6. Keep the public executor limit at 65,536 and concurrency at one.
7. Select no optimization merely because it starts; memory, correctness, and
   repeated reliability must all pass.

## Experiment Runner

One ignored phase-three runner owns every process by PID, PGID, session ID,
start ticks, cwd, and observed argv. It uses an allowlisted environment and
isolated HOME, caches, state, traces, logs, and ports. It revalidates every
group member before termination and records the complete process history.

The runner records JSON only: argv, versions, timestamps, state transitions,
HTTP status, token counts, pass/fail booleans, hashes, memory integers, and
bounded timing. It never retains prompts, model output, tool arguments/results,
credentials, or Authorization headers. Synthetic near-limit input is generated
at runtime and discarded.

Memory snapshots include `/proc/meminfo` MemAvailable, Cached, SReclaimable,
and Shmem plus exact-owned RSS/PSS. GPU used/free bytes are recorded only when
the platform reports them; null remains null. Stage snapshots at process start,
weights loaded, initialization complete, ready, post-request, unload/sleep,
wake, and teardown provide approximate composition. They are labeled as stage
deltas, not exact weight/KV/CUDA allocations.

## Unload Mechanism Matrix

The same baseline command and model revision are used throughout.

### A. Full service stop/start

Run the executor under one transient user unit whose name begins
`dgx-moa-dev-phase3-`. The unit launches only the exact foreground command and
isolated paths. Stop and start that unit once, measure memory and readiness, and
then remove the transient unit. Production unit names are never read or acted
on. If transient-unit isolation cannot be proven before execution, this row is
not run and cannot be claimed from the foreground Task 10 result alone.

### B and C. Sleep levels 1 and 2

Start one loopback executor with sleep mode and dev routes enabled. After a
short and tool-call baseline, run level 1 sleep, bounded memory settlement,
wake, health, short response, and tool call. Repeat for level 2 only if the
installed engine reports successful sleep and wake. Any crash, corrupt output,
failed wake, increased settled memory, or unsupported response rejects that
level.

### D. Live-process KV discard or constraint

With the same process awake, reset prefix/KV state through the installed native
dev-only `POST /reset_prefix_cache` route and measure retained memory.
Separately treat the current 1,700,000,000-byte explicit reservation as the
BF16/auto constrained baseline. Reset success without a material MemAvailable
improvement is recorded as a cache-clear result, not an unload mechanism.

### Mechanism selection

Full stop remains mandatory fallback. A live-process mechanism may replace it
only if it:

- returns at least 90% of the matched full-stop MemAvailable delta after the
  same bounded settlement window;
- leaves no owned-memory growth across two sleep/wake or clear/reuse cycles;
- wakes faster than a full restart;
- has zero failures and passes short, native-tool, and near-64K checks.

Otherwise full stop is selected. System-wide MemAvailable noise and unavailable
GPU bytes remain explicit limitations.

## 64K Optimization Matrix

Candidates are screened independently so every required option receives either
a physical row or a precise unsupported rejection. Each physical candidate
differs from the current baseline by one setting:

1. current auto KV dtype, 1,700,000,000 KV bytes, default graph and cache;
2. FP8 KV dtype with 900,000,000 KV bytes;
3. prefix caching explicitly disabled;
4. eager mode instead of CUDA graphs;
5. chunked prefill with `max_num_batched_tokens=8192`;
6. CPU weight offload at 4 GiB as a unified-memory negative control;
7. native KV offload at 1 GiB as a unified-memory negative control.

`gpu_memory_utilization` is not swept because explicit KV bytes override its KV
allocation effect. `max_num_seqs=1` remains fixed. Unsupported configuration is
recorded and rejected rather than patched around.

FP8 starts at 900,000,000 bytes, slightly above half the known auto-dtype
reservation. One bounded 1,000,000,000-byte retry is allowed only when the
first failure is insufficient KV capacity. Dynamic scale calculation is tested
at configuration/startup. Because local vLLM disables it for Qwen3 Next and the
checkpoint has no KV scales, FP8 cannot be selected unless fixed-scale physical
quality matches the baseline with no instability. Startup alone is insufficient.

Prefix caching is tested with two identical synthetic system-prefix requests.
Record first and repeat prefill latency, hit-rate evidence, post-request
MemAvailable/PSS, reset result, and retained cost. Disable it only if latency
benefit is absent or its retained-memory cost conflicts with recovery.

## Physical Quality Contract

The runner builds a nonsensitive prompt with the local tokenizer and chat
template. Prompt usage must fall between 63,000 and 64,500 tokens, leaving room
for response tokens under the 65,536 server limit. The backend must accept and
process it without OOM and return the expected synthetic retrieval token.

Every selectable candidate must also pass:

- five fixed short-answer checks with exact expected facts;
- one response exceeding 1,000 tokens without unexpected truncation;
- three forced native tool calls with valid names, IDs, and JSON arguments;
- one deterministic code task whose generated function passes a bounded local
  test without executing arbitrary model-provided shell;
- one strict review-shaped JSON-schema response;
- finite logits/output behavior, HTTP success, and valid finish reasons;
- recorded warm latency and exact-owned/system memory deltas.

Only the selected configuration runs three clean start/ready/near-64K/tool/stop
cycles. Selection requires zero load, request, validation, or teardown failures
across all three. A final gateway request confirms advertised 65,536 context and
normal client behavior.

## Resident Profile Decision

After the mechanism and 64K configuration pass, the undeployed target topology
is changed to:

- always resident: authenticated gateway and lifecycle supervisor;
- normally warm when usage justifies it: executor;
- on demand: planner, reviewer, reasoner, and judge.

Direct chat and agent aliases continue to require only executor. Explicit
orchestration with a cold optional role returns typed `model_loading` 503. No
silent executor-only degradation is added. Production lifecycle mode stays
disabled and no unit is started or deployed by the tracked change.

## Rust Evaluation

Measure the isolated Python gateway/supervisor with models absent: PSS/RSS,
five-minute idle CPU, event-loop delay distribution, startup time, and existing
restart-recovery tests. Compare that footprint with measured model memory.

No Rust prototype is created unless Python shows a material problem: idle PSS
above 256 MiB, sustained idle CPU above 1%, p99 event-loop delay above 50 ms, or
an unresolved lifecycle-correctness failure attributable to the Python runtime.
Otherwise `docs/RUST_EVALUATION.md` records the measured rejection. This avoids
a second supervisor implementation with no demonstrated benefit.

## Tracked Changes

The ignored runner and raw roots remain outside Git. Tracked changes are limited
to what measured selection requires:

- minimal environment-to-vLLM argument support in `gateway/src/dgx_moa/serve.py`
  and its existing test file, only for selected settings;
- resident target/config changes after physical proof;
- `docs/MEMORY_OPTIMIZATION.md`, `docs/RUST_EVALUATION.md`, and evidence/state/
  operations/decision updates.

No general mechanism interface, plugin system, new dependency, dashboard,
daemon, or Rust scaffold is introduced.

## Validation and Evidence Gates

The ignored runner is test-driven for ownership, redaction, token targeting,
candidate validation, threshold selection, and teardown. Before every physical
execution, run the full repository gates, runner tests/lint/compile/dry-run,
port/process checks, memory gates, and model metadata fingerprint. After each
execution, independently review raw evidence before using it in documentation.

Final tracked gates are pytest, Ruff format/check, MyPy, user-unit verification,
shell syntax, trace completeness, and `git diff --check`. Failed starts, quality
regressions, unsupported flags, leaks, and inconclusive memory rows remain in
`docs/VALIDATION.md`; they are never rewritten as passes.

## Acceptance Boundary

Phase three is complete only when:

- A through D have supported or honestly rejected physical rows;
- one unload mechanism is selected with full stop preserved as fallback;
- one selected executor configuration passes three 65,536-capable cycles and
  the complete quality contract;
- executor-only warm memory and cold memory are measured against the existing
  three-role resident evidence;
- optional roles are absent while cold and the undeployed resident design no
  longer requires them;
- Python baseline measurements support a documented Rust decision;
- all final gates and independent evidence review pass.
