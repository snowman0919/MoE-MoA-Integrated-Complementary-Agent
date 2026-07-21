# Training Data

The disabled Phase F collector is separate from operational traces. Completed
trace snapshots may be projected into a dedicated SQLite WAL database and a
content-addressed gzip JSON object store only when collection is explicitly
enabled. Object writes are bounded, hash-verified, deduplicated and atomically
renamed. A free-space guard rejects training writes without failing inference.

Eligibility fails closed unless the trace is explicitly eligible and its
repository is configured `training_allowed`. Request/user opt-out, repository
`internal_only`/`training_denied`/unknown, tombstones, or unapproved external
model output prevent training eligibility. Excluded content is replaced with
metadata rather than copied into the training store.

Eligible traces create distinct Executor, Reasoner, Planner, Reviewer, routing,
tool-use and Skill candidates only when the corresponding trace material exists.
Successful and failed repair trajectories receive evidence-based quality labels.
Preference candidates require accepted and rejected answers plus observable
grounding evidence. Exact candidate deduplication is transactional; normalized
Jaccard near-duplicate detection is available for the later weekly pipeline.

The disabled admin workflow can inspect a candidate, perform only allowlisted
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

This foundation does not export approved training data, train a model, or upload
anything. The authenticated review/retention/package workflows and weekly
scheduler remain disabled until physical validation.
