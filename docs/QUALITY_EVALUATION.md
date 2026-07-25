# Frontier Agent Non-Inferiority Protocol

This protocol is preregistered before confirmatory runs. It compares the
Dynamic MoA Codex, OpenCode, and Hermes client paths with the native Codex
GPT-5.6 Sol agent under matched, blinded conditions. The local five-task panel
is a repository-agent evaluation; it must not be reported as a public
Artificial Analysis score.

## External anchors

- OpenAI reports GPT-5.6 Sol at 80 on the Artificial Analysis Coding Agent
  Index. The public index combines DeepSWE, Terminal-Bench v2, and
  SWE-Atlas-QnA, each with three attempts per task.
  <https://openai.com/index/gpt-5-6/>
- Artificial Analysis Intelligence Index v4.1 weights Agents 34%, Coding 24%,
  Scientific Reasoning 24%, and General 18%. It uses matched settings,
  pass@1, wall time, token use, and cost, and reports that its sub-1% aggregate
  95% confidence estimate relies on more than ten repeats for some models.
  <https://artificialanalysis.ai/methodology/intelligence-benchmarking>
- Artificial Analysis Coding Agent Index reports task-normalized pass@1,
  execution time, token use, and cost from the same attempts. Its current
  components contain 321 tasks with three attempts per task.
  <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>
- Anthropic reports Claude Opus 5 as state of the art on Frontier-Bench v0.1
  and GDPval-AA v2, with stronger verification and long-horizon behavior than
  Opus 4.8. The published Frontier-Bench result is the mean of five attempts
  per task. Opus 5 costs $5 per million input and $25 per million output
  tokens.
  <https://www.anthropic.com/news/claude-opus-5>

The public results set the evaluation dimensions and frontier expectations.
They are not numerically pooled with this smaller local panel.

## Frozen local panel

The panel contains five standard-library repository tasks: rate limiter,
atomic store, DAG runner, webhook verifier, and safe JSONL report. Every
attempt starts from an isolated committed fixture and receives the same task
text, tests, limits, tools, network policy, and wall-clock limit.

The evaluated variants are:

1. native Codex with GPT-5.6 Sol at high reasoning (`baseline`);
2. Dynamic MoA through Codex;
3. Dynamic MoA through OpenCode;
4. Dynamic MoA through installed Hermes.

Before execution, the runner must seal and later verify the fixture commit,
tests SHA-256, prompt SHA-256, runner SHA-256, client version and binary hash,
model/provider configuration fingerprint, container image digest, and
deterministic attempt order. Keys, prompts, hidden reasoning, raw provider
outputs, request IDs, and repository names are excluded from metrics and
training archives.

## Confirmatory sample and blindness

- Confirmatory inference uses ten complete repeats: 50 attempts per variant,
  200 attempts total.
- Each task contributes exactly ten matched pairs per Dynamic MoA client.
- Existing `v4-r1` through `v4-r3` runs are diagnostic pilots because this
  protocol was finalized after those runs began. They cannot establish the
  final parity claim.
- Confirmatory run IDs, attempt order, hashes, margins, bootstrap seed, and
  analysis code commit are sealed before the first confirmatory result.
- Failed or timed-out attempts remain failures. Diagnostic retries receive a
  new attempt ID and never replace the original.
- Artifact packages use opaque variant labels. The quality scorer cannot see
  provider, model, route, latency, token use, or cost.

## Hard reliability gate

Every Dynamic MoA attempt must pass public tests, hidden tests, file-scope
checks, test-integrity checks, requested-language checks, isolation checks,
and final-terminal checks. Any of the following fails the variant:

- nonzero harness, public-test, or hidden-test exit;
- timeout, 5xx, stream disconnect, missing terminal, or premature completion;
- modified tests, scope escape, missing tool/test evidence, or secret leak;
- provider switch after dispatch or mixed local/remote output;
- missing required provenance, latency, cost, tool, retry, context/cache, or
  memory telemetry.

Infrastructure failures are counted because availability is part of the
product. A baseline failure remains in the reliability table; its quality
pair is marked unavailable rather than silently discarded.

## Blinded quality score

Each passing artifact receives a 100-point score:

- contract completeness: 30;
- correctness and edge cases: 25;
- security and data integrity: 20;
- maintainability and diff discipline: 15;
- validation and evidence discipline: 10.

The primary judge is a frozen GPT-5.6 Sol rubric invocation over opaque
artifacts. Claude Opus 5 independently scores a deterministic 20% stratified
sample plus every pair whose primary score differs by more than 10 points.
If fewer than 80% of dual-scored artifacts agree within 10 points, Opus 5
scoring expands to the full panel before unblinding. Judge prompts, model
versions, effort, and output schemas are fixed; only parsed scores and
redacted findings are retained.

