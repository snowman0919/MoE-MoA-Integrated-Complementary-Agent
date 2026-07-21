# Evidence Graph

The task-scoped graph remains embedded in `SessionState` and therefore uses the
existing SQLite WAL persistence and trace boundary. Nodes now carry a canonical
node type, original event kind, source, payload, timestamp, and explicit trust
class. Edges preserve the existing `from`/`to` trace shape while validating the
required relationship vocabulary.

Trust ordering is deterministic: test-confirmed fact, tool-observed fact,
policy decision, user-provided constraint, review finding, model assertion, and
unverified assumption. The `stronger_evidence` resolver guarantees that tool
and test observations defeat unsupported model claims; equal-rank ties use the
stable node ID.

New objectives, model/agent decisions, Skill and policy selections, provider
failures, tool/test evidence, findings and completion evidence are classified at
the central Controller append boundary. Unknown kinds remain visible as
`assumption` with `unverified_assumption` trust rather than receiving invented
authority.

Replay snapshots validate the full graph: duplicate node IDs, self edges, and
dangling references fail closed. Explicit `contradicts` edges resolve
deterministically by trust rank without deleting either source. The controller
does not infer contradiction edges from free text; specialists or policy must
record that structured relationship explicitly.
