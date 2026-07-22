# Remote Judge

The Remote Judge is a read-only independent quality gate. The Executor remains
the only tool owner, loop controller, correction owner, and client-visible final
response author.

`gateway.remote_judge` selects a bounded provider. Checked-in defaults use
`enabled: false` and `provider: disabled`. The implemented production provider
is NVIDIA NIM with model `z-ai/glm-5.2`; mock and disabled providers support
isolated deterministic validation. Provider credentials are read only from the
configured environment variable at call time.

Each call transmits a sanitized `JudgeEvidencePackage`, never the whole
conversation or repository. The package contains the objective, constraints,
acceptance state, bounded draft/diff/tool/test/build evidence, specialist
findings, failures, policy decisions, selected Skills, retrieved Knowledge, and
one judgment question. Email, phone, secret-pattern, entropy, credential-key,
and authorization redaction runs before transport.

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
for low/medium risk. High/critical risk fails closed. No Executor/Judge rewrite
loop is created. Approval permits final delivery. Any other verdict suppresses
the draft, persists structured correction instructions, and returns a bounded
correction state; the next Executor turn receives those instructions. Remote
approval alone is evaluation evidence, not an objective fact or automatic
gold-training label.

Physical NVIDIA NIM validation and production enablement remain pending. Do not
enable the provider until the cases in `docs/VALIDATION.md` cover valid approval,
unsupported claims, failed-test inconsistency, missing acceptance evidence,
edits, timeout, rate limit, invalid output, redaction, denied training policy,
and two-call enforcement.
Use `scripts/validate-remote-judge.py` for the credentialed quality cases. Mock
transport tests remain the authority for deterministic timeout, rate-limit,
invalid-output, redaction, and retry fault injection.
