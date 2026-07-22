# Weekly Maintenance and Packaging

The disabled Phase G foundation computes the previous complete Monday-Sunday
window in a configured timezone (default `Asia/Seoul`). Skill and Knowledge
maintenance writes JSON and Markdown reports with usage, value classification,
regressions or harmful selections, conflicts, staleness, duplicates, and
approval-required recommendations. The aggregate Runtime Improvement report has
all required Skill, Knowledge, Prompt, Policy, Routing, Judge, specialist, loop,
tool/MCP, dataset, promotion, deprecation, automatic-action, and human-decision
sections. Missing measured inputs remain empty; they are never synthesized. The
jobs perform no automatic deletion, promotion, or core deprecation.

The packager builds the prescribed role-specific dataset tree, reports,
snapshots, manifest, indices, metadata-only quarantine and SHA-256 checksums in a
same-filesystem staging directory. It rechecks eligibility and privacy, removes
exact and normalized near duplicates, invokes `7zz` then `7z`, verifies with
`7z t`, fsyncs, atomically renames the archive, writes a checksum sidecar and
updates a WAL archive registry. Window/schema/policy/source content and exact
model/Judge configuration form the idempotency key. Production jobs derive
SHA-256 fingerprints from Skill, Knowledge, Prompt, Policy, and specialist
routing state rather than writing placeholder versions. A configurable
free-space reserve is checked before staging; low storage records a sanitized
failure and leaves serving state untouched. Failed verification removes
temporary archives without deleting source candidates.

Completed packages can be reverified against both the recorded SHA-256 and
`7z t`. Revocation writes an archive-registry tombstone and changes the package
state without deleting its source candidates. A normal rerun refuses to revive
that idempotency key; only explicit regeneration may atomically rebuild it after
exclusions have been reapplied. Authenticated verify, revoke, regeneration,
dry-run-first retention, and hold workflows are implemented.

Optional encryption fails closed because available 7z password flags expose the
password in process arguments. A protected non-command-line password mechanism
must be proven before enabling encryption.

This host has a user-local `7z` wrapper backed by Ubuntu arm64 7-Zip 23.01;
the installed binary/module/wrapper SHA-256 values are respectively
`e50e9cd58cc8ec1a2fdb7f64e3e0f87ce29cad2dd78c5da36712234d208f690b`,
`c1f1e2e03c325ee48ec2727168e6812a602dcb67ac828cc09d3de18fc3d7ead0`, and
`ae16c842a851d11cb28c382021065d49db13070044ec00e7a7efe4fdd89eeb56`.
The authoritative 2026-07-22 isolated physical result is
`/tmp/dgx-moa-self-evolving-physical-20260722-r9/physical-validation.json`,
SHA-256 `cc98684cfbbc8055dc21328c09db27c7131631cd2742be4db74f95d39df56f26`.
It produced and tested real archives, retained non-empty loop-transition and
repair-preference datasets, verified the SHA-256 sidecar, exercised idempotent
rerun and explicit revocation/regeneration, and detected deliberate corruption
and archiver failure. It used synthetic data only; no production data was
exported.
The extended maintenance validation at
`/tmp/dgx-moa-v2-maintenance-WzvpXt/runtime/physical-validation.json` also
generated Skill, Knowledge, and aggregate Runtime Improvement reports and
retained zero automatic actions. Its regenerated archive SHA-256 was
`59d4ad30d4ab19994e8158262aa1930b77622c893f1d28e3121f9214b7cc2efc`.
No timer was installed because systemd topology changes require separate human
approval. Instead, enabling weekly jobs starts a bounded in-process scheduler:
Skill, Knowledge, and aggregate Runtime Improvement reports Sunday 03:00, then
previous-complete-week packaging Monday 02:00 in the configured timezone.
Reports contain real role/type/language/quality/privacy/
dedup/Skill/routing/failure aggregates and request/candidate indices. Completion
publishes only package ID, counts, relative storage identifier, checksum, and
verification status through the observation bus. Checked-in weekly jobs remain
disabled. The production filesystem currently has less than the configured
10 GB reserve, so enabling the scheduler remains blocked. An isolated real-clock
check scheduled both jobs for the next
`Asia/Seoul` minute: package fired at `2026-07-22T09:09:00.005371+09:00` and
Skill maintenance at `2026-07-22T09:09:00.291290+09:00`. The first validation
attempt used the non-IANA OS abbreviation `KST` and timed out; the authoritative
rerun used the configured IANA key `Asia/Seoul`. No production scheduled run or
real Discord/Telegram notification has occurred.
