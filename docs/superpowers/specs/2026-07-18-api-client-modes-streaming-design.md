# API Client Modes and Real Streaming Design

Date: 2026-07-18
Status: approved architecture, pending written-spec review
Starting dev commit: `e47991dc4eeb71d54a05e5e17e49f5f9a8d50836`
Production reference commit: `c2a9af0d6b5db8dd940842c56a7236ac867061ff`

## Scope

This is the first sub-project of the runtime-reliability Goal. It fixes the API
contract and latency defects before lifecycle unloading or memory optimization:

- discoverable client modes selected by the OpenAI `model` field;
- executor-only chat and external-agent paths;
- normal executor content and native tool calls;
- immediate, cancellable SSE forwarding with bounded observation capture;
- practical output budgets and explicit truncation;
- deterministic orchestration and reviewer policy;
- stage-specific timing and failure evidence.

Later sub-projects retain the full Goal: usage statistics, lifecycle state,
adaptive unloading, loading progress, memory studies, Hermes/OpenCode physical
matrices, 64K validation, documentation completion, and the final PR.

## Verified Starting State

The clean `dev` worktree passes 110 tests, Ruff format/check, MyPy, shell syntax,
and systemd verification. Current code nevertheless confirms these defects:

- `/v1/models` exposes only `dgx-moa-agent`;
- missing project metadata selects the standard route and invokes the planner;
- every stopped non-streaming executor response invokes the reviewer;
- streaming accumulates all upstream chunks, waits for review, then replays them;
- streaming reviewer failure preserves output while non-streaming failure becomes
  a generic 502;
- executor output is capped at 1,000 tokens;
- all model contexts are configured at 65,536 and lower runtime overrides are
  ignored by `max(configured, override)`;
- reviewer input contains final assistant output but lacks bounded diff, tool,
  validation, scope, and completion evidence.

Installed runtime versions are vLLM 0.22.1, OpenCode 1.17.18, and Hermes Agent
0.18.2. Production services were stopped during the audit; model-process memory
was therefore zero and `/proc/meminfo` reported about 116.25 GiB available.

## Architecture

Keep one authenticated FastAPI gateway and one executor provider. Add a small
alias-to-mode mapping at the API boundary; do not introduce another gateway,
framework, database, or service layer.

| Public model | Runtime mode | Required roles | Tool-loop owner |
| --- | --- | --- | --- |
| `dgx-moa-chat` | `chat` | executor | client, when tools supplied |
| `dgx-moa-agent` | `agent` | executor | external agent client |
| `dgx-moa-orchestrated` | `orchestrated` | policy-selected | gateway policy |

`dgx-moa-agent` remains the existing public name but changes to the external-agent
contract required by the Goal. `/v1/models` advertises all three aliases with
65,536 context. Unknown aliases return an OpenAI-compatible invalid-model error.
No User-Agent inference or required custom metadata participates in mode selection.

## Request Flow

### Chat and agent modes

1. Authenticate and validate the OpenAI request.
2. Resolve the model alias and require only the executor.
3. Preserve supported request fields and translate only the public alias to the
   executor's served name.
4. Call the executor directly, without planner, reviewer, Judge, or an internal
   tool loop.
5. Preserve upstream response identity, model-visible content, tool calls, finish
   reason, usage, and timestamps while returning the requested public alias where
   OpenAI clients expect it.

Chat and agent share transport behavior. Their semantic difference is explicit
policy and observability: agent mode guarantees that native tool calls and tool
results pass through unchanged and that the external client owns continuation.

### Orchestrated mode

The existing controller remains only for explicit orchestration. A deterministic
classifier records one of:

- `plain_chat`;
- `read_only_question`;
- `native_agent_turn`;
- `small_clear_edit`;
- `multi_file_task`;
- `recovery_task`;
- `high_risk_task`;
- `explicit_orchestrated`.

Classification uses the public alias, messages, tools/tool results, and optional
internal hints. Absence of metadata never triggers planning. Plain chat,
read-only questions, native agent turns, and small clear edits use only the
executor. Multi-file work may use planning; high-risk and explicitly
orchestrated work may use planning plus evidence-based review. Judge remains
explicit and on-demand.

## Executor Contract

Planner, reviewer, and Judge keep strict structured JSON. Executor receives this
contract instead of a JSON-only or single-step imitation:

> Use native OpenAI tool calls when an action is required. Otherwise return normal
> assistant content. Do not encode tool calls as JSON text or wrap native tool
> calls in prose or Markdown fences.

Supported incoming fields are preserved when vLLM 0.22.1 supports them:
`messages`, `tools`, `tool_choice`, `parallel_tool_calls`, `temperature`, `top_p`,
`max_tokens`, `stop`, `stream`, `stream_options`, and `response_format`.
Unsupported combinations are rejected before upstream work with an
OpenAI-compatible error object containing `message`, `type`, `code`, and `param`.
No field is silently rewritten when doing so changes client-visible semantics.

