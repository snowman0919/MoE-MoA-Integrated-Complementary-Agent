# Runtime Skills

## Development boundary

Runtime Skills are implemented in `gateway/src/dgx_moa/skills.py` and remain
disabled in checked-in configuration. The protected production environment
enables an empty governed registry; no production Skill was promoted or
populated by this work.

A Skill is a validated resource with a safe ID, immutable semantic version,
source and lifecycle state, matching tags, input/output contracts, structured
procedure, tool allow/deny requests, agent recommendations, validation evidence
and provenance. Mutable quality statistics live separately in `metrics.db`, so
production Skill documents remain immutable.

Logical stores are `core`, `generated`, `experimental`, `deprecated`,
`disabled`, `archived`, and `packs`. Atomic writes use a same-directory
temporary file and `os.replace`. A conflicting write to an existing version is
rejected. Runtime-created resources must begin experimental.

## Retrieval and activation

The registry searches only active Skills and returns a configured top-k of 1
through 10. Ranking records lexical overlap, task classification, language,
framework, failure fingerprints, historical reliability, bounded quality gain,
and regression penalties. Only the latest active version per Skill ID is
eligible.

The Controller performs selection at the Executor boundary. Other models may
recommend a Skill but cannot activate it. Activation records ID, version,
selection reason and score, policy-required flag, initial result, evidence IDs,
procedure, requested tool subset and recommended agents. A Skill never grants a
tool or permission that the request and Executor do not already have.

## Configuration

```yaml
gateway:
  runtime_skills:
    enabled: false
    root: data/skills
    retrieval_limit: 3
    max_context_characters: 6000
```

An isolated process may supply the same strict object through
`DGX_MOA_RUNTIME_SKILLS`. Corrupt registry content degrades Skill observation
and emits `skill_selection_failed`; it does not stop an otherwise valid request.

## Generated candidates

A structured recurring pattern needs at least two distinct evidence IDs before
it can create an immutable `generated` draft. Pattern types cover task classes,
failure fingerprints, repair sequences, review checklists, tool workflows, and
architecture decisions. Drafts always start experimental and unvalidated.

Candidate evaluation is injected as an isolated callback so the registry never
grants tools or mutates a host. A passing evaluation requires isolated
validation, historical replay, regression evaluation, and Reviewer inspection;
high-impact candidates also require a successful Remote Judge validation. The result is
a new immutable candidate version. Even a passed candidate remains
experimental until the existing explicit approval-based promotion gate is used.

The 2026-07-22 isolated physical run exercised recurring-pattern draft creation,
isolated validation, historical replay, regression evaluation, Reviewer
inspection, an Executor-evidenced helpful canary, explicit promotion, and
explicit rollback. It created no production registry and does not authorize
automatic promotion.

## Packs

Pack export creates a ZIP containing `manifest.json` and versioned Skill JSON.
The manifest records schema version, dependencies, compatibility metadata and
SHA-256 hashes. A configured signer can add a detached key ID and signature.
Import verifies hashes and any present or required signature through the
configured verifier. Imported Skills always enter `experimental`; import never
promotes directly to production.
