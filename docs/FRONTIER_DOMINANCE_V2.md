# Frontier-Dominance v2 Release-Gate Report

Updated: 2026-08-21
Audit baseline: `75bee24a020fb2c36cd0eadd10357c8b09d8d968`

## Outcome

The request-path implementation and fail-closed evaluators are present, but the
release is **not certified**. No approved deployment was made, so there is no
paired before/after current-Qwen run, role ablation, fault-recovery run, or soak
run. A same-machine baseline plus four-client hidden-validation matrix completed
but failed 6 of 25 cells. Frontier dominance and the requested
verified-completion reduction are therefore not claimed.

## Implemented controls

- Shared local-model HTTP connections and a bounded tokenization cache.
- Bounded projection cache, indexed pending tool-call/objective recovery, and
  rebuildable DB apply/rollback commands.
- Per-role projection evidence/contribution deltas and a shared deadline for
  optional Planner, Reviewer, and Frontier fan-in; required safety roles keep
  their full role timeout.
- The safe checked-in Reasoner endpoint is loopback-only; process lifecycle may
  remain externally managed, but inference may not route over LAN or tailnet.
- Batched asynchronous stage telemetry and shutdown-time invocation CSV
  aggregation; canonical state/request finalization remains synchronous.
- Admission, projection, role inference, fan-in, Executor TTFT/decode, review,
  state/usage persistence, and verified-completion telemetry. Per-role queue and
  ready times remain in `role_request_usage`.
- Fail-closed `frontier-dominance-v2` paired evaluator and objective-verifier
  Frontier Floor. Selection never grants merge or deployment authority.
- Explicit ExecutionGraph Executor node types and per-request Controller parity.
  Any delta blocks authority; no authoritative graph mode exists.

`dgx-moa-fast` remains Executor-only. `dgx-moa` remains the required
Reasoner+Executor path. Successful tool continuation retains its direct Executor
path. No role was removed or newly enabled without same-task ablation evidence.

## Measured latency and efficiency

| Metric | Baseline | Candidate | Gate | Result |
| --- | ---: | ---: | ---: | --- |
| Admission / projection / role queue-inference / fan-in | not recorded as one comparable current-Qwen epoch | instrumentation added; no paired stage distribution | measured pair required | `NOT_RUN` |
| Executor TTFT / decode | no paired repository-task distribution | no paired repository-task distribution | comparable p50/p95/p99 | `NOT_RUN` |
| Verified completion p50 | unavailable | 140.915 s across 19 verified completions | `<= 0.80x` current | `INCONCLUSIVE` |
| Verified completion p95 | unavailable | 394.376 s across 19 verified completions | `<= 0.90x` current | `INCONCLUSIVE` |
| Tokens / successful task | unavailable | unavailable | `<= 1.20x` comparator | `INCONCLUSIVE` |
| External cost / successful task | unavailable | unavailable | `<= 1.20x` comparator | `INCONCLUSIVE` |
| Successful tasks/hour | unavailable | 13.344 over the fixed 25-cell epoch | report only | measured, not comparable |

Raw throughput from the production promotion is not substituted for these
request-level metrics.

### Supplemental current-Qwen request baseline

A read-only query of the production usage database from the Qwen start at
`2026-08-19T04:16:00Z` found 21 requests and 18 ordinary completions. Fifteen
requests started locally without a recorded fallback; 12 completed, with
request-completion p50/p95/p99 `15.082/138.854/146.306` seconds and request TTFT
`9.552/31.765/32.247` seconds. Six local attempts fell back after HTTP 400 and
all completed. This is operational request completion, not objective-verified
repository-task completion, so it does not populate or pass the latency gate.

Raw local artifact:
`data/diagnostics/frontier-dominance-v2/audit-20260820-after/qwen-request-baseline.json`
(`sha256:56cf5afaa40f330d88986308e5e5e82ba8ca1d718fa5a428662c504a879c060a`).

## Role ablation

| Comparison | Same task set | Hidden validation | Outcome |
| --- | --- | --- | --- |
| Reasoner on vs off | no | no | `NOT_RUN`; Reasoner routing unchanged |
| Planner on vs off | no | no | `NOT_RUN`; optional policy unchanged |
| Reviewer on vs off | no | no | `NOT_RUN`; safety behavior unchanged |
| Frontier on vs off | no | no | `NOT_RUN`; candidate/manual-promotion channel preserved |

## Frontier-dominance-v2

The absence manifest returns `INCONCLUSIVE` with
`comparators_not_pinned`, `missing_pairs`, `independent_epochs_incomplete`, and
`client_matrix_incomplete`. Raw local artifacts:

- `data/diagnostics/frontier-dominance-v2/audit-20260820/missing-evidence-input.json`
  (`sha256:231658c3a82c472461bd3a9cfd461629d2d257378bc4ada184f304300690e664`)