Executor output defaults to 4,096 tokens. A documented server maximum bounds
larger requests; requests above that maximum receive a typed validation error
instead of silent clipping. `finish_reason=length` is recorded as truncation:
chat returns the valid partial answer, agent leaves continuation to the client,
and orchestrated mode may perform at most one policy-enabled continuation.

## Streaming

Provider startup must complete and upstream HTTP errors must be known before the
gateway sends downstream SSE headers. After that point, each upstream SSE byte
chunk is forwarded as received; the same chunk feeds a bounded parser/capture for
trace and optional advisory review.

The streaming path guarantees:

- first content or tool delta is not delayed by planner or reviewer completion;
- native tool-call deltas are not reconstructed or rewritten;
- capture has a fixed byte ceiling and never retains a second unbounded chunk list;
- `[DONE]` is forwarded or synthesized exactly once, then the response closes;
- downstream disconnect closes the upstream response and finalizes counters and
  trace state in `finally` cleanup;
- no retry occurs after any downstream byte or tool-call delta was emitted;
- reviewer output cannot invalidate an already-started standard stream.

For orchestrated streaming, optional review runs only after executor completion
and is advisory. It records status for a later correction turn. It is never a
pre-delivery gate.

## Reviewer Policy and Evidence

Low-risk requests fail open when review is unavailable: preserve valid executor
output, set `review_status=failed`, set `observability_degraded=true`, and record
the typed failure. High-risk explicit orchestration may fail closed according to
the recorded classifier result. Streaming and non-streaming use the same risk
policy.

Review runs only when meaningful implementation evidence exists. Its bounded
input includes available objective, acceptance criteria, changed paths, diff
summary, tool results, validation results, scope evidence, completion evidence,
known failures, executor message, and finish reason. A prose-only chat response
does not invoke a code reviewer.

## Timing and Errors

Each request records monotonic timestamps for acceptance, upstream start, first
upstream byte, first downstream byte, and completion. Role calls additionally
record planner, executor-first-byte, executor-total, and reviewer duration.
Timeouts are stage-specific and bounded. A retryable executor backend failure may
receive one retry only before downstream bytes or tool calls exist.

OpenAI-compatible typed errors cover authentication, validation, invalid model,
model loading, backend timeout, backend failure, and unsupported parameters.
Streaming requests receive a normal JSON error before SSE starts when upstream
setup fails.

## State and Trace Boundaries

Existing SQLite state and trace storage remain. Phase one adds mode,
classification, role requirements, timing fields, truncation, review-failure
policy, and stream completion/cancellation evidence. Content-free aggregate usage
statistics belong to the lifecycle/statistics sub-project; phase-one traces may
retain their existing bounded task evidence but must not add secrets.

## Testing and Validation

Implementation starts by reproducing one real buffered request in an isolated dev
runtime and measuring request start, planner duration, executor first byte,
executor completion, reviewer duration, downstream first byte, and final status.
The runtime uses a separate gateway port, SQLite database, trace directory, and
run directory, with controlled foreground model processes; it does not start,
stop, or replace production services.

Test-first coverage then proves:

- all aliases, discovery, and unknown-model behavior;
- executor-only chat and agent routing without project metadata;
- native tool-call and tool-result identity;
- natural executor output and structured non-executor roles;
- first downstream chunk before upstream completion;
- reviewer non-blocking behavior, bounded capture, cancellation, and one `[DONE]`;
- supported-field preservation and typed unsupported combinations;
- 4,096 default, explicit server maximum, and `finish_reason=length` evidence;
- deterministic classification and consistent reviewer failure policy;
- stage-specific timing and timeout attribution.

After unit checks, isolated real-client validation covers curl, the official
OpenAI Python client, a small streaming consumer, OpenCode, and Hermes Agent.
Phase-one evidence is appended to `docs/VALIDATION.md`; failed attempts remain.

## Deliberate Non-Changes

Phase one does not add lifecycle systemd control, adaptive timers, loading
progress parsing, new memory flags, Rust, or a new database. Those changes need
their own measured design after API behavior is reliable. Production remains
read-only; no service restart, deployment, merge, AppArmor change, Frontier run,
or recursive improvement occurs.

## Acceptance Boundary

Phase one is complete only when unit checks pass and physical isolated-dev
evidence proves immediate streaming, correct native tool round trips, executor-only
ordinary clients, practical output budgets, and consistent reviewer failures.
That completion does not complete the overall Goal; lifecycle, memory, 64K,
extended client matrices, soak, documentation, push, and PR work remain required.
