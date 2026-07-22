# Training Data

The Phase F collector is separate from operational traces. Completed
trace snapshots may be projected into a dedicated SQLite WAL database and a
content-addressed Zstandard JSON object store only when collection is explicitly
enabled. Object writes are bounded, hash-verified, deduplicated and atomically
renamed at `objects/sha256/ab/cd/<hash>.json.zst`. Legacy gzip objects remain
readable for migration. A free-space guard rejects training writes without
failing inference.

Raw training events use the fixed provider classes `local`, `frontier`, and
`opencode_go`. Required quality-label fields remain explicitly null when the
trace contains no trustworthy measurement; the collector does not infer them.

Eligibility fails closed unless the trace is explicitly eligible and its
repository is configured `training_allowed`. Request/user opt-out, repository
`internal_only`/`training_denied`/unknown, tombstones, or unapproved external
model output prevent training eligibility. Excluded content is replaced with
metadata rather than copied into the training store.

Production clients that may contribute data must send `X-Workspace-ID` and
`X-Workspace-Path`; the stable ID must exactly match a configured repository
policy. Never classify the fallback `external-api` identity as
`training_allowed`, because it can contain requests for unrelated repositories.

Eligible traces create distinct Executor, Reasoner, Planner, Reviewer, routing,
tool-use, Skill, and engineering-loop candidates only when the corresponding
trace material exists. Successful and failed trajectories receive evidence-based
quality labels and failure classes. A successful evidence-grounded answer paired
with retained failures produces a repair preference; Frontier prestige alone
never does. Derived candidates retain the source trace's privacy counters. Exact
candidate deduplication is transactional; normalized Jaccard near-duplicate
detection is available for the weekly pipeline.

When external-output training is explicitly permitted, OpenCode Go evaluations
produce separate categorical Judge verdict, finding, correction, escalation,
and explicitly later-confirmed false-approval/false-rejection candidates. These
projections retain severity/category and deterministic confirmation metadata,
not verbatim provider findings or correction prose. Without that explicit
permission, raw external output remains ineligible.

The admin workflow can inspect a candidate, perform only allowlisted
review-state transitions, and retrieve the immutable audit history. Approval
and packaging fail closed for ineligible candidates. Request exclusion creates
a tombstone and transactionally revokes linked candidates; repository exclusion
stores only a canonical identity hash and causes later collection to fail
closed. These routes require the existing admin boundary and return `404` while
training collection is disabled.

Quality admission now checks language, evidence grounding, conversation
reconstruction, tool-call/result IDs, loop-transition continuity, truncation,
and malformed-output labels. User opt-out stores only a SHA-256 subject hash.
Integrity verification covers both SQLite and referenced content objects;
backup uses SQLite online backup, integrity check, fsync, and atomic replace.

This foundation does not train a model or upload anything. An isolated synthetic
run physically collected candidates, backed up and integrity-checked the WAL
store, and placed non-empty loop-transition and repair-preference datasets in a
verified real 7z archive. Production collection and the bounded weekly scheduler
are enabled only through the protected override for workspace `moa-production`;
external output, retention apply, archive export, and model training remain
disabled.
