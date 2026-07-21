# Privacy and Retention

Training sanitization detects common API/OAuth/authorization credentials,
private-key markers, connection strings, high-entropy tokens, email addresses
and phone numbers. Synthetic tests verify redaction. Raw external-model output
is excluded unless both provider and project permission are configured.

Unknown repository policy is never training-eligible. Request and user opt-out
flags are snapshot into trace metrics; retroactive request exclusion creates a
tombstone and revokes every linked candidate. Repository exclusions persist a
canonical identity hash rather than the raw repository path. Package selection
rechecks tombstones, so a later weekly package cannot include a revoked request
even if its sanitized candidate predates the tombstone.

Retention is dry-run by default. Legal, investigation, preservation, and
unresolved-deletion holds block candidate/event/archive removal. Request
tombstones revoke linked candidates; package revocation creates a tombstone and
requires explicit regeneration. Only `apply=true` removes expired eligible
records and unreferenced CAS objects or archives, with package-root escape and
shared-archive checks. These paths have synthetic unit evidence only, so no
production retention claim is made.
