# Frontier Agent Non-Inferiority Protocol

This protocol is preregistered before confirmatory runs. It compares the
Dynamic MoA Codex, OpenCode, and Hermes client paths with the native Codex
GPT-5.6 Sol agent under matched, blinded conditions. The local five-task panel
is a repository-agent evaluation; it must not be reported as a public
Artificial Analysis score.

## External anchors

- OpenAI reports GPT-5.6 Sol with max reasoning at 80 on Artificial Analysis
  Coding Agent Index v1.1 in its 2026-07-09 launch post. That historical score
  is not treated as a score on the current v1.3 methodology.
  <https://openai.com/index/gpt-5-6/>
- Artificial Analysis Intelligence Index v4.1 weights Agents 34%, Coding 24%,
  Scientific Reasoning 24%, and General 18%. It uses matched settings,
  pass@1, wall time, token use, and cost, and reports that its sub-1% aggregate
  95% confidence estimate relies on more than ten repeats for some models.
  <https://artificialanalysis.ai/methodology/intelligence-benchmarking>
- Artificial Analysis Coding Agent Index v1.3 combines DeepSWE,
  Terminal-Bench v2, and SWE-Atlas-QnA with equal component weight. Its current
  components contain 321 tasks with three attempts per task; it also reports
  pooled execution time, token use, and provider-list-price cost from those
  attempts.
  <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>
- Anthropic's 2026-07-24 launch post reports Claude Opus 5 as state of the art
  on its Frontier-Bench v0.1 and GDPval-AA v2 runs, with stronger verification
  and long-horizon behavior than Opus 4.8. Its Frontier-Bench result is a
  vendor-run mean of five attempts per task and used Opus 4.8 fallback for
  Opus 5 safety-classifier refusals. Opus 5 costs $5 per million input and $25
  per million output tokens.
  <https://www.anthropic.com/news/claude-opus-5>
- Terminal-Bench 2.0 contains 89 human-authored, realistic terminal tasks with
  isolated environments and comprehensive outcome tests. Its authors report
  frontier agents below 65%, supporting container isolation and observable
  completion as hard gates rather than relying on model self-report.
  <https://arxiv.org/abs/2601.11868>
- DeepSWE contains 113 original long-horizon tasks across 91 repositories and
  five languages, with hand-written behavioral verifiers intended to reduce
  contamination and accept alternative correct implementations. This supports
  hidden outcome checks and retaining every failed trajectory.
  <https://arxiv.org/abs/2607.07946>
- GPQA contains 448 expert-authored graduate-level biology, physics, and
  chemistry questions and reports a large expert/non-expert accuracy gap. It
  motivates independent Scientific Reasoning evidence but is not reproduced by
  the local repository tasks.
  <https://arxiv.org/abs/2311.12022>
- MMLU-Pro expands choices from four to ten, removes noisy/trivial items, and
  reports lower prompt sensitivity across 24 prompt styles than MMLU. It
  motivates a distinct General reasoning category and prompt freezing.
  <https://proceedings.neurips.cc/paper_files/paper/2024/hash/ad236edc564f3e3156e1b2feafb99a24-Abstract.html>

The public results set evaluation dimensions and frontier expectations only.
Vendor claims and results from different index versions are not numerically
pooled with this smaller local panel or used as confirmatory evidence.

## Frozen breadth panel

Scientific Reasoning and General are evaluated separately from the 200-attempt
coding panel so its preregistration is unchanged. The breadth panel contains
two Scientific Reasoning repository tasks (random-effects meta-analysis and
first-order decay inference) and two General repository tasks (deterministic
ranked-choice resolution and time-zone-aware scheduling). These are local
agentic work samples, not replicas of Artificial Analysis tasks and not a
public Intelligence Index score.

The same four variants, opaque labels, functional and telemetry hard gates,
judge rubric, quality margin, speed margin, cost gate, and provider-pinning
rules apply. Each breadth task receives ten matched repeats per variant: 40
attempts per variant and 160 total. Category-level quality and log speed ratios
use task-stratified paired bootstrap intervals with 10,000 samples and seed
`56052027`. Scientific and General must each independently pass reliability,
quality, speed, and cost non-inferiority. A weighted aggregate is not reported
because the local tasks are not numerically commensurate with the published
Artificial Analysis components. Any fixture, runner, prompt, scorer, model, or
protocol change after sealing invalidates the whole breadth epoch.

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
artifacts through Codex OAuth, model `gpt-5.6-sol`, high reasoning, and
temperature-independent structured output. Claude Opus 5 uses OpenRouter model
`anthropic/claude-opus-5`, high reasoning, and temperature zero to independently
score through its pinned OpenRouter Amazon Bedrock route (provider slug
`amazon-bedrock`, fallbacks disabled). Numeric range keywords are removed from
the transmitted JSON schema because the Anthropic route rejects them; the
scorer enforces those ranges locally. The returned provider must still equal
Amazon Bedrock. The secondary sample contains exactly two repeats per
task/opaque-variant stratum, plus every matched baseline/candidate pair whose
primary scores differ by more than 10 points.
If fewer than 80% of dual-scored artifacts agree within 10 points, Opus 5
scoring expands to the full panel before unblinding. Judge prompts, model
versions, effort, and output schemas are fixed; only parsed scores and
redacted findings are retained.

