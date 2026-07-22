# Runtime Knowledge Base

Runtime Knowledge is reusable verified information. It is separate from Skills
(procedures) and Policy (enforced rules).

The SQLite registry uses WAL, foreign keys, immutable `(knowledge_id, version)`
rows, bounded payload models, and an integrity check. Entries include category,
domains, repository scope, structured content, source evidence, provenance,
confidence class/basis, validation evidence, and lifecycle ancestry.

Only active latest versions are retrieved. Bounded lexical/domain/repository
matching records the selection reason and score. The Executor alone places the
bounded summary, conditions, recommended actions, and open contradiction IDs
into task context and Evidence Graph. Retrieved Knowledge grants no tools or
authority.

Generated candidates require source, duplicate, contradiction, repository,
privacy, and license checks plus evidence. High-impact candidates also require
Reviewer or Judge approval. Promotion, lifecycle changes, conflict resolution,
and rollback create new versions and require explicit approval. Conflicting
entries remain stored and visible until an approved superseding entry resolves
the conflict; they are never silently overwritten.

Checked-in `gateway.runtime_knowledge.enabled` is `false`. Isolated validation
may set `DGX_MOA_RUNTIME_KNOWLEDGE` to a separate database. The protected
production environment enables an empty registry whose SQLite integrity and
bounded empty retrieval passed; no production Knowledge entry was promoted.
