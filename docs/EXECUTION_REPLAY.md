# Execution Replay

The Phase H foundation snapshots task state, Evidence Graph, exact Skill
versions, policy version/hash, model-role revisions, invoked roles, structured
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
internal provider callback and a separately controlled environment. This has
unit evidence only and is not production-enabled.
