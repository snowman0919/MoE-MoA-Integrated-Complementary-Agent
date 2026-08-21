# State

Updated: 2026-08-20

## Authority layers

Do not collapse these three layers:

- **Checked-in fail-closed defaults:** lifecycle disabled, empty unit map,
  Qwen local deployment `runtime_validated: false`, memory fraction `0.5`, and
  DSpark disabled. The required Qwythos Reasoner is loopback-only at
  `127.0.0.1:11434` with externally managed process lifecycle.
- **Checked-in candidate manifest:** source
  `Qwen/Qwen3.8-27B@1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, generated artifact
  `snowman0919/qwen38-executor-27b-dspark-nvfp4-v1@034de5c1743e53fcae8b0be9d3e68526522723ed`,
  SGLang, loopback `9001`, context 262,144, one request, and the remote route
  `MiMo -> DeepSeek` after local failure.
- **Last physically promoted deployment:** a separately reviewed ignored
  overlay uses the same pinned official source, ModelOpt
  `fbcdc16c2d67ca6db3f33b2848e923600f7012c7`, SGLang
  `0111b290312aa224962397db86c04fe112539fb2`, and DSpark
  `85ef153be924f17ce4bf62726954eeaa4a73e854`. It uses memory fraction `0.35`,
  FP8 E4M3 KV, 270,000 total KV tokens, chunked prefill 4,096, batch-one
  decode/verify graphs, DSpark block 7, an unquantized draft, and two continuous
  decode steps. A 2026-08-20 read-only lock audit hashed the exact target tree as
  `60962ffb37101ac62934633beeb0bf661821e001761f5a5c6ff5328455845ec5`
  and draft tree as
  `4d3ca17e0e2365d6458d9161be086742850a0395cb35319b77545ba0156a1c66`.

The production promotion is append-only evidence in `docs/VALIDATION.md`; it
does not turn the safe checked-in candidate flags into deployment authority.

## Current decision authority

This file contains current operating facts only. Measured successes and failures
are append-only in `docs/VALIDATION.md`; frozen plans and the pre-closeout state
remain reachable through `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`,
`archive/20260814/*`, and `git show 6e050aa53:docs/STATE.md`.

```text
2026-08-14 Runtime Completion audit = COMPLETE_WITH_EXCEPTIONS
2026-08-15 Runtime Completion re-audit = COMPLETE_WITH_EXTERNAL_GOVERNANCE_EXCEPTION
현재 Gateway release = PILOT_ACTIVE
전체 Dynamic MoA 프로젝트 = IN_PROGRESS
PRODUCTION_BETA / STABLE = 미달성
```

Earlier Runtime releases passed their recorded isolated-client, key-isolation,
canary, and rollback gates. The current Qwen Executor has only the narrower
physical evidence described above; P0 current-Executor certification remains
open. This does not promote policy-disabled paths or the overall project beyond
`PILOT_ACTIVE`.

## Inspected production release

| Item | Current fact |
| --- | --- |
| Source | Audit baseline and reported controller commit `75bee24a020fb2c36cd0eadd10357c8b09d8d968`; the 2026-08-20 production checkout was observed at `ea3831ea43c3b32aef712041a464f242fc2095fd`, so exact loaded-source identity remains a certification manifest requirement |
| Rollback | Pre-Qwen environment, unit, model configuration, and lifecycle DB backup: `/home/kotori9/.local/state/dgx-moa/backups/qwen38-production-20260819T1245KST`; Phase 3 MARLIN evidence remains preserved |
| Gateway | PID `2869097`, `NRestarts=0`, healthy authenticated listener on `0.0.0.0:9000`; `/healthz` and `/readyz` passed on 2026-08-20 |
| Public catalog | only `dgx-moa` and `dgx-moa-fast`, both `context_length: 262144` |
| Active Executor | Qwen3.8 27B NVFP4 + DSpark on loopback `127.0.0.1:9001`; PID `2700788`, `NRestarts=0` |
| Superseded Pilot | transient `dgx-moa-pilot-v1-release-attempt12.service` was stopped and collected; tailnet `19000` fails closed |
| Lifecycle | status `READY`, desired `ON`, effective route `local/qwen3.8-27b`, generation `35`; checked-in lifecycle defaults remain disabled and empty |
| Enabled integration | Dashboard and Codex OAuth Frontier; optional local roles were inactive in the 2026-08-20 inspection |
| Open production exception | Reasoner still targets `100.90.167.128:11434`; this violates the current loopback-only role endpoint rule and requires a separately approved overlay change |
| Disabled policy paths | ExecutionGraph control, Remote Judge, Loop Engineering, Runtime Skills/Knowledge/Evolution, declarative policy, training collection, weekly jobs |

The checkout/report mismatch above is recorded, not resolved by inference.
Correcting production metadata or restarting either service requires separate
deployment approval and was not done by this work.

The current request-path/release-gate audit is in
`docs/FRONTIER_DOMINANCE_V2.md`; all latency, ablation, Frontier-dominance, and
P0 claims there fail closed when physical evidence is absent.

## Executor authority layers

| Layer | Authority |
| --- | --- |
| Active production request path | Qwen3.8 27B NVFP4 + DSpark on loopback `9001` |
| Bounded overflow path | MiMo after allowed local failure/contention; only a MiMo model-scoped failure may select DeepSeek V4 Flash |
| Public API context | `262144`, returned by the authenticated 2026-08-20 `/v1/models` inspection |
| Resident local target | generated Qwen3.8 NVFP4 target plus pinned DSpark draft with the measured overlay above |
| Preserved rollback baseline | Phase 3 `65536`, seq1, 1.7 GB KV, `gpu_memory_utilization=0.5`, MARLIN |

The 65K MARLIN profile remains safety/rollback evidence, not the public context
or current provider.

## Implementation matrix

| Capability | Current classification | Measured boundary |
| --- | --- | --- |
| Chat / Responses common execution | `REAL_API_COMPONENT_VERIFIED` | Qwen local/Gateway smokes exist; the complete current-Executor repository tool loop is not yet certified |
| Raw API / Codex / OpenCode / Hermes current-Executor matrix | `PARTIAL_COMPONENT_EVIDENCE` | one current-Qwen task/epoch ran in pinned Docker harnesses: raw and OpenCode passed; Codex and Hermes failed; the isolated P0 stack and complete matrix remain unrun |
| ExecutionGraph | `DISABLED_BY_POLICY` | production aggregate reports `graph_count=0`; graph control remains non-authoritative |
| Role Context projection | `PHYSICALLY_VERIFIED` | local tool continuation recorded snapshot `1726`, projection `2493`, rendered prompt `11329` bytes, and `2484` provider prompt tokens with tool evidence and zero drops |
| Evidence persistence | `PHYSICALLY_VERIFIED` | four current-release trace-v3 sessions plus request, role, provider, projection, Dashboard and usage lineage |
| Planner / Reviewer / Judge / Frontier | `PHYSICALLY_VERIFIED` / `DISABLED_BY_POLICY` | remote Planner/Reviewer and Codex OAuth Frontier are live; local optional roles and Remote Judge remain disabled |
| API-key isolation / overflow Executor | `PRESERVED_HISTORICAL_EVIDENCE` | separate bounded evaluation keys proved the earlier Mistral/Flash paths; this is not current-Qwen P0 evidence |
| Tool call / continuation | `REAL_API_COMPONENT_VERIFIED` | direct Qwen native-tool output passed; full Gateway repeated-tool continuation plus hidden validation remains P0-open |
| Streaming / cancellation / recovery | `PHYSICALLY_VERIFIED` | SSE terminal, consumer close, active-request drain, Codex reconnect family fixed and replayed |
| Dashboard / WebSocket | `PHYSICALLY_VERIFIED` | operator private-detail audit returned current trace/projection data; WebSocket handshake returned `101` and first frame `connected` |
| Logging / training candidate | `PHYSICALLY_VERIFIED` / `DISABLED_BY_POLICY` | safe runtime logs are live; collection and promotion remain disabled |
| Deployment / rollback | `PHYSICALLY_VERIFIED` | Qwen promotion backup is preserved and explicit stop/reclamation passed; production rollback was not repeated in this work |

## Public behavior

- `dgx-moa` is the primary Reasoner + Executor policy path.
- `dgx-moa-fast` is the intentional Executor-only compatibility path.
- The client owns tool execution and sends matching tool results back to the
  gateway; the Executor owns routing and client-visible final synthesis.
- Historical inputs such as `dgx-moa-agent`, `dgx-moa-orchestrated`, and
  `dgx-moa-chat` remain internal compatibility inputs for durable continuation
  and rollback only. They are not discoverable public aliases.
- Bearer authentication remains mandatory. Role inference endpoints are not
  exposed on wildcard interfaces.

See `docs/API_CLIENT_MODES.md` for the public request contract and
`docs/MODEL_LIFECYCLE.md` for lifecycle semantics.

## Audit exceptions and remaining gates

- CI is checked in and green on both long-lived branches, but GitHub branch
  protection and repository rulesets are absent. The available token has
  administration read permission only: `EXTERNAL_PERMISSION_REQUIRED`.
- Structural codebase reduction is not claimed. The overlay integration added
  focused attribution guards/tests and canonical graph artifacts; no legacy
  adapter or rollback asset was proven unreferenced enough to delete.
- Internal compatibility aliases, wrappers, and rollback assets remain because
  references, durable continuations, tests, or physical rollback depend on
  them. No dead public launcher was proven safe to delete in this closeout.
- Large `api.py`/`controller.py` decomposition is a separate post-Pilot backlog,
  not a Runtime-audit completion claim.
- Fresh blind non-inferiority, Reasoner ablation, specialist/Judge/ExecutionGraph
  promotion, training/weekly gates, and release-integrity enforcement remain
  incomplete. They gate `PRODUCTION_BETA` or `STABLE`, not this narrow audit.
- The current-Executor component run has passing raw-client and OpenCode rows.
  Codex produced a patch that passed hidden validation but timed out before
  final synthesis. Its Gateway session completed 61 of 62 requests, so this was
  not a backend hang: Reviewer/Frontier rejected after the first patch and
  public test, Codex made no later file change, and 57 client-visible agent
  messages were empty while the fail-closed completion gate kept requiring a
  correction. Hermes completed normally but failed hidden validation because
  its constructor accepted `float("nan")` as a positive window.
  This one-task, one-epoch diagnostic is not `HARNESS_E2E_VERIFIED`; the
  complete matrix and isolated digest-pinned topology remain required.

## Repository state

The audit implementation branch starts at canonical
`main@75bee24a020fb2c36cd0eadd10357c8b09d8d968`. The production checkout was
read-only inspected at `ea3831ea43c3b32aef712041a464f242fc2095fd`; it was not
merged, reset, restarted, or deployed. Historical cleanup and archive tags
remain recorded in the append-only validation history.
