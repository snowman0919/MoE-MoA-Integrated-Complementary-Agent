# Weekly Maintenance and Packaging

The disabled Phase G foundation computes the previous complete Monday-Sunday
window in a configured timezone (default `Asia/Seoul`). Skill maintenance writes
JSON and Markdown reports with usage, value classification, regressions,
duplicates and approval-required recommendations; it performs no automatic
deletion or core deprecation.

The packager builds the prescribed role-specific dataset tree, reports,
snapshots, manifest, indices, metadata-only quarantine and SHA-256 checksums in a
same-filesystem staging directory. It rechecks eligibility and privacy, removes
exact and normalized near duplicates, invokes `7zz` then `7z`, verifies with
`7z t`, fsyncs, atomically renames the archive, writes a checksum sidecar and
updates a WAL archive registry. Window/schema/policy/source content form the
idempotency key. Failed verification removes temporary archives and records a
sanitized failure class without deleting source candidates.

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
No timer was installed because systemd topology changes require separate human
approval. Instead, enabling weekly jobs starts a bounded in-process scheduler:
Skill reports Sunday 03:00 and previous-complete-week packaging Monday 02:00 in
the configured timezone. Reports contain real role/type/language/quality/privacy/
dedup/Skill/routing/failure aggregates and request/candidate indices. Completion
publishes only package ID, counts, relative storage identifier, checksum, and
verification status through the observation bus. Checked-in weekly jobs remain
disabled and no wall-clock scheduled run or real Discord/Telegram notification
has occurred.
