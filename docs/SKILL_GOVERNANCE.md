# Skill Governance

Production Skill versions are immutable. Modification creates a candidate
successor; core modification requires an explicit approval ID. Promotion
requires passed validation with evidence plus a human approval ID and creates a
new active version. Generated and imported candidates cannot bypass this gate.

Rollback creates another active version rather than modifying history. It
requires an active current version, a previously validated target and explicit
human approval. Both versions remain in provenance and rollback metrics.

The Phase C foundation can turn an externally detected recurring pattern into a
generated draft and record a bounded multi-gate evaluation. It does not scan
production autonomously. A validated runtime-generated candidate needs an
Executor-evidenced helpful canary before explicit approval can promote it.
Lifecycle changes create immutable successor versions; core changes require
approval, while generated experimental disablement additionally allows an
explicit policy permission. Weekly maintenance is scheduled but remains
disabled and never deletes or promotes automatically.
