# Loop Engineering

## Current development boundary

The `dev` source contains the Phase A state foundation and the Phase B bounded
action loop. It is disabled by checked-in default and enabled by the protected
production environment after the live-provider gate passed on 2026-07-22.
An isolated synthetic physical run has exercised successful, no-progress, and
duplicate-failure termination.

`LoopState` is persisted inside the existing task-scoped `SessionState`, so it
uses the existing SQLite WAL transaction and rollback boundary. It records:

- objective, loop type, iteration and explicit termination reason;
- accepted/completed work, changed paths, findings, agents and Skills;
- evidence IDs and required acceptance criteria;
- remaining iteration, tool, role-call, token, Frontier-cost and wall-clock budgets;
- consecutive no-progress state.

Required criteria can pass only with at least one evidence ID. Waivers require
a reason. The deterministic completion predicate requires every required
criterion to be passed or waived and retains the existing Reviewer approval
gate.

The available termination reasons, minimum normalized failure taxonomy, and
failure-fingerprint normalization are in
`gateway/src/dgx_moa/loop_engineering.py`. Fingerprints remove timestamps,
temporary-directory names, request UUIDs, memory addresses and irrelevant line
numbers before hashing. A repeated fingerprint requires a different strategy on
its second occurrence and terminates at the third occurrence. The existing Controller creates a loop only when the
feature flag is enabled, associates new Evidence Graph nodes with it, persists
evidence-backed completion metadata, and applies the configured no-progress
limit.

The Phase B admission boundary now covers iterations, Reasoner entries,
Planner/Reviewer calls and their structured retries, Codex OAuth Frontier,
Heavy Judge, streamed and non-streamed tool calls, observed tokens, known
Frontier cost, and wall time. Parallel client-visible tool calls are disabled
while the loop is active so admission occurs before each emitted call. Only
tool/test/build/lint/type-check/repository/diff/review/Frontier/user/provider/
policy evidence can unlock another iteration; new model assertions alone cannot.
Completion, cancellation, provider outage, no progress, duplicate failure and
budget exhaustion persist explicit termination reasons.

## Configuration

Safe checked-in defaults keep the foundation disabled:

```yaml
gateway:
  loop_engineering:
    enabled: false
    defaults:
      iterations: 8
      tool_calls: 100
      reasoner_reentries: 8
      planner_calls: 2
      reviewer_calls: 8
      frontier_calls: 4
      judge_calls: 2
      tokens: 1000000
      external_cost_usd: 10
      wall_clock_seconds: 1800
    duplicate_fingerprint_limit: 2
    no_progress_iteration_limit: 2
    local_failures_before_frontier: 2
    request_class_overrides: {}
    risk_level_overrides: {}
```

An isolated process may provide the same object through
`DGX_MOA_LOOP_ENGINEERING`. Request-class overrides are applied before
low/medium/high risk overrides. Do not enable it in production until isolated
live providers and real-client validation pass.

## Production gate status

Permission, operator-decision, policy-block and unresolved-disagreement paths
terminate explicitly. Live Reasoner, Executor, local/remote Reviewer, real-client
success, correction, cold-routing, and warm-up-transition validation passed.
Runtime Skills, declarative policy, training, weekly packaging, replay, and the
other separately governed capabilities retain their own disabled gates.
