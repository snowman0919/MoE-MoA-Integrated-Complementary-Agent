# Frontier collaboration

Frontier is a routinely available external expert for qualifying architecture,
design, difficult review, ambiguity, and disagreement tasks. It is not an
emergency-only fallback and it never owns deployment, tools, or final output.

## Authentication and execution

Frontier uses `codex exec --json --sandbox read-only` with an existing Codex
OAuth profile stored outside the repository. It does not use an OpenAI API key.
Profile directories and locks remain owner-only; credentials are never copied
into task evidence, traces, or configuration. Creating a new gateway client
token is allowed, but that is independent from Frontier OAuth.
The subprocess receives an explicit minimal environment allowlist; gateway
tokens, API keys, passwords, and unrelated credentials are not inherited.

The supported modes are:

- `architecture`: recommended architecture, decisions, trade-offs, failure
  modes, implementation sequence, and review questions.
- `code_review`: approve/revise/reject, severity findings, suggestions, missing
  tests, and confidence.
- `disagreement`: preferred position, supporting evidence, rejected assumptions,
  required follow-up, and confidence.

Each invocation has a correlation ID, read-only sandbox, bounded timeout,
bounded retry count, profile lock, and circuit breaker. Failures distinguish
timeout, rate limit, usage limit, authentication, provider, protocol, and open
circuit. Optional failures retain completed local evidence and lower derived
confidence; policy-required failures return a typed retryable response.
The adapter tries the configured `primary` OAuth profile first and falls back
once to `secondary` on authentication, usage-limit, or rate-limit failures.
Provider and protocol failures do not silently change identities. The selected
profile name is recorded in collaboration evidence and traces; OAuth material
is not.
The checked-in task budget permits at most three Frontier collaborations and
three recursive cycles, so architecture and later review can both occur without
an unbounded model conversation.

## External-data boundary

The gateway transmits only the requested categories from a bounded evidence
package: objective, acceptance criteria, relevant architecture or diff excerpts,
test/static-analysis evidence, local findings, and specific questions. Redaction
removes keys, credentials, private values, and irrelevant content. Traces record
category names, correlation, latency, token usage, and configured cost estimate,
not OAuth material or hidden reasoning.

Frontier cannot modify the repository, invoke host tools, push, merge, deploy,
change systemd/network configuration, or start recursive agents. The Executor
accepts or rejects every recommendation against shared evidence.

## Current state

The Codex OAuth adapter and three schemas are implemented and unit-tested on
`dev`. Real isolated Codex OAuth calls previously passed architecture,
code-review, and disagreement modes; the safe child-environment boundary,
redaction, and token accounting were also observed. Primary-to-secondary
profile fallback is now automated and covered by a subprocess-level test.
Both profiles were reauthenticated on 2026-07-21. A physical adapter call
observed the primary usage-limit failure, completed through `secondary`, and
recorded `profile=secondary`. Timeout, rate-limit,
authentication, required and optional fallback, and circuit-breaker paths pass
automated tests. Checked-in gateway configuration still keeps Frontier disabled,
and the complete local-role physical matrix has not passed, so production
enablement remains unapproved.
Historical candidate-edit behavior is documented separately in
`CODEX_FRONTIER.md` and is not this collaboration path.