The blinded package contains only the opaque variant, repeat, task contract,
starter source, candidate source, and boolean functional checks. It excludes
the client final response, provider/model/route data, timing, cost, tokens,
telemetry, raw logs, prompts, request IDs, repository names, and credentials.
Both judges return the five rubric components and their sum. The final score is
the primary score when no secondary score is required and the arithmetic mean
when both scores exist. Judge disagreement is reported separately and is never
silently discarded. A missing, malformed, or out-of-range required judge score
makes the confirmatory analysis inconclusive.

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

## Sustained-Goal context-retention gate

The repeated panel and a direct-model soak do not prove long-session coherence.
A separate isolated task must complete five dependency-ordered work phases
through a real Codex, OpenCode, or installed Hermes client, the authenticated
Gateway, Dynamic MoA routing, host tool continuations, and one intentional
client reconnect. It must preserve:

- objective, acceptance criteria, dependency plan, current phase, and next
  action;
- repository identity, branch, dirty state, evidence hashes, and provider
  provenance;
- bounded context summaries and prefix/cache hit telemetry;
- tool ownership, review obligations, and unresolved risks.

The run fails on unexplained 5xx, lost continuation, repeated whole-document
reads without new need, premature goal completion, plan drift, missing phase,
missing host-tool use, secret
persistence, or inability to resume. Completion requires an actual
implementation, independent review, passing validation, and a terminal
response. Elapsed wall time is reported but is not a pass criterion.
The configured wall-clock limit is only a fail-safe and observation ceiling;
direct-local inference or an idle soak outside this client-to-Gateway path is
not sustained-Goal evidence. A ten-hour duration alone is neither required nor
sufficient: the gate is successful completion of the dependency-ordered work
through the real client and MoA path, including reconnect and context recovery.

`scripts/analyze-long-horizon.py` freezes the machine-readable gate. Evidence
uses protocol `frontier-long-goal-v43` and contains one header, consecutive
phases `intake_and_plan`, `core_implementation`, `integration_and_tests`,
`independent_review_and_repair`, and `full_validation_and_final`, followed by
one final record. It requires stable SHA-256
identities for the session, objective, acceptance criteria, plan, repository,
branch, and provider configuration; every phase additionally requires a clean
worktree, a terminal client turn with host-tool use,
next-action/context/evidence hashes, provider/model provenance and pinning,
latency, context/cache tokens, tool/retry/provider-error counts, memory/swap,
and variable cost.

The full run must observe Reasoner, Executor, Planner, and Reviewer provenance.
At least one intentional reconnect and one positive cache read are mandatory.
Any provider error, unjustified repeated read, premature completion, identity
drift, missing checkpoint, private/raw field, failed validation, unapproved
review, unresolved critical finding, or missing final terminal fails the gate.
The final record must match the last clean implementation commit, differ from
the baseline, and carry implementation, review, and validation evidence
hashes. Ordinary variable cost must remain at or below the preregistered
per-run $10 ceiling. OpenRouter remains eligible only after the bounded Codex
OAuth profile chain is unavailable and a mandatory specialist/Executor path
requires fallback. The analyzer records no prompt, hidden reasoning, provider
output, request ID, key, cookie, authorization value, or repository name.
The harness derives next-action, context, and evidence hashes from selected
fields in the actual Gateway session state. It never stores those source
fields, prompts, repository values, or provider output. A model-authored
checkpoint file and a minimum elapsed time are not required.
Earlier epochs remain immutable diagnostic history and cannot be relabeled as
v18 confirmation. Elapsed time and direct local-model activity cannot replace
evidence from the authenticated client-to-Gateway-to-MoA path.

The isolated candidate runtime must reserve the sustained task, rather than
production defaults, with the following frozen Loop Engineering ceilings:
`iterations=256`, `tool_calls=1000`, `reasoner_reentries=256`,
`planner_calls=32`, `reviewer_calls=64`, `frontier_calls=128`,
`tokens=8000000`, `external_cost_usd=10`, and
`wall_clock_seconds=43200`. These are fail-safe ceilings, not work targets;
the task still ends as soon as its checkpoint contract is satisfied. OpenRouter
remains eligible only under the fallback and total-cost rules above.

## Change control

Failures may be diagnosed from redacted logs, but fixes are allowed only in a
`dev`-based `auto/<layer>/<proposal-id>` worktree. Confirmatory results are
invalidated by any candidate code, model, prompt, threshold, fixture, or
analysis change and must restart under a newly sealed protocol version.
Production transition, merge, deployment, or model deletion requires separate
human approval after all physical and statistical gates pass.
