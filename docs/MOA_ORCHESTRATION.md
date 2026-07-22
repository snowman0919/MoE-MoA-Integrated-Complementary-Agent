# Dynamic MoA orchestration

When enabled after physical gates, the Executor retrieves bounded active
Runtime Knowledge before Skills and records both selection reasons. A required
Remote Judge receives only sanitized evidence after concrete specialist/tool
evidence exists. It cannot call tools or replace the final response; the
Executor applies any required edits and owns targeted revalidation. Remote
calls are capped at an initial judgment plus one recheck.

## Authority and profiles

`dgx-moa` is the primary Reasoner + Executor profile. `dgx-moa-fast` is the
only intentional Executor-only compatibility profile. `dgx-moa-agent` retains
the core MoA while an external client owns the tool-result loop.
`dgx-moa-orchestrated` enables dynamic specialists and Frontier collaboration.

For every normal MoA turn the gateway builds bounded shared context, invokes the
external Ollama Reasoner, validates its structured contribution, and supplies
that contribution to the Executor. The Reasoner cannot issue tools, edit files,
call another provider, or answer the client. The Executor owns the structured
routing decision, native tool calls, recommendation resolution, and final output.

## Bounded artifacts

The Reasoner returns problem interpretation, constraints, concise reasoning
conclusions, risks, unknowns, recommended actions, additional-agent
recommendations, and self-reported confidence. Confidence is only a routing
feature. Derived confidence also considers validation, failures, unsupported
assumptions, review findings, retries, and disagreement.

The Executor decision names required and optional agents, per-agent reasons,
parallelizability, continuation, and confidence. Deterministic safety policy may
add agents but cannot silently remove a hard-required review. Architecture and
design normally add Planner + Frontier; code review normally adds Reviewer +
Frontier; unresolved high-risk disagreement may add Heavy Judge.

Each request has at most the configured step budget. Contributions are one-shot
structured artifacts, not an unbounded agent conversation. Meaningful new tool,
test, repository, or review evidence may start another bounded Reasoner turn;
trivial tool events do not.

The disabled development loop adds explicit per-role/tool/token/cost/wall-clock
budgets and requires allowlisted new evidence before another iteration. The
Executor alone retrieves and activates bounded Skills and remains the only
client-visible tool/final-response owner. Generated Skill canaries and replay
evaluations do not gain direct host mutation authority.
Frontier has a separate maximum of three invocations per task and three bounded
recursive cycles. A material local Reviewer rejection can trigger a sequential
Frontier code review when the initial routing decision did not already select it.

## Collaboration patterns

- Core: Reasoner → Executor.
- Design: independent Planner and Frontier architecture work in parallel →
  Executor synthesis.
- Implementation: Reasoner → Executor tool call → client tool result → Executor;
  meaningful failure evidence may re-enter Reasoner.
- Review: independent local Reviewer + Frontier code review → Executor resolution.
- Adjudication: unresolved material high-risk disagreement → exclusive Heavy Judge.

Optional Frontier failure is recorded and lowers derived confidence. A policy-
required Frontier failure returns typed `503`; the trace must never claim that a
review occurred. Only the Executor response is returned to ordinary clients.

## Current deployment boundary

The contracts are production-enabled. The core, external-client loops, Codex
OAuth modes, evidence traces, and per-token accounting have production physical
evidence. Planner and Reviewer passed real-weight client paths; the exclusive
Heavy Judge resume path passed a real-weight adjudication, guard-error matrix,
teardown, and resident restoration. Safe checked-in lifecycle and Frontier
defaults remain disabled/empty; the ignored 0600 production environment enables
the reviewed adaptive unit map and ordered OAuth profiles.
