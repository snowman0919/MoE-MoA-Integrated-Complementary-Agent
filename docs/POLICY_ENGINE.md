# Declarative Policy Engine

The disabled Phase D foundation is implemented in `gateway/src/dgx_moa/policy.py`.
It accepts versioned rules with `any`/`all`, dotted equality, changed-path glob,
and numeric `gte` conditions. It deliberately does not evaluate Python, shell,
templates, or arbitrary expressions.

Matched rules aggregate `require`, `recommend`, `deny`, `limit`, `redact`,
`request_approval`, and per-role `fail_closed` actions. Limits choose the most
restrictive matched value; any matching true fail-closed action wins.
Every decision records policy version, content hash, matched rule IDs and the
aggregated actions as a `policy_decision` evidence node.

The Controller enforces request denial, missing approval, bounded loop limits,
Planner/Reviewer/Judge role requirements, Frontier escalation metadata, and
globbed per-tool denial before client-visible execution. Policy-selected
Reviewer and Remote Judge failures fail closed. Denial and missing
approval persist `POLICY_BLOCKED` and `PERMISSION_REQUIRED` respectively.
Configured dotted-field redaction is applied before Evidence Graph, decision,
raw tool-result, normalized tool-execution, orchestration, Reasoner, Planner,
Reviewer, Frontier, and Judge persistence. Redacting a whole list or object
preserves its container type so downstream schemas remain valid. Unit tests and
isolated physical validation cover these boundaries; the engine remains
disabled in production.

```yaml
gateway:
  declarative_policy:
    enabled: false
    version: development-disabled
    policies: []
```

An isolated process may pass the same strict object through
`DGX_MOA_DECLARATIVE_POLICY`.