For every Dynamic MoA client, calculate matched score differences
`candidate - baseline`. Use a task-stratified paired percentile bootstrap with
10,000 resamples and fixed seed `56052026`.

- quality non-inferiority margin: -5 points;
- non-inferior: one-sided 95% lower bound is greater than -5;
- superior: one-sided 95% lower bound is greater than 0;
- inferior: one-sided 95% upper bound is below -5;
- otherwise: inconclusive, never parity.

## Speed gate

Measure end-to-end wall time from accepted client request through the final
terminal, including model loading, queueing, retries, tools, tests, review, and
final synthesis. Also report time to first visible progress, time to first
tool call, p50, p90, p95, and timeout count.

For each matched pair, analyze `log(candidate_seconds / baseline_seconds)`.
Exponentiate the mean and its task-stratified bootstrap interval.

- speed non-inferiority margin: 1.50x;
- non-inferior: one-sided 95% upper bound is below 1.50;
- superior: one-sided 95% upper bound is below 1.00;
- any 1800-second timeout independently fails the reliability gate.

## Cost gate

Codex OAuth and OpenCode Go are one combined fixed $30 monthly expense.
Ordinary panel execution may use those subscriptions and local compute but
must incur $0.00 variable OpenRouter spend. Any ordinary attempt that uses a
paid OpenRouter fallback fails the cost gate.

Report per attempt:

- local and remote calls by provider/model;
- input, cached-input, reasoning, and output tokens when exposed;
- local GPU-seconds, peak allocated memory, and host swap delta;
- list-price-equivalent remote cost;
- actual variable paid cost;
- amortized fixed-plan cost at the observed monthly task volume.

Claude Opus 5 judge spend is a separately budgeted evaluation cost and is not
charged to the candidate execution path. Missing cost telemetry is not zero;
it fails telemetry completeness.

## Overall decision

A client is `FRONTIER-NONINFERIOR` only when all are true:

1. the hard reliability gate passes all 50 attempts;
2. blinded quality is non-inferior;
3. speed is non-inferior;
4. ordinary variable paid cost is zero and telemetry is complete;
5. no security, provider-pinning, or topology invariant fails.

`FRONTIER-SUPERIOR` additionally requires both quality and speed superiority.
Any failed hard gate or a confidence interval proving inferiority yields
`INFERIOR`. All other outcomes are `INCONCLUSIVE`.

## Ten-hour context-retention gate

The repeated panel does not prove long-session coherence. A separate isolated
task must run for at least ten hours with checkpoint snapshots every 30
minutes and one intentional client reconnect. It must preserve:

- objective, acceptance criteria, dependency plan, current phase, and next
  action;
- repository identity, branch, dirty state, evidence hashes, and provider
  provenance;
- bounded context summaries and prefix/cache hit telemetry;
- tool ownership, review obligations, and unresolved risks.

The run fails on unexplained 5xx, lost continuation, repeated whole-document
reads without new need, premature goal completion, plan drift, missing
checkpoint, secret persistence, or inability to resume. Completion requires
an actual implementation, independent review, passing validation, and a
terminal response after the ten-hour threshold.

`scripts/analyze-long-horizon.py` freezes the machine-readable gate. Evidence
contains one header, checkpoints `0` through `20` scheduled 1,800 seconds apart
with a 60-second scheduling tolerance, and one final record. It requires stable
SHA-256 identities for the session, objective, acceptance criteria, plan,
repository, branch, and provider configuration; every checkpoint additionally
requires a clean commit, next-action/context/evidence hashes, provider/model
provenance and pinning, latency, context/cache tokens, tool/retry/provider-error
counts, memory/swap, and variable cost.

At least one intentional reconnect and one positive cache read are mandatory.
Any provider error, unjustified repeated read, premature completion, identity
drift, missing checkpoint, schedule drift, private/raw field, failed validation,
unapproved review, unresolved critical finding, or missing final terminal fails
the gate. The final record must be at least 36,000 actual seconds after the
header, match the last clean implementation commit, differ from the baseline,
and carry implementation, review, and validation evidence hashes. Any nonzero
ordinary variable cost fails. The analyzer records no prompt, hidden reasoning,
provider output, request ID, key, cookie, authorization value, or repository
name.

## Change control

Failures may be diagnosed from redacted logs, but fixes are allowed only in a
`dev`-based `auto/<layer>/<proposal-id>` worktree. Confirmatory results are
invalidated by any candidate code, model, prompt, threshold, fixture, or
analysis change and must restart under a newly sealed protocol version.
Production transition, merge, deployment, or model deletion requires separate
human approval after all physical and statistical gates pass.
