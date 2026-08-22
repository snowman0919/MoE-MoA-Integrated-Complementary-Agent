# Client Quality Evaluation Protocol

This protocol compares the deployed Dynamic MoA client paths with the Codex
GPT-5.6 Sol user experience. It is a local system evaluation, not a claim that
the five-task panel reproduces a public benchmark score.

## External anchors

- OpenAI reports GPT-5.6 Sol at 80 on Artificial Analysis Coding Agent Index
  v1.1 and 58.9 on Intelligence Index v4.1. Sol API list pricing is $5 per
  million input tokens and $30 per million output tokens, with a 90% cached
  input discount.
  <https://openai.com/index/gpt-5-6/>
- Artificial Analysis Coding Agent Index covers DeepSWE, Terminal-Bench v2,
  and SWE-Atlas-QnA: 321 tasks with three attempts per task. It reports
  pass@1, wall time, token use, and cost from the same attempts.
  <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>
- Artificial Analysis Intelligence Index gives Agents 34%, Coding 24%,
  Scientific Reasoning 24%, and General 18%. Its reported sub-1% 95%
  confidence estimate relies on more than ten repeats for some models.
  <https://artificialanalysis.ai/methodology/intelligence-benchmarking>
- Anthropic reports Opus 5 as a stronger long-horizon coding and verification
  model than Opus 4.8, priced at $5 per million input and $25 per million
  output tokens. It is an optional paid stress comparator or blind judge, not
  the default execution path.
  <https://www.anthropic.com/news/claude-opus-5>

## Frozen local panel

The initial panel contains five standard-library repository tasks:
rate-limiter, atomic-store, DAG runner, webhook verifier, and safe JSONL
report. Each attempt starts from an isolated committed fixture and is evaluated
by public tests, hidden tests, file-scope checks, terminal evidence, requested
language, bad-terminal detection, Docker isolation, and the text the selected
client actually exposes to its user. The latter is extracted from the raw
OpenAI final event, OpenCode's last text part, Codex's last completed agent
message, or Hermes stdout. It must be non-empty, clean of internal tool
protocol, no longer than the requested limit, and report the requested changed
file, exact validation command and result, and remaining risk.

Successful completion is timed through the public, hidden, and user-visible
checks, not merely until the client process exits. Failed contracts retain a
time-to-verdict but have no verified-completion value and do not contribute to
successful-task throughput.

The runner records and verifies the gateway URL, runner SHA-256, prompt
SHA-256, test SHA-256, and initial commit before an attempt starts. A
deterministic SHA-256 order fixes the 25 attempts in each repeat before any
result is observed.

## Preregistered decision rules

1. Run three complete repeats first: five task attempts per harness and 75 total
   attempts across baseline, raw OpenAI-compatible, OpenCode, Codex, and Hermes.
2. A hard reliability gate requires every attempt to pass all checks and
   permits no stream disconnect, failed terminal, modified test, scope escape,
   missing test evidence, or isolation failure.
3. Blind quality scoring uses opaque harness labels and a 100-point rubric:
   contract completeness 30, correctness and edge cases 25, security and data
   integrity 20, maintainability 15, and evidence discipline 10.
4. Compare each Dynamic MoA harness with its task-and-repeat-matched baseline.
   The quality non-inferiority margin is -5 points. Use a deterministic
   stratified paired bootstrap with 10,000 samples; non-inferiority requires
   the one-sided 95% lower confidence bound to exceed -5.
5. If three repeats do not establish the bound, report the panel as
   underpowered and expand to ten repeats before making a parity claim.
6. Report paired duration ratios, retry counts, terminal failures, provider
   provenance, local/remote use, tokens, and marginal remote cost. The user's
   Codex OAuth plus OpenCode Go subscriptions are one combined fixed
   $30/month; OpenRouter spend is variable and separately reported.
7. Opus 5 through OpenRouter is allowed only for a bounded blind review or
   when a required Frontier path is unavailable. Raw provider output and keys
   are not committed or included in training archives.

## Long-horizon gate

The repeated panel measures restartability and cumulative runtime, but it does
not prove that one context remains coherent for ten hours. A separate
checkpointed task must run for at least ten hours and demonstrate:

- no unexplained 5xx, stream disconnect, or lost tool continuation;
- recovery after one intentional client reconnect;
- preserved objective, plan, repository identity, and evidence after
  compaction;
- no premature goal completion;
- final implementation, independent review, and passing validation.

The Goal remains active until the hard reliability gate and the statistical
quality rule pass, or a clear failure is improved and the same frozen protocol
is rerun.

## Frontier dominance v2

`scripts/evaluate-frontier-dominance-v2.py` is the release-claim gate. Its input
must contain real repository tasks, paired execution, isolated workspaces,
external hidden validation, digest-verified raw evidence, two independent epoch
manifests, and all four clients (`raw_openai_compatible`, `codex`, `opencode`,
`hermes`). It rejects mocks, generated patches, validator exposure, unintended
fallbacks, missing evidence, and any target false completion.

For every pinned comparator it requires a one-sided 95% paired-success LCB above
`+3%p`; task-type, language, and context-length stratum LCBs above `-5%p`;
current-system verified-completion p50/p95 at most `0.80x`/`0.90x`; no comparator
p50 degradation and comparator p95 at most `1.10x`; and successful-task tokens
and external cost at most `1.20x`. Missing or insufficient real data returns
`INCONCLUSIVE`, never `PASS`.

The current repository contains the evaluator and schema checks but no qualifying
Qwen input artifact. No Frontier dominance claim is active.
