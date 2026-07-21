# Declarative Policy Engine

The disabled Phase D foundation is implemented in `gateway/src/dgx_moa/policy.py`.
It accepts versioned rules with `any`/`all`, dotted equality, changed-path glob,
and numeric `gte` conditions. It deliberately does not evaluate Python, shell,
templates, or arbitrary expressions.

Matched rules aggregate `require`, `recommend`, `deny`, `limit`, `redact`, and
`request_approval` actions. Limits choose the most restrictive matched value.
Every decision records policy version, content hash, matched rule IDs and the
aggregated actions as a `policy_decision` evidence node.

The Controller enforces request denial, missing approval, bounded loop limits,
Planner/Reviewer/Judge role requirements, Frontier escalation metadata, and
globbed per-tool denial before client-visible execution. Denial and missing
approval persist `POLICY_BLOCKED` and `PERMISSION_REQUIRED` respectively.
Configured dotted-field redaction is applied before Evidence Graph, decision,
raw tool-result and normalized tool-execution persistence. Other optional
artifact boundaries still require an explicit audit before Phase D can be
described as complete, so it remains disabled in production.

```yaml
gateway:
  declarative_policy:
    enabled: false
    version: development-disabled
    policies: []
```

An isolated process may pass the same strict object through
`DGX_MOA_DECLARATIVE_POLICY`.
