# Execution Replay

The Phase H foundation snapshots task state, engineering-loop state, Evidence
Graph, exact Skill, Knowledge, and Prompt versions, policy version/hash,
model-role revisions, invoked roles, structured
mock provider outputs and the original outcome. Snapshot files are written
atomically and protected by a canonical SHA-256 content hash.

Supported modes are audit, regression, Skill evaluation, routing-policy
comparison and training-candidate validation. Exact replay refuses live
providers and requires mock output for every originally invoked role. Live
comparative replay records `live_provider_outputs`; Frontier, stochastic model
configuration and tool/filesystem state are recorded as additional sources of
nondeterminism. The runtime never claims bit-for-bit determinism while any such
source remains.

Audit replay can inspect the original bounded outcome without provider calls.
Other modes accept an explicit evaluator and either complete mocks or a live
provider callback. The authenticated admin API accepts audit replay and exact
mock replay. It refuses live comparative replay because that requires the
internal provider callback and a separately controlled environment. The
2026-07-22 isolated physical run verified the snapshot hash and exact-replayed a
non-empty loop state and Evidence Graph. Production then enabled the
operator-only endpoint and exact-replayed an Executor snapshot with
`prompt.executor@1`, a stable hash, complete mocks, no nondeterminism, and a
deterministic claim. A non-exact routing-policy comparison returned 409 because
the admin surface intentionally has no live provider callback.
