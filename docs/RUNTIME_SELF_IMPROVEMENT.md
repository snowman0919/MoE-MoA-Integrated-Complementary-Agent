# Runtime self-improvement

The governed evolution registry stores immutable Prompt, Policy, Routing,
failure-handling, and Judge-prompt candidates in SQLite/WAL. Prompt roles are
bounded to Reasoner, Executor, Planner, Reviewer, Frontier, Judge, Skill
generation, Knowledge generation, and dataset transformation.

The only allowed lifecycle is:

`candidate -> evaluated -> canary -> active`

Evaluation requires schema validation, historical replay, regression thresholds,
Reviewer approval, and evidence IDs. High-impact changes additionally require
Judge approval. Canary start requires human approval and a versioned rollback
target. Promotion requires an Executor-evidenced helpful canary and another
explicit approval. Rollback creates a new active version with both current and
target ancestry. Rejected candidates remain immutable evidence.

When the disabled runtime gate is enabled, the latest approved active Prompt may
replace only the matching role-policy text inside the existing prompt sandwich.
Output schemas, bounded context, untrusted-data separation, no-hidden-reasoning
rules, and Executor tool/final authority remain controller-owned and cannot be
overridden by a registry Prompt.

Checked-in `gateway.runtime_evolution.enabled` is `false`. The registry never
auto-promotes or edits Git, services, production state, or Frontier hosts. Weekly
recommendations are candidates only.
