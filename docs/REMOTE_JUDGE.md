# Remote Judge

The Remote Judge is a read-only independent quality gate. The Executor remains
the only tool owner, loop controller, correction owner, and client-visible final
response author.

`gateway.remote_judge` selects a bounded provider. Checked-in defaults use
`enabled: false` and `provider: disabled`. The implemented production provider
is OpenCode Go with model `glm-5.2`; mock and disabled providers support
isolated deterministic validation. Provider credentials are read only from the
configured environment variable at call time.

Each call transmits a sanitized `JudgeEvidencePackage`, never the whole
conversation or repository. The package contains the objective, constraints,
acceptance state, bounded draft/diff/tool/test/build evidence, specialist
findings, failures, policy decisions, selected Skills, retrieved Knowledge, and
one judgment question. Email, phone, secret-pattern, entropy, credential-key,
and authorization redaction runs before transport.
For an `internal_only` or `training_denied` repository, objective, draft, diff,
specialist prose, and retrieved content are withheld; only bounded criterion,
tool, test, and build status metadata may leave the host.

The response must match `judge-verdict-v1`. It contains a verdict, risk class,
all seven criterion states, structured findings, bounded required edits, a
recheck flag, and a confidence class. It contains no tools. Each request ID is
limited to two calls: one initial judgment and one recheck.

Selective routing is deterministic. High/critical risk, authentication or
security changes, database schema or destructive migrations, concurrency or
state-machine changes, destructive actions, production deployment approval,
production Skill/Prompt/Policy/Routing promotion, weekly gold candidates,
test/claim inconsistency, Reviewer/Frontier disagreement, rejected review, and
repeated failure fingerprints trigger the gate. Tool-call turns are never sent
as final drafts. A high-risk streaming request returns a bounded non-streaming
retry requirement before any model output can escape.

Timeout, rate-limit, and provider failures fall back once to the local Reviewer
for low/medium risk. High/critical risk and policy-selected Judge paths fail
closed. No Executor/Judge rewrite loop is created. Approval permits final
delivery. `approve_with_edits`, `revise`, and `retry_with_evidence` cause one
bounded same-request Executor correction followed by targeted local Reviewer
validation. An Important/Critical or explicitly requested recheck consumes the
single remaining Judge call. A failed correction or recheck suppresses the
draft and returns a bounded correction state. Remote approval alone is
evaluation evidence, not an objective fact or automatic gold-training label.

Physical OpenCode Go validation and production enablement passed on 2026-07-22.
The cases in `docs/VALIDATION.md` cover valid approval, unsupported claims,
failed-test inconsistency, missing acceptance evidence, edits, timeout, rate
limit, invalid output, redaction, denied training policy, and two-call
enforcement. Production keeps the credential in its protected 0600 environment
and exposes no Judge endpoint.
Use `scripts/validate-remote-judge.py` with `OPENCODE_GO_API_KEY` for the
credentialed quality cases. Mock
transport tests remain the authority for deterministic timeout, rate-limit,
invalid-output, redaction, and retry fault injection.