- `data/diagnostics/frontier-dominance-v2/audit-20260820/frontier-dominance-v2-result.json`
  (`sha256:a66052888f8bf1c5cbabc5cfcdac37784748a928b4eff7edd00c93c62a9e8a71`)

Reproduce with:

```bash
.venv/bin/python scripts/evaluate-frontier-dominance-v2.py \
  data/diagnostics/frontier-dominance-v2/audit-20260820/missing-evidence-input.json \
  data/diagnostics/frontier-dominance-v2/audit-20260820/frontier-dominance-v2-result.json
```

Exit `2` means the release claim is not proven.

## Current-Executor P0

| Gate | Status | Evidence |
| --- | --- | --- |
| `STATIC_VERIFIED` | pass | same-machine P0 Compose pins Gateway, Executor, Reasoner, and harness images; role endpoints remain internal and only the authenticated Gateway publishes port 9000 |
| `REAL_API_COMPONENT_VERIFIED` | pass | authenticated production health/models/ready check plus digest-pinned container preflight; aliases/context matched and SGLang `0.5.18.dev728+g0111b2903`, Torch `2.13.0+cu130`, and GB10 were visible inside the container |
| `HARNESS_E2E_VERIFIED` | fail | the isolated same-machine stack completed the latest 25-cell baseline plus four-client epoch, but six cells failed |
| `FAULT_RECOVERY_VERIFIED` | fail | not run |
| `SOAK_VERIFIED` | fail | not run |
| `RELEASE_CERTIFIED` | fail | all preceding gates are required |

Raw local audit:
`data/diagnostics/frontier-dominance-v2/audit-20260821-p0-verdict/p0-static.json`
(`sha256:13805e7c0b94f2cdbc4589bf26930a3db48f643568d7b24aada9eb874a250a0e`).
The audit is read-only and exits `2` until every gate is physically evidenced.

The complete 2026-08-21 epoch
`qwen38-p0-bounded-full-epoch3-20260821` ran the five frozen tasks through the
baseline, raw OpenAI-compatible, Codex, OpenCode, and Hermes harnesses on the
same machine. The matrix completed all 25 cells but did not pass: baseline
`4/5`, raw `4/5`, Codex `3/5`, OpenCode `4/5`, and Hermes `3/5` (18/25 total).
The summary is
`/home/kotori9/.local/share/dgx-moa/frontier-dominance-v2/client-quality/qwen38-p0-bounded-full-epoch3-20260821/summary.json`
(`sha256:bd0c202e60341b860f3adcba4e7012fa88f0b45ece0f737aab57ba5412ddcc16`).

This epoch also validates the client-visible boundary, not only repository
artifacts. Each score preserves `user-visible-output.txt` and checks the exact
text exposed by that harness. Two Hermes cells changed only the requested file
and passed public and hidden validation, but failed solely because the visible
stdout contained duplicate/progress summaries and exceeded the requested
six-line final-response limit. The Codex webhook cell timed out after
1,800.210 seconds with a changed source file but no final user-visible output.
These rows remain failures; no artifact-only success is substituted.
Hermes revision `31e571a` documents `--oneshot` as printing only final response
text, while its retained session database contains one final assistant message;
the duplicate is therefore a client stdout defect, not a second Gateway final.
The harness intentionally evaluates the duplicated text because that is what
the user received.

The Codex atomic-store disconnect was traced to both required-Reasoner
structured attempts exhausting the 1,500-token cap and ending in
`JSONDecodeError`; the Ollama service itself remained healthy. Structured
Ollama requests now set `think=false`, while unstructured requests and the
shared JSON parser are unchanged. Gateway image
`sha256:c0cabfa4c9d7daa38507ebf24ebc5049b85b8b3c2f0aa4cc45fa07f9b8f89b80`
was rebuilt and restarted on the same machine. A fresh isolated
`codex/atomic-store` reproduction completed in 227.462 seconds with all
artifact, public/hidden validation, terminal, and user-visible checks passing
and no reconnect marker. Its score is
`/home/kotori9/.local/share/dgx-moa/frontier-dominance-v2/client-quality/qwen38-p0-reasoner-nonthinking-codex-atomic-20260821/codex/atomic-store/score.json`
(`sha256:9ae275fcd0c4cfdfdf012edb7b630c25a82146ad1a8c630bdd486ce0310cb658`).
This focused reproduction does not replace the failed complete epoch or satisfy
the two-independent-epoch gate.

The subsequent fixed-order epoch
`qwen38-p0-verdict-full-epoch4-20260821` used that Gateway image and the latest
user-visible contract for all 25 cells. It completed the matrix but failed the
hard gate: baseline `5/5`, Codex `4/5`, Hermes `4/5`, OpenCode `3/5`, and raw
`3/5` (19/25 total). Its summary is
`/home/kotori9/.local/share/dgx-moa/frontier-dominance-v2/client-quality/qwen38-p0-verdict-full-epoch4-20260821/summary.json`
(`sha256:21d037aa91939bd2d42d87e569fe0cfa00f6324ce304df4cc9efbf6ff30b978b`);
the frozen schedule digest is
`sha256:4a1c7ba6feb56ce120e4d5699246a4ec66641d8c0b21bcc6c0925a98493d26f8`.

The epoch measures completion only after artifact, public, hidden, and actual
user-visible output checks finish. Across 25 attempts, 19 verified completions
had p50/p95/p99 `140.915/394.376/484.726` seconds; all verdicts, including
failures, had p50/p95/p99 `146.319/468.975/500.500` seconds. Wall time was
5,125.731 seconds and verified throughput was 13.344 tasks/hour. Four client
processes exited successfully despite a failed contract. OpenCode atomic-store
also exposed a nonconforming user response and timed out in both public and
hidden validation; raw atomic-store exited `2` with no user-visible final.
These are failures even where the requested source file changed. This single
epoch is bounded evidence only: it is neither a passing soak nor a paired
latency improvement claim.

The same audit content-hashed all current model files and captured the live
inference argv. The target artifact is 20,616,726,735 bytes across 48 files at
`sha256:60962ffb37101ac62934633beeb0bf661821e001761f5a5c6ff5328455845ec5`;
the DSpark draft is 2,718,609,744 bytes across six files at
`sha256:4d3ca17e0e2365d6458d9161be086742850a0395cb35319b77545ba0156a1c66`.
All source, ModelOpt, SGLang, draft-revision, loopback, context, quantization,
and DSpark argv checks passed. The local Reasoner identity is
`Qwythos-v2-9B:Q4`, 6,825,527,487 bytes at digest
`28c00e59acfbf4fffff55acacd3de3c7b95cf2f382e59f84f713ab9129d09df7`.
The current reproducible Gateway build is the image recorded above at
`sha256:c0cabfa4c9d7daa38507ebf24ebc5049b85b8b3c2f0aa4cc45fa07f9b8f89b80`.

One non-certifying component run exercised the live Gateway from the pinned
Docker harness against the `rate-limiter` task. OpenCode `1.17.18` completed
the edit, public tests, external hidden validation, and Korean final response
in 474.764 seconds. Codex `0.146.0` completed the edit, repeated tool calls,
public tests, and hidden validation, but never emitted its required final
response and timed out at 1,800.079 seconds. Its row therefore fails despite
the valid patch. Hermes revision `31e571a` completed in 424.331 seconds, but
failed hidden validation because its implementation accepted a NaN window.
The standard-library raw client passed in 279.451 seconds after ten model
turns and nine tool calls. It measured 27.375 seconds to the first valid tool
call, request latency p50/p95 of 15.115/94.096 seconds, and
tool-result-to-next-action p50/p95 of 7.883/94.096 seconds. The summary is
`data/diagnostics/frontier-dominance-v2/audit-20260820-after/component-e2e/p0-component-e2e-20260820-01/component-summary.json`
(`sha256:e41c3bbb029b9fe77fad35e12581abfbb55b9e900481c5778b8f34e46dcec1c3`).
This partial run does not change `HARNESS_E2E_VERIFIED`: only one task and one
epoch ran, the Codex and Hermes rows failed, and the topology was not the
required isolated digest-pinned P0 stack.

The Codex timeout is a bounded convergence failure rather than a Gateway or
Executor hang. The retained session completed 61 of 62 requests; the last was
cancelled by the 1,800-second harness deadline. Reviewer plus Frontier ran on
request nine after the only file change and the first passing public test.
Codex then made no correction, emitted 57 empty agent-message events, and kept
inspecting until its container exhausted process creation. The fail-closed
review gate correctly withheld final synthesis. This single false-positive or
unresolved-review observation does not justify weakening review or adding a
task-specific prompt exception. Hermes is a separate model-quality failure:
its implementation used a positivity check that does not reject NaN, exactly
matching the external hidden-validation failure.

## Rollback and remaining risk

Run the offline rebuildable-schema rollback only against the intended database:

```bash
PYTHONPATH=gateway/src .venv/bin/python scripts/manage-request-path-db.py rollback PATH_TO_DB
```

It removes only pending indexes and stage telemetry; canonical sessions and
request usage remain. The production checkout/controller-commit discrepancy is
still unresolved.
Deployment, systemd changes, model promotion, training export, and graph
authority remain outside this work and require separate approval. The isolated
same-machine P0 stack exists and was used for the complete epoch above, but its
latest six failed cells, missing second passing independent epoch,
fault-recovery evidence, and soak evidence keep release certification false.
