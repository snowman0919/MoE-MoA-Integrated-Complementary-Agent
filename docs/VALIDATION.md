# Validation

## Codex Responses continuity and client matrix — 2026-07-24

The reported Codex Goal session did not fail at its first MCP lookup. The
unknown `codex-apps` server call fell back to a successful native file read,
but later unnecessary probes consumed the Engineering loop and five client
retries surfaced the terminal failure as a stream interruption.

Responses translation now converts only local `file://` MCP reads to a
shell-quoted `exec_command`, preserves a concise user-visible progress message
before each tool batch, pins the selected call for that turn, and emits SSE
keep-alives while the upstream model is silent. The Executor prompt asks for
independent tools in one batch while retaining ordered tools as sequential
continuations. The compatible output ceiling is 32,768 tokens within the
preserved 65,536-token Executor context.

The isolated suite passed `879 passed`; Ruff formatting, Ruff lint, strict mypy
over 43 source files, and `git diff --check` passed. An exact Responses request
for the reported `codex-apps` plus macOS `file://` URI emitted Korean progress
before an `exec_command` call and terminated with `response.completed`.
A forced client disconnect received an immediate SSE keep-alive, and a retry
with the same session completed without a terminal loop reason.

Hermes Agent 0.18.2, OpenCode 1.17.18, and the official Codex CLI build at
`808d3c2702ce8eae007c457aa930e7c3b68dd5f6c` ran in separate read-only-root
Docker sandboxes with capabilities dropped and only isolated client state and
workspaces writable. Hermes accepted a 32,768-token request, created and
verified `HERMES_32768_PASS`, and reported in Korean. OpenCode emitted ordered
`write`, `bash`, and Korean final events, independently verifying
`OPENCODE_32768_PASS`. Codex read the Goal document, batched `pwd` and `ls`,
created and separately verified `CODEX_32768_PASS`, then returned a Korean
completion instead of stopping after the document read.

PR `#104` merged as production `main@2a6aa01`. The gateway drained to zero
active requests before restart; readiness passed on both tailnet and loopback,
and Hermes retained PID `1796553`. The exact production MCP request accepted
32,768 tokens, emitted progress before the remapped `exec_command`, and ended
with `response.completed`. The official Codex CLI then read the Goal once,
batched `pwd` and `ls`, created and independently verified
`PRODUCTION_CODEX_PASS`, and returned a concise Korean completion. Gateway
session `f3865615-8154-4f3a-9284-02eeabc52b28` recorded one objective
resolution, one history compaction, three successful tool executions, and a
final `finish_reasons=["stop"]`.

## Resolved Goal history compaction — 2026-07-23

Postdeployment session `a1bc31fd-543b-4df2-abf0-baadbd43de8b`
successfully resolved 950 objective characters but repeatedly received its
prior Goal-reading history from the client. The Executor followed the retained
`cat`, `wc`, `sed`, `awk`, `file`, `od`, and `xxd` pattern instead of beginning
implementation. It terminated with two Engineering iterations and 14 tool
calls still available because its token budget reached zero.

Once an objective file is resolved, model input now removes assistant tool
calls targeting that Goal path and their paired tool results. Unrelated
implementation history remains. The full isolated suite passed 866 tests;
Ruff and strict mypy passed.

PR `#77` deployed to production main
`1331ca1045b3834f578c001c930c9b8c38647151`. Authenticated physical session
`physical-goal-compact-1784806818` resolved 579 objective characters, recorded
two removed history messages, selected `inspect_workspace` as its next tool,
and retained no termination reason. Gateway readiness was `ready`; Hermes
retained PID `1796553` and its `2026-07-23 16:30:58 KST` start time.

## Goal shell-noise and redundant-read recovery — 2026-07-23

The reported interrupted Goal session
`3b922bcb-f099-4282-b9d5-484cbf6ca3b7` ended with
`BUDGET_EXHAUSTED`, not an initial transport failure. All seven stored tool
results had exit code zero. Successful file output included the Codex command
envelope and `pyenv: cannot rehash ... isn't writable`; later failed
`filesystem` MCP retries were registered as active failures and consumed the
remaining Engineering iterations. The client reconnects then surfaced the
terminal 409 as repeated 502 responses.

Tool-result normalization now removes the Codex command envelope and that exact
benign pyenv startup warning while preserving real stderr, exit codes, and
failure classes. A failed duplicate read of an already resolved
`goal-objective.md` remains recorded evidence but does not reopen the completed
read or consume another Engineering iteration. The Executor prompt also treats
the loaded current objective as authoritative and forbids another filesystem or
MCP read of that objective.

PR `#75` deployed to production main
`a84e4cbc5a324c8db220d826d6d40e2116bb97f7`. The full isolated suite passed
865 tests; Ruff and strict mypy passed. Authenticated physical session
`physical-goal-noise-1784801408` stored 434 objective characters with the
startup warning absent, retained the redundant MCP failure as
`MCP_SERVER_UNAVAILABLE`, had zero active failures, stayed on Engineering
iteration one with three iterations remaining, and continued to
`inspect_workspace`. Gateway readiness was `ready`; Hermes retained PID
`1796553` and its `2026-07-23 16:30:58 KST` start time throughout deployment.

## Resolved Goal objective propagation — 2026-07-23

The reported summary-only Goal output was traced to a predeployment session:
the last matching request preceded the current runtime deployment and no
matching postdeployment request existed. Its stored evidence nevertheless
confirmed a separate defect: after a successful objective-file fallback read,
the session retained only the `/goal ...goal-objective.md` wrapper as the model
objective. The loaded document remained ordinary recent tool output, so the
Executor could summarize it instead of treating it as the task.

The stable wrapper remains the session-correlation objective. A successful
read of its `goal-objective.md` target now records a bounded resolved objective,
and every model-facing role uses that document as the effective task. Failed
MCP output cannot populate it. Streaming tool observation also preserves the
call arguments needed to correlate the returned content with the requested
goal path. Focused propagation and continuation tests passed; the full isolated
suite passed 864 tests, and Ruff and strict mypy passed.

PRs `#72` and `#73` deployed to production main
`094b756dd670468e53d4cd6764ebb6e4814ed710`. An authenticated two-turn
`dgx-moa` Responses run retained one session across a remapped result, persisted
294 characters of resolved Goal content and one resolution event, then emitted
`inspect_workspace` with no summary text. State remained executing with
`final_status=null`. Only the Codex gateway restarted; Hermes was not restarted.

## Successful tool-continuation budget — 2026-07-23

The postdeployment Codex Goal retry preserved one session and reached executor
step three, but failed after four HTTP turns. Persisted state showed 27 of 30
tool calls still available while the four-iteration and four-Reasoner-entry
budgets were exhausted. The successful objective-file reads were therefore
being charged as new Engineering iterations and rerunning the Reasoner even
though they were continuations of one Executor decision.

Successful tool-result continuations now remain in the current Engineering
iteration and return directly to the Executor. A continuation with active tool
failure evidence retains the existing full orchestration and Reasoner re-entry.
Focused tests verified one Reasoner/iteration for a successful continuation and
two Reasoner calls for a failed continuation. The full isolated suite passed
863 tests; Ruff and strict mypy passed.

PR `#70` deployed to production main
`1da8de1b41bd348bd8eb5cd37f7a7873da0828f4`. An authenticated five-turn
`dgx-moa` Responses run deliberately remapped every continuation call ID. All
turns retained one session and completed without a failed terminal event.
Persisted state recorded executor `step_count=5`, one Engineering iteration,
one Reasoner invocation, four recovery events, three remaining iterations,
three remaining Reasoner entries, and no termination reason.

## Streaming goal continuity and tool batching — 2026-07-23

Inspection of the attached Hermes/Codex goal run found 107 SQLite session rows
for one objective between `01:46:16` and `02:40:36` UTC. Each streamed
Responses turn received a new generated session ID before Chat continuation
recovery could run. The rows repeatedly restarted at executor step one while
re-observing up to 12 prior tool results; the final row remained in
`phase=executing` with no completion criteria or termination reason despite
returning `finish_reason=stop`.

Streaming Responses now resolves same-token tool-result ownership before
generating a session ID, including the existing unique same-objective recovery
for remapped call IDs. A focused two-turn streamed test verified one persisted
session, the same `X-Session-ID`, `step_count=2`, retained tool output, and a
cleared remapped pending call. Physical validation then exposed that the local
Executor can emit a tool payload with `finish_reason=stop`; streamed state now
opens the continuation whenever an observed tool-call ID exists, matching the
already validated non-stream behavior. Independent tool calls now default to parallel
execution when the client does not explicitly select sequential execution.
The Executor prompt also requires batching independent calls and forbids
re-reading an unchanged successfully loaded `/goal` objective.

The same regression run exposed that the executor total-timeout context crossed
an async-generator `yield`. Its scheduled cancellation therefore targeted the
task that consumed the first chunk rather than only the next upstream wait.
The stream now applies the unchanged absolute deadline to each upstream
`anext` operation, so a timeout raises `StageTimeout` without cancelling the
downstream consumer. Focused streaming, continuation, timeout, and translation
tests passed 30/30. The final isolated suite passed 863 tests with the existing
third-party Starlette TestClient deprecation warning.

PRs `#67` and `#68` deployed to production main
`71a2d3cabd9c26f419c636ae7bc2ad1fb0fc3e9d`. After the approved exact
Executor full stop/start and gateway/Hermes restart, authenticated readiness
reported resident ready with Executor and Reasoner ready. A real two-turn
streamed `dgx-moa` tool continuation used a deliberately remapped call ID and
returned the same session header on both turns; persisted state recorded
`step_count=2`, one tool result, one recovery event, and remained executing
rather than declaring completion. A separate authenticated `dgx-moa-fast`
request omitted `parallel_tool_calls`, requested two independent functions,
and emitted both function calls in one response with exactly one terminal
`response.completed`.

## Readable detailed live observation — 2026-07-22

The live-observation formatter now renders batched events as separated multi-line
cards. Isolated tests verified that prompt and structured Reasoner artifacts are
excluded by default, admitted only by their independent operator settings,
bounded by `max_content_characters`, and passed through the existing secret
redactor before provider delivery. This path exposes the Reasoner's explicit
schema artifact, not hidden model reasoning. Telegram and Discord remain
external processors even when the gateway listener is tailnet-only.

The focused observation/config run passed 36 tests. The full regression run
passed 803 tests with the existing third-party Starlette TestClient deprecation
warning. Ruff reported no issues, and strict mypy reported no issues in 37
source files.

Production main `cda93203d8ec7568cd35b6eb776e66b7e4c5ab4f` was then deployed with
the protected runtime override enabling prompt and structured Reasoner artifact
delivery with a 3,000-character content bound. The first request issued
immediately after lifecycle recovery returned `503`; the retry completed with
HTTP 200 and `VALIDATION_OK` in 14,367.043 ms. Its stored `request_received`
event contained a 67-character prompt, and `reasoner_completed` contained
problem interpretation, two reasoning-summary steps, risks, unknowns, and
recommended actions. Provider metrics after the batch reported three events
sent, zero dropped, and zero Telegram errors. Gateway, Executor, and the
resident target were all active after the selected exact Executor stop/start
fallback; the Executor retained context 65,536, one sequence, 1,700,000,000 KV
bytes, `gpu_memory_utilization=0.5`, and MARLIN.

## Governed data-path production deployment — 2026-07-22

PR `#36` merged to `main` as `40fce082860b0884f224127a7ebafc6eae4f94d5`
and the production worktree fast-forwarded from `dc46af0` while preserving its
untracked state file. The controlled gateway restart exercised the selected
exact Executor full stop/start. Gateway PID `2675698`, Executor PID `2675772`,
and the resident target returned active; the Executor argv retained context
`65536`, one sequence, `1700000000` KV bytes, `gpu_memory_utilization=0.50`,
and MARLIN. The resident readiness guard passed with `68359168000` bytes
available. Planner, Reviewer, and Judge remained inactive.

Authenticated readiness and model discovery returned HTTP `200` and advertised
all public aliases at context `65536`. A request made immediately after model
readiness received one transient HTTP `503`; the retry twenty seconds later and
all subsequent requests returned HTTP `200`, including exact `POSTDEPLOY_READY`.
Post-retry journals contained no traceback, exception, OOM, stream disconnect,
or restart loop. The gateway remained the only scoped tailnet listener at
`100.125.239.72:9000`; the Executor remained loopback-only at `127.0.0.1:8101`.

The production Responses SSE check emitted exactly one `response.completed`, no
`response.failed`, no reasoning event, and the exact marker. Chat SSE emitted
one `[DONE]`, the exact marker, and no reasoning content. A real Responses
function-tool round requested exactly `exec_command({"cmd":"pwd"})`, preserved
its call ID, accepted the observed output continuation, returned completed, and
included the observed production path.

The postdeployment harness result is
`/tmp/dgx-moa-live-client-matrix-20260722-postdeploy-r1/summary.json`, SHA-256
`300f7effdc77f40848401dede4c7e6313b833a7ec4f510683c8ef40346e1c628`.
Codex CLI `0.144.6`, OpenCode `1.17.18`, and Hermes Agent `0.18.2` each exited
zero with its exact marker. Generic and primary Reasoner paths returned valid
HTTP `200` JSON, the isolated gateway stopped, raw client artifacts were
removed, and the production Git fingerprint was unchanged.

At the final observation point, production SQLite and the atomic CSV matched
exactly for every nonzero aggregate: Executor 16/16 completed invocations and
`Qwythos-v2-9B:Q4` Reasoner 9/9, with zero failures. `/metrics` exposed exactly
32 fixed unlabelled names. Runtime inspection confirmed Loop Engineering,
runtime Skills, declarative policy, live observation, training collection, and
weekly jobs remain disabled; this deployment did not enable or export them.

### Isolated observer and real-clock scheduler follow-up

Three focused physical checks passed against a real loopback HTTP server:
Discord/Telegram-shaped thread targets and safe payloads, HTTP 429 and connection
outage isolation, and scoped approval controls covering allowlists, nonce expiry,
audit, and idempotency. No actual platform credential or message was used.

The first real-clock scheduler probe passed the OS abbreviation `KST`, which is
not an IANA ZoneInfo key, so both scheduler tasks exited and the probe correctly
timed out. The authoritative rerun used the configured `Asia/Seoul` key and real
`asyncio.sleep`: package fired at `2026-07-22T09:09:00.005371+09:00` and Skill
maintenance at `2026-07-22T09:09:00.291290+09:00`. This proves isolated
wall-clock firing, not a production weekly run or real chat delivery.

### Production Telegram observation enablement

The operator supplied one raw Telegram bot token in a 0600 untracked file. It
matched the Bot API token shape, authenticated as `@kodex9_AI_observer_bot`, and
was immediately moved out of the Git worktree to
`/home/kotori9/.config/dgx-moa/telegram.token`; the discovered target was stored
separately with mode 0600 and neither value was printed. The initial update poll
was empty. After the user initiated `/start`, exactly one private target was
available.

The runtime `TelegramProvider` sent an allowlisted validation event successfully;
synthetic prompt and authorization fields were absent before transport. The
protected production environment was then updated atomically with Telegram
observation enabled and controls disabled. The required gateway restart used the
selected exact Executor stop/start and restored the resident profile with
`68366192640` available bytes and the unchanged 65,536-token baseline.

As in the prior deployment, the first request immediately after resident
readiness received one transient HTTP `503`; the bounded retry had no further
failure. The successful production `dgx-moa` request returned exact
`TELEGRAM_PRODUCTION_OK` and `finish_reason=stop`. Observer metrics changed from
zero to three sent events with zero drops and zero Telegram errors. Weekly jobs,
training collection, observation controls, and Discord remain disabled.

## Governed runtime production deployment — 2026-07-22

PR `#34` merged to `main` as `979a608` and the production worktree was
fast-forwarded while preserving its untracked state database. Restarting the
gateway exercised the resident target's selected exact stop/start relationship,
so the Executor reloaded once with PID `2572119`; it returned active using
context `65536`, one sequence, `1700000000` KV bytes,
`gpu_memory_utilization=0.50`, and MARLIN. Gateway PID `2571891`, the resident
target, and Executor are active. Planner, Reviewer, and Judge remain cold.

Authenticated `/readyz` and `/v1/models` returned HTTP `200`; all public model
metadata reports context `65536`. The primary `dgx-moa` Reasoner + Executor path
returned exact `READY`. The production tool-continuation and Chat streaming
smoke passed, followed by isolated real-client runs of Codex CLI `0.144.6`,
OpenCode `1.17.18`, and Hermes `0.18.2`; each exited zero and returned its exact
marker. A direct Responses stream returned exactly one `response.completed`, no
`response.failed`, and no reasoning event. The atomic runtime CSV matched every
nonzero model-invocation database aggregate; its deployed rows include
`dgx-moa-executor` and `Qwythos-v2-9B:Q4`.

The first post-resident smoke reached Chat during the readiness boundary and
received the single expected `503`. A later smoke completed model work but its
final evidence helper exposed an unquoted JSON unit map in the protected
production environment. Adding only the documented outer quoting preserved the
same adaptive unit map and made both systemd EnvironmentFile and shell loading
equivalent; the complete rerun then passed. Post-deployment journals contain no
unhandled traceback, stream disconnect, OOM, or service restart loop after
readiness.

The only authenticated tailnet listener is the gateway at
`100.125.239.72:9000`; the configured Executor remains loopback-only at `8101`.
The configured external Reasoner remains `Qwythos-v2-9B:Q4` at
`192.168.0.197:11434`. Frontier remains Codex OAuth `gpt-5.6-sol`/high with
authenticated primary and secondary profiles and bounded failover. Loop
Engineering, runtime Skills, declarative policy, live observation and controls,
training collection, and weekly jobs remain production-disabled pending their
documented enablement gates; no production training data or external chat
message was emitted.

## Goal workflow completion follow-up — 2026-07-22

The predeployment live client matrix used the development source on isolated
loopback port `19300`, a generated validation-only bearer token, separate client
homes/state, and the already-resident physical Executor. The first run stopped
before startup because the checked-in authenticated configuration correctly has
no secret; the harness now disables authentication only while loading that base
and immediately installs its generated token. The second run exposed two real
integration defects: OpenCode omitted its output limit and requested more than
the gateway's 16,384 generated-token cap, while streamed Codex/Hermes requests
updated request usage but bypassed model-invocation usage. The shared streamed
invocation path and OpenCode `context=65536`, `output=16384` declaration were
corrected.

The third run at `/tmp/dgx-moa-live-client-matrix-20260722-r3` passed, and the
equivalent final run at `/tmp/dgx-moa-live-client-matrix-20260722-r4` also
removed all raw client homes/session stores after extracting content-free
evidence. The extended run at `/tmp/dgx-moa-live-client-matrix-20260722-r5`
also passed the primary `dgx-moa` Reasoner + Executor path and recorded one
`Qwythos-v2-9B:Q4` Reasoner invocation plus six Executor invocations. Generic
HTTP, Codex CLI 0.144.6, OpenCode 1.17.18, and Hermes 0.18.2 all completed through
the physical Executor; six Executor invocations were present in the atomic
runtime CSV; the isolated gateway stopped; and the production worktree Git
fingerprint was unchanged. The 16,384 value is the per-response generated-token
limit, not the Executor context window. The physical Phase 3 context remains
65,536 with one sequence.

The accompanying read-only runtime inspection showed the resident Executor
process with `--max-model-len 65536`, `--max-num-seqs 1`,
`--kv-cache-memory-bytes 1700000000`, `--gpu-memory-utilization 0.50`, and
`--moe-backend MARLIN`. The configured external Ollama endpoint's `/api/ps`
reported `Qwythos-v2-9B:Q4` with `context_length=65536` and 7,680,305,397 VRAM
bytes. These are direct runtime observations, not inferred benchmark values.

An initial isolated physical run at
`/tmp/dgx-moa-self-evolving-physical-20260722` stopped before packaging because
dictionary-key secret redaction did not increment its aggregate counter. The
counter was corrected without discarding the failed evidence. The new run at
`/tmp/dgx-moa-self-evolving-physical-20260722-r2` completed with
`status=passed` using real 7-Zip 23.01 arm64. Its regenerated W29 archive SHA-256
is `1799e1b9114e6ff959052ba984446f25637ddc5250ec81fe1ed528a34cf2f425`;
both `7z t` and `sha256sum -c` passed. The run physically exercised redaction,
quality/licensing/opt-out gates, CAS integrity and SQLite backup, empty and full
weeks, late arrivals, near duplicates, idempotency, revocation/regeneration,
deliberate archive corruption, archiver failure, and capacity-failure isolation
using synthetic data only. The subsequent full regression reported `785
passed` with the existing third-party Starlette warning.

Synthetic tests now additionally cover dry-run-first training/archive retention,
legal/preservation/deletion holds, CAS cleanup, atomic SQLite backup and
corruption detection, hashed persistent user opt-out, authenticated package
verify/revoke/regenerate and exact replay APIs, Seoul cron calculation and
scheduler lifecycle, safe weekly notifications, populated reports/indices,
tool/loop/conversation quality gates, generated-Skill canaries and versioned
lifecycle transitions, and graph-wide consistency/contradiction resolution.

The final post-client-fix full suite reported `786 passed` with the one existing
third-party Starlette warning. Ruff, mypy for 37 source files, and diff checks
passed after the Evidence Edge input/serialization alias fix; focused evidence,
replay, and controller regression tests reported `17 passed` afterward.

The final predeployment tree reported `791 passed` with the same third-party
warning; Ruff, the 74-file format check, mypy for 37 source files, and diff
checks passed. A bounded Codex OAuth `gpt-5.6-sol`/high review rejected an empty
delegated-chat result being converted to a completed Responses payload. The
shared conversion now emits a failed `backend_error` when no usable assistant
text or tool call exists, and three missing/empty/malformed upstream shapes have
endpoint regressions. The focused OAuth re-review used the primary profile and
approved with confidence `0.97`, no findings, and no missing tests. Its separate
title-history concern was rejected because the retained OpenCode 1.17.18 wire
capture and physical regression prove that the automatic title prompt can
precede trailing work-history messages.

All new feature gates remain disabled. No real Discord/Telegram message,
wall-clock scheduled week, live provider replay, production-data deletion or
export, production mutation, merge, or deployment occurred in this validation
row. Discord/Telegram physical provider behavior and the broader runtime/Skill
failure matrix remain separate gates; they are not established by the real-7z
or client results.

### Self-evolving data-path physical extension

The retained `r3` attempt correctly refused to reuse the same deterministic
weekly archive identity after its candidate source changed. The validator now
uses one stable initial candidate set for idempotency checks and reserves source
changes for the explicit regeneration path instead of weakening the collision
guard.

The authoritative corrected result is
`/tmp/dgx-moa-self-evolving-physical-20260722-r9/physical-validation.json`,
SHA-256 `cc98684cfbbc8055dc21328c09db27c7131631cd2742be4db74f95d39df56f26`.
It reports `status=passed` with real 7-Zip 23.01 arm64. The initial candidate
archive checksum was
`9a2201f12cf47535f74368a834ba14752ed2ef9277abad71457b5fb87246d8be`;
the explicitly regenerated archive checksum was
`c646f9f4b3d3d09f8595ed5c657a58616fff8680bf154a3cdee230eae298a556`.

The run physically validated policy redaction with scalar/list/object schema
preservation, a non-empty Evidence Graph, hash-protected exact replay of the
persisted engineering loop, successful/no-progress/duplicate loop termination,
and generated-Skill draft creation through isolated validation, historical
replay, regression evaluation, Reviewer inspection, an Executor-evidenced
helpful canary, explicit promotion, and explicit rollback. Before regeneration,
the real archive contained non-empty `state-transitions.jsonl` and
`repair-preferences.jsonl`. Existing CAS, privacy, licensing, opt-out, SQLite
backup, capacity isolation, idempotency, revocation/regeneration, empty-week,
corruption, and archiver-failure checks also passed with synthetic data.

This result does not validate live provider replay, actual Discord/Telegram
delivery, a wall-clock scheduler firing, or production enablement. Those gates
remain disabled.

After these persistence and dataset-path changes, the focused policy/replay/
trace/training/weekly run initially reported `66 passed`. A final Codex OAuth
`gpt-5.6-sol`/high review found that repair preferences needed an explicit
successful completion-evidence gate. The fix and failed/ungrounded counterexamples
reported `68 passed`; physical run `r9` passed afterward. The final complete
suite reported `802 passed` with the existing third-party Starlette warning;
all 75 files were formatted, Ruff passed, mypy passed for 38 source files, the
trace schema parsed, all shell scripts passed syntax checks, and
`git diff --check` was clean.

## Policy persistence and training-review follow-up — 2026-07-22

Policy tests now cover actual tool admission globs plus dotted redaction at
Evidence Graph, raw tool-result and normalized tool-execution persistence
boundaries. A tool result without a preceding assistant call also retains its
normalized arguments instead of silently substituting an empty JSON string.
Built-in redaction preserves prior policy-redaction markers on repeated passes.

Training tests now cover transactional and audited candidate approval,
invalid-transition rejection, ineligible approval rejection, packaged-candidate
revocation after request opt-out, hashed repository exclusion, collector
fail-closed behavior, and authenticated admin inspect/transition/request and
repository exclusion routes. Focused policy/security tests reported `14 passed`;
focused training/admin tests reported `26 passed`. After the package and Skill
follow-ups, the complete suite reported `761 passed` with the one existing
third-party Starlette warning; 73 files passed the format check, Ruff passed,
mypy passed for 37 source files, and diff checks passed.

This is synthetic unit evidence. Policy, collection, review APIs, and exclusion
workflows remain disabled; no production data was read, exported, packaged, or
deleted, and nothing was deployed. Operator-facing package regeneration and
retention enforcement remain incomplete.

The weekly synthetic-7z suite now also covers completed-package reverification,
registry tombstones, refusal to revive a revoked idempotency key, and explicit
atomic regeneration. The focused suite reported `8 passed`; no real 7z binary
or archive was used. Runtime Skill tests now cover distinct recurring-pattern
evidence, experimental-only generated drafts, immutable failed-to-passed
candidate versions, all mandatory evaluation gates, the additional Frontier
gate for high-impact candidates, and continued prohibition on automatic
promotion. The focused Skill suite reported `15 passed`.

Three focused metrics tests cover the complete fixed name set, loop outcome and
recurrence counters, authenticated HTTP exposure, zero-label rendering, and
absence of synthetic request/prompt content. Skill, observer, and training
overlays use aggregate counters only. This is process-local unit evidence; no
production scraper or dashboard was configured.

## Execution Replay Phase H foundation — 2026-07-22

Five focused tests cover canonical snapshot roundtrip/tamper detection, captured
task/evidence/Skill/policy/model state, complete mocked exact replay, rejection
of missing mocks and live calls in exact mode, live comparative nondeterminism,
explicit evaluation, and provider-free audit replay. The full suite reported
`742 passed`; format, Ruff, mypy for 36 source files, and diff checks passed.

No real local, Frontier or tool replay was performed. Production integration,
comparative quality/cost benchmarks and physical replay validation remain
pending; nothing was deployed.

## Weekly Skill/Data Packaging Phase G foundation — 2026-07-22

Seven focused tests cover the complete Seoul weekly window, required package
tree and checksums, verified atomic archive publication, source-stable
idempotency, failed verification cleanup, missing-7z and unsafe-encryption
fail-closed behavior, evidence-backed non-destructive Skill recommendations,
eligibility/privacy rescans, and exact/near deduplication. The full suite
reported `737 passed`; format, Ruff, mypy for 35 source files, and diff checks
passed.

Archive tests used a synthetic executable. This host has no real `7zz`/`7z` and
only about 3.8GB free, so physical archive creation, scheduling, retention,
notification, revocation and regeneration remain unverified. Nothing was
exported or deployed.

## Privacy-aware Training Collection Phase F foundation — 2026-07-22

Ten focused tests cover content addressing/deduplication/hash reads, object size
limits, synthetic secret/entropy/email/phone redaction, unknown repository and
opt-out exclusion, external-output license exclusion, evidence-grounded quality
tiering, grounded preference validation, separate WAL storage, tombstone package
filtering, normalized near duplicates, role/routing/tool/Skill separation, and a
disk-capacity failure that does not escape into request serving. Trace/config
tests additionally cover collection hooks, schema-compatible gate snapshots and
separate database enforcement.

The full suite reported `729 passed` with the one existing third-party Starlette
warning; format, Ruff, mypy for 34 source files, and diff checks passed. This is
unit evidence only. Collection remains disabled and no production content,
external output, training export, package, model training or deployment occurred.

## Live Observation Phase E foundation — 2026-07-22

Focused tests cover field allowlisting, unpublished-event suppression, batching,
bounded-queue drops, Discord thread and Telegram topic targeting, observer
failure isolation, nonce scope/expiry, allowlist and role authorization,
idempotent audit records, admin endpoint disablement, and a complete pause
command/replay. The full suite reported `716 passed` with the one existing
third-party Starlette warning; format, Ruff, mypy for 33 source files, and diff
checks passed.

This is unit evidence only. Observation and controls remain disabled; no real
Discord/Telegram provider, provider rate limit, provider outage, unauthorized
platform identity, or production deployment was exercised.

## Typed Evidence Graph Phase E foundation — 2026-07-22

Four focused tests cover tool/test precedence over model assertions, explicit
unknown-assumption classification, relationship validation, and role-specific
agent node types. The Controller suite plus focused evidence suite passed `53`.
The full suite then reported `703 passed` with the existing third-party
Starlette warning. This is unit evidence only; replay and physical validation
remain pending and no production deployment occurred.

## Declarative Policy Phase D foundation — 2026-07-22

Seven focused policy tests cover version/hash traceability, boolean/path/numeric
matching, restrictive limit aggregation, invalid-condition rejection, explicit
request denial, Controller role/evidence integration, and persisted missing-
approval termination. Combined policy/config tests passed `30`.

The full source gate reported `699 passed` with the one existing third-party
Starlette warning. Ruff formatted 10 changed files; the subsequent format check,
lint, mypy check for 31 source files, and diff check all passed. This is unit
evidence only. The policy engine remains disabled and partial; no physical
provider, real client, production policy, or deployment was exercised.

## Runtime Skills Phase C foundation — 2026-07-22

The disabled Phase C foundation adds strict Skill schema validation, atomic
immutable storage, separate SQLite quality metrics, bounded latest-active
retrieval, Executor-only activation records, evidence-and-approval promotion,
new-version rollback, and manifest/hash/signature-aware pack import/export.
Focused Skill tests passed `13`; combined configuration and Skill tests passed
`33` before the full gate.

The serialized source gate passed: `uv run pytest -q` reported `691 passed` and
the one existing third-party Starlette warning; `uv run ruff check .` passed;
`uv run mypy gateway/src/dgx_moa` passed for 30 source files; and
`git diff --check` passed. This is unit evidence only. Runtime Skills remain
disabled, no physical role provider or real Codex client was exercised, no
production registry was created, and no deployment occurred.

## Bounded Loop Engineering action admission — 2026-07-22

The disabled development path now admits each iteration and actual Reasoner,
Planner, Reviewer, Frontier, Judge and client-visible tool call against persisted
budgets. Structured retries consume another role call. Streamed tool admission
occurs before the first tool event; a denied Responses call emits one terminal
`response.failed` and no tool event. Observed token totals and known Frontier
cost consume separate budgets. Request-class and low/medium/high risk overrides
merge deterministically.

Only allowlisted observable evidence unlocks another iteration; Reasoner or
Executor assertions do not. User feedback is deduplicated by content hash and
stored without content. Failure evidence ignores timing noise. Identical tool
failures persist across retries, require a different strategy on occurrence two,
and terminate at occurrence three. Completion, cancellation, provider outage,
no progress and exhaustion persist explicit loop outcomes.

Focused tests cover admission before provider/tool calls, retry exhaustion,
stream terminal compatibility, loop types, risk overrides, evidence
deduplication, cancellation and repeated failures. The final complete suite
passed 677 tests with the existing Starlette warning; Ruff, Mypy over 29 source
files, and diff check passed. No physical or production validation has been
performed, and checked-in enablement remains false.

## Loop Engineering Phase A foundation — 2026-07-22

The development source adds a feature-gated, task-persisted `LoopState` with
typed loop classes, evidence-backed acceptance criteria, explicit remaining
budgets, no-progress tracking, termination reasons, and stable failure
fingerprints. The controller creates it only after request identity is known,
links new Evidence Graph node IDs, and retains the existing Reviewer approval
gate for completion. Safe checked-in configuration keeps it disabled.

Focused validation passed 11 tests covering persistence integration,
evidence-backed completion, configured no-progress termination, iteration and
Frontier-call exhaustion, deterministic normalization of timestamps, temporary
paths, request IDs, memory addresses and line-number noise, duplicate-failure
strategy change/termination, and strict environment configuration. Ruff passed
and Mypy passed 29 source files. This is
development/unit evidence only. The complete regression suite passed 655 tests
with the existing Starlette warning. Phase B action admission, physical providers,
real clients, cancellation, production enablement, and deployment remain
unvalidated and disabled.

## Goal-file fallback and runtime invocation CSV — 2026-07-22

The supplied Codex transcript and correlated production trace
`ec4923b2-3dac-4b21-8af7-86b4919090a0` showed that Codex first called
`read_mcp_resource` with the invented server name `local_filesystem`. That call
failed immediately with `unknown MCP server`. Native file and shell fallbacks
then read the same goal file successfully, but the gateway retained the earlier
MCP error as an active failure. Routing therefore selected Planner and Frontier
despite the recovered observation, and the request ended after `31.720` seconds
with a retryable Planner `model_loading` 503. The displayed answer consequently
reported that no models had been invoked even though the trace recorded core
and collaboration attempts.

The controller now correlates tool calls by normalized local target path. A
later successful native file or shell observation resolves the matching MCP
failure for routing purposes while retaining both records as audit evidence.
Resolved failures no longer lower confidence or trigger specialist escalation.
Model discovery instructions also state that local paths and `file://` URIs use
native file/shell tools and that only an exact server name and URI returned by
MCP discovery may be passed to `read_mcp_resource`.

A stale `unload_queued` lifecycle state is now cancelled when a new request
arrives, rather than being returned as a false loading state. When an optional
role genuinely returns `model_loading`, the Responses adapter keeps the
existing stream open with heartbeats and retries inside the configured loading
deadline. It emits `response.failed` only when the deadline expires or a
non-loading error occurs.

Each recorded model invocation now updates the runtime-owned
`model-invocation-rates.csv` atomically. It reports configured role/model rows
and preserves historically observed role/model pairs for all-time and
trailing-one-hour windows, distinct gateway requests using the model, invocation
count, request participation rate, success/failure counts, average latency, and
token totals. The denominator is distinct gateway requests
observed in the same window, so rates across roles need not sum to 100%. The
file begins accumulating exact evidence after a gateway using this source is
started; no historical calls are inferred or backfilled.

Focused regressions passed 5 tests. The complete source gate passed 647 tests
with the existing Starlette TestClient deprecation warning, followed by Ruff,
Mypy over 28 source files, and diff check. These results validate the development
source only. No production deployment, restart, or physical post-deployment
measurement has been performed for this change.

## Intermittent Responses disconnect and invocation rates — 2026-07-22

The reported production window contained 21 gateway requests: 13 completed, 6
failed, and 2 were cancelled. One cancelled trace waited `79566.922` ms for its
first downstream byte while Reasoner and Executor routing ran before the HTTP
stream existed. Another continuation failed after `29876.735` ms because the
external `Qwythos-v2-9B:Q4` response raised `JSONDecodeError`; the following
client retry succeeded. Six simultaneous Codex utility requests used
`gpt-5.6-luna` and were rejected as unknown-model 404s. These are the measured
sources of the intermittent reconnects; model services had zero restarts.

The shared Responses endpoint now returns its HTTP stream immediately, sends an
SSE comment heartbeat at once and every 15 seconds until Chat preprocessing
finishes, and converts unexpected pre-stream exceptions to terminal
`response.failed`. Q4 structured-output parsing retries once internally. The
observed Codex utility slug is normalized to the existing Executor-only
`dgx-moa-fast` path but is not advertised as a public model. Arbitrary unknown
models remain rejected, and Frontier remains Codex OAuth only.

Eight tool results occurred in the measured hour: six `exec_command`, one
`read_mcp_resources`, and one `read_mcp_resource`. All reported exit code zero,
but the MCP results contained `unsupported call` and `unknown MCP server` and
were incorrectly recorded as successes. The existing observation boundary now
classifies these as `UNSUPPORTED_TOOL` and `MCP_SERVER_UNAVAILABLE`, enabling
the existing replan and duplicate-failure guard. No MCP server is synthesized
or mutated by the gateway.

Role invocation rate uses gateway requests as the denominator. The measured
one-hour window was Executor 21/21 (`100%`), Q4 Reasoner 21/21 (`100%`), Planner
2/21 (`9.5%`), Reviewer 3/21 (`14.3%`), primary Codex OAuth Frontier 4/21
(`19.0%`), and Heavy Judge 0/21 (`0%`). The cumulative usage snapshot was 244
requests: Executor 244 (`100%`), Reasoner 71 (`29.1%`), Planner 99 (`40.6%`),
Reviewer 98 (`40.2%`), Frontier 7 (`2.9%`), and Judge 0. Rates can exceed a
combined 100% because one request may invoke multiple roles.

Isolated physical validation returned the first heartbeat in `30.758` ms and
completed the Luna compatibility request as exact `LUNA_FAST_OK` in `0.370`
seconds. A real Q4 core request returned its first heartbeat in `1.027` ms,
sent two heartbeats, and completed exact `Q4_HEARTBEAT_OK` in `17.075` seconds.
A real Q4 + Executor tool request returned its first heartbeat in `1.428` ms,
exposed zero text deltas, produced `pwd` arguments, and ended
`response.completed` in `9.585` seconds.

Final gates passed 643 tests with the existing Starlette warning, Ruff, Mypy,
and diff check. The cancellation regression proves that closing after the first
heartbeat cancels and awaits pending Chat work and finalizes usage as cancelled.
Primary-profile Codex OAuth review approved with Critical 0, Important 0 and
confidence `0.76`; no API key was created or used. A client that has already
disconnected cannot receive a terminal SSE event, so the enforceable contract
is terminal completed/failed for server-controlled endings plus task cleanup on
client cancellation.

PR `#32` merged as production main `229be8d`. The controlled deployment used
the selected full Executor stop/start and preserved context `65536`, one
sequence, `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN.
Weight loading took `251.57` seconds; total model loading took `262.618`
seconds, with `67121` KV tokens and `1.02x` maximum concurrency.

The authenticated production Luna utility request received its first heartbeat
in `8.526` ms, completed exact `PROD_LUNA_OK` in `1.982` seconds, and reported
served model `dgx-moa-fast`. The Q4 + Executor tool request received its first
heartbeat in `1.204` ms, sent two heartbeats, exposed zero text deltas, returned
`{"cmd": "pwd"}`, and ended `response.completed` in `18.266` seconds. A near
match returned exactly one `response.failed`; the safe journal recorded its
session, model, source, HTTP 404, error type/code, and failure class.

Real Codex then completed the native tool loop without reconnecting: the
pre-tool agent message was empty, `/usr/bin/zsh -lc pwd` exited zero, final text
was exact `CODEX_HEARTBEAT_OK` plus the observed path, and `turn.completed`
reported `15546` input / `45` output tokens. Trace
`d62657a8-1ca7-4295-a6b3-c52b907f111d` recorded exact Q4 and no failure. Its
degraded label remains the known missing-provenance classification for the
temporary CLI workspace, not a model or stream failure. Gateway, Executor, and
resident target all remained active.

## Responses privacy/terminal fix and Q4 Reasoner — 2026-07-22

Production trace
`data/traces/main/production/2026-07-21/bf7ce95c-fe52-4a08-bf61-d70cb59c9adc.jsonl`
matched the reported Codex task. Successful tool turns ended with
`finish_reason=tool_calls`, but Planner/Reasoner and unsupported-tool failures
returned non-stream JSON or ended without a Responses terminal event. Codex
therefore retried and reported `stream closed before response.completed`.
Executor text emitted before a later tool delta was also translated immediately,
which exposed its tool-selection narrative as ordinary output.

The adapter now delays Responses text until upstream classification, discards it
when a tool call or failure follows, requires `[DONE]` or `finish_reason`, and
emits `response.failed` for pre-stream HTTP errors, non-stream error responses,
upstream error frames, truncated EOF, oversized buffers, and iterator failures.
Content-free `responses_stream_terminal` records preserve the correlated session,
model, source, status, error class/code, and safe counts without prompts,
reasoning, tool arguments, bodies, or exception messages. Reasoner failure traces
add provider, served model, latency, HTTP status, and failure class.

The configured external Ollama Reasoner changed from `Qwythos-v2-9B:Q5` to exact
`Qwythos-v2-9B:Q4`. `/api/tags` physically reported digest
`9f14d2d170086958ad4b216b402617441838b578820f479fd729766e6fc08dc1`
and stored size `6,825,527,520` bytes. A schema-constrained request at
context `65536` completed with all eight contribution keys in `17.469` seconds,
including `4.390` seconds load. `/api/ps` then reported runtime size
`8,630,462,050`, VRAM `7,402,244,012`, and context `65536`.

An isolated real gateway produced a terminal `response.failed` and safe journal
record for an HTTP exception. A real Executor tool request exposed no narrative
text delta and completed with `pwd`; a real `dgx-moa` request returned exact
`Q4_CORE_OK`. Trace `q4-core-validation` recorded Reasoner revision `Q4`,
Reasoner `7355.864` ms, Executor `320.025` ms, no Reasoner-unavailable event,
and a completed session. The degraded trace label reflected intentionally absent
workspace provenance headers, not an inference failure.

Automated gates passed 632 tests before Frontier review. Primary-profile Codex
OAuth review rejected two missing counterexamples: top-level error-only frames
and EOF without a terminal marker. Both were fixed with privacy regressions,
control-character-safe log fields, and an explicit 1,000,000-character bound.
Focused gates then passed 187 tests plus Ruff and Mypy. The final complete gate
passed 636 tests with the existing Starlette warning, Ruff, Mypy, and diff check.
The bounded OAuth
re-review approved with Critical 0, Important 0, confidence `0.96`; no API key
was created or used.

PR `#30` merged as production main `dc82514`. The controlled restart performed
the selected full Executor stop/start. Weight loading took `254.14` seconds and
total model loading took `265.766` seconds. The unchanged command and runtime
reported context `65536`, one sequence, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, MARLIN, `67121` KV tokens, and `1.02x` maximum
concurrency. Gateway, Executor, and resident target all returned active.

An authenticated unknown-model stream returned the single terminal
`response.failed`; the journal recorded source `chat_http_exception`, HTTP 404,
error type, and code without content. An authenticated real Executor request
returned `response.function_call_arguments.done` with `{"cmd": "pwd"}` and
`response.completed`, with zero `response.output_text.delta` events. A real
`dgx-moa` request returned exact `Q4_PROD_OK` then `response.completed`; trace
`prod-q4-stream-validation` recorded exact Reasoner revision `Q4` and no failure.

Finally Codex CLI used the production Responses provider against a temporary Git
workspace. Its pre-tool agent message was empty, it executed
`/usr/bin/zsh -lc pwd`, returned exact `CODEX_STREAM_OK` plus the observed path,
and ended with `turn.completed` and usage `15415` input / `41` output tokens.
Trace `13400371-7f3f-42c5-a5ee-877d4cbc9bdf` recorded Q4 and zero failures. Its
degraded label is the existing missing-provenance classification for the
temporary CLI workspace, not a model or stream failure.

## Production Codex Responses tool loop — 2026-07-22

Production incident trace
`data/traces/main/production/2026-07-21/869069ff-5a0c-41c4-a037-bf9eca278400.jsonl`
returned HTTP 200 but ended the Executor stream with `finish_reason=stop` and
no native tool delta. The client-visible result was a Bash code block rather
than an executed command. Inspection confirmed that the Responses adapter did
not forward `instructions`, `tools`, `tool_choice`, or `parallel_tool_calls`
to the Chat/Executor path and translated only text deltas.

Dev commit `63e32b3` added bounded function-tool conversion, streamed Responses
function-call events, non-stream function-call output, and
`function_call`/`function_call_output` continuation conversion. The complete
suite passed `625` tests with the existing Starlette TestClient deprecation
warning; focused Ruff checks passed. PR `#23` merged as production main
`037edaa`.

The production gateway restart caused the lifecycle controller to perform the
selected full Executor service stop/start. The unchanged Phase 3 baseline was
observed in the new argv: context `65536`, one sequence, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN. Weight loading took `250.77` seconds;
the gateway, Executor, and Reasoner subsequently reported ready.

A real authenticated streaming `dgx-moa` request used a flat Responses
`exec_command` function schema and `tool_choice=required`. It returned call ID
`chatcmpl-tool-8d20a0982ea80d6a`, accumulated valid arguments
`{"cmd":"pwd"}`, emitted both `response.function_call_arguments.done` and
`response.output_item.done`, then emitted `response.completed`. Production
trace `41880c39-99ae-43ff-9522-2868e44ca6ff` recorded
`finish_reason=tool_calls`.

The authenticated continuation supplied the matching `function_call` and
`function_call_output` with observed stdout
`/home/kotori9/dgx-moa-agent`. Trace
`3c935a05-5ec8-4f40-a7a2-91c042c11ee9` recorded the tool execution and the
stream returned the observed directory in `response.output_text.done`, followed
by `response.completed`. Both requests returned HTTP 200. Final `/readyz`
reported profile `resident`, Executor `ready`, Reasoner `ready`, and optional
Planner/Reviewer/Judge stopped.

Real Codex CLI `0.144.6` then used the production custom provider with the
Responses wire API, an ephemeral read-only sandbox, and no API-key creation.
It made three HTTP 200 Responses turns under correlated trace
`0570e4b9-f8b5-4e17-b342-d265ff4ac7c0`: two native tool-call turns, followed by
a text turn after Codex executed `pwd`. The client emitted exact final text
`CODEX_TOOL_OK /home/kotori9/dgx-moa-agent` and `turn.completed`. Codex also
reported a non-blocking model-catalog metadata warning because the gateway's
OpenAI-compatible `/v1/models` list has `data` rather than Codex's additional
top-level `models` field; it defaulted metadata and completed the tool loop.

### Responses custom/freeform tool production deployment — 2026-07-22

The follow-up audit found that the deployed adapter preserved standard
`function` tools but silently omitted Responses `custom` tools such as Codex
`apply_patch`. The development fix wraps each custom tool in one strict Chat
function string field for local Executor inference, then restores native
`custom_tool_call`, `response.custom_tool_call_input.delta`, and
`response.custom_tool_call_input.done` objects. Custom call/output continuation
items map back to assistant/tool Chat messages; mixed standard function tools
remain unchanged.

The focused regressions cover a tool name arriving after its call ID, valid
freeform input, non-string decoded input fallback, function+custom coexistence,
and both custom continuation items. Full publication gates passed `627` tests
with the existing Starlette warning; Ruff format/check, Mypy for 29 source
files, user-systemd verification, every shell syntax check, trace audit `10/10`
at 100%, and `git diff --check` all passed. Host OpenAI Python parsed all 12
synthetic typed events through `response.completed`.

A real primary-profile Codex OAuth review first returned `revise`, Critical 0
and Important 2, confidence 0.90, in `40899.016` ms with `25060` tokens. It
identified premature stream-kind classification and unchecked decoded input
types. Both were fixed with regressions. The bounded re-review returned
`approve`, Critical 0, Important 0, missing tests 0, confidence 0.93, in
`6448.757` ms with `14708` tokens. No API key was created or used. PR `#26`
merged the reviewed custom/freeform adapter as production main `14579f4`.

An authenticated production wire probe then returned a native
`custom_tool_call` for `emit_marker`, exact `CUSTOM_WIRE_OK` input delta/done,
`response.output_item.done`, and `response.completed`. The first real Codex
edit counterexample deliberately required `apply_patch` while CLI fallback
metadata did not advertise it. Trace
`e8057a51-3eb1-4e0f-b983-e90068ecb319` retained the resulting
`unsupported call: apply_patch`; its workspace sandbox also retained the
independent Bubblewrap `RTM_NEWADDR` denial. Repeating with the tool actually
advertised by fallback metadata and a controlled no-sandbox temporary Git
workspace passed two `exec_command` calls, exact file content, final
`CODEX_TOOL_EDIT_OK`, and `turn.completed` in trace
`2423adcf-f40c-43d3-8be3-a389146b0be3`.

PR `#27` merged Responses usage normalization and a Codex catalog alongside the
unchanged OpenAI `data` list as main `20b5296`. Full gates passed `630` tests,
Ruff, and Mypy. Two primary-profile OAuth reviews approved with Critical 0 and
Important 0; confidence was 0.90 and 0.97. Production physical validation
reported nonzero Codex usage (`31503` input, `203` output), proving that the
stream now includes upstream usage. It also exposed one installed-version
contract difference: Codex CLI `0.144.6` required
`supports_reasoning_summaries`, while the initially consulted current protocol
source used a different compatibility field. The retained parser error named
that exact missing field; it did not disconnect an inference stream.

PR `#28` added the installed CLI's complete serialized metadata field set and
merged as production main `993d653`. A bounded primary OAuth review approved
with Critical 0, Important 0, no missing tests, confidence 0.96, and `14542`
tokens. Both deployment restarts used the selected exact full Executor
stop/start and preserved context `65536`, one sequence, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN. Measured weight loads were `265.913`
and `265.277` seconds; the final cache held `67121` tokens and reported `1.02x`
maximum concurrency at `65536`.

The final real Codex run had no catalog fallback or stream-disconnect warning.
It exercised three malformed freeform patches; Codex rejected each with the
correct first-line, last-line, or hunk-header error and made no file change.
The fourth native `apply_patch` emitted a completed `file_change`, created
`marker.txt`, and `exec_command` read exact bytes `CUSTOM_PATCH_OK\n`. Codex
returned exact `CODEX_CUSTOM_TOOL_OK`, `turn.completed`, and nonzero usage
(`36122` input, `527` output). Production trace
`0cb2e314-2b6d-4d56-9ce5-3db12ad65153` retains all rejected and successful
tool observations; its `degraded` status is expected because the deliberate
negative calls and one invalid `write_stdin` process ID remain visible. Final
`/readyz` reported resident profile with Executor and external Reasoner ready;
Planner and Judge were inactive, while Reviewer independently resumed its
previous lifecycle generation after the snapshot.

The final trace itself has no missing mandatory field and contains all four
required lifecycle events: `session_started`, `route_selected`,
`assistant_stream_finished`, and `session_ended`. The whole production archive
audit is not clean: it measured 191 sessions, 121 complete, 70 incomplete, 11
legacy, and 63.35% completeness. Its historical gaps are 57 absent
`session_ended` events plus older task/workspace/model-revision fields. This
pre-existing archive debt is retained rather than rewritten; it does not erase
the complete final production trace or the development publication audit that
passed 10/10.

## Dynamic MoA isolated validation — 2026-07-21

This section records only observed results for the current `dev` candidate. The
gateway ran on loopback `127.0.0.1:19300` with isolated SQLite at
`/tmp/dgx-moa-dynamic-validation.8P4ruq/gateway.db`, lifecycle disabled, and
Frontier enabled only in that process. It used the already-running loopback
Executor for inference and the external Ollama Reasoner. Later optional-role
rows started direct loopback-only development Planner/Reviewer processes; all
were stopped after measurement. No production service was restarted or
reconfigured.

- Final automated validation: 610 tests passed with one upstream Starlette
  deprecation warning; Ruff passed; mypy passed for all 29 source files;
  `git diff --check` passed.
- Ollama `/api/tags` exposed `Qwythos-v2-9B:Q5`, size `7632668897` bytes. A
  32-token strict probe exhausted its budget in `thinking` and returned empty
  content. A 512-token probe returned `{"ready": true}`, used 63 prompt and 167
  eval tokens, and reported `2073546671` ns total duration. The candidate keeps
  a 1,500-token Reasoner budget.
- `/api/ps` then exposed that the persistent model was actually loaded with only
  8,192 context. Adding the configured `num_ctx=65536` to native Ollama requests
  reloaded it and returned `{"ready":true}` in `11420701139` ns total, including
  `4043920028` ns load time, 47 prompt tokens, and 183 eval tokens. The following
  `/api/ps` reported exact model `Qwythos-v2-9B:Q5`, context `65536`, size
  `9672494936` bytes, and `7392303512` VRAM bytes. Readiness now uses `/api/ps`
  rather than treating `/api/tags` installation metadata as residency evidence.
- A fresh isolated gateway using the corrected provider returned exact
  `POST_CONTEXT_OK` from `dgx-moa`, HTTP 200, with Executor usage `566/4/570`.
  Its separate SQLite recorded mode `moa`, roles `[reasoner, executor]`, one
  successful warm row for each role, one `reasoner_completed`, and one terminal
  session. The follow-up `/api/ps` still reported context `65536`. The temporary
  loopback listener was stopped; production gateway/Executor stayed active and
  Planner/Reviewer/Judge stayed inactive.
- The first integrated core request exposed a real system-only template defect:
  Ollama returned HTTP 400 because the model requires a user query. The gateway
  returned typed `reasoner_required_unavailable` 503 and did not degrade. After
  adding bounded user task data, non-streaming `dgx-moa` returned
  `CORE_MOA_OK`, HTTP 200, with Executor usage `483/5/488` prompt/output/total.
  SQLite recorded Reasoner confidence 1.0 and roles `[reasoner, executor]`.
- Streaming `dgx-moa` returned `STREAM_MOA_OK` in native SSE deltas, exactly one
  `[DONE]`, and Executor usage `586/5/591`.
- Native agent mode issued `get_validation_marker` with ID
  `chatcmpl-tool-b456f776ad48d719` and arguments `{"name":"core"}`. The matching
  tool-result continuation returned `TOOL_MOA_OK`. Reasoner participated in
  both requests; only Executor emitted the tool call and final content.
- Real OpenCode `1.17.18` returned `OPENCODE_DYNAMIC_MOA_OK` with usage
  `3084/7/3091`. Its relative-path read attempt asked for a path and made no tool
  call. The explicit absolute-path retry issued native `read` on the isolated
  fixture, observed `OPENCODE_DYNAMIC_MOA_FIXTURE`, and continued with
  `OPENCODE_TOOL_MOA_OK`; step usages were `3243/40/3283` and `3518/7/3525`.
- Real Hermes Agent `0.18.2` returned `HERMES_DYNAMIC_MOA_OK` in one API call
  with usage `3344/7/3351`. Its isolated `read_file` task returned
  `HERMES_TOOL_MOA_OK` in two API calls with aggregate usage `7360/48/7408`.
  Hermes probe requests to unsupported compatibility paths received 404 before
  it selected `/v1/models`; inference and tool continuation passed.
- Across the isolated database there were 14 completed MoA requests and exactly
  14 `reasoner_completed` events. Twelve agent-mode requests, including client
  title/continuation turns, all recorded roles `[reasoner, executor]`. Three
  tool-result and three tool-execution events were observed.
- Codex CLI `0.144.6` reported both isolated profile directories as logged in,
  but real calls returned 401 `token_invalidated`/`refresh_token_invalidated`.
  The active default Codex OAuth profile returned `OAUTH_OK`; no API key was
  created. The Frontier adapter was changed to use this explicit default OAuth
  home.
- Real Frontier architecture mode succeeded after strict schemas added
  `additionalProperties:false`: `34961/598/35559` tokens and `20365.547` ms.
  Real disagreement mode preferred the default OAuth profile from the supplied
  evidence with confidence 1.0: `33254/275/33529` tokens and `28160.595` ms.
  The first code-review mode embedded a sandbox startup failure as a Critical
  finding and rejected; this is retained failed evidence. Replacing temporary
  shell file reads with inline redacted/allowlisted/bounded evidence produced a
  successful `approve`, no findings or missing tests, confidence 0.92,
  `20721/117/20838` tokens, and `6073.12` ms.
- After changing Frontier subprocess inheritance to an explicit safe environment
  allowlist, a real disagreement call ran while sentinel gateway/OpenAI key
  variables existed in the parent. The child environment excluded both by
  construction; OAuth still succeeded and preferred the allowlist boundary in
  `7395.451` ms with `16648` total tokens.
- A post-implementation Codex OAuth code review initially rejected with one
  Critical and two Important findings (`24835/1330/26165` tokens,
  `37775.64` ms). The optional-role and duplicate-stream claims were disproved
  by the active empty optional-role policy, idempotent stream cleanup, and
  direct regressions. The valid unconfigured-dynamic-role finding was fixed with
  a typed `model_not_managed` response and cold per-role accounting. A second
  bounded Codex OAuth review approved with Critical 0 and Important 0,
  confidence 0.9, `20819/666/21485` tokens, and `23014.673` ms. Its only missing
  test was the already-declared full physical Planner/Reviewer/Heavy Judge
  integration matrix.
- A later bounded Codex OAuth re-review was requested only for stdout failure
  classification and exact-output enforcement. Codex CLI `0.144.6` selected
  OpenAI `gpt-5.6-terra` through the logged-in OAuth provider but exited `1`
  with `You've hit your usage limit`; no review verdict was produced. Focused
  regressions, the 609-test suite, Ruff, and mypy passed, but this failed OAuth
  review attempt is retained rather than described as approval.
- Integrated architecture routing recorded Reasoner `1712` total tokens,
  Executor routing `708`, Planner/Frontier parallel selection, Planner
  `ConnectError`, and a completed Frontier architecture artifact
  (`16667/616/17283`, `25270.012` ms). The request correctly ended HTTP 502
  because Planner was unavailable; Frontier evidence was not cancelled.
- Integrated security code review recorded Reasoner `1615`, Executor routing
  `431`, local Planner and Reviewer connection failures, and completed Frontier
  code-review evidence (`16600/224/16824`, `10095.351` ms). The request correctly
  ended HTTP 502. This measurement exposed and led to a fix for derived
  confidence remaining high after local-agent failures.
- A later sequential real-weight run kept the production Executor active and
  started only a direct development Planner. Planner loaded five shards in
  `32.73` seconds, used `19.57 GiB` model memory, exposed 83,740 KV tokens at
  context 65,536, and stopped cleanly after the test. The corrected architecture
  request returned exact `ARCH_DYNAMIC_OK`, HTTP 200, in `110.091` seconds.
  SQLite recorded roles `[reasoner, executor, planner]`; the Executor selected
  Planner + Frontier in parallel. Agent totals were Reasoner `2293`, Executor
  routing `659`, Planner `784`, Frontier `16735/782/17517` in `27053.394` ms,
  and Executor synthesis `2379/4/2383`. No Reviewer invocation was recorded
  because this was security architecture without implementation evidence.
- The first direct Reviewer start failed before weight loading because the
  development command omitted the checked-in `flash_attn.ops` namespace shim.
  Repeating with the same read-only `compat` path used by the reviewed unit
  succeeded: four shards loaded in `108.35` seconds, model memory was
  `18.09 GiB`, and KV capacity was 67,383 tokens at context 65,536. The real
  code-review request returned exact `REVIEW_DYNAMIC_OK`, HTTP 200, in `43.379`
  seconds with roles `[reasoner, executor, reviewer]`. Reviewer + Frontier ran
  in parallel; local Reviewer approved with no findings. Agent totals were
  Reasoner `1545`, Executor routing `480`, Reviewer `882`, Frontier
  `16643/225/16868` in `9596.842` ms, and Executor synthesis `1119/5/1124`.
  Derived confidence remained honestly low because the Reasoner reported 0.0.
- A real OpenCode `1.17.18` architecture request then returned exact
  `OPENCODE_ARCH_DYNAMIC_OK`. Its work session recorded roles
  `[reasoner, executor, planner]` and completed in `101.877` seconds. Agent
  totals were Reasoner `2015`, Executor routing `494`, Planner `1158`, Codex
  OAuth Frontier architecture `20818/411/21229` in `14720.662` ms, and
  Executor synthesis `4359/6/4365`. Planner and Frontier ran in parallel.
  Capturing the concurrent OpenCode title request exposed its current exact
  system marker, `You are a title generator. You output ONLY a thread title.`
  The first isolated run separated the title state but still let its
  orchestrated alias select Planner. The corrected path overrides only that
  automatic title request to `fast`. A second real OpenCode run returned exact
  `OPENCODE_TITLE_ISOLATION_OK`; its title request used only Executor, `300`
  tokens, and `0.251` seconds, while the work session independently used the
  Reasoner + Executor core and no optional agent.
- A real OpenCode review task issued native `read` for `FIXTURE.txt`, observed
  `OPENCODE_DYNAMIC_MOA_FIXTURE`, and sent the tool evidence back through the
  external client loop. The continuation reinvoked Reasoner and returned exact
  `OPENCODE_REVIEW_DYNAMIC_OK`. Its successful evidence-bearing round ran local
  Reviewer and Codex OAuth Frontier code review in parallel: Reviewer used
  `991` total tokens in `5852.177` ms; Frontier used
  `16708/244/16952` in `13562.639` ms; final Executor synthesis used
  `4045/7/4052`. One preceding continuation attempt failed after the Executor's
  structured routing response exhausted its `1500`-token bound; OpenCode retried
  and the next bounded decision succeeded. The retained usage rows report this
  failed attempt instead of hiding it. The automatic title request again used
  only the fast Executor path (`307` tokens, `0.540` seconds).
- Real Hermes Agent `0.18.2` using `dgx-moa-orchestrated` returned exact
  `HERMES_ARCH_DYNAMIC_OK` in one API call and `88.453` seconds. SQLite recorded
  roles `[reasoner, executor, planner]`: Reasoner used `1214` total tokens,
  Executor routing `404`, Planner `1505` in `70212.833` ms, Codex OAuth
  Frontier architecture `16615/542/17157` in `19767.367` ms, and final Executor
  synthesis `4782/6/4788`. Planner and Frontier ran in parallel while Hermes
  remained the external client.
- The first bounded Hermes missing-file recovery completed four API calls but
  exposed that Hermes sends neither the gateway session header nor body session
  metadata. Each tool continuation therefore created a new state, and Hermes
  reports missing files as exit code `0` with `File not found` in stderr. The
  gateway now retains bounded streaming tool-call IDs, correlates headerless
  continuations only within the same authenticated token, and classifies common
  missing/denied stderr markers as failures. A regression proves a second token
  cannot claim the pending continuation.
- The corrected real Hermes recovery kept all four calls in one state, observed
  two `NONEXISTENT_PATH` failures and the final fixture, reinvoked Reasoner on
  every turn, and invoked Codex OAuth Frontier after the second failure. The
  state recorded two Frontier architecture collaborations (`17065` and `17129`
  total tokens), four Executor final-synthesis calls, two active failure rows,
  derived confidence `low`, and no pending tool-call IDs. Hermes exited `0` and
  included `HERMES_RECOVERY_CORRELATED_OK`, but added an explanatory fixture
  paragraph despite the exact-output instruction; this row is therefore a
  recovery success and an exact-output failure, not an exact pass.
- A real Hermes evidence-bearing review first hit one retained backend failure
  when the Executor routing JSON exhausted the `1500`-token cap. Hermes retried;
  the successful state kept both API calls correlated, invoked Frontier code
  review before the tool call, issued `read_file`, then reinvoked Reasoner and
  ran local Reviewer + Frontier code review in parallel. The evidence-bearing
  round used Reasoner `1517`, Executor routing `410`, Reviewer `830` in
  `5878.852` ms, Frontier `16681/195/16876` in `9497.463` ms, and Executor
  synthesis `4176/96/4272`. Hermes exited `0` and included
  `HERMES_REVIEW_DYNAMIC_OK`, but added a paragraph explaining the fixture had
  no substantive implementation. This is a dynamic review/tool success and an
  exact-output failure.
- Post-fix Hermes strict-format reruns closed both retained output failures. The
  first recovery attempt was rejected by the harness because it supplied the
  invalid trace origin `physical-validation`; three HTTP 502 retries were
  retained and the gateway was restarted with the allowed `validation` origin.
  The identical recovery task then returned exactly
  `HERMES_RECOVERY_CORRELATED_OK` in four API calls with `18726/133/18859`
  client-reported tokens. Gateway state recorded four Reasoner and two Frontier
  invocations, derived confidence `low`, and no pending tool IDs.
- The identical evidence-bearing review task then returned exactly
  `HERMES_REVIEW_DYNAMIC_OK` in two API calls with `8593/48/8641`
  client-reported tokens. Gateway state recorded two Reasoner, two Reviewer, and
  two Frontier invocations, no pending tool IDs, and derived confidence
  `conflicted`, preserving rather than hiding the independent review conflict.
  The direct Reviewer and isolated gateway stopped cleanly; ports `8103` and
  `19300` closed while the production Executor remained active at context
  `65536`.
- Real structured-output failures exposed three bounded recovery defects. The
  Executor controller now retries one invalid/truncated routing decision with a
  512-token minimal-schema request. Reviewer results are validated by one
  strict Pydantic schema (`status` enum and `findings: list[str]`) on both the
  original response and one evidence-preserving retry; a parseable
  `{"status":"approved","findings":"none"}` is rejected rather than recorded
  as approval. The Reviewer retry is capped at 1,024 tokens because the real
  North model can spend more than 512 completion tokens reasoning before it
  emits final JSON. Optional Frontier unavailability is reapplied as derived
  confidence `low` after local-review conflict handling.
- A final all-relevant-role security-boundary request returned the exact seven
  expected booleans, HTTP 200, in `125.950` seconds. Roles were Reasoner,
  Executor, Planner, Reviewer, and Codex OAuth Frontier. Planner + Reviewer +
  Frontier ran concurrently; the pre-Reviewer rejected with all six stated
  defects, Frontier rejected independently, Executor synthesized the exact
  answer, and the post-Reviewer approved it. Both Reviewer outputs passed the
  strict schema without retry. All-agent usage was `31314` tokens: Reasoner
  `1954`, Executor routing `705`, Planner `1254`, pre-Reviewer `1937`, Frontier
  `21042`, final Executor `1837`, and post-Reviewer `2585`.
- The final Reviewer-only candidate row (Frontier intentionally unavailable)
  returned the same exact seven booleans in `126.501` seconds and `9434`
  all-agent tokens. The post-review passed, but the pre-review exhausted its
  original budget and its evidence-preserving retry still failed schema
  validation. The gateway did not synthesize approval: it recorded degraded
  observability and derived confidence `low`. A separate direct compact probe
  of the same real Reviewer rejected with all six findings in `596` total
  tokens. This demonstrates prompt sensitivity, not a reliable Reviewer-only
  quality gain.
- Real OpenCode `1.17.18` completed the missing multi-file row in an isolated
  directory through `dgx-moa-agent`. It edited exactly `tags.py`, `report.py`,
  and `test_tags.py`, ran `python -m unittest -q`, passed 7 tests, and returned
  exact `OPENCODE_MULTIFILE_MOA_OK`. One work state retained four Reasoner
  rounds, five tool results, roles `[reasoner, executor]`, and no optional
  agent; its automatic title state remained fast Executor-only.
- A real OpenCode recovery row then issued two failed reads and one successful
  fixture read in one Executor tool-call response. This exposed that OpenCode
  reports `File not found` as exit `0` in stdout, unlike Hermes stderr. The
  common observer now treats only reliable stdout markers (`not found`, `no
  such file`, `permission denied`) as failures while preserving benign text
  such as `tests failed before the fix`. The post-fix rerun returned exact
  `OPENCODE_RECOVERY_CLASSIFIED_OK`; SQLite recorded two
  `NONEXISTENT_PATH` failures, two Reasoner rounds, empty pending tool IDs, and
  derived confidence `low`. Codex OAuth Frontier was selected after the second
  failure; the CLI returned optional `FRONTIER_USAGE_LIMIT`, which was recorded
  and safely fell back to local synthesis.
- Real Hermes Agent `0.18.2` completed the missing multi-file implementation in
  an isolated directory through `dgx-moa-agent`. It implemented `slugs.py`,
  `links.py`, and `test_links.py`; `python -m unittest -q` passed 5 tests.
  Hermes reported 6 API calls and `39162` aggregate tokens. Gateway state kept
  six Reasoner rounds, Executor-only tool ownership, two correlated tool-result
  continuations, and no pending tool IDs. The first final response contained
  the required marker but prefixed explanatory text, so exact formatting
  failed.
- The shared Executor prompt now explicitly preserves client-visible formatting
  from the current objective. A real post-fix Hermes two-tool continuation read
  the implementation, ran the same 5 tests, and returned exact
  `HERMES_MULTIFILE_EXACT_OK` with no extra text. It used 2 API calls, `10948`
  aggregate client-reported tokens, two Reasoner rounds, two tool results, and
  no pending tool IDs. This validates the one-line fix after a real Hermes tool
  loop without repeating the full file rewrite.
- Both direct development role servers and both loopback gateways were stopped.
  Ports 8102, 8103, and 19300 were closed, MemAvailable recovered to
  `69052440 kB`, production gateway/Executor remained active, and the Executor
  still reported context 65,536. No systemd unit or topology was changed.
- Production observation found gateway and Executor services active on tailnet
  port 9000 and loopback 8101, while the stored profile state said `stopped` and
  both targets reported inactive. The production worktree already contained six
  user-owned modifications before validation. This run did not alter them.

The Heavy Judge resume path was later physically exercised and passed. Later
Hermes recovery and review reruns also passed strict formatting, completing the
declared client rows. This is representative coverage, not a full cross-product.
OpenCode now covers its declared small read/edit, multi-file, architecture,
failure-recovery, and review rows. Hermes now covers normal, multi-step tool,
multi-file, failure-recovery, architecture, and review rows. Hermes architecture passed;
its correlated recovery passed the evidence/routing contract but failed exact
output formatting, and its review passed routing while also failing exact
formatting.
OpenCode architecture and evidence-bearing review now pass with the expected
real Planner/Reviewer and Codex OAuth Frontier paths. The controlled
same-task comparison and representative task coverage below jointly cover the
declared variants and task classes; they do not claim a full cross-product.

An additional isolated authenticated gateway used two temporary environment-
only tokens with IDs `opencode` and `hermes`. Both completed one
`dgx-moa-fast` request with HTTP 200; an unknown token returned 401. SQLite
grouping reported one request and 276 tokens for each safe ID. The token values
were not committed and are not production credentials.

### Limited Executor-only versus core comparison

Six isolated real requests compared `dgx-moa-fast` and `dgx-moa` on the same
Executor and three prompts. This is a small diagnostic, not the required full
representative evaluation.

| Variant | Simple | Retry-boundary | Architecture strict check | Median latency | All-agent tokens |
| --- | --- | --- | --- | ---: | ---: |
| Executor only | pass, 279.577 ms | pass, 347.055 ms | fail, 914.797 ms | 347.055 ms | 971 |
| Reasoner + Executor | pass, 4194.684 ms | pass, 11709.950 ms | fail, 16605.674 ms | 11709.950 ms | 7092 |

Executor-only agent totals were `289`, `327`, and `355`. Core totals including
the separately traced Reasoner were `1756`, `2471`, and `2865`. Thus this small
sample measured about 7.3 times as many tokens for the core. Both variants were
equally correct on the two exact tasks. The first architecture parser check
failed both. A direct repeat showed Executor-only returning the four required
keys as empty objects, while the core returned non-empty trust boundaries,
failure modes, migration steps, and test-plan content. That single qualitative
difference is insufficient to establish a quality benefit.

Measured conclusion: the Reasoner adds substantial latency and token cost on
trivial tasks, and the current sample does not yet demonstrate enough quality
gain to justify it across the required representative matrix. Keep
`dgx-moa-fast` explicit. Planner/Reviewer/Frontier and defect/claim metrics are
measured in the tables below; this limited table must not be read alone.

### Controlled seven-key security-boundary comparison

One fixed non-streaming task stated six gateway security defects and one
unsupported database risk, then required seven exact booleans. This isolates
routing and collaboration cost; it is not the required representative
multi-task evaluation. First-byte latency equals total latency because these
were non-streaming requests. No implementation or test execution was part of
the task, so test-pass rate is not applicable.

| Variant | Successful result | Exact criteria | Total latency | All-agent tokens | Retained caveat |
| --- | --- | ---: | ---: | ---: | --- |
| Executor only | yes | 7/7 | 1.439 s | 683 | baseline |
| Reasoner + Executor | yes | 7/7 | 38.746 s | 3,270 | no measured quality gain |
| Reasoner + Executor + Frontier | yes | 7/7 | 41.863 s | 21,149 | one earlier typed Reasoner 503 |
| Reasoner + Executor + Planner | yes | 7/7 | 124.271 s | 6,432 | one earlier truncated-routing 502 |
| Reasoner + Executor + Reviewer | yes | 7/7 | 126.501 s | 9,434 | pre-review schema failure; low confidence |
| Full relevant collaboration | yes | 7/7 | 125.950 s | 31,314 | all strict reviews valid |

Every successful final answer had acceptance coverage `7/7`, stated-defect
recall `6/6`, and unsupported-claim suppression `1/1`; no row had a tool
failure. The latest full row's local pre-Reviewer also recalled `6/6`. The
latest Reviewer-only row cannot claim Reviewer defect recall because its
pre-review artifact failed validation. The Codex OAuth CLI reported token use
but no billable price, so Frontier cost is recorded as unavailable rather than
inferred. With Planner and Reviewer simultaneously resident, a measured
pre-request host snapshot had `20309760 kB` MemAvailable and a post-request
snapshot had `19951464 kB`; these are noisy unified-memory observations, not
GPU-byte attribution.

Measured conclusion for this task: every variant was equally correct, while
the always-active Reasoner and each specialist path added substantial latency
and tokens. This row does not demonstrate enough quality improvement to justify
the added cost.

### Representative task coverage

The controlled security row supplies the same-task comparison across every
required agent variant. Existing real-client rows supply the other required
task classes without rerunning a 36-cell cross-product.

| Task class | Physical row | Outcome | Measured cost/evidence |
| --- | --- | --- | --- |
| Simple question | fast versus core diagnostic | both exact tasks passed | median 0.347 s / 971 tokens versus 11.710 s / 7,092 tokens across three prompts |
| Repository architecture | OpenCode Planner + OAuth Frontier | exact architecture marker; parallel specialists | 101.877 s; 29,261 all-agent tokens |
| Multi-file implementation | OpenCode core agent | exact marker; 3 files; 7/7 tests | 37,286 all-agent tokens; 5 tool results; 4 Reasoner rounds; 0 failures |
| Debugging/recovery | OpenCode orchestrated | exact marker after 2 expected failures | 18,308 all-agent tokens; 3 tool results; 2 Reasoner rounds; 1 recovery continuation |
| Code review | OpenCode Reviewer + OAuth Frontier | exact marker; independent parallel review | 991 Reviewer, 16,952 Frontier, and 4,052 final-Executor tokens reported |
| Security-sensitive change | full relevant collaboration | exact 7/7; defect recall 6/6; unsupported claim suppressed | 125.950 s; 31,314 all-agent tokens |

The multi-file final turn recorded downstream first byte at `29270.105` ms;
the recovery final turn recorded `36270.375` ms. Non-streaming security rows
have first-byte equal to total latency. Streaming behavior was independently
validated with native deltas and one `[DONE]`. Frontier cost remains unknown
because Codex OAuth reports tokens but no billable price; no price is inferred.
Only the implementation row has an applicable test pass rate. Tool failures
were zero except the two intentionally induced recovery failures; that task
needed one correction boundary. Memory evidence remains the simultaneous
Planner/Reviewer host snapshots recorded above.

Measured product conclusion: the Reasoner and specialists improved structure
on one architecture repeat, but did not improve exact correctness on the
controlled tasks enough to justify their latency and token cost. Keep
`dgx-moa-fast` available and treat `dgx-moa` default status as a product-policy
choice, not a benchmark-proven quality win.

## Environment

- `docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L`: exit `0`; detected NVIDIA GB10.
- `hf auth whoami`: exit `0`; authenticated.
- Required ports are unoccupied.

Gateway, resident systemd, model, integration, and profile evidence is recorded
below. Heavy-judge validation is appended after its first isolated startup.

## Executor Runtime

- vLLM startup: `435` seconds; readiness and `/v1/models` passed.
- Model memory: `44.31 GiB` reported by vLLM; measured available-memory drop
  `53276835840` bytes; remaining available memory `67773710336` bytes.
- Completion: `READY`; warm latency `0.103836927` seconds; `2` output tokens.
- Tool call: valid `read_file` call; ID `chatcmpl-tool-95e68c30eba02ec8`;
  arguments decoded to `/tmp/example.txt`; latency `0.828135645` seconds.
- Clean stop restored available memory to `122827276288` bytes.

## Reviewer Runtime

- First startup attempt failed: `Value error, The checkpoint you are trying to
  load has model type cohere2_moe but Transformers does not recognize this architecture.`
- vLLM `0.22.1` contains native `Cohere2MoeForCausalLM`; compatible HF config
  alias loaded all original MoE fields. `cohere_melody 0.10.0` installed per model card.
- Startup: `213` seconds; readiness and `/v1/models` passed.
- Structured result: `{"status":"approved","findings":[]}`; reasoning parsed separately.
- Latency: `4.041933448` seconds; `125` completion tokens; measured decode
  rate `30.925793709406964` tokens/second.
- Measured available-memory drop: `26989322240` bytes; remaining available
  memory `95837954048` bytes.
- Clean stop restored available memory to `121841950720` bytes.

## Planner Runtime

- Startup: `131` seconds; readiness and `/v1/models` passed.
- Strict plan JSON passed with one plan step, one acceptance criterion, and no tool call.
- A `256` token trial ended `finish_reason=length`; configured planner budget
  `1500` avoids that measured lower bound. `512` token trial completed in
  `6.963814218` seconds with `271` tokens.
- Measured decode rate: `38.91545516816371` tokens/second.
- Measured available-memory drop: `25925709824` bytes; remaining available
  memory `95916240896` bytes.
- Clean stop restored available memory to `122724655104` bytes.

## Resident Profile

- Executor + reviewer first passed with `45066366976` bytes available.
- Initial second-process trial failed before load because vLLM defaulted to
  `gpu_memory_utilization=0.92`; calibrated per-role values fixed the guard.
- First low-KV trial proved reviewer needs `0.66 GiB` for 8192 tokens; final
  reviewer and planner reservations are `750000000` bytes.
- Executor + planner + reviewer passed concurrently with all required context
  limits and `25814450176` bytes initially available.
- Final benchmark after integration: `25148334080` bytes available, exceeding
  required `20000000000` by `5148334080` bytes.
- `scripts/start-judge.sh` while resident active: exit `73`, exact output
  `resident role executor is running`.
- Current systemd resident target: executor, planner, and reviewer all active;
  final `/proc/meminfo` `MemAvailable` was `22406086656` bytes.
- Executor vLLM reported `17829` KV tokens at `16384` context; planner reported
  `59392` at `8192`; reviewer reported `8649` at `8192`.

## Gateway

- User systemd service active on `127.0.0.1:9000`.
- `/healthz`, `/readyz`, `/v1/models`, non-streaming, and streaming passed.
- Real gateway tool call ID `chatcmpl-tool-9f4743372a9de247` and JSON arguments
  survived planner/executor round trip.
- Real gateway tool-call latency: `11.151994731` seconds.
- Session `integration-tool` remained in SQLite after service restart.
- Measured gateway `/healthz` overhead: `0.000731` seconds.
- Bearer rejection, malformed tool call, timeout, HTTP 500, replay blocking,
  no-progress blocking, planner/reviewer/judge routing, rollback, redaction,
  compression, integrity, capacity, and completion gates have automated tests.

- Production-tailnet service check (`100.125.239.72:9000`) after main-branch
  runtime restart:
  - `POST /v1/responses` with `dgx-moa-orchestrated` and no `reasoner_mode`:
    `200`, completion success.
  - `GET /v1/responses?input=...`:
    `200` (response shim path works).
  - `GET /v1/responses` with missing `input`:
    `405 Method Not Allowed` (by design; query-only GET shim requires `input`).
  - `POST /v1/responses` with `metadata.reasoner_mode=required` now returns
    `200` after `reasoner` control transition to external mode (`control:
    external`, `unmanaged_roles` no longer includes reasoner).
  - `/v1/model-status` shows reasoner control as `external` and `unmanaged_roles`
    = `["judge"]` (previously included `reasoner`).

## Build And Tests

- `uv run ruff format --check .`: passed.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 18 source files.
- `uv run pytest -q`: `17 passed`, one third-party TestClient deprecation warning.
- `docker compose config -q`: passed.
- `docker compose build gateway`: passed; image
  `sha256:2a1f97eb4c54c6b5644621a3ace80ac15b9259410dcbb06cf5702b869fc3742b`.
- Targeted post-change tests: `11 passed`; Ruff and mypy passed after strict
  judge and context-tuner additions.
- Final `scripts/verify-models.sh executor reviewer planner`: all verified.
- Final incomplete-file scan under model root: zero files.

## Development Branch Validation

- Frontier foundation on `dev`: `codex --version` returned `codex-cli 0.144.1`.
  `codex exec --help` confirmed structured `--json`, `--output-schema`, and
  `workspace-write` sandbox support; App Server is experimental, so the bounded
  JSONL runner is selected. Official model documentation identifies GPT-5.6 Sol as
  `gpt-5.6-sol`; installed Codex configuration confirms
  `model_reasoning_effort = "high"`. Account entitlement remains unverified until
  a separate OAuth profile runs its smoke test.
  `scripts/codex-profile.sh status` reported `primary` and `secondary` as
  `authenticated=no`, `state=not_configured`; no OAuth profile directory or
  credential was created. Frontier provider, profile, worktree, immutable-baseline,
  human-approval, and cycle-limit tests passed locally; full suite was
  `78 passed` with one third-party TestClient warning.
- Primary OAuth smoke on `2026-07-11`: Codex started a `gpt-5.6-sol` High request
  from isolated `frontier/phase8-smoke` worktree. CLI returned its explicit usage
  limit before work began; this is `FRONTIER_USAGE_LIMIT`, not a profile failover.
- Secondary OAuth smoke first reached Codex schema validation and exposed an invalid
  `const`-only property in `frontier-result-v1.json`; corrected schemas now include
  required property types before retrying.
- Secondary OAuth retry authenticated `gpt-5.6-sol` with High reasoning and returned
  valid `frontier-result-v1` JSON from `frontier/phase8-smoke`, with no changed files.
  Status was `blocked`: Codex sandbox bubblewrap could not configure loopback
  (`RTM_NEWADDR: Operation not permitted`) before task inspection. Recorded as
  `FRONTIER_VALIDATION_FAILURE`; no profile rotation, merge, or deployment occurred.
- `uv run pytest -q`: exit `0`; `74 passed`, one third-party TestClient warning.
- `uv run ruff check gateway/src tests`: exit `0`.
- `uv run mypy`: exit `0`; `23` source files.
- `scripts/run-mvp-benchmark.sh`: exit `0`; `10/10` synthetic fixture tasks
  passed. Input/output token metrics are explicitly unknown (`null`); fixture
  repository identities are recorded in emitted traces.
- `scripts/validate-opencode-synthetic.sh`: OpenCode-compatible HTTP client
  covers read-only, one-file, multi-file, failure/recovery, reviewer correction,
  gateway restart persistence, tool-call identity, usage, and streaming. Physical
  remote OpenCode remains separately unverified.
- `scripts/mine-improvements.sh`, `scripts/evaluate-improvement.sh`,
  `scripts/build-training-dataset.sh`, and `scripts/export-agentic-traces.sh`:
  exit `0`.
- Re-run on `2026-07-11`: mining produced `IMP-2026-0001`; candidate comparison
  remained `not_recommended` with automatic merge false. Dataset build emitted
  10 Silver executor-SFT samples with train/validation/test split `3/5/2`.
- `systemd-analyze --user verify systemd/*`: exit `0`.
- Read-only user-service check on `2026-07-11`: gateway `/healthz` returned
  `200` on configured tailnet address `100.125.239.72:9000`; loopback is not
  configured for this gateway. `/readyz` returned `503` because profile state
  was `failed` after judge startup hit the 16 GiB headroom gate (`exit 70`).
  Rollback completed without intervention: executor, reviewer, and planner
  returned ready; gateway `/readyz` returned `200`; available memory was
  `23037333504` bytes.
- Real gateway read-only request, session `runtime-readonly-1783700774`:
  HTTP `200`, response `READY`, usage `356` prompt / `2` completion / `358`
  total tokens.
- Real tool continuation, session `runtime-tool-1783700822`: first HTTP `200`
  response preserved tool ID `chatcmpl-tool-a8fafd00dce4b44d` for
  `read_file("/tmp/dgx-moa-validation.txt")`, usage `678` prompt / `35`
  completion / `713` total. A normalized synthetic tool observation continued
  in the same session with HTTP `200`, no additional tool call, and
  `{"output":"validation fixture"}`; usage `629` prompt / `7` completion /
  `636` total tokens.
- `scripts/validate-opencode-loop.sh` against recovered resident services:
  exit `0`; session `opencode-loop-1783701252`; authenticated discovery,
  tool-result continuation, and streaming passed.
- Repeated resident OpenCode-compatible validation on `2026-07-11`:
  `scripts/validate-opencode-loop.sh` exit `0`; session
  `opencode-loop-1783736024`; tool-result continuation and streaming passed.
  `MemAvailable` immediately after was `22945952 kB`.
- Physical remote OpenCode read-only validation on `2026-07-11`: SSH alias `win`
  reached Windows host `Pocket4`, OpenCode `1.17.18`, and tailnet gateway
  `100.125.239.72:9000`. A temporary read-only project config allowed only
  `read`, `glob`, and `grep`; OpenCode emitted a real tool event and returned
  `README_PRESENT`. Gateway credential was piped over SSH only and neither stored
  nor logged. A one-file test was not accepted: its noninteractive OpenCode child
  did not exit, so the test-created PID and temporary fixture were removed.
- Bounded one-file rerun invoked the Windows `opencode.exe` directly rather than
  its npm shim. It changed the isolated fixture (`changed=true`) but retained a
  worker process and provided no final completion within the bounded run; that PID
  and fixture were removed. This is edit-path evidence only, not a completed
  one-file scenario.
- OpenCode `serve`/`run --attach` diagnostic: a loopback-only server reached
  readiness on Pocket4, but the attach client exited without submitting the task
  or changing the fixture. Server, temporary config, and fixture were removed.
- Consolidated `scripts/smoke-test.sh`: exit `0`; session
  `opencode-loop-1783728287`; tool continuation and streaming passed. The
  streaming check captures output before matching `[DONE]`, avoiding a
  `pipefail` false failure from `grep -q` closing its input early.
- Final read-only resident check: `/readyz` returned `200` with executor,
  planner, and reviewer ready; `MemAvailable` was `23184121856` bytes.
- Heavy Judge maintenance on `2026-07-11`: Mistral judge loaded in `603.49`
  seconds with the unchanged `4000000000`-byte KV reservation. vLLM measured
  `22192` KV tokens and `2.71x` concurrency at `8192` context; profile
  readiness had `18105536512` available bytes, above the unchanged 16 GiB
  safety gate. A strict `JudgeVerdict` smoke passed with `accept`, `low` risk,
  `completion_allowed=true`, zero resolved disagreements, and zero mandatory
  changes. Judge then stopped and resident was restored; final gateway
  `/readyz` returned `200` with `23834812` KiB available. No model, unit,
  headroom, resident-context, or trace setting was changed.
- Raw SSE protocol capture on `2026-07-11`: real resident gateway normal,
  tool-call, and tool-result continuation streams each ended `data: [DONE]`
  followed by HTTP EOF. Their final finish reasons were respectively `stop`,
  `tool_calls`, and `stop`; no stale `tool_calls` finish reason or post-DONE
  usage was observed. Artifact: `data/diagnostics/opencode-completion/`
  `opencode-sse-48850860-c3a6-4a69-a5b2-9234f0758417.json`.
- Physical OpenCode completion differential on `2026-07-11`: direct Windows
  `opencode.exe` `1.17.18` invocation with an explicit isolated `--dir` completed
  the one-file scenario against both the resident gateway and a temporary
  loopback-only fake server. Both runs emitted `write`, `tool-calls`, continuation
  text `WORKER_DONE`, final `stop`, created `COMPLETION.txt` with `DONE`, and
  exited `0`. The fake B server was stopped and all temporary processes and
  fixtures were removed. This does not reproduce a gateway protocol or OpenCode
  completion-lifecycle defect. Artifact:
  `data/diagnostics/opencode-completion/opencode-physical-20260711.json`.
- Completion lifecycle re-validation on `2026-07-12`: after deploy fast-forward
  and resident restoration, raw gateway normal, tool-call, and continuation SSE
  streams recorded `stop`, `tool_calls`, and `stop` respectively, each followed
  by `[DONE]`, HTTP EOF, and a matching `stream_completed` gateway timestamp.
  Artifact: `data/diagnostics/opencode-completion/`
  `opencode-sse-d656ffdc-ca38-4340-b9eb-d2b79445ae4f.json`.
- Bounded physical OpenCode acceptance on `2026-07-12`: Pocket4 OpenCode
  `1.17.18` ran direct `opencode.exe` with explicit isolated `--dir`; PowerShell
  parent PID `3544` started run-owned OpenCode PID `35868`. It emitted
  `tool-calls`, then continuation final `stop` in session
  `ses_0ae328bf5ffeCrrWy7hFprQjIN`, wrote `COMPLETION.txt` as `DONE`, and
  exited `0`. Child snapshots observed `opencode.exe` and `conhost.exe` during
  the run; after final SSE the run-owned child list was empty. The fixture and
  all run-owned processes were removed. Artifact:
  `data/diagnostics/opencode-completion/`
  `opencode-physical-59a5d08a-e1d0-4b56-aacf-53801cb86471.json`.
- Final live loop checks on `2026-07-12`: `scripts/validate-opencode-loop.sh`
  passed session `opencode-loop-1783783547`; `scripts/smoke-test.sh` passed
  session `opencode-loop-1783783550`; gateway `/readyz` returned `200` with
  executor, planner, and reviewer ready.
- Post-resolution fixed ten-task benchmark: `scripts/run-mvp-benchmark.sh`
  passed `10/10`, task success rate `1.0`, route distribution `3/6/1`
  fast/standard/escalation, tool calls per successful task `1.2`, and time per
  successful task `0.0311096` seconds. Its trace inspection found `10` JSONL
  files with `24` indexed `failure_classified` events. The bounded improvement
  evaluation again selected `REPEATED_ACTION` (one fixture) but returned
  `not_recommended`, `0.0%` reduction, and automatic merge `false`; no candidate
  was applied.

## Tailscale

- Attempted `tailscale serve --bg http://127.0.0.1:9000`.
- Blocker: `Serve is not enabled on your tailnet.`
- Enable URL: `https://login.tailscale.com/f/serve?node=ngaf9Ptc8f11CNTRL`.
- Funnel was never enabled or used.

## Production Baseline Stabilization — 2026-07-12

- Starting `dev` commit: `5760c6bab0c48766441e6245e13401b69569bfb8`.
- Logging semantics v2 adds strict runtime provenance, durable session
  trajectories, linked agent decisions/tool executions/evaluations, typed failure
  attribution and resolution, explicit training eligibility, date-partitioned
  JSONL, SQLite trace indexing, and primary/secondary persistence policy tests.
- Legacy v1 remains readable and classified `legacy`; it is excluded from
  completeness claims and automatic training export.
- Final automated run before documentation: `96 passed`, one upstream
  Starlette/httpx deprecation warning. Ruff format/check and MyPy passed.
- Fixed synthetic benchmark passed `10/10`, task success `1.0`, routes
  fast/standard/escalation `3/6/1`, tool calls per success `1.2`. Its ten v2
  traces audited `10/10`, `100%`, with no missing fields or lifecycle events.
- Improvement mining excluded the benchmark's synthetic injected failures and
  returned `no_actionable_failure`; no candidate cycle was started.

### Real OpenCode staging

- Local OpenCode `1.17.18` ran against the direct tailnet gateway using disposable
  Git fixtures. The required ten-session distribution was read/repository analysis
  `3`, small edit `3`, multi-file `2`, failure recovery `1`, and bounded engineering
  `1`.
- Required-session outcomes were 6 completed and 4 failed. The failed read,
  two multi-file tasks, and bounded-engineering task reached the explicit
  180-second harness bound and/or failed fixture validation; none was deleted or
  reclassified as successful.
- An earlier calibration task completed in OpenCode but failed harness finalization
  because OpenCode supplied its own `ses_*` gateway ID. The failure was retained;
  the harness now discovers that real ID from OpenCode JSONL. A stream-finalizer
  race and bytes-on-timeout path were also fixed and regression-tested.
- Validation partitions audited 11/11 staging/calibration sessions and 2/2
  review/blocked sessions at `100%` applicable mandatory completeness, including
  completed, failed, and blocked terminal records.
- Controlled no-progress session `blocked-soak-1783826633` returned HTTP
  `200`, `200`, then `502`; it was finalized `blocked` with expected
  `NO_PROGRESS` attribution so it cannot pollute active mining.

### Review and runtime behavior

- A real reviewer flow first returned HTTP `502` because North followed raw task
  or observation text (`READY`) rather than the structured verdict schema. The
  diagnostic failure was preserved with context attribution and resolving commit.
- The fixed prompt removes raw objectives from reviewer/judge contexts and ends
  with a literal JSON-only output boundary. Exact real-model replay returned
  `{"status":"approved","findings":[]}`. A full updated FastAPI path using the
  real planner, executor, and reviewer returned HTTP `200`, a structured rejected
  verdict, phase `correction`, and blocked completion. Its trace audited `1/1`,
  `100%`.
- Controlled resident restart exposed reviewer CUDA initialization failures and a
  planner readiness sample below the unchanged 20 GiB startup gate. Rollback was
  preserved. A configurable 10-second unified-memory settle delay was added;
  clean prestart measured `123138887680` bytes and the final resident restoration
  succeeded without changing models, KV, contexts, units, or headroom criteria.
- Gateway was failure-restarted to load validation code; SQLite continuation state
  remained available. The final resident target/profile is ready and gateway
  `/readyz` returns `200`.

### Bounded soak

- Memory monitor window: epoch `1783799804` through `1783826671`, duration
  `26867` seconds (`7h 27m 47s`), `5370` samples.
- Minimum observed `MemAvailable`: `20783300608` bytes; maximum:
  `123198304256` bytes.
- The window covered actual OpenCode work, idle periods, gateway restart,
  resident restart and rollback/recovery, real tool continuation, review flow,
  one explicit block, and trace archive reads/writes.
- SQLite state errors: `0`; trace archive errors: `0`; observability degradation:
  `0`. Startup/backend and profile rollback incidents remain visible in journald
  and runtime status rather than being erased.
- This is a bounded soak, not a 24-hour stability claim. The 24-hour observation
  state is pending.

### Deferred physical checks

- Heavy Judge was not reloaded: Judge code, model, KV reservation, context, and
  profile architecture did not change; the prior physical structured-verdict and
  resident-restoration evidence remains authoritative.
- Pocket4 physical completion was not rerun: OpenAI serialization and tool-result
  continuation behavior did not change; the prior OpenCode `1.17.18` completion
  baseline remains authoritative.
- Frontier remains connected but disabled for the recorded host bubblewrap
  capability failure. No AppArmor, networking, sandbox, or OAuth rotation change
  was made.

### Final command pass

- `uv run pytest -q`: `96 passed`, one upstream deprecation warning.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
  `systemd-analyze --user verify systemd/*`, and shell syntax checks: exit `0`.
- `scripts/validate-opencode-loop.sh`: session `opencode-loop-1783828819`,
  tool continuation and streaming passed.
- `scripts/smoke-test.sh`: session `opencode-loop-1783828822`, tool continuation
  and streaming passed.
- Final fixed benchmark: `10/10`, success `1.0`, routes `3/6/1`, tool calls per
  success `1.2`, time per success `0.0420419` seconds; trace audit `10/10`, `100%`.
- Final direct tailnet `/healthz`, `/readyz`, and authenticated `/v1/models`
  passed; only `dgx-moa-agent` is exposed. Resident target/profile and all three
  role services are ready. tmux `dgx-opencode` remains active on OpenCode `1.17.18`.
- Post-finalizer regression: `opencode-loop-1783829101` and
  `opencode-loop-1783829104` both passed continuation and streaming; their main
  and stream sessions finalized completed. The full July 12 validation partition
  then audited `10/10`, `100%`, with zero missing fields or events.

### Multiple tool-call regression

- Gateway regression tests preserve two valid executor tool calls and attribute
  each tool result to its matching call ID.
- OpenCode `1.17.18` session `ses_0ab465307ffetVHiBQf40HnwFn` completed against
  the updated gateway with two `read` calls in one assistant message. Gateway
  state recorded one structured decision containing both calls; OpenCode exited
  `0`, fixture validation exited `0`, and finalization exited `0`.
- `uv run pytest -q`: `98 passed`, one upstream Starlette/httpx deprecation
  warning. Ruff format/check and MyPy passed.

### Context overflow regression

- OpenCode `1.17.18` session `ses_0ab2dda76ffeKbk9p2yiJ2SSmY` exposed the
  executor limit: at least `15385` input plus `1000` requested output tokens
  exceeded the configured `16384` context. The streaming gateway had already
  returned HTTP `200`, so the upstream `400` surfaced as a connection reset.
- The gateway now bounds structured tool content and reused stdout/stderr across
  the retained window, and opens the upstream stream before returning HTTP
  headers. Successful stdout containing words such as `failed` is no longer
  classified as a failed action.
- OpenCode session `ses_0ab28024effe7ILeEx30RyB72q` read eight 353-line files,
  then completed the same conversation with `CONTEXT_DONE`, `12426` input and
  `22` output tokens, `finish_reason=stop`, and HTTP `200` without a reset.
- `uv run pytest -q`: `102 passed`, one upstream Starlette/httpx deprecation
  warning. Ruff format/check and MyPy passed.

### Runtime context calibration

- Executor candidates `24576/750000000`, `20480/600000000`, and
  `18432/525000000` each had enough measured KV tokens but failed the required
  three-cycle resident startup criterion when reviewer or planner CUDA context
  allocation returned OOM. The stable selection remains `16384/500000000`.
- Runtime `main@d8b4708` was cleanly restarted with the selected baseline. All
  resident roles became ready with `23362560000` bytes available; executor
  five-request and near-limit probes passed in `5.863` seconds.
- OpenCode `1.17.18` continued large-history session
  `ses_0ab28024effe7ILeEx30RyB72q` against the deployed gateway and returned
  `RUNTIME_DONE`, `12636` input and `23` output tokens, `finish_reason=stop`,
  and HTTP `200`.

### OpenCode title-request isolation

- OpenCode session `ses_0aab526deffeBz5wMjmBm3MPmd` first sent the automatic
  `Generate a title for this conversation` request with the work session ID.
  Gateway state consequently retained that title request as the objective, and
  later work requests stopped after title-oriented tool loops despite HTTP `200`
  and `finish_reason=stop`.
- Title requests now use an internal `<session-id>:title` state key while the
  client continues to receive its original session ID. The API regression sends
  a title request followed by `Create AGENTS.md` with the same client session ID
  and verifies their objectives remain isolated.
- `uv run pytest`: `103 passed`, one upstream Starlette/httpx deprecation
  warning. `uv run ruff check gateway/src tests` and `git diff --check` passed.
- A temporary loopback staging gateway using the resident executor received a
  title request and then `Create AGENTS.md` with client session
  `physical-title-isolation`. Its SQLite state recorded
  `physical-title-isolation:title` with the title objective and
  `physical-title-isolation` with `Create AGENTS.md`; the title response stopped
  normally. The staging process was then stopped and its temporary state removed.
- After PR `#6` merged, production `main@eeb4484` was restarted and resident
  readiness returned `200`. The authenticated production sequence
  `production-title-isolation-1783844401` recorded the title objective only in
  its `:title` state and `Create AGENTS.md` in the work state; both requests
  returned HTTP `200`.

### Resident guard recovery and Hermes compatibility

- On 2026-07-12, planner completed model startup but its post-start guard
  rejected `21415972864` available bytes against a `21474836480`-byte threshold.
  The planner stopped and OpenCode received gateway `502` responses. PR `#8`
  aligned role and resident guards with the documented `20000000000`-byte
  requirement; planner then started successfully and `/readyz` returned `200`.
- An authenticated Hermes-compatible OpenAI streaming request without a custom
  session header returned content chunks, `finish_reason=stop`, and `[DONE]`.
- Live read-only routing audit on 2026-07-12: no configured or locally present
  model matched `VibeThinker` or `Hermes`. The resident 21,562 MiB GPU process
  was the planner, `cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit`; the executor
  and reviewer used 47,009 MiB and 19,753 MiB respectively. Since the current
  resident startup, 34 planner requests returned HTTP 200, while 3 executor
  requests returned HTTP 200 and 30 returned HTTP 400. Every inspected session
  selected the standard route and recorded planner then executor; reviewer had
  no chat-completion request. The executor failures measured 15,385 prompt
  tokens plus the configured 1,000 output tokens, exceeding its 16,384-token
  limit. This is an operational observation, not a benchmark.

### VibeThinker reasoner integration preparation

- On 2026-07-12, the development worktree downloaded and verified
  `WeiboAI/VibeThinker-3B@77bd2cced09193c8b9a59a32bd8577bbd1f3e01c` at
  `/home/kotori9/models/dgx-moa/reasoner`: two safetensors shards,
  `6188996125` bytes, valid tokenizer/chat template, and no incomplete files.
  This is a model-integrity check only; the production services were not
  restarted and no resident 65,536-context readiness or capacity result is
  claimed.

### 65,536-context resident candidate rejection

- On 2026-07-12, candidate `9929115` ran from the production runtime worktree
  with `runtime_channel=dev` and `trace_origin=validation`; it was not merged.
  Executor, reviewer, and planner each started at `65536` and reported,
  respectively, `78748`, `175790`, and `140174` GPU KV tokens. Their measured
  maximum 65,536-token concurrency values were `1.20x`, `2.68x`, and `2.14x`.
- The resident profile was rejected before VibeThinker could start: planner's
  post-start guard measured `17965121536` available bytes, below the then-current
  `20000000000`-byte safety minimum, and exited `70`. The guard was not
  weakened. Stable `main` was restored with executor `16384`, planner/reviewer
  `8192`, authenticated tailnet health, model discovery, and `/readyz` all
  returning success. This is a failed capacity validation, not a performance
  benchmark.

- On 2026-07-13, explicit operator approval changed the resident startup floor
  to `10737418240` bytes (10 GiB). The 65,536-context candidate is retested
  under that floor; kernel OOM or a lower measured value remains a rejection.

### 65,536-context 10-GiB-floor retry rejection

- On 2026-07-13, candidate `41bfba1` started all four resident roles at
  `65536`: executor `67121`, reviewer `67383`, planner `83740`, and
  VibeThinker reasoner `66448` GPU-KV tokens (each at least `65536`). The
  post-start guards recorded, in role order, `67721474048`, `46267162624`,
  `22638268416`, and `12540280832` available host-memory bytes. The initial
  full start therefore passed the explicit `10737418240`-byte floor.
- A required dependency recycle exposed an unstable result: the reviewer's
  first CUDA initialization returned `torch.AcceleratorError: CUDA error: out
  of memory` and systemd retried it successfully, but the reasoner's next
  post-start guard measured `10208575488` bytes, below the 10-GiB floor by
  `528842752` bytes. Its guard stopped the service before accepting the
  profile. No kernel panic, host restart, or host-OOM event was observed;
  direct kernel-log access was unavailable to the unprivileged service user.
- The candidate is rejected because it cannot consistently meet the approved
  10-GiB guard. It was not merged or deployed. The production worktree was
  returned to `main`; baseline resident recovery is in progress. This is a
  capacity/safety validation result, not a benchmark.

### Codex multi-agent activation check

- On 2026-07-13, `primary` and `secondary` Codex OAuth profiles were present
  and the installed CLI was `0.144.1`. The profile test was updated for that
  CLI by removing its unsupported `--ask-for-approval` argument and requiring
  a JSON `turn.completed` event.
- Both real read-only test invocations returned HTTP `401` with
  `token_invalidated` / revoked refresh-token errors. No task was accepted or
  changed. Frontier configuration is enabled and retains independent profile
  workers, but interactive OAuth re-login is required before either agent is
  usable.

### 64K three-role resident validation

- On 2026-07-13, candidate `4b2fe2b` excluded VibeThinker from the resident
  target while retaining it as an optional configured model. Executor,
  reviewer, and planner started at `65536` and reported `67121`, `67383`, and
  `83740` GPU-KV tokens. Their post-start host-memory measurements were
  `68723949568`, `42841587712`, and `18525147136` bytes, above the approved
  5-GiB floor.
- The authenticated gateway request `resident64k-no-reasoner-*` returned HTTP
  `200` and `finish_reason=stop`. Its decision events were planner then
  executor; no `reasoner_completed` event was written. The reviewer required
  one systemd CUDA-OOM retry before becoming ready; no kernel panic or host-OOM
  event was observed.

### OpenCode title-history recovery

- OpenCode can send its automatic title prompt after the work-message history.
  The former single-user-message detection stored that title as the work-session
  objective, causing the model to complete a title and exit its loop.
- Production sequence `title-history-1783851856` confirmed that a trailing title
  prompt now uses only `:title` state while `Create AGENTS.md` remains the work
  objective. All resident roles and `/readyz` were active after deployment.

### Codex multi-agent activation

- On 2026-07-13, interactive OAuth re-login was followed by separate read-only
  `primary` and `secondary` Codex calls using `gpt-5.6-sol`. Both returned an
  agent message of `READY` and a JSON `turn.completed` event. The profile test
  now requires that completion event, so an expired token cannot be reported
  as healthy. No sandbox or systemd hardening was weakened.

### Hermes current-objective and context discovery regression

- A live Telegram turn on 2026-07-13 sent 124 history messages without a stable
  gateway session header. The gateway created a new state for each provider
  call and selected the oldest user message, `모델 변경완료`, as every objective.
  Hermes made at least 24 provider calls in that turn and issued three unrelated
  model-change clarification calls. The reviewer endpoint received zero chat
  completions during the observed streaming turn.
- The gateway model-discovery response omitted a context field, so Hermes logged
  a 256,000-token fallback despite the deployed 65,536-token limit.
- `uv run pytest -q` passed `110` tests; Ruff and MyPy passed. A loopback staging
  request containing an old model-change message and the latest context-analysis
  request returned HTTP `200`, `finish_reason=stop`, advertised `65536`, and
  persisted the latest context-analysis request as its objective. Its measured
  decision roles were planner then executor.
- The first streaming-review candidate invoked reviewer EngineCore PID `1459380`
  but passed raw SSE as evidence; the reviewer exhausted its structured response
  path and recorded `review_failed: ValueError`. The executor stream still ended
  normally. Passing only the reconstructed assistant content removed that noise.
- The corrected physical streaming request returned HTTP `200`, preserved
  `STREAM_REVIEW_OK` and `[DONE]` in its 1,484-byte SSE response, and recorded
  planner, executor, then reviewer decisions followed by `review_completed` and
  `stream_completed`. The reviewer rejected this synthetic response with the
  route's three missing-metadata findings; this validates invocation and protocol
  completion, not review quality.
- Production session `production-stream-review-1783915400` then recorded
  planner, executor, and reviewer decisions, an approved reviewer result with no
  findings, `finish_reason=stop`, and `stream_completed`. Resident readiness was
  HTTP `200` with executor, planner, and reviewer ready; reasoner and judge stayed
  stopped.

### Phase-one physical streaming-buffer baseline

- On 2026-07-18, clean development commit `0b83e18` was measured against the
  read-only production reference `c2a9af0`. Installed versions were vLLM
  `0.22.1`, OpenCode `1.17.18`, and Hermes Agent `0.18.2`. Production gateway,
  executor, planner, and reviewer user services were all inactive and their
  ports were unbound before the isolated run.
- Controlled foreground model processes used loopback ports `8101`, `8102`, and
  `8103`. The isolated gateway used `127.0.0.1:19000`, SQLite path
  `/tmp/dgx-moa-phase1.6roKBd/state/gateway.db`, trace root
  `/tmp/dgx-moa-phase1.6roKBd/traces`, and run root
  `/tmp/dgx-moa-phase1.6roKBd/data/run`. No production service or production
  worktree was changed.
- The first foreground model launch failed before model loading because the
  shared settings validator required a gateway API key. The retry used a new
  isolated validation credential supplied only through the process environment;
  no credential was written or recorded.
- The executor's default FlashInfer-CUTLASS path began a first-run SM121a build
  containing 96 object targets. After 9 targets, that diagnostic process was
  stopped because the kernel build was unrelated to gateway buffering. The same
  physical executor model was restarted with vLLM's supported `MARLIN` MoE
  backend, already exercised by the reviewer runtime. Its model load took
  `245.521061` seconds. This override is diagnostic evidence, not a production
  backend selection.
- One authenticated streaming request asked for twenty numbered lines with
  `max_tokens=1000`. Monotonic timestamps in nanoseconds were request accepted
  `1230195082686135`, planner start `1230195118466714`, planner complete
  `1230219591415785`, executor start `1230219596688357`, executor first byte
  `1230221185713404`, executor complete `1230228218239311`, reviewer start
  `1230228225083613`, reviewer complete `1230262583974904`, downstream first
  byte `1230262588265733`, and downstream completion `1230262595932885`.
- Derived durations were planner `24.472949071` seconds, executor first-byte
  latency `1.589025047` seconds, executor total `8.621550954` seconds, reviewer
  `34.358891291` seconds, and downstream first-byte latency `67.505579598`
  seconds from request acceptance. The downstream first byte followed the
  executor first byte by `41.402552329` seconds and followed reviewer completion
  by only `0.004290829` seconds. This proves full executor buffering behind the
  reviewer.
- Final client status was HTTP `200`; the response contained `62174` SSE bytes
  and exactly one `[DONE]`. This is a defect reproduction and timing baseline,
  not a throughput or quality benchmark.

### Phase-one isolated post-fix validation

- On 2026-07-18, development commit `0d95591` was validated against the
  unchanged production reference `c2a9af0`. The production worktree was clean
  on `main`; all production gateway/model units and targets were inactive, and
  ports `8101`, `8102`, `8103`, `8104`, `8110`, `9000`, and `19000` were
  unbound before the run.
- The pre-runtime gates reported `180 passed, 1 warning in 2.27s`, `48 files
  already formatted`, Ruff `All checks passed!`, MyPy success for 26 source
  files, clean systemd verification, clean shell syntax, and clean
  `git diff --check`. The warning was the existing Starlette TestClient
  deprecation. The repository trace audit exited `1`: 10 sessions, 4 complete,
  6 incomplete/legacy, and 40.0% mandatory-field completeness. The six missing
  records were `legacy_v1`; ignored root records with duplicate session IDs
  sort after and shadow the corresponding nested v2 records.
- The isolated root was `/tmp/dgx-moa-phase1-post.ahMvu6`, with separate
  `state/gateway.db`, `traces`, `data/run`, and `logs` paths. The gateway bound
  only `127.0.0.1:19000`; physical models bound only loopback `8101`, `8102`,
  and `8103`. A fresh API credential existed only in the supervisor process
  environment and was unset when that process exited.
- Controlled process groups were executor `3896715`, reviewer retry `3915544`,
  planner `3921619`, timed gateway `3973021`, and temporary tailnet relay
  `3985247`. The executor used the same diagnostic vLLM `MARLIN` MoE backend as
  Task 0. It advertised maximum model length `65536`; reviewer and planner also
  advertised `65536`.
- Executor checkpoint loading took `606.69` seconds. The first reviewer start
  failed before weight loading with CUDA `cudaMemGetInfo` out-of-memory; its
  log was retained, memory was allowed to settle, and the unchanged retry loaded
  four shards in `196.34` seconds and became ready. Planner then became ready.
  All three real model endpoints were concurrently healthy before client tests.

#### Generic OpenAI-compatible clients

- Authenticated `/v1/models` returned, in order, `dgx-moa-chat`,
  `dgx-moa-agent`, and `dgx-moa-orchestrated`, each with
  `context_length=65536`.
- Curl non-streaming chat session `physical-curl-nonstream` returned HTTP `200`,
  natural content `CHAT_OK`, completion ID `chatcmpl-9051f38c1b87592a`,
  `finish_reason=stop`, and usage `260/3/263`. Persisted policy was
  `chat/plain_chat`, requiring and recording only executor.
- Curl streaming agent session `physical-curl-stream` returned HTTP `200`,
  content `STREAM_OK`, `1029` bytes, completion ID
  `chatcmpl-9cacc35b31422f23`, and exactly one `[DONE]`. Persisted policy was
  `agent/native_agent_turn`, requiring and recording only executor.
- The official OpenAI Python client `2.6.1`, using no project metadata, returned
  HTTP `200`, `OPENAI_OK`, completion ID `chatcmpl-b55b4713f2a48802`, session
  header `99e087e8-2c49-4ce6-9699-adac639e2d74`, `finish_reason=stop`, and usage
  `260/4/264`. Its state was executor-only.
- A minimal HTTPX `0.28.1` streaming consumer, also without project metadata,
  returned HTTP `200`, `HTTPX_OK`, `1252` bytes, and exactly one `[DONE]` in
  session `2ad4d7f0-5e41-49fc-8af6-e649d8d01242`. Its first raw byte was at
  monotonic nanoseconds `1245245784681732`, completion was
  `1245245866156559`, and elapsed time was `285.885` milliseconds. Its state
  was `chat/plain_chat`, executor-only.
- Native tool session `physical-tool-loop` first returned exactly one
  `read_file` call with ID `chatcmpl-tool-b6f42439d220f9ab`, arguments
  `{"path":"/tmp/dgx-moa-physical.txt"}`, and `finish_reason=tool_calls`.
  A standard tool-result continuation preserved that ID and returned
  `PHYSICAL_TOOL_RESULT` in natural assistant content with
  `finish_reason=stop`. Both decisions were executor-only.
- Explicit orchestrated session `physical-orchestrated` returned HTTP `200`,
  `ORCHESTRATED_OK`, completion ID `chatcmpl-971a44e0da6ad77e`, and elapsed
  time `54.364` seconds. State recorded planner `14815.343` ms, executor
  `322.505` ms, reviewer `39178.55` ms, and an approved review. This is the
  explicit orchestration path, not an ordinary-client dependency.
- Negative requests returned these complete OpenAI error envelopes; the first
  three were re-captured against the CPU-only follow-up gateway and matched the
  original physical run:

  ```text
  HTTP 404 {"error":{"message":"unknown model","type":"invalid_request_error","code":"model_not_found","param":"model"}}
  HTTP 422 {"error":{"message":"tool_choice requires tools","type":"invalid_request_error","code":"invalid_request","param":null}}
  HTTP 401 {"error":{"message":"invalid bearer token","type":"authentication_error","code":"invalid_api_key","param":null}}
  HTTP 502 {"error":{"message":"All connection attempts failed","type":"backend_error","code":"backend_error","param":null}}
  ```

  The HTTP `502` was the retained orchestrated request after only the controlled
  planner group was stopped; it is distinct from the measured timeout below.

#### Exact post-fix streaming measurement

- The preserved Task 0 timing wrapper initially returned HTTP `500`, 21 bytes,
  and no DONE because Task 6 added `timeout_seconds` keywords to
  `Provider.stream()` after that wrapper was written. The retained exception was
  `TypeError`; an ignored validation-only wrapper was updated to forward the
  new keywords without changing gateway source.
- The successful session `physical-streaming-postfix-retry` used the exact Task
  0 prompt, `Write exactly twenty short numbered lines about reliable APIs.`
  Raw monotonic nanoseconds were request accepted `1245752311438712`, executor
  start `1245752342543874`, executor first byte `1245752523408335`, downstream
  headers `1245752524396351`, downstream first byte `1245752524595631`, executor
  complete `1245759218474816`, and downstream complete `1245759226444430`.
- Derived durations were executor start `0.031105162` seconds after acceptance,
  executor first-byte latency `0.180864461` seconds, executor first byte
  `0.211969623` seconds after acceptance, one-event transport overhead
  `0.001187296` seconds, executor total `6.875930942` seconds, downstream first
  byte `0.213156919` seconds after acceptance, and downstream total
  `6.915005718` seconds. The client received its first byte
  `6.693879185` seconds before executor completion; final forwarding finished
  `0.007969614` seconds after executor completion.
- Final status was HTTP `200`, `59652` bytes, and exactly one `[DONE]`.
  Persisted state was `agent/native_agent_turn`, with executor as the only
  required and recorded role, `finish_reason=stop`, and no truncation. Reviewer
  was absent from both state and the critical path.

#### Real HTTP executor-first-byte timeout

- A follow-up used no GPU model. A fresh root
  `/tmp/dgx-moa-timeout.uVbS91` contained state, trace, run, model-placeholder,
  and log paths. A real CPU-only OpenAI-compatible provider bound
  `127.0.0.1:19101`; the real gateway bound `127.0.0.1:19100` with
  `executor_first_byte_timeout_seconds=0.25` and the slow provider as its only
  executor. Production remained inactive and ports `9000`, `19100`, and
  `19101` were free before startup.
- The first gateway launcher, `uv run python -m dgx_moa.api`, exited without
  binding because `api.py` defines the console `main()` but no module
  `__main__` call; its empty log was retained. The retry used the declared
  `uv run dgx-moa` console entry point and bound normally. This failed harness
  attempt did not reach a request.
- Session `physical-executor-first-byte-timeout` sent an authenticated standard
  streaming request. The slow provider accepted the HTTP POST, returned HTTP
  `200` headers, and logged `stream=true`, model `timeout-executor`, and
  monotonic nanoseconds `1248155177768646`; it deliberately slept before its
  first SSE byte. The gateway cancelled that stream at `1248155425595592`,
  proving a first-byte timeout after connection and request acceptance rather
  than connection refusal.
- Client monotonic bounds were `1248154882995579` through
  `1248155487226164`. The gateway returned this complete HTTP response before
  starting SSE:

  ```text
  HTTP/1.1 504 Gateway Timeout
  date: Sat, 18 Jul 2026 03:40:28 GMT
  server: uvicorn
  content-length: 126
  content-type: application/json

  {"error":{"message":"executor_first_byte timed out","type":"timeout_error","code":"executor_first_byte_timeout","param":null}}
  ```

- SQLite state was `agent/native_agent_turn`, executor-only. Its single
  `request_timing` event recorded
  `stage_status={"executor_first_byte":"timed_out"}` and milliseconds
  `accepted=0.0`, `upstream_start=8.139`, `executor_total=257.988`,
  `first_downstream_byte=266.133`, and `completed=266.135`. The trace at
  `traces/dev/validation/2026-07-18/physical-executor-first-byte-timeout.jsonl`
  preserved the same timing metrics, task `TASK9-TIMEOUT`, workspace identity,
  executor decision, and `final_status=degraded`.
- The isolated one-session trace audit still exited `1`: its fields were
  complete, but `session_ended` was absent. Teardown stopped only gateway PGID
  `4026366` and provider PGID `4025162`; both ports were unbound, the
  environment-only credential was unset, memory was unchanged, production
  units remained inactive, and the production worktree remained clean.

#### Real OpenCode and Hermes clients

- Real OpenCode `1.17.18` ran through its documented `opencode run --pure
  --auto --format json --dir ... --model dgx-moa/dgx-moa-agent` interface from
  explicit isolated working directories. Its first normal attempt returned
  API HTTP `400` because a temporary config without a model `limit.output`
  caused the client to request more than the server cap of `16384`. Adding the
  documented temporary `limit: {context: 65536, output: 16384}` fixed the
  client configuration without changing repository source.
- OpenCode normal session `ses_08cd07ec3ffeHhZ6FnUz8r3GUQ` exited `0` with
  `OPENCODE_OK`, `finish_reason=stop`, and usage total/input/output
  `2824/2820/4`. Tool session `ses_08ccfe27effefpBnhcFEKpr03N` exited `0`,
  invoked native `read` call `call_ebb54446c04947f9bcfd77b4` on the isolated
  `FIXTURE.txt` with exact client input
  `{"filePath":"/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/FIXTURE.txt"}`,
  received `OPENCODE_PHYSICAL_FIXTURE`, and continued with
  `OPENCODE_TOOL_OK`. The gateway access log recorded HTTP `200` for both normal
  POSTs and all three tool-session POSTs. Normal state recorded request stream
  flags `[true,true]` and two `stream_completed` events; tool state recorded
  `[true,true,true]` and three `stream_completed` events, plus
  `tool_result_received`, `tool_execution_recorded`, and executor-only roles.
- Real Hermes Agent `0.18.2` (`2026.7.7.2`, upstream `d9ee3424`) used its
  documented one-shot CLI, `provider: custom`, environment-expanded
  `model.api_key`, model `dgx-moa-agent`, and the direct tailnet URL
  `http://100.125.239.72:9000/v1`. The environment reference prevented any
  credential from being stored. A controlled foreground TCP relay bound only
  `100.125.239.72:9000` after port 9000 and production inactivity were proved;
  it forwarded only to the isolated loopback gateway and was removed first at
  teardown. No Tailscale Serve, systemd, or production configuration changed.
- Hermes attempt one reached the endpoint but returned `HTTP 401: invalid bearer
  token`: version 0.18.2 deliberately host-gates `OPENAI_API_KEY` away from
  unrelated custom hosts and used its no-key placeholder. The retained retry
  used the documented `${DGX_MOA_API_KEY}` config reference. Normal session
  `20260718_121450_52e9b9` then exited `0` with `HERMES_OK`, one API call, and
  usage `3112/4/3116` input/output/total. Gateway state
  `7d5d40fd-f402-4a18-833f-c6caa9aaca2e` recorded `stream=true`, one
  `stream_completed`, and `finish_reason=stop`.
- Hermes tool session `20260718_121544_04de50` exited `0` with two API calls.
  Its exported transcript recorded native `read_file` call
  `call_b93806e12d814d80baa71f38` with arguments
  `{"path": "/tmp/dgx-moa-phase1-post.ahMvu6/hermes/work/FIXTURE.txt"}`,
  tool result `HERMES_PHYSICAL_FIXTURE`, `finish_reason=tool_calls`, and a
  continuation `HERMES_TOOL_OK` with `finish_reason=stop`. Gateway state IDs
  `063de118-5cc1-4d41-b606-19f8bd51b0c2` and
  `42087b8e-abaf-4893-87c3-0718a7199b4a` remained executor-only and recorded
  `stream=true` and one `stream_completed` each; the former finished
  `tool_calls`, while the continuation finished `stop` and recorded
  `tool_result_received` and `tool_execution_recorded`.

#### Exact retained failed-to-successful transitions

Only credential values are replaced by `[REDACTED]` below. All other paths,
ports, versions, flags, environment names, prompts, and output files are the
retained commands or configuration transitions.

The Task 0 baseline first started each role in its own foreground shell without
an API key. These three commands failed in the shared settings validator before
model loading:

```bash
cd /tmp/dgx-moa-phase1.6roKBd
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve planner
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve reviewer
```

The credential retry added only
`DGX_MOA_API_KEY='[REDACTED]'`. Its executor command did not pass a MoE-backend
override, so vLLM `0.22.1` selected FlashInfer-CUTLASS and began the first-run
SM121a build. After 9 of 96 objects, only that diagnostic executor was stopped;
the successful Task 0 executor retry added `DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN`:

```bash
exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  DGX_MOA_API_KEY='[REDACTED]' XDG_CACHE_HOME=/home/kotori9/.cache \
  MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor

exec env PYTHONPATH=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/compat:/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/gateway/src \
  DGX_MOA_CONFIG=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/config/models.yaml \
  DGX_MOA_API_KEY='[REDACTED]' DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN \
  XDG_CACHE_HOME=/home/kotori9/.cache MAX_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
  VLLM_BIN=/home/kotori9/.pyenv/shims/vllm \
  /home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent/.venv/bin/python -m dgx_moa.serve executor
```

Task 9 used the fresh root and environment established below. Its executor went
directly to MARLIN; the first reviewer command failed at CUDA
`cudaMemGetInfo` before weights, and the byte-for-byte same reviewer command
was retried after a 10-second memory-settle interval. Planner and the normal
gateway then started with the shown commands:

```bash
export TASK_RUN_ROOT=/tmp/dgx-moa-phase1-post.ahMvu6
export DGX_MOA_CONFIG="$TASK_RUN_ROOT/config.yaml"
export DGX_MOA_STATE_DB="$TASK_RUN_ROOT/state/gateway.db"
export DGX_MOA_BIND_HOST=127.0.0.1
export DGX_MOA_BIND_PORT=19000
export DGX_MOA_AUTH_ENABLED=true
export DGX_MOA_API_KEY='[REDACTED]'
export DGX_MOA_RUNTIME_CHANNEL=dev
export DGX_MOA_TRACE_ORIGIN=validation
export DGX_MOA_CONTROLLER_COMMIT=0d95591c86a81d6fcea290261a93917a3896d90e
export DGX_MOA_VLLM_VERSION=0.22.1
export DGX_MOA_PROJECT_ROOT=/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent
export PYTHONPATH=/home/kotori9/dgx-moa-agent/compat
export VLLM_BIN=/home/kotori9/.pyenv/shims/vllm
export XDG_CACHE_HOME=/home/kotori9/.cache
export MAX_JOBS=1
export CMAKE_BUILD_PARALLEL_LEVEL=1

DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN setsid uv run python -m dgx_moa.serve executor \
  >"$TASK_RUN_ROOT/logs/executor.log" 2>&1 &
setsid uv run python -m dgx_moa.serve reviewer \
  >"$TASK_RUN_ROOT/logs/reviewer.log" 2>&1 &
sleep 10
setsid uv run python -m dgx_moa.serve reviewer \
  >"$TASK_RUN_ROOT/logs/reviewer-retry.log" 2>&1 &
setsid uv run python -m dgx_moa.serve planner \
  >"$TASK_RUN_ROOT/logs/planner.log" 2>&1 &
setsid uv run dgx-moa >"$TASK_RUN_ROOT/logs/gateway.log" 2>&1 &
```

The retained vLLM `0.22.1` argv confirms the executable flags and ports. The
executor had `--moe-backend MARLIN`; the unchanged reviewer retry did not pass
a backend override and vLLM selected MARLIN automatically:

```bash
/home/kotori9/.pyenv/shims/vllm serve /home/kotori9/models/dgx-moa/executor \
  --host 127.0.0.1 --port 8101 --served-model-name dgx-moa-executor \
  --max-model-len 65536 --max-num-seqs 1 --kv-cache-memory-bytes 1700000000 \
  --gpu-memory-utilization 0.5 --moe-backend MARLIN \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder

/home/kotori9/.pyenv/shims/vllm serve /home/kotori9/models/dgx-moa/reviewer \
  --host 127.0.0.1 --port 8103 --served-model-name dgx-moa-reviewer \
  --max-model-len 65536 --max-num-seqs 1 --kv-cache-memory-bytes 2300000000 \
  --gpu-memory-utilization 0.25 \
  --hf-config-path /tmp/dgx-moa-phase1-post.ahMvu6/data/run/reviewer-hf-config \
  --reasoning-parser cohere_command4
```

The old timing wrapper was launched exactly as follows and its request returned
HTTP `500`, 21 bytes, no DONE, and
`TypeError: TimedProvider.stream() got an unexpected keyword argument
'timeout_seconds'`:

```bash
setsid uv run python /tmp/dgx-moa-phase1.6roKBd/timed_gateway.py \
  >"$TASK_RUN_ROOT/logs/timed-gateway.log" 2>&1 &
```

The validation-only adaptation added the new keyword-only parameters and
forwarded them upstream:

```python
async def stream(
    self,
    role: str,
    model: ModelConfig,
    request: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
    stage: str | None = None,
) -> AsyncIterator[bytes]:
    upstream = await super().stream(
        role, model, request, timeout_seconds=timeout_seconds, stage=stage
    )
```

The retry command used the adapted ignored file and produced the retained HTTP
`200` measurement:

```bash
setsid uv run python .superpowers/sdd/task-9-timed-gateway.py \
  >"$TASK_RUN_ROOT/logs/timed-gateway-retry.log" 2>&1 &
```

OpenCode `1.17.18` first created its temporary configuration without a model
limit and ran the following exact bounded command:

```bash
sed 's#http://<DGX_TAILSCALE_IP>:9000/v1#http://127.0.0.1:19000/v1#' \
  config/opencode.example.json | \
  jq '. + {permission:{"*":"deny",read:"allow"}}' \
  >"$TASK_RUN_ROOT/opencode/normal/opencode.json"

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir "$TASK_RUN_ROOT/opencode/normal" --model dgx-moa/dgx-moa-agent \
  'Reply exactly OPENCODE_OK.' \
  >"$TASK_RUN_ROOT/opencode/normal/stdout.jsonl" \
  2>"$TASK_RUN_ROOT/opencode/normal/stderr.log"
```

It exited with API HTTP `400` and complete body
`{"error":{"message":"max_tokens exceeds server maximum
16384","type":"invalid_request_error","code":"invalid_request","param":"max_tokens"}}`.
The exact configuration transition and otherwise unchanged retry were:

```bash
jq '.provider["dgx-moa"].models["dgx-moa-agent"].limit={context:65536,output:16384}' \
  "$TASK_RUN_ROOT/opencode/normal/opencode.json" \
  >"$TASK_RUN_ROOT/opencode/normal/opencode.json.tmp"
mv "$TASK_RUN_ROOT/opencode/normal/opencode.json.tmp" \
  "$TASK_RUN_ROOT/opencode/normal/opencode.json"

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir "$TASK_RUN_ROOT/opencode/normal" --model dgx-moa/dgx-moa-agent \
  'Reply exactly OPENCODE_OK.' \
  >"$TASK_RUN_ROOT/opencode/normal/retry.stdout.jsonl" \
  2>"$TASK_RUN_ROOT/opencode/normal/retry.stderr.log"
```

Hermes Agent `0.18.2` attempt one used a config with no `model.api_key`:

```yaml
model:
  default: dgx-moa-agent
  provider: custom
  base_url: http://100.125.239.72:9000/v1
  context_length: 65536
  max_tokens: 16384

platform_toolsets:
  cli:
    - file
```

Its exact invocation supplied only the host-gated generic environment variable:

```bash
cd /tmp/dgx-moa-phase1-post.ahMvu6/hermes/work
HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes \
  OPENAI_API_KEY="$DGX_MOA_API_KEY" NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal.stderr
```

It reached `100.125.239.72:9000` but returned `HTTP 401: invalid bearer token`.
The only config transition was adding the environment reference beneath
`model`:

```yaml
  api_key: ${DGX_MOA_API_KEY}
```

The retry removed the ineffective `OPENAI_API_KEY` assignment, retained
`DGX_MOA_API_KEY='[REDACTED]'` in the supervisor environment, and used the same
Hermes interface:

```bash
HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stderr
```

Finally, the CPU-only timeout harness provider started normally, but the first
real-gateway launcher exited without binding because the module has no
`__main__` call. The console-entry-point retry was the only launcher change:

```bash
TIMEOUT_ROOT=/tmp/dgx-moa-timeout.uVbS91
DGX_MOA_API_KEY='[REDACTED]'
export DGX_MOA_API_KEY
setsid uv run python .superpowers/sdd/task-9-timeout-provider.py \
  >"$TIMEOUT_ROOT/logs/provider.log" 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run python -m dgx_moa.api \
  >"$TIMEOUT_ROOT/logs/gateway.log" 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run dgx-moa \
  >"$TIMEOUT_ROOT/logs/gateway-retry.log" 2>&1 &
```

#### Safely redacted physical commands

The following are the exact successful client and follow-up harness commands.
Only the credential value is replaced by `[REDACTED]`; temporary paths, output
redirections, models, prompts, headers, and options are retained. Failed and
successful launch/configuration transitions are recorded immediately above.

```bash
export DGX_MOA_API_KEY='[REDACTED]'

curl --fail --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  http://127.0.0.1:19000/v1/models

curl --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-curl-nonstream' \
  --data '{"model":"dgx-moa-chat","messages":[{"role":"user","content":"Reply exactly CHAT_OK."}]}' \
  http://127.0.0.1:19000/v1/chat/completions

curl --no-buffer --silent --show-error \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-curl-stream' \
  --data '{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Reply exactly STREAM_OK."}],"stream":true}' \
  http://127.0.0.1:19000/v1/chat/completions

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir /tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal \
  --model dgx-moa/dgx-moa-agent 'Reply exactly OPENCODE_OK.' \
  >/tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal/retry.stdout.jsonl \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/opencode/normal/retry.stderr.log

timeout 180 "$HOME/.opencode/bin/opencode" run --pure --auto --format json \
  --dir /tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool \
  --model dgx-moa/dgx-moa-agent \
  'Use the read tool exactly once to read FIXTURE.txt, then reply OPENCODE_TOOL_OK followed by its content.' \
  >/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/stdout.jsonl \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/opencode/tool/stderr.log

HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Reply with exactly HERMES_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/normal-retry.stderr

HERMES_HOME=/tmp/dgx-moa-phase1-post.ahMvu6/hermes NO_COLOR=1 \
  hermes --ignore-rules -t file -z \
  'Use the read_file tool to read /tmp/dgx-moa-phase1-post.ahMvu6/hermes/work/FIXTURE.txt. Do not answer before using the tool. After the tool returns HERMES_PHYSICAL_FIXTURE, reply with exactly HERMES_TOOL_OK and nothing else.' \
  --usage-file /tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool-usage.json \
  >/tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool.stdout \
  2>/tmp/dgx-moa-phase1-post.ahMvu6/hermes/tool.stderr

setsid uv run python .superpowers/sdd/task-9-timeout-provider.py \
  >/tmp/dgx-moa-timeout.uVbS91/logs/provider.log 2>&1 &

DGX_MOA_CONFIG="$PWD/.superpowers/sdd/task-9-timeout-config.yaml" \
  DGX_MOA_PROJECT_ROOT="$PWD" setsid uv run dgx-moa \
  >/tmp/dgx-moa-timeout.uVbS91/logs/gateway-retry.log 2>&1 &

curl --silent --show-error --max-time 10 \
  --dump-header /tmp/dgx-moa-timeout.uVbS91/timeout.headers \
  --output /tmp/dgx-moa-timeout.uVbS91/timeout.body.json \
  --write-out '%{http_code}' \
  -H 'Authorization: Bearer [REDACTED]' \
  -H 'Content-Type: application/json' \
  -H 'X-Session-ID: physical-executor-first-byte-timeout' \
  -H 'X-Runtime-Channel: dev' \
  -H 'X-Trace-Origin: validation' \
  -H 'X-Task-ID: TASK9-TIMEOUT' \
  -H "X-Workspace-Path: $PWD" \
  -H 'X-Workspace-ID: task9-timeout' \
  -H 'X-Repository-Branch: dev' \
  -H 'X-Repository-Commit: 391f968' \
  -H 'X-Dirty-State: clean' \
  --data '{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Reply exactly TIMEOUT_UNEXPECTED."}],"stream":true,"max_tokens":64}' \
  http://127.0.0.1:19100/v1/chat/completions
```

#### Trace audit, teardown, and acceptance boundary

- The isolated trace audit exited `1`: 13 sessions, 0 complete, 0 legacy, and
  0.0% mandatory-field completeness. All 13 lacked `session_ended` and
  `workspace_identity`; 12 lacked `task_id`; decision task IDs were also
  missing. The client/stream checks passed, but this is a real phase-one
  observability gap and prevents an all-gates completion claim.
- The original Task 9 post-documentation gate run reported `180 passed, 1
  warning in 1.93s`, `48 files already formatted`, Ruff success, MyPy success
  for 26 source files, clean systemd verification, clean shell syntax, and
  clean `git diff --check`. The repository trace audit was the only nonzero
  command: exit `1`, 10 total, 4 complete, 6 incomplete/legacy, 40.0%
  mandatory-field completeness, with `legacy_v1` missing for six sessions.
- Teardown stopped only the verified controlled groups: tailnet relay first,
  then isolated gateway, reviewer, and executor; planner had already been
  stopped for the backend-error check. Ports `8101`, `8102`, `8103`, `8104`,
  `8110`, `9000`, and `19000` were unbound afterward, the owned PIDs were
  absent, no NVIDIA compute process remained, and `MemAvailable` returned to
  `120329036` kB. All production units/targets remained inactive and the
  production `main` worktree remained clean.
- The phase-one design audit finds the intended public aliases, executor
  contract, field preservation, typed errors, bounded immediate streaming,
  native tool ownership, reviewer policy, output limits, truncation, timing,
  and explicit context override covered by direct files and the current
  181-test suite; the physical matrix proves the principal client and latency
  contracts.
  Formal Task 9 completion remains blocked by all three nonzero trace audits. The
  overall runtime-reliability Goal remains active for usage statistics,
  lifecycle and adaptive unloading, loading progress, memory-mechanism study,
  near-limit 64K validation, extended client matrices, soak, remaining docs,
  push, and PR work.

#### Final re-review gate matrix

After adding the Hermes contract test and the retained command transitions, the
complete eight-command matrix was rerun. Earlier `180`-test pre-runtime and
original Task 9 post-documentation results above remain chronological evidence;
the current suite contains `181` tests.

1. `uv run pytest -q`: exit `0`, `181 passed, 1 warning`.
2. `uv run ruff format --check .`: exit `0`, `48 files already formatted`.
3. `uv run ruff check .`: exit `0`, `All checks passed!`.
4. `uv run mypy`: exit `0`, no issues in 26 source files.
5. `systemd-analyze --user verify systemd/*`: exit `0`, no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: exit `0`, no output.
7. `scripts/audit-trace-completeness.sh data/traces`: exit `1`, 10 total,
   4 complete, 6 incomplete, 6 legacy, 40.0% mandatory completeness, and
   `missing_fields={"legacy_v1":6}`.
8. `git diff --check`: exit `0`, no output.

The two retained isolated audits were also rerun after the same edit:

- `/tmp/dgx-moa-phase1-post.ahMvu6/traces`: exit `1`, 13 total and 0 complete;
  all 13 lack `session_ended` and `workspace_identity`, 12 lack top-level and
  first-decision task IDs, 4 lack the second-decision task ID, and 2 lack the
  third-decision task ID.
- `/tmp/dgx-moa-timeout.uVbS91/traces`: exit `1`, 1 total and 0 complete; the
  sole gap is one missing `session_ended` event, with no missing fields.

## 2026-07-18 — Isolated physical lifecycle matrix (Task 10)

Task 10 ran only foreground development processes from commit
`ee2d714a1b7a4cac7fca4655fa035535da94c727`. The production worktree remained
read-only at clean `main` commit
`c2a9af0d6b5db8dd940842c56a7236ac867061ff`; no service manager, profile,
deployment, AppArmor, or Frontier command was used. The successful raw root is
`/tmp/dgx-moa-task10-yhs6_hr8`; it ran from
`2026-07-18T15:03:58.596447+00:00` through
`2026-07-18T15:24:34.850669+00:00`. Its API key existed only in the harness
environment and is redacted from the manifest and results.

### Retained failure transitions

The following failed attempts remain as evidence and were not converted into
passes:

- `/tmp/dgx-moa-task10-f7w_eqsb` stopped before starting any process because
  this GPU reports `0, [N/A], [N/A]` for memory fields. The root contains only
  empty directories, so it is an observed failed attempt, not retained raw
  result evidence. The parser now preserves those fields as JSON null with
  `memory_metrics_available=false`; its regression test passes.
- `/tmp/dgx-moa-task10-xofa35a1` observed a transient empty `/proc` argv while
  capturing the optional process identity. The harness failed closed. The
  retained result itself ends with `RuntimeProcessLeak` and a running planner.
  That exact planner identity was revalidated and stopped afterward, and
  current read-only checks find none of its processes or ports, but no retained
  artifact attests that later cleanup. Identity capture now retries only the
  transient empty-argv state and has a regression test.
- `/tmp/dgx-moa-task10-53voozpd` reached real model health after about 1,034
  seconds, but the initial 3,600-second lifecycle poll interval could not
  observe it before the 1,200-second load timeout. Exact teardown passed. Load
  polling is now 2 seconds while automatic idle/residency thresholds remain
  independently fixed at 7,200 seconds.
- `/tmp/dgx-moa-task10-wv_g_4bp` reached ready in about 1,026 seconds and proved
  12 typed loading responses, one start, monotonic measured-shard progress,
  retry success, and an active-request guard. Its stream assertion sampled
  after the real stream had already closed. The harness now requires a fresh
  blocked scheduler decision while the stream lease is open and then requires
  a cancelled terminal state with `stream_aborted` and without
  `stream_completed`.
- `/tmp/dgx-moa-task10-uv1pt8ub` passed that stricter stream-disconnect proof,
  then exposed a real compatibility defect: vLLM returned a non-empty
  `message.tool_calls` with `finish_reason=stop`, so the gateway did not create
  a continuation lease. The run stopped only its exact owned groups and
  returned memory. The broader reliability goal authorized the separate source
  remediation commit `ee2d714`, made between validation attempts: the gateway
  now treats a validated non-empty tool-call payload as continuation evidence
  while preserving the provider's original finish reason. The new regression
  first failed, then the relevant three tests and the full 531-test suite
  passed. Task 10's final tracked change remains documentation-only.
- `/tmp/dgx-moa-task10-d36rm7e7` was the first result with all physical rows
  marked passed, but independent evidence review rejected it as final proof:
  traces retained raw objective/model/tool content, the v1 manifest overwrote
  the first executor identity on reload, and final host `MemAvailable` was
  `767856640` bytes below its initial snapshot after 120.19 seconds. Its rows
  remain useful diagnostic evidence, but the run is superseded by the final
  root above.

### Preflight, runtime, and immutable inputs

Immediately before the successful run, all eight non-mutating gates exited
zero: `uv run pytest -q` reported `531 passed, 1 warning`; Ruff format reported
53 files; Ruff check and MyPy for 28 source files passed; unit-file verification,
all shell syntax checks, and `git diff --check` were clean; the checked-in trace
audit reported 10/10 complete and 100.0% mandatory-field completeness. The
ignored harness also passed 9 tests, Ruff format/check, Python compilation, and
its dry run.

Preflight `MemAvailable` was `120673374208` bytes against the 80-GiB start gate
and 40-GiB continuous floor. Loopback ports were gateway `19200`, executor
`19201`, and optional `19202`; production ports `9000`, `8101`-`8104`, and
`8110` were unbound. There was no unowned DGX MoA/vLLM runtime. The exact
executor command retained `--max-model-len 65536`, `--max-num-seqs 1`,
`--kv-cache-memory-bytes 1700000000`, `--gpu-memory-utilization 0.5`,
`--moe-backend MARLIN`, automatic tool choice, and the `qwen3_coder` parser on
`127.0.0.1:19201`. Installed versions were vLLM `0.22.1`, OpenCode `1.17.18`,
and Hermes Agent `0.18.2`.

The model path metadata fingerprint was unchanged before and after: revision
`27a8f16f463b9a13c91c332c40cf93e09717347e`, metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
82 files, 4 directories, `47613238658` total bytes, and the same newest mtime.
This is a path/count/size/mtime/revision fingerprint, not a content hash or a
byte-for-byte model comparison.

The final run seeded only `cache` and `home/.cache/flashinfer` from the earlier
isolated root `/tmp/dgx-moa-task10-d36rm7e7`; provenance is recorded in
`cache-seed.json` and preflight. Root-dependent cache keys still caused the
first engine to rebuild much of its initialization path, so the seed is not
claimed as a complete cold-start cache hit.

### Successful physical rows

- Cold/single-flight: 12 concurrent real loopback requests all returned HTTP
  `503` with typed code `model_loading` in `0.14082865789532661` seconds, and
  the manifest recorded exactly one executor start.
- Progress/ready: observations followed `process_starting` ->
  `loading_weights` -> `initializing_engine` -> `warming_up` -> `ready`.
  Measured shard progress was monotonic and reached 100% without treating later
  initialization or warmup as ready. The lifecycle measured load duration was
  `942.7537190914154` seconds and the status wait was
  `944.0529136529658` seconds. vLLM separately logged weight loading in
  `238.88` seconds, model loading in `249.978614` seconds using 44.31 GiB, and
  initial profiling/warmup in `580.42` seconds. It reported a 67,121-token KV
  cache and 1.02x maximum concurrency for a 65,536-token request. The real retry
  returned HTTP `200` with `finish_reason=stop`.
- Guards: a real non-stream request held `active_request_count=1`; a real stream
  held `active_request_count=1` and `open_stream_count=1`, produced a fresh
  `reason=blocked` idle decision, and after downstream close ended
  `cancelled` with `stream_aborted` and no `stream_completed`; a real forced
  tool call held `continuation_lease_count=1`, and its matching real tool-result
  continuation released it. Each scheduler check left the executor ready.
- Timeout: a real request under the controlled 0.001-second executor total
  limit returned HTTP `504` with typed code `executor_total_timeout`.
- Ordered unload: after three manual hysteresis checks, the optional process
  stopped before the executor. The optional sample took
  `0.29537057876586914` seconds; the single executor unload sample took
  `1.361647605895996` seconds and ended in `cold`. Memory settlement took
  `6.216998043004423` seconds and there was no rapid retry.
- Reload: the next real request returned typed loading HTTP `503`, the manifest
  recorded exactly the second executor start, ready returned in
  `273.00104479002766` seconds, and the retry returned HTTP `200`. vLLM logged
  the second weight load at `237.30` seconds, model load at `248.278115`
  seconds, and profile/KV/warmup at `9.22` seconds including `2.86` seconds of
  compilation.
- Traces: the isolated success, disconnect/cancellation, and timeout roots each
  audited 1/1 complete with 100.0% mandatory-field completeness. The checked-in
  corpus independently audited 10/10 complete at 100.0%. Before final artifact
  capture, all six isolated trace files were atomically sanitized; objectives
  and model decisions use explicit placeholders, tool-event payloads retain
  only `content_redacted=true`, and raw tool/evidence fields are empty. A
  structural check over the seven root records plus three audit copies found
  zero violations, the three copies match their sanitized roots by SHA-256,
  and a known-sensitive-string scan found no match. These audits prove
  structural completeness, not semantic success: the named success trace has a
  completed `session_ended` event but top-level `final_status=degraded`. The
  separately reviewed sanitizer code and tests require a final teardown pass
  and make the harness fail closed if sanitization cannot complete.

### Memory and exact teardown

`nvidia-smi` was available but this unified-memory GPU exposed neither used nor
free byte fields, so every GPU byte value is null and no GPU percentage is
inferred. Host and exact-owned-process measurements were:

| Point | MemAvailable bytes | owned PSS bytes | owned RSS bytes |
| --- | ---: | ---: | ---: |
| initial | 120509042688 | 0 | 0 |
| warm ready | 65156329472 | 4532602880 | 4947398656 |
| immediately before ordered unload | 65325219840 | 4655138816 | 5070721024 |
| immediately after unload | 120379711488 | 0 | 0 |
| best bounded unload settle | 120564150272 | 0 | 0 |
| final after reload teardown | 120676032512 | 0 | 0 |

The final snapshot exceeded the initial snapshot by `166989824` bytes, while
exact-owned PSS/RSS were zero. This supports full process-memory return within
host `MemAvailable` snapshot noise; it does not establish a GPU-byte result
because those metrics were unavailable. The earlier `d36rm7e7` shortfall is
retained above rather than generalized away.

The v2 manifest preserves full history rather than only the latest role entry:
planner PID/PGID/session `1249683`, first executor `1249697`, and reloaded
executor `1274552`, each with start ticks, cwd, requested and observed argv,
start time, stop time, and `state=stopped`. It records planner start once and
executor start exactly twice, then planner stop, first executor stop, and final
executor stop. Each kill was limited to a recorded PID=PGID=session group after
leader and group-member identity revalidation.

The point-in-time, scoped final fingerprint found loopback ports
`19200`-`19202` and production ports
`9000`, `8101`-`8104`, and `8110` unbound, no DGX MoA/vLLM runtime process,
clean unchanged production, clean dev at `ee2d714`, and the unchanged metadata
fingerprint. The successful physical result contains no failures and reports
`passed=true`.

### Final post-documentation gates

An earlier post-documentation attempt launched all eight commands concurrently.
It found one real documentation-contract mismatch because the historical `527
passed` baseline had been replaced rather than retained, and one asynchronous
progress test missed its bounded scheduler-yield observation while CPU-heavy
gates ran beside it (`529 passed, 2 failed`). The historical line was restored
alongside the current baseline. The progress test then passed 10 of 10 isolated
repetitions, matching the earlier green full-suite runs; no lifecycle code
changed for that transient scheduling failure.

After the evidence correction, the first serialized gate run exited zero for
all eight commands. A verification rerun after recording that result then
reproduced the same test race even without concurrent gates: 530 passed and
`test_coordinator_preserves_prior_progress_when_new_logs_are_invalid` failed
while its background load was still `process_starting`. The isolated test
reproduced on repetition 12. Its bounded loop of 100 `asyncio.sleep(0)` yields
did not guarantee completion of the coordinator's `to_thread` calls.

Separate test-only commit `8cd8117` replaced yield counting with an event set
on entry to the second poll sleep. Runtime code did not change. The corrected
test passed 100/100 isolated repetitions, the full suite passed 531/531, and an
independent review confirmed that `coordinator.close()` still cancels and
collects the blocked task. Task 10's final tracked commit remains limited to
this documentation.

The final serialized gate run after that test stabilization exited zero for all
eight commands:

1. `uv run pytest -q`: `531 passed, 1 warning`.
2. `uv run ruff format --check .`: `53 files already formatted`.
3. `uv run ruff check .`: `All checks passed!`.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, 0
   incomplete, 0 legacy, and 100.0% mandatory-field completeness.
8. `git diff --check`: no output.

## Responses Streaming Compatibility — 2026-07-22

The Codex custom-model failure was reproduced from the checked-in route: an
authenticated `POST /v1/responses` request with `stream=true` was rejected with
HTTP 400 and `stream is not supported for /v1/responses` before inference.

The development gateway now translates the existing Chat Completions text SSE
stream into Responses API events. The focused checks observed ordered
`sequence_number` values, `response.output_text.delta` chunks, a terminal
`response.completed` object, converted token usage, no Chat Completions
`data: [DONE]` sentinel, HTTP 200, `text/event-stream`, and preservation of the
request session ID. Non-streaming Responses behavior remained covered.

Measured development checks:

1. Focused Responses checks: `3 passed`.
2. `ruff check` on the four changed Python files: all checks passed.
3. `mypy` on the two changed gateway modules: no issues found.
4. Full `pytest -q`: `624 passed`, with the existing third-party Starlette
   TestClient deprecation warning.
5. Host OpenAI Python client `2.6.1` parsed all nine emitted typed events from
   `ResponseCreatedEvent` through `ResponseCompletedEvent`; final text was `ok`
   and total token usage was `2`.

Production deployment was approved and merged as PR `#19`, commit
`52bd8fc89195497b9132a30c8fd90733f3103be6`. Restarting the gateway followed
the installed resident-target dependency and performed the selected exact
executor stop/start. The replacement executor retained context `65536`, one
sequence, `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN;
weight loading took `246.07` seconds. Gateway, executor, and resident target all
returned active, and health, model-list, and protected readiness checks passed.

Authenticated production streaming checks returned HTTP 200. `dgx-moa-fast`
emitted ten ordered events and exactly `STREAM_OK`; the primary `dgx-moa`
Reasoner+Executor path emitted nineteen ordered events, non-empty text, and a
completed response. An unauthenticated streaming request returned HTTP 401.
No secret value was printed or stored, and no systemd topology or model weight
was changed.

The subsequent Codex production retries returned HTTP 200 headers but closed
before `response.completed`. Executor journal evidence at `01:23:39` and
`01:25:10` showed vLLM rejecting Responses content parts with
`input_value='input_text'`; Chat Completions requires `type='text'`. The shared
Responses-to-Chat conversion now normalizes `input_text` and `output_text`
parts before routing. The exact regression check passed, followed by the full
suite at `624 passed` with the existing Starlette TestClient warning; Ruff and
Mypy passed on the changed path.

Production deployment PR `#21` merged as
`23e9631d7ffef0414060c9ac6f1c3284a548dd33`. After resident recovery, the
primary `dgx-moa` path received the same nested `input_text` shape and returned
HTTP 200 with eleven ordered events, exact text `INPUT_TEXT_OK`, and terminal
`response.completed`. The post-deployment gateway/executor journal contained
no validation error or traceback; gateway, executor, and resident target were
active.

### Heavy Judge validation and OAuth profile fallback (2026-07-21)

- The production Executor, Planner, and Reviewer were stopped for an approved
  isolated Heavy Judge run. The installed Judge unit revealed configuration
  drift: it launched at context `8192`, one sequence, ModelOpt FP4,
  `gpu_memory_utilization=0.85`, and `12000000000` KV bytes instead of the
  documented `4000000000`. Weight loading took `586.36` seconds and model
  loading reported `88.85 GiB` in `592.701` seconds. KV initialization left
  `6796004` KiB `MemAvailable`, below the 16-GiB Judge gate, so the Judge was
  stopped before readiness. Its systemd stop consumed the configured five-minute
  timeout and ended failed; memory recovered to `120529240` KiB.
- A direct development rerun restored the declared `4000000000` KV bytes with
  the same context, sequence count, utilization, and quantization. It loaded ten
  shards in `546.73` seconds and reported `88.85 GiB` model memory in
  `558.704` seconds, `22192` KV tokens, and `2.71x` concurrency. During kernel
  autotuning, `MemAvailable` reached `13810768` KiB, below the same 16-GiB
  safety line. The process was interrupted before readiness; port `8110` closed
  and memory recovered to `120686556` KiB. Therefore neither the new normal
  adjudication-resume path nor production promotion passed. This preserves the
  earlier 2026-07-11 ready-state result but does not treat it as evidence for
  the changed resume path.
- The fixed resident Executor was restored with context `65536`, one sequence,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN. It returned
  `/v1/models` HTTP `200`; `wait-profile.sh` reported
  `available_bytes=69101035520`. The gateway health check returned `ok`, the
  resident target and Executor were active, and Planner, Reviewer, Judge, and
  the Judge target were inactive.
- The authoritative retry used the same approved `4000000000` KV bytes,
  context `8192`, one sequence, `gpu_memory_utilization=0.85`, and ModelOpt FP4.
  It loaded ten shards in `541.43` seconds and reported `88.85 GiB` model
  memory in `553.070` seconds, `22192` KV tokens, and `2.71x` concurrency.
  Port `8110` returned the exact `dgx-moa-judge` model at context `8192`.
  Readiness-time `MemAvailable` was `18073493504` bytes against the unchanged
  `17179869184`-byte minimum, so the authoritative gate passed. Earlier
  sub-threshold samples occurred during weight loading and autotuning; the
  repository's selected gate is explicitly evaluated after readiness.
- An isolated authenticated dev gateway and isolated SQLite state exercised the
  resume API against that real Judge. Wrong profile returned HTTP `409`
  `judge_profile_required`; a missing session returned `404`
  `session_not_found`; and a session without pending evidence returned `409`
  `judge_not_pending`. The valid pending session returned HTTP `200` in 39
  seconds with `accept`, low risk, `completion_allowed=true`, and
  `resume_profile=resident`. Persisted state cleared pending evidence, set phase
  and final status to completed, recorded `judge_requested` and
  `judge_completed`, and measured 1056 prompt + 93 completion = 1149 total
  Judge tokens at `39278.236` ms.
- The isolated gateway and Judge exited cleanly, ports `19300` and `8110`
  closed, and `MemAvailable` recovered to `120334176` KiB. The fixed resident
  Executor was restored at context `65536`; `wait-profile.sh` reported
  `available_bytes=69124612096`. Final health reported resident ready with
  Executor and Reasoner ready, Planner/Reviewer/Judge stopped, the resident
  target active, and the Judge target inactive.
- The Codex OAuth adapter now tries `primary` and changes to `secondary` only on
  authentication, usage-limit, or rate-limit failures. A subprocess-level test
  forced primary `not logged in`, observed the ordered calls
  `[primary, secondary]`, and recorded `profile=secondary` on success. The
  selected profile is also persisted in collaboration invocation and trace
  evidence. Real primary and secondary calls each returned HTTP `401` with
  `token_invalidated` / `refresh_token_invalidated`; interactive OAuth re-login
  for both profiles is required before a physical fallback success can be
  claimed.
  The local CLI used for these calls was `codex-cli 0.144.6`.
- Both profiles were then reauthenticated with device OAuth. Primary's real
  read-only smoke authenticated but returned its account usage limit until
  2026-07-25 16:25. Secondary returned `READY` and `turn.completed`. A real
  `CodexOAuthCollaboration` architecture call subsequently observed the primary
  usage-limit failure, fell back to secondary, returned a schema-valid artifact,
  and reported `profile=secondary`, `mode=architecture`, and `13613` total
  tokens. This physically validates the ordered OAuth fallback without an API
  key or repository modification.
- Publication checks passed: `611` tests, Ruff format/check, mypy for 28 source
  files, user-systemd unit verification, shell syntax checks, and
  `git diff --check` all exited zero. The one pytest warning is the existing
  third-party Starlette TestClient deprecation.
- A later publication audit correctly failed `0/10` because the Python auditor
  had made seven Dynamic-MoA extensions retroactively mandatory for pre-MoA
  `agent-trace-v2` archives. An initial runtime-metric discriminator restored
  `10/10`, but an independent Frontier review correctly rejected it: a current
  trace could delete that optional metric and the MoA fields to masquerade as an
  archive. Current traces now use explicit `agent-trace-v3`, where all MoA
  fields are mandatory; v2 keeps its immutable pre-MoA contract. Regressions
  cover authentic v2 acceptance, v3 downgrade rejection, and missing
  `metrics.runtime_mode`. The unchanged corpus remains `10/10`, zero
  incomplete/legacy records, with no missing fields/events.
- Final serial publication gates passed with `612` tests and the existing one
  upstream Starlette warning; Ruff format/check, mypy for 28 source files,
  user-systemd verification, every shell syntax check, trace audit `10/10` at
  100.0%, and `git diff --check` all exited zero.
- A real secondary-profile Frontier code review of the 16.8-KB post-
  implementation diff returned `revise`, Critical 0 and Important 1, confidence
  0.97, in `26818.303` ms with `18957` tokens. It identified the optional
  runtime-metric downgrade in the initial trace compatibility fix. The finding
  was accepted and replaced by explicit v3 as described above. Requested
  regressions now cover auth/usage/rate failover, no failover for timeout,
  provider, protocol, or validation failures, selected-profile trace metadata
  without paths/credentials, authentic v2 acceptance, and v3 downgrade
  rejection.
- Post-fix serial publication gates passed with `618` tests and the existing one
  upstream Starlette warning; Ruff format/check, mypy for 28 source files,
  user-systemd verification, every shell syntax check, trace audit `10/10` at
  100.0%, and `git diff --check` all exited zero.
- A real secondary-profile Frontier re-review of the explicit-v3 fix returned
  `approve`, Critical 0, Important 0, missing tests 0, suggestions 0, confidence
  0.93, in `25380.793` ms with `20658` tokens. The review covered v2/v3
  consumers and schemas, downgrade rejection, fallback classification, and
  selected-profile trace metadata.
- Production-hotfix reconciliation gates passed with `621` tests and the
  existing upstream Starlette warning; Ruff format/check, mypy for 28 source
  files, user-systemd verification, every shell syntax check, trace audit
  `10/10` at 100.0%, and `git diff --check` all exited zero. The reconciliation
  preserves the authenticated `GET /v1/responses` shim and reports externally
  controlled roles without treating them as unmanaged.
- Frontier reconciliation review used the secondary OAuth profile throughout.
  The first review returned `revise`, Important 1, confidence 0.93, in
  `26174.539` ms with `15947` tokens because an external role could also appear
  in the systemd unit map. Configuration now rejects that contradiction and
  status rendering gives external control defensive precedence. The second
  review returned `revise`, Important 1, confidence 0.97, in `17859.387` ms
  with `15957` tokens because the omitted-model GET test did not assert the
  selected default. The assertion was added. The final review returned
  `approve`, Critical 0, Important 0, missing tests 0, confidence 0.99, in
  `10961.058` ms with `15564` tokens.
- A pre-restart production status check exposed legacy SQLite rows whose
  historical `runtime_mode` and per-role `client_mode` were `chat`; the current
  typed reader accepts only `fast`, `moa`, `agent`, or `orchestrated`. Read-time
  compatibility now maps only the exact legacy value `chat` to `fast`. A
  SQLite backup of the production database then completed the new runtime
  report with 157 requests, token ID `legacy`, and the persisted automation
  latch honestly reported disabled. The live production database was not
  modified by this compatibility check. The compatibility publication gate
  passed `622` tests with the existing Starlette warning, Ruff format/check,
  mypy for 28 source files, user-systemd verification, trace audit `10/10` at
  100.0%, and `git diff --check`.
- The first production architecture smoke returned typed `model_loading` and
  exposed a systemd ordering contradiction: `dgx-moa-planner.service` remained
  in `start-pre` while `wait-model.sh reviewer` polled port 8103. Planner was
  intentionally stopped; the lifecycle store recorded one
  `start_command_failed` without disabling automation. Planner and Reviewer are
  independent optional roles, so both now order after and preflight only the
  normally resident Executor. This preserves the resident prerequisite without
  making Planner depend on a cold Reviewer.
- A secondary-profile Frontier review of the bounded unit/test/documentation
  diff returned `approve`, Critical 0, Important 0, confidence 0.97, in
  `16307.331` ms with `14935` tokens. It requested the post-fix physical smoke
  below before considering the production acceptance criterion fully evidenced.
- Post-fix production deployment completed on reviewed `main`. Authentication
  rejected missing and invalid credentials with 401; `legacy`, `opencode`,
  `hermes`, and `operator` each returned 200 from the protected model route.
  Authenticated missing-input `GET /v1/responses` returned the designed 405.
  A legacy-key `POST /v1/responses` returned 200/completed in Responses API
  shape with 310 prompt, 6 completion, and 316 total tokens; the unauthenticated
  counterpart returned 401.
- The default `dgx-moa` production smoke returned 200/stop in 51 seconds with
  531 prompt, 5 completion, and 536 total tokens. Its usage row was attributed
  to `operator`, and role rows recorded successful Reasoner and Executor
  participation. Distinct `dgx-moa-agent` requests attributed 570 total tokens
  to `opencode` and 587 to `hermes`; both recorded Reasoner and Executor.
- The corrected Planner unit preflighted the ready Executor, started without
  Reviewer, and reached ready as generation 10 with retry count zero. The first
  vLLM process failed engine initialization; systemd's configured restart
  succeeded, and the stable retry was recorded rather than hidden. Reviewer
  stayed cold/inactive. The final architecture request returned 200 in 74
  seconds. It honestly ended `length` at the requested 128-token cap and left
  the session nonterminal rather than claiming completion.
- That architecture trace recorded Reasoner, Planner (1033 tokens), Frontier
  architecture via OAuth `secondary` (13484 prompt, 691 completion, 14175 total
  tokens, 22457.468 ms), and Executor final synthesis (2591 total tokens). The
  orchestration decision required Planner and Frontier in parallel. Final
  production status reported automation enabled with zero failures, Executor,
  Planner, and external Reasoner ready, Reviewer cold, Judge inactive, and only
  tailnet 9000 plus loopback 8101/8102 listening.

## Codex cold-start 503 diagnosis — 2026-07-21

Production journal and SQLite inspection showed three lifecycle failures within
the automation window. Planner generations 6 and 7 and reviewer generation 6
were recorded as `load_start_timeout` after 10 seconds, disabling automation.
The corresponding systemd services continued starting and later returned their
expected model IDs from loopback `/v1/models`; measured startup was roughly 151
seconds for reviewer and 90 seconds for planner. The failure was therefore a
controller timeout mismatch, not a model-load failure or `/v1/responses`
compatibility failure.

The dev fix passes the configured `model_load_timeout_seconds` to the systemd
lifecycle driver instead of its 10-second default. Final validation passed 610
tests, Ruff formatting and lint, and mypy for 29 source files. Production state,
services, latch, and configuration were not changed; recovery still requires
separate deployment approval.

## Role-Aware Lifecycle Gap Closure — 2026-07-20

The implementation commits add strict role policies, persisted generations and
unload queues, content-free per-role usage statistics, the complete cold 503
progress contract, a bounded global automation circuit, and atomic rollback.
The first full regression after implementation passed `567` tests with the one
existing third-party Starlette TestClient deprecation warning.

After the never-started-unit fix and documentation contract update, the final
serialized gates all exited zero: `572 passed` with the same warning; 55 files
Ruff-formatted; Ruff lint clean; MyPy clean for 29 source files; user-systemd
unit verification clean; every `scripts/*.sh` syntax check clean; checked-in
trace audit 10/10, zero legacy/incomplete and 100%; and `git diff --check` clean.

The physical control-plane harness used a fresh `/tmp` root, random loopback
ports, a separate config/state/run tree, and PID-unique runtime-linked user
systemd units for gateway, executor, planner, reviewer, and reasoner. It used
the real gateway/lifecycle/systemd/journal path with fake model weights; no
production unit was a command target.

Two retained failed attempts improved the validation itself:

- `/tmp/dgx-moa-systemd-control-20bt5iys` queried nonexistent `/health` instead
  of `/healthz`; the gateway was healthy and cleanup/production equality passed.
- `/tmp/dgx-moa-systemd-control-rvw5v3od` found a real fresh-install defect:
  a never-started unit had no unit journal cursor and failed with
  `cursor_malformed_output`. Commit `9fa2801` added a tested global
  user-journal cursor fallback while keeping subsequent reads exact-unit scoped.
- `/tmp/dgx-moa-systemd-control-9947ve4w` passed cold, MoA, unload, and reload;
  its circuit fixture incorrectly expected three retries from one role despite
  the role-local retry cap of two. The final fixture injected two reasoner and
  one reviewer failures to test the actual global circuit contract.

The authoritative result is
`/tmp/dgx-moa-systemd-control-wbakbkm9/physical-result.json`, SHA-256
`83ecea14eec43543f22bddf00dccff0e208d45e2e84609820891d54a939c8fdf`,
with `passed=true`:

- initial executor/planner/reviewer/reasoner states were all `cold`;
- five concurrent cold requests all returned JSON 503, generation 1 and
  unavailable honest weight progress, with exactly one executor start;
- all four roles reached `ready`, each with one start, and orchestration returned
  HTTP 200;
- all four roles idled to systemd `inactive` under the accelerated isolated
  policy;
- executor request/retry produced generation 2, exactly two cumulative starts,
  and HTTP 200;
- three cross-role start failures opened the circuit; the fourth request returned
  `lifecycle_automation_disabled`, performed zero mutation, and ready executor
  traffic still returned HTTP 200;
- rollback passed twice, removed the unit map, reset the latch, restarted the
  isolated gateway, and reported lifecycle disabled;
- production commit `e63fa6f`, clean state, gateway/executor PIDs, and listeners
  9000/8101 were byte-for-byte equal before and after; all dev runtime units were
  removed.

This result adds no real-weight memory or load-time claim. Duplicating the active
45G production executor would have violated the safety floor, and production was
not stopped or altered. Phase 3 remains authoritative for real executor
full-stop memory recovery.

Independent review then identified that the adaptive scheduler read the newest
overall role rows before filtering successes. A sufficiently large burst of 503
or failed rows could therefore displace valid successful gaps despite the
required “recent successful requests” window. Commit `87f45e3` moved the
`success=1` predicate into SQLite before the policy limit and added a regression
with newer failures hiding older successes. The post-fix full suite passed 569
tests with the same third-party warning; Ruff and MyPy were clean.

The next review pass found two more Important contract gaps. Observe mode had
kept managed records cold without reading actual service state, so it could only
record `state_not_ready`; it now performs exact-unit status and health reads but
still cannot start, stop, or sample unload memory. A separate parser gap allowed
nonfinite journal counters or an unexpected parser exception to fail the load;
numeric counters now require finite values and all parser exceptions preserve
prior progress or `unavailable` while readiness continues. Focused red/green
tests cover both paths. The post-fix full suite passed 572 tests with the same
warning; Ruff and MyPy were clean.

The final independent read-only re-review of `f7d90cf..9508e97` confirmed all
three fixes and reported Critical 0, Important 0, and Minor 0. It separately
confirmed that the never-started-unit fallback takes only an opaque global
journal cursor and keeps all subsequent progress reads scoped to the exact
authorized unit.

## Phase 4 Physical Client and PR Gate — 2026-07-19

The content-free summary is
`/tmp/dgx-moa-phase4-s5gy6ydh/summary.json`, SHA-256
`5249dd396c4ac8b6ed85e4474fb7c631f504055685138be90791999f03928a8f`.
It has schema `phase4-pr-gate-summary-v1`, `passed=true`, and no blockers.
Source SHA-256 values are:

- client matrix:
  `a805eba3314ef3dee96646eea687def52238a40184543e38fc15c8e715e74cdc`;
- lifecycle result:
  `9f2412e59641a667bacc475b22d1bc90fa0f616becb2fb45ee4b34509154c9f3`;
- retained-root sanitization:
  `e4561c6620bf6607d52b77149a63e3c87ee9ad363c3a76c40718dcfad76147e4`.

| Contract | Physical pass count |
| --- | ---: |
| Generic non-stream / stream / >1,000-token long | `5` / `10` / `3` |
| Native forced tools / continuations / multi-step loops | `5` / `3` / `1` |
| OpenCode read / small edit / multi-file / bounded engineering | `2` / `2` / `1` / `1` |
| Hermes normal / stream / tool / multi-step | `2` / `1` / `1` / `1` |

All ten Generic streams recorded `malformed=0`, exactly one `[DONE]`, and the
first event before completion. Each long case used `max_tokens=5000`, returned
`4393` completion tokens, and parsed 1,100 finite numeric items. The linked
near-limit authority remained the Phase 3 selected result: three HTTP 200
cycles at 63,786 prompt tokens and executor context 65,536.

OpenCode `1.17.18` ran six physical cases with isolated HOME/XDG/TMP roots.
Read cases had no effects; edit cases matched exact allowed paths and hashes;
the bounded task modified only `calc.py` plus known test cache artifacts and
passed independent pytest. Hermes Agent `0.18.2` ran five cases with isolated
HOME/XDG/TMP and `HERMES_HOME`. Gateway observation proved the designated
stream case sent `stream=true`; file-tool effects and API-call counts matched.
Other measured clients were curl 8.5.0, HTTPX 0.28.1, and OpenAI Python 2.6.1.

The final lifecycle run returned twelve typed loading 503 responses with one
executor start, reached ready with nondecreasing progress in
`269.0157511299476` seconds, and retried with 200. Active-request, stream, and
continuation leases blocked unload. Idle policy stopped planner before executor,
returned the executor to cold, and raised MemAvailable from `66538033152` to
`121120661504` bytes. The next request returned 503, produced exactly the
second executor start, reached ready in `270.9573212391697` seconds, and
retried with 200. Success/disconnect/timeout traces were each 1/1 complete and
the checked-in corpus remained 10/10 complete at 100% mandatory fields.

The explicit serial validation window was `3064.0628089904785` seconds
(`51m 4.063s`) and included chat, stream, tool, OpenCode, Hermes, idle, unload,
and reload. It is not a continuous-load or 24-hour soak claim. Production
pre/post Git/index, tracked-file metadata, unit, port, and runtime snapshots
were equal. Production mutation and leaked process/listener counts were zero.

After evidence extraction, retained client stores, DBs, logs, forbidden
fields/values, unparseable JSON, and raw DB/log files all audited to zero.
Independent review concluded `Critical=0`, `Important=0`. The gate authorizes
only a draft `dev`-to-`main` PR; it does not authorize merge, deployment, unit
changes, or production restart.

### Final publication verification

The publication gate requires the following results on the final committed
tree; they were rerun after this record was committed and before push:

1. `uv run pytest -q`: `533 passed`, one existing deprecation warning.
2. `uv run ruff format --check .`: `53 files already formatted`.
3. `uv run ruff check .`: all checks passed.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: exit zero, no output. This is the
   repository's existing systemd gate; the plan's named
   `scripts/validate-systemd.sh` does not exist.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: exit zero, no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, zero
   incomplete/legacy, 100% mandatory-field completeness.
8. `git diff --check origin/main...HEAD`: exit zero, no output.
9. Ignored Phase 4 harness: `16 passed`; Ruff format/check and MyPy passed.
10. Retained-root audit: summary passed with no blockers; source validator
    errors, forbidden fields/values, JSON parse errors, raw DB/log files,
    production mutation, leaked ports/processes, Critical findings, and
    Important findings were all zero. The current production full snapshot
    equaled the lifecycle post-snapshot.

## Phase 3 Unload Mechanism Study — 2026-07-19

### Pre-execution gates and scope

Before any model process started, the serialized repository gates passed:
`uv run pytest -q` reported `531 passed, 1 warning`; Ruff format/check, MyPy for
28 source files, user-unit verification, all shell syntax checks, and
`git diff --check` exited zero; the checked-in trace audit remained 10/10
complete at 100.0%. The ignored phase-three harness passed 21 tests before the
first physical attempt and 26 tests after the retained tokenizer, systemd
collection, request-timeout, and resume corrections. Its ignore-aware Ruff,
Python compilation, and direct installed-Python dry run passed.

Trials used only fresh paths under `/tmp/dgx-moa-phase3-*`, loopback port
`19301`, and exact transient units matching
`dgx-moa-dev-phase3-[a-f0-9]{8}.service` or exact Task 10-style owned
PID/PGID/SID groups. Production remained read-only `main` at `c2a9af0`; no
production service or port was acted on.

### Retained attempts

- `/tmp/dgx-moa-phase3-52ffwbov` failed before process start because
  Transformers 5.8 returned `BatchEncoding` while the runner counted mapping
  fields instead of `input_ids`. A failing regression was added; the real
  tokenizer then produced `63786` tokens.
- `/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms.json`, SHA-256
  `6a5ce3ba6055f265f93e6f7a06752bbd883002bcbabf65512ab109db3e440994`,
  preserves the first complete A-D attempt. A finished short/tool/near-limit
  HTTP 200 requests and stopped cleanly, but `systemctl show` represented its
  collected unit as `LoadState=not-found` with an empty working directory; the
  runner misclassified that as a mismatched live unit. B reached ready in
  `938.83` seconds but its sleep call exceeded httpx's five-second default.
  C was deliberately interrupted and exactly torn down rather than spending a
  full cold load on the known timeout bug. D reached ready in `952.86` seconds,
  completed live reset HTTP 200, and then failed its first exact post-reset
  short quality check.
- Tests first fixed `LoadState=not-found` normalization and physical endpoint
  timeout propagation. Resume did not rewrite the original. The authoritative
  `/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms-resumed.json`, SHA-256
  `625b25afbadbb1e8ef42f95e836df627ec22e37c87e07301102eaaa6194b6af9`,
  links the original SHA and retains its per-row failure summaries.

### Final physical result

The resumed result reports `passed=true`, no harness failures, and selection
`A_full_systemd_stop_start` with the same mechanism preserved as fallback.

- A passed two exact transient-unit cycles. Cold/warm ready times were
  `946.3586723739281` and `272.0807015961036` seconds; stop times were
  `1.146820979192853` and `1.118467804044485` seconds. MemAvailable deltas were
  `55227699200` and `54869725184` bytes. Short and forced native-tool checks
  passed. Backend prompt usage was `63786` tokens twice, with near-limit
  latencies `17.792744473088533` and `17.567367010051385` seconds.
- B level-1 sleep was natively supported and completed two cycles. Sleep times
  were `21.733480336144567` and `2.1252455201465636` seconds; wake times were
  `38.78946190699935` and `7.454574962845072` seconds. Its median
  `25938081792`-byte return was 47.12% of A, below the required 90%, and owned
  PSS did not remain stable. Short/tool checks and backend `63786`-token quality
  still passed, so the rejection is memory/stability-based rather than a
  capacity failure.
- C level-2 sleep and wake routes returned HTTP 200 after a
  `941.2777812271379`-second ready. Pre-sleep short/tool checks passed; the first
  post-wake exact short check failed, so no second-cycle, memory-selection, or
  near-limit claim is made.
- D's live reset route returned HTTP 200 after a `952.8551460539456`-second
  ready. Two identical-prefix probes passed with 1560 prompt tokens and
  `0.701514609856531`/`0.4988313359208405` seconds latency. The first exact
  post-reset short check failed, so reset is a rejected cache-clear result, not
  an unload mechanism.

The final point-in-time fingerprint found phase-three and production ports
unbound, runtime process count zero, unchanged clean dev/production commits,
and the unchanged model metadata fingerprint. GPU used/free byte metrics were
null, and no GPU percentage is inferred. Result JSON passed the recursive
content-free scan; retained manifests contain only the literal
`redacted-environment-only` API-key descriptor, not a credential. Detailed
selection math and limitations are in `docs/MEMORY_OPTIMIZATION.md`.

Independent read-only raw-evidence review passed with no blocker. It matched the
original SHA link, prior-attempt summaries, A identities and cgroups, all A/B
quality/timing/memory values, deterministic 90% calculation, C/D route success
followed by generic quality rejection, and the final fingerprint. It also
confirmed result/log redaction. Review limits are retained rather than promoted
away: A's systemd identities exist in resumed JSON while its generic foreground
manifests/events are empty; C/D failed text is intentionally unavailable; two
samples do not form a robust distribution; MemAvailable is noisy, GPU bytes are
null, and model equality is metadata-only. One vLLM shutdown log reports
`resource_tracker` semaphore cleanup, with no surviving process, port, PSS, or
RSS in the final checks.

## Phase 3 65,536-Token Candidate Study — 2026-07-19

The authoritative content-free result is
`/tmp/dgx-moa-phase3-7vfm7bzv/candidates-confirmed.json`, SHA-256
`10f233b47acfb52e54ee41532963d68e38831e7337818d4335b57f3bc2eaad03`.
It reports `passed=true`, no failures, and selection `baseline`. The final
fingerprint records clean dev `eb165d3`, clean production `main` at `c2a9af0`,
unchanged model revision `27a8f16` and metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
all scoped phase-three/production ports unbound, and runtime process count zero.

All physical candidates kept `--max-model-len 65536` and
`--max-num-seqs 1`. Baseline, FP8, eager, chunked-8K, and CPU-offload screening
reported exactly 63,786 backend prompt tokens with the expected needle and
`finish_reason=stop`. KV offload failed during startup because the installed
hybrid layout required a GPU block size divisible by its hash block size;
teardown still left PSS/RSS zero. Prefix-off was rejected without process start
because the installed baseline already disabled prefix caching.

The final baseline and eager trials passed the complete contract:

| Check | Baseline | Eager |
| --- | ---: | ---: |
| cold ready | `934.9303155951202s` | `912.4722288539633s` |
| near-64K latency / reported prompt tokens | `17.774531355826184s` / `63786` | `20.046998847974464s` / `63786` |
| five short cases / forced native tools | 5/5 / 3/3 | 5/5 / 3/3 |
| long numeric items / completion tokens / latency | `1100` / `4393` / `113.90377882798202s` | `1100` / `4394` / `203.29746027011424s` |
| restricted code / strict reviewer JSON | pass / pass | pass / pass |
| warm owned PSS | `4545508352` | `3859753984` bytes |
| warm MemAvailable | `66737324032` | `66124435456` bytes |
| owned-memory growth | `512000` | `385024` bytes |
| post-stop owned PSS/RSS | `0` / `0` | `0` / `0` |

Although eager lowered owned PSS by `685754368` bytes, its warm MemAvailable
was `612888576` bytes lower than baseline. The fixed `268435456`-byte noise
band therefore rejected eager before the lowest-PSS tie-breaker. The selected
baseline settings are the existing `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, and MARLIN; Task 4 requires no source change.

FP8 used `--kv-cache-dtype fp8 --calculate-kv-scales` with `900000000` KV
bytes, reached capacity 68,560 tokens, and required no capacity retry. The
installed hybrid path disabled calculated dynamic scales and checkpoint scales
were absent. Its warm PSS was `4537163776`, only `8344576` bytes below the final
baseline and far inside the noise band. Its retained full-contract failure was
from the superseded long fixture. FP8 is noncompetitive on memory; that retained
failure cannot be attributed to model quality.

The runner retained each correction rather than rewriting evidence. The
diagnostic result at `/tmp/dgx-moa-phase3-dktd_9pv/long-diagnostic.json`, SHA-256
`e165f0d227cfe2713a8bee901567eee23fe3931c2cfd960ca5a209ddf9cc0340`,
proved that the first long request parsed finite numbers but exhausted its
1,400-token cap after 700 items. The 2,400-token repeat still did not
self-terminate. The confirmed request enumerated 1 through 1100 and used an
`END` stop with a 5,000-token cap. A later `ENOSPC` attempt is preserved in
`candidates-verified.partial.json`: baseline's log records nvcc failing to write
a generated C file, then eager cache seeding also failed. Only derived
experiment cache directories were removed. The current harness now gates on 10
GiB free disk, but the confirmed artifact predates and did not exercise that
gate.

The ignored harness finished with 60 passing tests plus ignore-aware Ruff and
Python compilation. No prompt, model output, native tool argument value,
Authorization header, API key, or model weight is present in result JSON;
normalized output SHA-256 and content-free usage metadata are retained instead.
GPU used/free byte fields remained null, so no GPU percentage is claimed. This
remains undeployed development evidence; production was not started, stopped,
restarted, edited, or deployed.

## Phase 3 Selected Full-Stop Repetition and Resident Handoff — 2026-07-19

The authoritative independently reviewed result is
`/tmp/dgx-moa-phase3-1vjxvw8w/selected.json`, SHA-256
`fb2fc9261509acf4b51fad4b201b5210bd5a9bcb6c578006c45856e2692e7f9b`.
It has schema `phase3-selected-systemd-v1`, `passed=true`, no failures, selected
candidate `baseline`, and mechanism `A_full_systemd_stop_start`. The earlier
direct-process repetition at `/tmp/dgx-moa-phase3-kp3gj7ms/selected.json`,
SHA-256 `09fc8090771c4f665b8943c9e410b5e21595dc03bf422be833866f637b79655e`,
is retained as non-authoritative failed evidence: it proved exact process
teardown but did not execute the selected transient-systemd mechanism.

All three authoritative cycles used transient unit
`dgx-moa-dev-phase3-e6a0d509.service` with distinct invocations and PIDs
`2368754`, `2395854`, and `2442335`. In every row PID, PGID, and session ID were
equal; cwd, exact baseline argv, and unit-named cgroup were recorded; identity
revalidation passed immediately before stop; and the collected unit was absent.

| Cycle | ready | near-64K latency / backend tokens | PSS growth | post PGID PSS/RSS | post cgroup PSS/RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `938.3187154009938s` | `17.752001809887588s` / `63786` | `45056` bytes | `0` / `0` | `0` / `0` |
| 2 | `270.0974161340855s` | `17.56501955492422s` / `63786` | `2690048` bytes | `0` / `0` | `0` / `0` |
| 3 | `274.08552565216087s` | `17.564852259820327s` / `63786` | `2891776` bytes | `0` / `0` | `0` / `0` |

Each cycle passed five short cases, the expected near-limit needle,
the 1,100-item ascending numeric response, three native tool calls, restricted
code validation, and strict reviewer JSON. Port 19301 was unbound after every
stop. The post-third-cycle isolated gateway request on port 19300 returned 200
and advertised context length 65,536 for all three public aliases; only status
and configuration metadata were retained.

The final fingerprint records dev `6f8ab4d`, clean production `main` at
`c2a9af0`, unchanged model revision `27a8f16` and metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`,
all scoped ports unbound, and runtime count zero. The transient unit currently
has `LoadState=not-found` and MainPID zero. Results are content-free; the
independent review passed after rejecting and preserving the first mechanism
mismatch.

The tracked resident target change is undeployed. It requires only gateway and
executor, waits only for executor readiness, and verifies all optional resident
services/ports stopped on profile stop. Optional services retain `PartOf` for
cleanup. Lifecycle remains disabled with an empty unit map; a later
human-reviewed deployment is required for fixed/adaptive on-demand loading and
typed cold-role `503` behavior. Rollback restores the previous gateway,
executor, planner, and reviewer target requirements plus the prior script
arrays. No production process, unit, worktree, or deployment was mutated.

## Phase 3 Python Gateway Residency and Rust Decision — 2026-07-19

The authoritative five-minute content-free result is
`/tmp/dgx-moa-phase3-gateway-nzacnu_v/gateway-probe.json`, SHA-256
`4513ca3f6980f7fcfb81d7f7a360851325fcd7f90cddcb475f2612c17f2f6d62`.
It reports `passed=true`, no failures, 600 samples at 500 ms intervals, and
`300.02134908083826` seconds measured. The isolated gateway became ready in
`0.20371862896718085` seconds.

Peak process-group PSS/RSS was `48741376` / `56139776` bytes. Idle CPU was
`0.24998221036527596%` of one core. Loopback `/healthz` latency
p50/p95/p99/max was `1.5531240496784449` / `1.894660061225295` /
`2.1657010074704885` / `2.8134610038250685` ms. Schedule-drift
p50/p95/p99/max was `0.16089505515992641` / `0.685602892190218` /
`0.7837000302970409` / `1.084138872101903` ms.

The predeclared Rust rejection thresholds were PSS at most 256 MiB, CPU at most
1%, p99 at most 50 ms, and no remaining Python-attributable correctness gap.
The focused lifecycle/API/runtime-status recovery run passed `360` tests with
only the existing Starlette TestClient deprecation warning. All conditions
therefore reject a Rust rewrite for Phase 3; no crate or improvised prototype
was created. The gateway peak PSS is about 1.07% of the selected executor's
`4545508352`-byte warm owned PSS.

PID, PGID, and session were all `2478575`; identity was revalidated before the
exact group stop. Post-stop owned member count, PSS, and RSS were zero, the port
was unbound, and runtime process count was zero. Production stayed clean and
unchanged at `c2a9af0d6b5db8dd940842c56a7236ac867061ff`.

The first executable smoke root,
`/tmp/dgx-moa-phase3-gateway-r8uzjlp_`, is retained as non-authoritative failed
evidence: a probe-only log-directory ordering defect occurred before child
start, with the port still unbound. The corrected three-second smoke passed at
`/tmp/dgx-moa-phase3-gateway-rf8b296y/gateway-probe.json`, SHA-256
`4cdcf0f40e124818236d52175c9dd29a9e47880017a697d796752a260405d1da`.
Detailed responsibilities and limitations are in `docs/RUST_EVALUATION.md`.

## Phase 3 Publication Cross-check — 2026-07-19

The published topology comparison preserves the earlier measured rows rather
than substituting the later candidate run. The contemporaneous checked-in
validation record says the older three-role 64K resident profile recorded
`18525147136` bytes MemAvailable after planner start. No retained raw artifact
was available to the final independent review for that historical row. Task 10's
isolated executor-only lifecycle row recorded `65156329472` bytes warm-ready
MemAvailable, `4532602880` bytes owned PSS, and `4947398656` bytes owned RSS.
Its initial cold snapshot was `120509042688` bytes; the best post-unload settle
was `120564150272` bytes with owned PSS/RSS zero. Cold load, warm reload, and
executor unload were `942.7537190914154`, `273.00104479002766`, and
`1.361647605895996` seconds. The separate full-stop mechanism stops were
`1.146820979192853` and `1.118467804044485` seconds. Sleep-level-1 sleep/wake
times were `21.733480336144567` / `38.78946190699935` and
`2.1252455201465636` / `7.454574962845072` seconds; speed could not overcome
its memory/stability rejection.

Retained Phase 3 roots and their roles are explicit:

- `/tmp/dgx-moa-phase3-52ffwbov`: empty retained path from the pre-process
  tokenizer-count failure. Its cause comes from the contemporaneous run record
  and cannot be independently reconstructed from this raw root.
- `/tmp/dgx-moa-phase3-9l7a3ayp`: original mechanism failures plus the linked
  authoritative resumed result; the original was not rewritten.
- `/tmp/dgx-moa-phase3-dktd_9pv`: content-free long-fixture diagnostic.
- `/tmp/dgx-moa-phase3-7vfm7bzv`: candidate generations and partials, including
  the retained `ENOSPC` attempt, plus the authoritative confirmed selection.
- `/tmp/dgx-moa-phase3-kp3gj7ms`: quality-passing direct-process repetition
  rejected as non-authoritative because it did not run the selected transient
  systemd mechanism.
- `/tmp/dgx-moa-phase3-1vjxvw8w`: authoritative three-cycle transient-systemd
  repetition and gateway advertisement probe.
- `/tmp/dgx-moa-phase3-gateway-r8uzjlp_`: probe-only directory-order failure
  before child process start.
- `/tmp/dgx-moa-phase3-gateway-rf8b296y`: corrected three-second probe smoke.
- `/tmp/dgx-moa-phase3-gateway-nzacnu_v`: authoritative five-minute Python
  residency measurement.

Every selected physical result is content-free and reports exact teardown. Host
MemAvailable remains system-wide and noisy; GPU used/free bytes remain null;
the executor equality check is revision plus path/count/size/mtime metadata,
not a model-content hash. The checked-in resident target and lifecycle contract
are undeployed, and Phase 3 made no tracked trace-schema change.

### Serialized pre-commit publication gates

All eight commands ran sequentially and exited zero:

1. `uv run pytest -q`: `533 passed`, one existing third-party Starlette
   TestClient deprecation warning.
2. `uv run ruff format --check .`: 53 files already formatted.
3. `uv run ruff check .`: all checks passed.
4. `uv run mypy`: no issues in 28 source files.
5. `systemd-analyze --user verify systemd/*`: no output.
6. `for file in scripts/*.sh; do bash -n "$file"; done`: no output.
7. `scripts/audit-trace-completeness.sh data/traces`: 10/10 complete, zero
   incomplete/legacy, 100.0% mandatory-field completeness.
8. `git diff --check`: no output.

# MoA Runtime v2.0 release gate — 2026-07-22

The current `dev@7b9055f` release candidate passed the complete serialized
promotion gate before the `main` merge:

- `uv run pytest -q`: `803 passed`, with the existing third-party Starlette
  TestClient deprecation warning.
- Ruff format/check and strict mypy: clean across 75 formatted files and 38
  source files.
- `systemd-analyze --user verify systemd/*`, every `scripts/*.sh` `bash -n`,
  and `git diff --check`: clean.
- `scripts/audit-trace-completeness.sh data/traces`: 10/10 sessions complete,
  zero incomplete or legacy sessions, 100.0% mandatory-field completeness.
- `scripts/validate-self-evolving-runtime.py` passed with real 7-Zip 23.01.
  It verified bounded success/no-progress/duplicate termination, exact mocked
  replay, Evidence Graph restoration, governed Skill evaluation/canary/
  promotion/rollback, privacy redaction, capacity isolation, archive creation,
  integrity testing, idempotent replay, revocation/regeneration, empty-week and
  corrupt/archive-failure handling. The regenerated archive SHA-256 was
  `03fc6cab9f6c84b466cbd209bdcdbd5913daafeecf988b1edde44541c9884b4a`.

The temporary synthetic evidence root was
`/tmp/dgx-moa-v2-release-cHXe8L`. No production data was read or packaged.
Production-disabled gates remain disabled unless separately documented as
physically enabled.

## MoA Runtime v2.0 production promotion — 2026-07-22

PR `#42` merged the validated release evidence as `main@14fbd8f`. The production
worktree fast-forwarded from `ec389c5` with its existing untracked runtime
database preserved and no tracked-file changes. Restarting only
`dgx-moa-gateway.service` exercised the selected exact Executor stop/start. The
Executor entered activation at `13:26:42 KST`, exposed trustworthy shard counts
through `10/10`, became active at `13:42:18 KST`, and restored the resident
target with `67956502528` bytes MemAvailable at its readiness check. The Phase 3
65,536 context, one sequence, 1,700,000,000 KV bytes, 0.5 GPU utilization, and
MARLIN command remained unchanged.

Authenticated health, model-catalog, and ready checks passed. One primary
`dgx-moa` request sent immediately after port readiness returned `503` before
the lifecycle state reached ready; after the service and resident target became
active, the same production request returned exact `READY` with
`finish_reason=stop`. Gateway, Executor, and resident target were all active;
both services reported exit status zero and zero restarts. Model endpoints
remained loopback-only and the authenticated gateway remained the only tailnet
listener. Production-disabled Loop Engineering, Skills, policy, training,
weekly, replay-admin, and automatic-promotion gates were not enabled.

## Remote Judge and Runtime Knowledge foundations — 2026-07-22

The corrected v2 completion audit found that the earlier release did not
implement the specified NVIDIA NIM GLM-5.2 Remote Judge or a separate Runtime
Knowledge registry. The new development foundation adds both behind disabled
checked-in defaults.

Mock-transport Remote Judge tests passed strict evidence-package redaction,
OpenAI-compatible NIM request construction, `z-ai/glm-5.2` selection, strict
seven-criterion verdict parsing, read-only/no-tools behavior, timeout and
invalid-output classification, rate-limit retry, and the two-call request
budget. A Controller test proved the remote provider receives bounded tool
evidence without invoking the local model provider or Heavy Judge profile.

Runtime Knowledge tests passed immutable SQLite/WAL versions, missing lookup,
bounded active-latest retrieval, validation and explicit promotion, retrieval
evidence, conflict retention, approved supersession, rollback ancestry, and
database integrity. Trace and replay snapshots now retain Knowledge versions;
replay also retains prompt versions, routing configuration, provider-output
references, and all named comparison modes.

The serialized verification passed:

- `uv run pytest -q`: `813 passed`, with the existing third-party Starlette
  TestClient deprecation warning.
- `uv run ruff format --check .`: 79 files formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy`: no issues in 40 source files.
- `systemd-analyze --user verify systemd/*`, every shell script `bash -n`, and
  `git diff --check`: clean.

This is implementation and unit/mock evidence only. No NVIDIA credential was
present or required, no live NIM/GLM-5.2 request occurred, no production
Knowledge database was created, and neither feature is production-enabled.

## Governed evolution and complete weekly tree — 2026-07-22

The complete serialized development verification passed after this slice:

- `uv run pytest -q`: `821 passed`, with the existing third-party Starlette
  TestClient deprecation warning.
- `uv run ruff format --check .`: 81 files formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy`: no issues in 41 source files.
- `systemd-analyze --user verify systemd/*`, every shell script `bash -n`, and
  `git diff --check`: clean.
- `scripts/audit-trace-completeness.sh data/traces`: 10/10 sessions complete,
  zero incomplete or legacy sessions, and 100.0% mandatory-field completeness.

The development registry physically exercised Prompt candidate creation,
schema/replay/regression/Reviewer evaluation, approved canary, Executor-evidenced
helpful outcome, explicit promotion, and versioned rollback. High-impact unit
coverage rejects evaluation without Judge approval. The controller preserves its
schema, untrusted-data, safety, and authority layers around any active registered
role Prompt.

The weekly package tree now creates the specified Judge, preference, MCP,
Routing, Knowledge, Prompt, Policy, negative, index, quarantine, snapshot, and
report paths. Judge, Knowledge, Prompt, and Policy candidates route to separate
datasets rather than falling into generic Executor SFT output. Manifest identity
now includes Skill, Knowledge, Prompt, Policy, and Routing versions plus Judge
configuration.

`/tmp/dgx-moa-v2-foundations-L23Ogd/runtime/physical-validation.json` reports
`status=passed` using real 7-Zip 23.01. It includes bounded loops, exact replay,
Skill and Knowledge validation/promotion/retrieval, Prompt replay/canary/
promotion/rollback, sanitized mock Remote Judge evidence, complete role/loop
packaging, archive verification, idempotent replay, revocation/regeneration,
capacity isolation, and expected corruption/archive-creation failures. The
regenerated archive SHA-256 is
`6f0eb3500cced7b32dd85da7004ffa958fbf1a5c6ec2cd8162204895fefde2e2`.

This remains synthetic isolated evidence. It is not a live NVIDIA NIM call, a
real weekly production window, or authorization for automatic promotion,
training collection, retention apply, scheduler installation, or production
enablement.

## Selective Remote Judge delivery gate — 2026-07-22

The development controller now deterministically selects the Remote Judge for
the specified high-risk, security, schema/migration, concurrency/state-machine,
destructive, deployment, promotion, weekly-gold, disagreement, repeated-failure,
and test/claim inconsistency conditions. A mocked end-to-end gateway request
proved that the local Reviewer runs before the Judge, `approve` permits the
Executor draft, and `revise` suppresses that draft with a bounded HTTP 409
correction state. A separate streaming case proved that high-risk content is
rejected before upstream generation and must be retried non-streaming. Tool-call
turns are excluded from final-draft judgment. The default loop budget now
matches the two-call initial/recheck contract.

The serialized verification passed:

- `uv run pytest -q`: `826 passed`, with the existing third-party Starlette
  TestClient deprecation warning.
- `uv run ruff format --check .`: 81 files formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy`: no issues in 41 source files.
- systemd unit verification, every shell script `bash -n`, and
  `git diff --check`: clean.
- trace completeness: 10/10 sessions, zero incomplete or legacy sessions, and
  100.0% mandatory-field completeness.

This is mocked provider evidence. It does not satisfy the live NVIDIA NIM
physical matrix or authorize production Remote Judge enablement.

## Weekly Knowledge and Runtime Improvement reports — 2026-07-22

The isolated validator created versioned Runtime Knowledge, retrieved it,
recorded a helpful outcome and real last-retrieval timestamp, then generated
Skill, Knowledge, and aggregate Runtime Improvement JSON/Markdown reports. The
aggregate contains every required report section, leaves unavailable measured
inputs empty, and records zero automatic actions. Unit coverage separately
classifies a harmful active entry as a deprecation candidate requiring human
approval and verifies the additive SQLite metrics-schema migration.

`/tmp/dgx-moa-v2-maintenance-WzvpXt/runtime/physical-validation.json` reports
`status=passed` with `skill_knowledge_runtime_reports=true` using real 7-Zip
23.01. The regenerated archive SHA-256 is
`59d4ad30d4ab19994e8158262aa1930b77622c893f1d28e3121f9214b7cc2efc`.
This is isolated synthetic evidence, not a complete production weekly window or
authorization to enable the scheduler.

The complete serialized verification passed with `828 passed` and the existing
third-party Starlette warning, 81 files formatted, clean Ruff, strict mypy clean
across 41 source files, clean systemd/shell/diff checks, and 10/10 complete
traces with 100.0% mandatory-field completeness.

## Evidence-driven evolution candidate generation — 2026-07-22

The development generator requires at least two occurrences and explicit source
evidence, rejects signal/kind mismatches, sanitizes secrets and personal data,
and idempotently creates Prompt, Policy, Routing, or failure-handling candidates.
It never advances beyond `candidate`; generated Policy artifacts are always
high impact and therefore retain the Reviewer/Judge/canary/approval gates.

`/tmp/dgx-moa-v2-candidates-yXECD5/runtime/physical-validation.json` reports
`status=passed` and `policy_routing_candidate_generation=true`. The isolated run
generated both candidate kinds and proved they remained unpromoted while the
rest of the bounded runtime validator and real 7-Zip archive checks passed. The
regenerated archive SHA-256 is
`5d5c2c837225b0222afb8f34d028e52701baa56922bdf9b2de191d04e255c23f`.

The complete serialized verification passed with `830 passed`, the existing
third-party Starlette warning, 81 files formatted, clean Ruff and strict mypy
across 41 source files, clean systemd/shell/diff checks, and 10/10 complete
traces with 100.0% mandatory-field completeness.

## Knowledge and Judge metric wiring — 2026-07-22

The fixed label-free metrics endpoint now overlays measured Knowledge retrieval,
helpful/harmful outcomes, open conflicts, candidates, promotions, and
deprecations from the separate registry. Remote Judge completion events carry
only measured latency and token counts from the bounded provider ledger; later
confirmed false-approval/false-rejection and approval-timeout events increment
their fixed counters. Unit and endpoint tests cover each path without request,
prompt, path, or raw-failure labels.

The serialized gate passed with `832 passed`, the existing Starlette warning,
81 formatted files, clean Ruff and strict mypy across 41 source files, clean
systemd/shell/diff checks, and 10/10 complete traces with 100.0% mandatory-field
completeness. This is unit/mock evidence; no live NIM token accounting occurred.

## NVIDIA endpoint contract review — 2026-07-22

The current official NVIDIA GLM-5.2 reference identifies model
`z-ai/glm-5.2` and the OpenAI-compatible endpoint
`https://integrate.api.nvidia.com/v1/chat/completions`; the model reference also
lists structured output support. The provider now normalizes both a service-root
configuration and NVIDIA's documented `/v1` base URL to exactly one `/v1`.
Focused transport, Ruff, and strict mypy checks passed. This documentation and
mock transport check is not a credentialed live-provider validation.

The post-validator serialized gate passed with `832 passed`, the existing
Starlette warning, 82 formatted files, clean Ruff and strict mypy across 41
source files, clean systemd/shell/diff checks, and 10/10 complete traces with
100.0% mandatory-field completeness. External NIM and Discord gates remain
unmet, so this is not release approval.

## Structured role-artifact boundary — 2026-07-22

Reasoner persistence now excludes hidden reasoning and accepts only bounded
assumptions, constraints, conclusions, hypotheses, evidence references,
recommended actions, additional-agent recommendations, and a categorical
confidence. Planner responses now use a strict scope/dependency/risk/validation/
rollback/acceptance artifact, and Reviewer findings use the required structured
severity, evidence, location, impact, and correction fields. Legacy Reasoner
input is migrated without retaining its reasoning field; policy redaction of the
public `plan` field remains effective across the internal ordered-step schema.

The serialized gate passed with `833 passed` and the existing third-party
Starlette warning, 82 formatted files, clean Ruff, and strict mypy across 41
source files. User-systemd verification, every shell script `bash -n`, and
`git diff --check` exited zero. The checked-in trace audit reported 10/10
complete sessions, zero incomplete or legacy sessions, and 100.0% mandatory
field completeness.

The isolated self-evolving-runtime validator reported `status=passed` at
`/tmp/dgx-moa-v2-role-schema.PsSdu5/runtime/physical-validation.json` using real
7-Zip 23.01. The regenerated archive SHA-256 is
`8590690031b3c3b721ff6ac91b1672ae731888112fd00fb734d45f7f0cfd04ca`.
This remains isolated synthetic evidence; it is not a live NVIDIA NIM call, a
real Discord notification, a production weekly window, or release approval.

## MoA Runtime 2.0 local gap closure — 2026-07-22

The development package, FastAPI metadata, and persisted gateway default now
identify version `2.0.0`. Selective Remote Judge correction now stays within the
same request: one bounded Executor correction, targeted local Reviewer
validation, and at most one recheck. A deterministic revise-then-approve case
delivered only the corrected draft; a repeated revise case suppressed delivery
after exactly two Judge calls. Reviewer artifacts are present in both initial
and recheck evidence packages.

The declarative Policy schema now includes per-role `fail_closed`; a low-risk
Remote Judge outage with a Judge fail-closed policy did not use the Reviewer
fallback. High-impact generated Skills require Judge validation rather than a
Frontier substitute. New training objects are real Zstandard frames at the
specified `.json.zst` content-addressed path, with bounded legacy gzip reads.
Permitted NVIDIA evaluation traces produce categorical role-specific Judge
datasets, including only explicitly later-confirmed false approvals or false
rejections and no verbatim finding/correction prose.

The serialized gate passed with `837 passed` and the existing third-party
Starlette warning, 82 formatted files, clean Ruff, and strict mypy across 41
source files. User-systemd verification, every shell script `bash -n`, and
`git diff --check` exited zero. The checked-in trace audit reported 10/10
complete sessions, zero incomplete or legacy sessions, and 100.0% mandatory
field completeness.

The isolated self-evolving-runtime validator reported `status=passed` at
`/tmp/dgx-moa-v2-gap-closure.3JuQPn/runtime/physical-validation.json` using real
7-Zip 23.01. The regenerated archive SHA-256 is
`747720b74f06f00976f1fad3d3f99e912a20fe5d7f7564191713a5b3672af90b`.
Protected production configuration inspection exposed no values and found
Telegram configured, Discord unconfigured, and no NVIDIA endpoint/key variable.
Therefore the live NVIDIA matrix and real Discord delivery gate remain unmet;
this section is not release approval.

## Observation and training-schema coverage — 2026-07-22

The existing observation bus now publishes the previously dropped safe
Knowledge, Judge, tool-completion, failure, policy-block, and approval events.
Reasoner, Planner, and Executor starts are emitted by their real call paths.
The Judge projection retains verdict, risk, and recheck state while dropping
correction prose. Training events now enforce exactly `local`, `frontier`, or
`nvidia_nim`; required quality labels remain null when evidence is unavailable.

The serialized gate passed with `838 passed` and the existing third-party
Starlette warning, 82 formatted files, clean Ruff, and strict mypy across 41
source files. User-systemd verification, every shell script `bash -n`, and
`git diff --check` exited zero. The trace audit remained 10/10 complete with
100.0% mandatory-field completeness. The isolated validator reported
`status=passed` at
`/tmp/dgx-moa-v2-observation.cW1CDi/runtime/physical-validation.json`; its real
7-Zip 23.01 regenerated archive SHA-256 is
`68ea79a698275c630db10616801eff0c1ffc667a4b4650c4d869f4c67e52cd0a`.
This does not satisfy the still-missing live Discord or NVIDIA gates.

## Judge recheck and repository-policy boundary — 2026-07-22

The bounded correction flow now consumes its optional second Judge call only
when the first verdict both requests a recheck and contains an Important or
Critical finding. A Minor finding with `recheck_required=true` completed after
the one Executor correction and targeted Reviewer validation with one Judge
call; the Important case retained the two-call recheck. For `internal_only` and
`training_denied` repositories, the Judge package withholds objective, draft,
diff, specialist prose, and retrieved content while retaining only bounded
criterion/tool/test/build status metadata.

The serialized gate passed with `839 passed` and the existing third-party
Starlette warning, 82 formatted files, clean Ruff, and strict mypy across 41
source files. User-systemd verification, every shell script `bash -n`, and
`git diff --check` exited zero. Trace completeness remained 10/10 and 100.0%.
The isolated validator reported `status=passed` at
`/tmp/dgx-moa-v2-judge-policy.CpR521/runtime/physical-validation.json`; its real
7-Zip 23.01 archive SHA-256 is
`cbc20c4347d01002d4fe400cd58d26a916ba074eb8ac8604db4fbb7a1dc10ca7`.
Live NVIDIA evidence remains unavailable. Discord was subsequently removed from
the production release scope by explicit operator direction; the already
validated production Telegram path is the sole selected observation provider.

## Production observation scope and live NIM credential check — 2026-07-22

The operator explicitly discarded the Discord webhook requirement. Production
observation therefore remains Telegram-only with controls disabled; Discord is
unconfigured and is not a release gate. This changes scope, not evidence: the
existing isolated Discord transport tests remain compatibility coverage, while
the measured production Telegram identity, target, safe-send, and core-request
evidence remains authoritative.

A protected 0600 local `nim_api` credential was supplied for the live NVIDIA
matrix. An initial operator-side runner incorrectly passed the complete
`NVIDIA_API_KEY=...` assignment as the bearer value and received HTTP 401. The
file was then parsed as an environment assignment; its value matched NVIDIA's
documented `nvapi-...` contract, model-catalog authentication succeeded, and
real GLM-5.2 verdicts were returned. No credential value was printed, copied to
Git, or installed in production.

The first full run stopped at the bounded-correction fixture because GLM-5.2
returned `reject` with one required edit and `recheck_required=true` for an
unsupported production-health claim. The fixture incorrectly allowed only
`approve_with_edits` or `revise`, even though the required strict schema and
specification also allow a correction-bearing `reject`. A focused repeat
confirmed high-confidence rejection, failed grounding/completeness, passing
test consistency, three findings, one required edit, and 709 total tokens. The
validator expectation was corrected to accept the bounded non-approval verdict
family only when required edits are present. This is partial live-provider
evidence until the corrected full matrix passes.

All credential-independent gates were rerun after the observation-scope change:

- `uv run pytest -q`: `839 passed`, with the existing third-party Starlette
  deprecation warning.
- Ruff format/check and strict mypy: clean across 82 formatted files and 41
  source files.
- User-systemd verification, every shell script `bash -n`, and
  `git diff --check`: clean.
- Trace completeness: 10/10 sessions, zero incomplete or legacy sessions, and
  100.0% mandatory-field completeness.
- The isolated self-evolving-runtime validator reported `status=passed` at
  `/tmp/dgx-moa-v2-final.2WwWd4/runtime/physical-validation.json` using real
  7-Zip 23.01. Its regenerated archive SHA-256 is
  `dd9b96960a165b86e4197dbf1fd44b028592b5da85d68506d686456cb9efcd0d`.

These results isolate the remaining promotion blocker to completion of the
corrected live Judge matrix.

Subsequent live runs authenticated consistently and produced the expected
individual outcomes across attempts: grounded evidence was approved; an
unsupported production claim, a failed test reported as success, and a missing
acceptance criterion were not approved; the unsupported health claim produced a
bounded correction; and the minimal corrected draft was approved with all seven
criteria passing, zero findings, zero edits, and 268 total tokens. The provider
prompt was tightened to require evidence-linked findings and bounded edits for
non-approval, forbid hidden reasoning/prose outside the schema, and limit
rechecks to Important/Critical corrections. Requests now set `max_tokens=1024`
and best-effort deterministic `seed=0`; focused mock/unit coverage verifies both
parameters.

The sustained gate still failed. Multiple calls exceeded 120 seconds twice and
correctly surfaced `JudgeTimeout`; the latest checkpoint at
`/tmp/dgx-moa-live-nim.ygb2Zi/validation.json` recorded
`approve_valid_response` before the next case timed out. Other attempts reached
the correction or corrected-recheck assertion but did not complete the entire
matrix in one run. The validator now writes an atomic, sanitized checkpoint
after every completed case so provider failures cannot erase measured progress.
After a later recovery probe returned `approve` with all criteria passing and
386 total tokens, the full matrix was retried; it again completed the first
approval case and then exhausted both 120-second attempts on the unsupported-
claim case. This confirms intermittent single-call recovery does not satisfy the
sustained release gate.
No production credential was installed, Remote Judge remains disabled, and
`main`/production promotion remains blocked until one complete live matrix
passes under the specified 120-second timeout and one-retry contract.

## OpenCode Go specialist routing and Judge replacement — 2026-07-22

The operator superseded the NVIDIA NIM design and selected OpenCode Go. The
protected repository-root `opencode_api` file was mode 0600, contained one raw
credential line rather than an environment assignment, remained ignored, and
was never printed or copied into Git. A credentialed `/v1/models` request
returned exact IDs `deepseek-v4-pro`, `deepseek-v4-flash`, and `glm-5.2`.

Credentialed specialist validation initially exposed two real compatibility
failures. OpenCode Go rejected the local vLLM strict `json_schema` request with
HTTP 400; after adapting it to `json_object`, the first Planner output exhausted
800 completion tokens with `finish_reason=length`. At 4096 tokens it completed
but did not follow the Pydantic field shapes until the sanitized schema itself
was prepended as a system constraint. These failures are retained as rejected
evidence and are not production claims.

After the bounded adapter and role-specific token floors were implemented,
`scripts/validate-specialist-routing.py` passed both real structured calls:

- Planner `deepseek-v4-pro`: valid `PlannerPlan`, 20.884 seconds, 529 prompt
  tokens, 1540 completion tokens, 2069 total tokens.
- Reviewer `deepseek-v4-flash`: valid `ReviewResult`, 2.496 seconds, 478 prompt
  tokens, 120 completion tokens, 598 total tokens.

The local Planner and Reviewer remain the preferred providers when real
inference readiness and queue/cost prediction permit. The DeepSeek calls are
only the pinned remote path for cold, loading, unhealthy, or slower local
specialists while one local warm-up proceeds independently.

The replacement OpenCode Go GLM-5.2 Judge completed the entire credentialed
matrix in one run at
`/tmp/dgx-moa-opencode-validation.WilZSu/remote-judge.json` (SHA-256
`9194dd6c23197db57e74d1443a23dad977854c9aa0c3537a58dbe8f04a8d7d7a`).
Grounded evidence and the corrected recheck were approved. Unsupported claims,
failed-test contradictions, missing acceptance evidence, and the unsupported
health claim were rejected with one evidence-linked finding and one bounded
required edit. Local enforcement blocked the third call for the correction
request. The sanitized checkpoint reports `status=passed`.

The final automated gate passed with `846 passed` and the existing third-party
Starlette warning. Ruff format/check, strict mypy across 41 source files,
`git diff --check`, and the secret-pattern diff scan were clean. The isolated
self-evolving-runtime validator reported `status=passed`; its real 7-Zip 23.01
archive SHA-256 is
`a3c1ec39adb4b0c04f6443caaafc0fcd733dcfbea262afc08e3c589ce010db93`.
Archive inspection confirmed all five new routing paths:
`specialist-residency-routing.jsonl`, `local-vs-remote-routing.jsonl`,
`warmup-decisions.jsonl`, `eviction-decisions.jsonl`, and
`latency-prediction.jsonl`.

The first production cold smoke returned HTTP 200 through remote
`deepseek-v4-pro` in 36.584 seconds while reusing local load generation 15. The
first local load attempt failed with a measured CUDA OOM and was recorded as
`specialist_warmup_failed`; systemd's bounded retry subsequently brought the
Planner endpoint up without affecting the resident Executor. A direct real
inference readiness check then exposed an insufficient 8-token probe: it ended
with `finish_reason=length` and null content. The same probe at 256 tokens ended
with `finish_reason=stop` and content `READY` in 6.2 seconds. The readiness token
limit was raised to the physically successful value before final production
acceptance.

After readiness recovery, the next synthetic architecture request correctly
selected local Planner twice but both 1500-token calls returned no structured
content, so the gateway failed closed with HTTP 502. A direct local
`PlannerPlan` inference at 4096 tokens then completed in 37.070 seconds with
`finish_reason=stop`, a schema-valid result, 46 prompt tokens, 1438 completion
tokens, and 1484 total tokens. The local Planner completion ceiling was raised
to the physically validated 4096-token bound before repeating the warm-route
production smoke.

The repeated production smoke then completed HTTP 200 through local Planner.
Routing recorded `READY`, `local_within_cost_margin`, predicted local/remote
completion of 30.0/25.75 seconds, actual local completion of 47.078 seconds,
and warm-up benefit. The post-restart metrics also exposed that predictive
prewarming a role already in `READY` was incorrectly counted as a reused
started/completed warm-up. The scheduler was corrected to return `not_needed`
without creating a task or event for an already-ready specialist.

After that correction, a fresh gateway process started with zero specialist
metrics. A READY Planner architecture request completed HTTP 200 through local
Planner in 51.738 seconds, while warm-up started/completed/failed/unused metrics
all remained zero. This confirms predictive classification no longer creates a
false warm-up for a resident specialist.

Reviewer production coverage used an initially stopped local service. A forced
code-review request completed HTTP 200 through remote `deepseek-v4-flash` in
4.771 seconds with routing reason `local_not_ready` and reused load generation
13. Local loading continued independently and passed the real inference probe
after 168.115 seconds, producing `specialist_warmup_completed` and logical state
`READY`. A subsequent forced review saw that READY local provider but selected
remote with reason `remote_predicted_faster`; it completed HTTP 200 in 7.016
seconds. Throughout these Planner and Reviewer checks, the gateway, Executor,
and Reasoner remained ready; no current request changed providers after
dispatch. The final automated gate contains `847 passed`, clean Ruff, and clean
strict mypy across 41 source files.

## MoA Runtime v2.0 completion audit rerun — 2026-07-22

The post-deployment completion audit reran `uv run pytest -q`: `847 passed`
with the existing third-party Starlette TestClient deprecation warning. The
isolated `scripts/validate-self-evolving-runtime.py` run used real 7-Zip 23.01
and reported `status=passed`; its regenerated archive SHA-256 was
`1de6b4fb91cc64cd60a99c758da14a657f1865b364a0ee27803a2a9ed8006e3c`.

Protected production configuration inspection exposed no secret values. It
confirmed adaptive lifecycle, OpenCode Go Remote Judge and specialist routing,
and Telegram observation enabled; Loop Engineering, Runtime Skills, Runtime
Knowledge, runtime evolution, declarative policy, training collection, weekly
jobs, retention apply, replay administration, and observation controls remain
disabled. Gateway, Executor, Planner, and Reviewer units were active, `/readyz`
was ready, all three local model services plus the external Reasoner were ready,
and the Remote Judge reported available. Consequently the OpenCode provider
slice is production-complete, but the full self-evolving-runtime objective is
not complete until its remaining documented physical production gates pass.

## Live-provider Loop Engineering shadow gate — 2026-07-22

A loopback-only shadow gateway used the production `main` model endpoints and
OpenCode credential while isolating its state, Skill, Knowledge, evolution,
training, and weekly stores under `/tmp`. Lifecycle mutation, Frontier, and
observation delivery were disabled. Loop Engineering, Runtime Skills, Runtime
Knowledge, runtime evolution, declarative policy, training collection, and the
weekly scheduler were enabled only in that shadow process.

The first clean local-provider run exposed a real completion bug: the Reasoner,
Executor, and local Reviewer completed and the Reviewer returned `approved`, but
post-synthesis metadata was applied only inside the conditional post-synthesis
review block. Because the pre-synthesis review had already approved the request,
that block was skipped; the HTTP 200 response was correct but completion
evidence remained empty and the loop stayed open.

Moving metadata application after the optional review block preserved the
review requirement while closing the missed path. The identical fixed-code run
returned HTTP 200 with exact `LOOP_GATE_OK`, persisted two acceptance-evidence
items, retained `review_status=approved`, and terminated the loop `SUCCESS` with
`phase=completed` and `final_status=completed`. It also recorded a declarative
policy decision, a bounded empty Knowledge retrieval, non-empty Evidence Graph,
and a training candidate without exposing secrets. The full automated suite
then passed with `849 passed`; an additional regression case covers the
pre-synthesis-approved path.

## Production Loop Engineering and review guard gate — 2026-07-22

PR `#50` deployed the completion-evidence fix as `main@04c11ce`. The protected
production environment enabled Loop Engineering, and the controlled gateway
restart performed the selected exact Executor full stop/start. The unchanged
65,536 context, one sequence, 1,700,000,000 KV bytes, 0.5 GPU utilization, and
MARLIN baseline loaded all 10/10 shards and passed its inference readiness
probe. One request at the reconciliation boundary correctly returned retryable
503 while generation 13 was still `load_queued`; the retry ran with Executor
READY.

That retry used remote Reviewer while the local Reviewer was `LOADING`, returned
HTTP 200, persisted two completion-evidence items, retained Reviewer approval,
and terminated the production loop `SUCCESS` with `phase=completed`,
`final_status=completed`, and observation status `ok`. The remote call completed
in 13.063 seconds and reused the independent local warm-up.

The local Reviewer initially failed engine initialization and continued through
the remote provider as designed. Its bounded service retry later passed 4/4
shards and the real readiness probe. A subsequent request exposed a guard race:
the remote response and local READY transition both succeeded, but the lifecycle
transition invalidated the local evaluation-guard transition ID and produced
HTTP 502. The stuck guard was cleared only after the request ended and Reviewer
READY was verified.

PR `#51` fixed that race as `main@0ba545d`: remote specialist calls no longer
claim a local evaluation guard, while a selected local specialist remains
protected by its existing active-request lease. The deterministic regression
forces a Reviewer READY transition during the remote call. The serialized gate
passed with `850 passed`, clean Ruff, strict mypy, systemd and shell validation,
10/10 complete traces, and 100.0% mandatory trace fields.

The controlled production rerun overlapped remote Reviewer calls with local
generation 16 warm-up and returned HTTP 200 without the prior guard error. The
Reviewer rejected deliberately incomplete release evidence with Important and
Critical findings, so the Loop correctly remained in `correction` rather than
claiming success. The evaluation guard was false after the request. Local
Reviewer generation 16 then completed 4/4 shards, passed the real inference
probe, and reached logical `READY`. Gateway, Executor, Reasoner, resident target,
and Remote Judge remained ready/available throughout the final check.

## Runtime context and declarative Policy production gate — 2026-07-22

A loopback-only shadow used the production Executor endpoint and isolated
registries. One human-approved test Skill, one validated test Knowledge entry,
and one bounded policy rule were active only in that shadow. A real
`dgx-moa-fast` request returned exact `CONTEXT_GATE_OK`, selected
`validation.evidence@1.0.0` and `validation.measured-evidence@1`, matched policy
`bounded-validation`, reduced the loop tool budget to 5, retained completion
evidence, and kept observation status `ok`. Evidence Graph nodes included the
Skill selection, Knowledge entry, and hashed policy decision.

Production then enabled empty governed Skill and Knowledge registries plus
declarative Policy `production-v1`. The controlled restart again completed the
unchanged Executor 10/10 load and inference readiness probe; the already warm
Reviewer also passed its 4/4 load and readiness probe before resident target
restoration. An ordinary production request returned HTTP 200 with exact
`PROD_CONTEXT_OK`, zero Skill/Knowledge selections, one unmatched
`production-v1` decision, and observation status `ok`. The empty Skill metrics
database existed and the production Knowledge SQLite integrity check passed.

A second production request marked `destructive_operation=true` without the
required approval. It was rejected before model execution with HTTP 403,
`code=approval_required`, `phase=blocked`, `final_status=blocked`, and Loop
termination `PERMISSION_REQUIRED`. The evidence recorded matched rule
`destructive-operation-approval` and required approval
`destructive-operation`. No Skill, Knowledge, Prompt, or Policy candidate was
automatically promoted.

## Production Evolution and exact Replay gate — 2026-07-22

PR `#54` added active Prompt provenance to `SessionState` and trace metrics as
`artifact_id@version`, so Replay snapshots retain the exact Prompt selected for
each role. Focused evolution/trace/replay tests passed `28 passed`; the full
suite passed `850 passed` with clean Ruff formatting/check, strict mypy over 42
source files, systemd verification, shell syntax checks, 10/10 complete traces,
and 100.0% mandatory trace fields.

The reviewed change was merged and deployed as `main@cbcb011`. The protected
production environment enabled only the authenticated admin API and an empty
Evolution registry. Training Collection and Weekly Packaging remained disabled.
SQLite `integrity_check` returned `ok`, with zero evolution artifacts and zero
canaries; no Prompt, Policy, or Routing candidate was promoted.

An operator-authenticated production exact regression replay used a bounded
Executor snapshot containing `prompt.executor@1`. It returned exact mocks,
`deterministic_claim=true`, no nondeterminism sources, and snapshot SHA-256
`f52007548ab34989bbeb3b7d301735226cae06a7a8357b8e6112028c07054924`. A
non-exact routing-policy comparison returned HTTP 409 because the admin API has
no internal live-provider callback. Training and Weekly admin probes each
returned HTTP 404 with their disabled-feature errors.

The deployment restart used the selected exact Executor full stop/start. Its
unchanged baseline loaded 10/10 shards with context 65,536, one sequence,
1,700,000,000 KV bytes, 0.5 GPU utilization, and MARLIN, then passed the real
`/v1/models` readiness probe. Resident restoration subsequently loaded the
Reviewer through its own four-shard readiness sequence and real readiness
probe. A final authenticated `dgx-moa-fast` inference returned exact
`DEPLOY_READY`. `/readyz` reported the resident profile ready with Executor,
Reviewer, and Reasoner ready, Planner intentionally stopped, and the separate
Remote Judge available.

## Policy trace and Weekly storage audit — 2026-07-22

PR `#56` fixed the pre-model Policy-block trace boundary. Production request
`prod-policy-trace-145d1ce` returned HTTP 403 with `approval_required`, Loop
termination `PERMISSION_REQUIRED`, zero agent decisions and invocations, a
persisted `route_selected` event, and no missing trace fields. Deployment
`main@145d1ce` restored the unchanged Executor baseline through 10/10 shards and
the real readiness probe, then restored Reviewer through 4/4 shards and its
readiness probe. Gateway, Executor, Reviewer, and resident target were active.

The completion audit also found that Training enforced its 10 GB reserve while
Weekly archive staging did not, and the production scheduler supplied placeholder
registry versions. The fix adds the same configurable reserve before archive
staging, content-derived SHA-256 versions for Skill, Knowledge, Prompt, Policy,
and Routing state, exact model/Judge configuration in idempotency, concrete
schema versions, and measured candidate analytics for the Runtime Improvement
report.

The isolated current-code run at
`/dev/shm/dgx-moa-weekly-audit.iO2kWt/run/physical-validation.json` has SHA-256
`d4d970925477b6750cf8bac1e88dc7fb395ad3967c8880ff96e1005601c2bbf2` and
`status=passed`. It used real 7-Zip 23.01, verified and regenerated archive
SHA-256 `244cf964bb36dee3ee4da91ab7f8e82dc1cce611644c3a9bb38eb03eaa7e5d79`,
and rejected a deliberately impossible Weekly reserve before staging. The full
suite passed `853 passed`; Ruff, strict mypy over 41 source files, shell syntax,
systemd verification, and diff checks were clean. Production Training and
Weekly jobs remain disabled because only 1.3 GB is free against the 10 GB
reserve; no production data was collected or packaged.

## Routing cost redaction regression — 2026-07-22

The production trace audit found that the generic dictionary-key redactor
treated the `tokens` segment in
`remote_api_cost_per_million_tokens_usd` as a credential and replaced the
measured cost with `[REDACTED]`. The shared key classifier now redacts exact
credential names and credential-name suffixes, including camel-case forms,
while retaining cost, token-count, and redaction-count measurements. Synthetic
API key, Authorization, cookie, access-token, and client-secret regressions
remain redacted in both trace and training sanitization paths. The full suite
passed `855 passed`; Ruff formatting/check, strict mypy over 41 source files,
and diff checks were clean.

PR `#58` deployed the fix as `main@fe46d5c`. Gateway, Executor, and the
partially loading Reviewer were fully stopped before resident restoration; the
Reviewer stop timeout was cleared without changing its dynamic cold-residency
policy. The protected Executor retained context 65,536, one sequence,
1,700,000,000 KV bytes, 0.5 GPU utilization, and MARLIN, loaded 10/10 shards,
and passed the real `/v1/models` readiness probe. Gateway, Executor, and the
resident target were active while Planner and Reviewer remained cold.

The first deployment-boundary request returned retryable HTTP 503. After
`/readyz` reported Executor ready, the authenticated `dgx-moa-fast` retry
returned HTTP 200 with exact `REDACTION_READY`. Its persisted trace contained
two numeric `remote_api_cost_per_million_tokens_usd` values (`0.0`, `0.0`), no
Authorization or API-key marker, and no missing trace fields.

## Hermes authentication repair and production Training/Weekly enablement — 2026-07-23

The 2026-07-22 16:49 `HTTP 401: User not found` was traced to Hermes' stale
direct OpenRouter fallback after Codex OAuth returned 429; it was not an
OpenCode Go runtime response. The invalid OpenRouter credential and fallback
were removed, Hermes compression was pinned to `custom:dgx-moa-agent` with
`dgx-moa-fast`, and the gateway restarted with zero restarts. A physical
compression request returned exact `HERMES_COMPRESSION_OK`; no later Hermes
journal entry matched `401`, `User not found`, OpenRouter, or authentication
failure. A cold-Reviewer production request returned HTTP 200 and exact
`HERMES_RUNTIME_OK` remotely in 4.5815 seconds while local warm-up generation 17
continued independently. The local Reviewer subsequently passed `/v1/models`
and a real inference probe before normal idle eviction.

After explicit operator approval, `pip cache purge` removed 4,582 files and
14,882.0 MB. Measured root free space increased from about 1.33 GB to
16,222,420,992 bytes, above both configured 10 GB reserves. The protected
production override enabled Training Collection and Weekly jobs, mapped only
`moa-production` to `training_allowed`, and kept `external_output_permitted`
false. Hermes now supplies stable `X-Workspace-ID: moa-production` and the
production workspace path; `external-api` remains unknown.

The gateway restart performed the selected exact Executor stop/start. The
unchanged baseline loaded its 44.30 GiB checkpoint with context 65,536, one
sequence, 1,700,000,000 KV bytes, 0.5 GPU utilization, and MARLIN. Both
`/v1/models` and an actual inference probe returning exact `EXECUTOR_READY`
passed; `/readyz` then reported Executor and Reasoner ready with cold optional
specialists and Remote Judge available.

Authenticated activation request `training-weekly-activation-20260723` returned
HTTP 200 with exact `TRAINING_WEEKLY_READY`. Its v3 trace recorded workspace
`moa-production`, policy `training_allowed`, and explicit eligibility. The
collector physically wrote one event, one candidate, one request link, two
Zstandard content-addressed objects, and SQLite WAL state; `integrity_check`
returned `ok`. The intentionally minimal probe's candidate was rejected by the
quality gate and the trace honestly remained `degraded`; it was not promoted.
Metrics reported one created and one excluded candidate. The in-process Seoul
scheduler is enabled, with first production Skill maintenance scheduled for
2026-07-26 03:00 and packaging for 2026-07-27 02:00. No scheduled package,
retention apply, archive export, or model training was triggered during this
enablement.

## Local-first specialists and deterministic Korean Telegram cards — 2026-07-23

The Hermes observability benchmark exposed two distinct remote-selection paths.
READY Planner selection initially chose local, but `complete_specialist()` sent
the human-readable session ID into the UUID-backed lifecycle lease instead of
the current request UUID. Lease acquisition failed and the router recorded
`local_readiness_race` before dispatching OpenCode Go. READY Reviewer calls were
sent remotely because the fixed 45/5-second local/remote estimates preferred
remote. The three sessions still used the local Reasoner three times and local
Executor five times, but all four Planner/Reviewer calls were remote; mandatory
Frontier failure then caused Hermes to switch the client-visible final response
to its Codex fallback.

The correction passes `SessionState.current_request_id` to lifecycle leases and,
at that deployment, selected every inference-probed READY or BUSY local
specialist. The later 2026-07-24 busy-routing validation below supersedes the
BUSY selection rule. Provider switching after dispatch remains prohibited.
Runtime Knowledge and the separate GLM-5.2 Judge remain enabled. Executor
prompting now requests concise output by default without forcing a language and
still expands when the objective explicitly asks for detail.

Telegram rendering is deterministic Python formatting, not an LLM call. It uses
Korean process titles, labels, known state/provider/routing translations, and
includes model/provider provenance, residency, predictions, actual latency,
tokens, warm-up, failure, and terminal information from the existing safe
allowlist. It does not translate model-generated content. Discord rendering
remains unchanged. The production override disables prompt and Reasoner artifact
forwarding so process telemetry stays compact and payload-free.

Current credentialed, synthetic-only OpenCode Go checks returned schema-valid
Planner `deepseek-v4-pro` in 13.653 seconds with 1,496 total tokens and Reviewer
`deepseek-v4-flash` in 2.170 seconds with 546 total tokens. A bounded GLM-5.2
Judge case returned `approve` in 3.667 seconds with 451 total tokens. Focused
specialist/observation/controller tests passed `71 passed`; the full suite
passed `857 passed` with the existing third-party Starlette warning. Ruff
format/check, strict mypy over 41 source files, and `git diff --check` were clean.

Production `main@acc55d8` retained the protected Executor baseline and passed
`/v1/models` plus an actual inference returning exact `EXECUTOR_READY`.
The first deployment-boundary request returned HTTP 503 while lifecycle
reconciliation overlapped a systemd activation. The stable retry returned HTTP
200 with exact `COLD_FALLBACK_OK`: its Reviewer event pinned OpenCode Go
`deepseek-v4-flash`, reason `local_not_ready`, residency `LOADING`, and load
generation 19 while the local service continued loading independently. After
the Reviewer loaded 18.09 GiB and a real inference returned exact
`REVIEWER_READY`, a second evidence-bearing review returned HTTP 200 with exact
`LOCAL_REVIEW_OK`; its provider event pinned `dgx-moa-reviewer`, reason
`local_ready`, residency `READY`, and generation 20. Runtime counters then
reported one local call, one remote call, one cold miss, and zero Telegram
errors. Hermes has no configured fallback providers, so it can no longer
replace a runtime result with Codex after a gateway failure.

The same deployment exposed a lifecycle control false negative: blocking
`systemctl start` exceeded the driver's short command timeout while the healthy
Reviewer continued loading, recording `start_command_failed` and
`specialist_warmup_failed`. The driver now submits exact systemd starts with
`--no-block`, recognizes `activating` as an expected transitional state, and
continues polling until the inference health probe succeeds. Exact blocking
service stop remains unchanged. Regression coverage verifies the exact argv,
systemd activating-state parsing, and transition from activating through a
successful inference probe to READY. The full suite passed `859 passed` with
the existing third-party Starlette warning; Ruff and strict mypy over 41 source
files were clean.

After deploying the lifecycle correction as `main@bb625e3`, the production
generation-21 cold review returned HTTP 200 with exact `ASYNC_COLD_OK` through
`deepseek-v4-flash` while Reviewer remained `LOADING`. The same singleflight
generation stayed active for 152.110 seconds, completed only after the service
readiness inference succeeded, and emitted `specialist_warmup_completed`
without a start-command or warm-up failure. The next review returned HTTP 200
with exact `ASYNC_LOCAL_OK` through `dgx-moa-reviewer`, reason `local_ready`,
state `READY`, generation 21. Restart-scoped metrics measured local 1, remote 1,
cold miss 1, warm-up started 1, completed 1, failed 0. Live observation sent 32
events with zero drops and zero Telegram errors. Gateway, Executor, Reviewer,
and Hermes were active; `/readyz` reported Executor, Reviewer, and Reasoner
ready with Remote Judge available.

## Codex goal continuation and language preservation — 2026-07-23

The reported Codex goal run created eight separate runtime sessions for one
tool loop. The final session remained `phase=executing`, had no completion
criteria or termination reason, and recorded `finish_reason=stop`; the client
therefore treated the Executor's English objective summary as goal completion.
Responses text-part content had also been stored as a Python list
representation instead of the contained text. Six accumulated tool results and
one pending call per prior session confirmed that remapped continuation call
IDs prevented the existing exact-owner lookup from joining the turns.

The gateway now extracts text parts through one shared helper. When a
sessionless continuation has a remapped call ID, it reuses a single
unfinished same-token, same-objective owner and rejects ambiguous matches. It
also clears the superseded pending ID and releases the continuation lease.
Executor constraints preserve the actual objective's language, including an
objective loaded through a wrapper, and prohibit treating a `/goal` file read
or summary as completion without verified criteria. Existing independent
Planner, Reviewer, and Frontier tasks remain parallel; dependency-ordered
Reasoner, Executor routing, and final synthesis remain sequential. The full
suite passed `861 passed` with the existing third-party Starlette warning;
Ruff, strict mypy over 41 source files, and `git diff --check` were clean.

Production `main@4b208b3` then ran a sessionless Responses `/goal` probe whose
English wrapper referenced a synthetic Korean objective. Four turns retained
one session with four steps and three tool results. The Executor first called
`read_goal`, then called `status_check` instead of returning an objective
summary. After the matching validation result reported all synthetic criteria
passed, the only final text was Korean: `이제 완료되었습니다.` The persisted
session had no pending tool calls. Gateway, Executor, Hermes, and `/readyz`
remained healthy; Planner and Reviewer stayed dynamically cold.

## Operator API-key control and workspace-less goal routing — 2026-07-23

The pre-change production authentication check found that every configured
general key could call both inference and `/v1/admin/runtime-status`. The
gateway now stores named key records in the mode-0600 state database, separates
`general` inference authority from `admin` inference and operator authority,
enforces expiry, revocation, cumulative request/token limits, and a configured
maximum of three active admin keys. The tailnet-only `/admin/api-keys` operator
page and its management endpoints require an admin key. Per the explicit
operator requirement, authenticated admins can retrieve plaintext key values;
the page uses `Cache-Control: no-store` and emits secret-free management audit
events. Database copies and backups therefore remain secrets. The later
operator-session validation below supersedes the original in-memory login.

Production `main@61840bf` returned HTTP 403 when a general key requested an
admin endpoint and HTTP 200 for the configured operator key. A temporary
general key round-tripped its plaintext value through the admin-only endpoint,
completed one inference request, returned HTTP 429 at its request limit,
accepted an admin update, and returned HTTP 401 after revocation. The dashboard
reported 19 task/model rows and 16 actual role/model rows. Its HTML returned
HTTP 200 with `no-store`; the state database remained mode 0600 and the
management audit contained no secret. The full suite passed `869 passed` with
the existing third-party Starlette warning; Ruff, strict mypy over 42 source
files, and focused 33-test security coverage were clean.

The repeated workspace-less Codex goal failure was separate from history
compaction: after the objective read succeeded, absent repository metadata let
the Executor search filesystem roots and unrelated home/environment paths
until its budget expired. Executor policy now allows one inspection of the
current directory and uses it when writable, while prohibiting root, unrelated
home, environment, and system-path repository searches. A production
`dgx-moa-fast` goal continuation without repository headers was offered both
`inspect_current_directory` and `scan_filesystem_root`; it selected only
`inspect_current_directory`, returned `finish_reason=tool_calls`, and persisted
`identity_quality=client_unspecified`, `phase=executing`, one pending tool call,
and no terminal status. It therefore neither scanned roots nor treated the
objective read as completion.

## Revoked managed API-key deletion — 2026-07-23

The operator UI previously sent the revoke endpoint again for an already
revoked key, which correctly returned HTTP 404 but offered no permanent-delete
path. Managed keys can now be deleted only after revocation; environment-backed
keys remain protected because deleting their database row would only make them
reappear at restart. Historical usage remains available for audit graphs.

The full suite passed `869 passed` with the existing third-party Starlette
warning; Ruff and strict mypy over 42 source files were clean. Production
`main@dea5b4e` deleted the revoked managed key `validation-1784809472` with HTTP
204, omitted it from the next key listing, and returned HTTP 404 for a repeated
delete. The updated UI exposed the permanent-delete confirmation flow. Gateway
and Hermes remained active, and Hermes retained PID 1796553.

## Masked key console, dated usage, and operator sessions — 2026-07-23

The key list no longer returns plaintext values. The UI displays the existing
masked value until an operator selects the eye or copy control, which calls the
administrator-only reveal endpoint. Usage queries accept one key and an
inclusive native-calendar date range. Operator login exchanges the credential
for a random 30-day session; only its SHA-256 digest is stored server-side, and
the browser receives an HttpOnly, SameSite-Strict cookie. Rotation, revocation,
and logout invalidate associated sessions. The deployment has no Tailscale
HTTPS certificate, so `Secure` is conditional on a future HTTPS ingress;
traffic remains within the encrypted tailnet.

The full suite passed `869 passed` with the existing third-party Starlette
warning; Ruff, JavaScript syntax checking, and strict mypy over 42 source files
were clean. Production `main@f03fe59` returned HTTP 204 for login and HTTP 200
for cookie-only administrator access. The cookie carried `Max-Age=2592000`,
`HttpOnly`, and `SameSite=strict`, contained no operator credential, and the key
list contained no plaintext field. On-demand reveal matched the configured
operator key without logging it. The July date query returned only `operator`
usage. Logout returned HTTP 204 and the same cookie then received HTTP 401.
Gateway and Hermes remained active, and Hermes retained PID 1796553.

## Authenticated localhost gateway access — 2026-07-23

The gateway remains bound specifically to `100.125.239.72:9000`. A
socket-activated systemd proxy now listens specifically on
`127.0.0.1:9000` and forwards to the configured gateway bind target; no
`0.0.0.0:9000` listener or second gateway process was introduced. The proxy
uses the existing bind host/port environment, requires the gateway service, and
exits after five idle minutes while its socket remains available.

The full suite passed `870 passed` with the existing third-party Starlette
warning; `systemd-analyze --user verify`, Ruff, and strict mypy over 42 source
files were clean. Production `main@cbe61e5` returned HTTP 401 rather than a
connection failure for unauthenticated loopback requests, HTTP 200 for an
authenticated loopback `/v1/models` request, and HTTP 200 for the same
authenticated tailnet request. The loopback socket and proxy were both active
with service type `exec`. Gateway and Hermes were not restarted, and Hermes
retained PID 1796553.

## API-key form validation and unlimited quotas — 2026-07-23

The operator form previously discarded the gateway's structured
`error.message` and attempted to parse every error response as JSON. A
validation failure therefore appeared only as `Unprocessable Content`, while
an upstream HTML error produced `Unexpected token '<'`. The UI now lowercases
key names while typing, displays structured validation messages, and falls back
to the HTTP status when a response is not JSON. Blank quota creation and update
values map to database `NULL`, which is the existing unlimited representation.

The full suite passed `870 passed` with the existing third-party Starlette
warning; JavaScript syntax checking, Ruff, and strict mypy over 42 source files
were clean. Production `main@a484b9d` created the attempted `Reici` input as
active general key `reici` with request limit 5,000 and token limit 1,000,000.
A temporary key created with both limits omitted returned `NULL` for both,
then revoked and deleted with HTTP 204. The updated UI contained lowercase
normalization, non-JSON error handling, and explicit `공란=무제한` labels.
After the deployment restart, gateway, loopback socket, and loopback proxy were
active; Hermes was not restarted and retained PID 1796553.

## Daily stacked model-usage chart — 2026-07-23

The operator usage endpoint now groups actual model invocations and measured
tokens by API key, UTC day, and model. The existing key and calendar range
filters feed an OpenCode-style vertical stacked bar chart with a stable model
legend and per-segment token/call tooltip. Invocation-level provider cost is
not present in the usage database, so the chart reports tokens rather than
inventing cost.

The full suite passed `870 passed` with the existing third-party Starlette
warning; JavaScript syntax checking, Ruff, and strict mypy over 42 source files
were clean. Production `main@dc9b04f` returned five July daily-model rows for
the `operator` key across four models and 26,553 measured tokens; every row was
pinned to the requested key. The deployed page contained the stacked plot,
model legend, and daily token title. Gateway, loopback socket, and loopback
proxy were active; Hermes was not restarted and retained PID 1796553.

## Unknown MCP server recovery — 2026-07-23

An unavailable MCP server no longer terminates the correction turn with HTTP
409. Exact repeats of this failure request replanning while the existing
duplicate-failure boundary remains unchanged for other tools. The next Executor
request omits `read_mcp_resource` and explicitly directs local paths to an
available native file or shell tool, preventing retries with guessed server
names or altered URIs.

The full suite passed `871 passed` with the existing third-party Starlette
warning, and targeted Ruff checks were clean. Production `main@beae5dc`
received two identical `MCP_SERVER_UNAVAILABLE` observations in session
`validation-mcp-recovery-7409647564`. The Responses API returned HTTP 200 in
2.304 seconds with an `exec_command` function call. Persisted events included
`replan_requested` and `tool_temporarily_unavailable`; the session remained
`phase=executing` with no final status. Gateway and both authenticated
tailnet/loopback listeners were active. Hermes was not restarted and retained
PID 1796553.

## Operator console backing model names — 2026-07-23

The operator console now lists the configured Executor, Planner, and Reviewer
service names beside their backing model repositories. The same label is used
in usage legends and tooltips, and comes from the active model configuration
rather than a duplicated UI mapping.

The full suite passed `871 passed` with the existing third-party Starlette
warning; targeted Ruff and JavaScript syntax checks were clean. Production
`main@42ba003` returned HTTP 200 with
`dgx-moa-executor -> RedHatAI/Qwen3-Coder-Next-NVFP4`,
`dgx-moa-planner -> cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit`, and
`dgx-moa-reviewer -> CohereLabs/North-Mini-Code-1.0-w4a16`. The deployed HTML
contained the catalog and shared model-label rendering. Gateway and both
tailnet/loopback listeners were active. Hermes was not restarted and retained
PID 1796553.

## Codex interrupted-goal stream recovery — 2026-07-23

The Codex failure was a transport-retry deadlock rather than an unreadable
attachment. The native `exec_command` had already resolved the goal objective,
but a downstream stream interruption permanently terminated the engineering
loop as `CLIENT_CANCELLED`; five Codex reconnects then reused the same blocked
session. Running sessions now resume after transport cancellation, while
operator-terminated sessions remain terminal. Replayed goal-file reads are
compacted before observation, and MCP read/list tools remain suppressed after
an unavailable-server failure even when a native fallback resolved it.

The full suite passed `873 passed` with the existing third-party Starlette
warning, and targeted Ruff checks were clean. After production
`main@fd315cb`, the original failed session
`ee8b0c96-e22a-4d40-bc0d-83998d9452bf` returned HTTP 200 with
`response.completed`, no `response.failed`, and only an `exec_command` tool
call. It recorded `engineering_loop_resumed` and suppressed
`read_mcp_resource`, `list_mcp_resources`, and
`list_mcp_resource_templates`. Persisted state was `phase=executing`,
`final_status=null`, and `termination_reason=null`. Gateway and both
tailnet/loopback listeners were active. Hermes was not restarted and retained
PID 1796553.

## Short operator model labels — 2026-07-23

The operator console keeps full model repository identifiers in its
administrator API but renders the requested compact names in the role catalog,
usage legend, and tooltips: `Qwen3-Next`, `Nemotron-30B`, and
`North-Mini-30B`.

The full suite passed `873 passed` with the existing third-party Starlette
warning; targeted Ruff and JavaScript syntax checks were clean. Production
`main@356b8fa` returned HTTP 200 for the deployed console, contained all three
compact labels, and used the shared `modelLabel` renderer for the catalog.
Authenticated gateway listeners remained available on tailnet and loopback.
Hermes was not restarted and retained PID 1796553.

## Official Codex CLI goal-loop compatibility — 2026-07-23

The 22:35 KST request was accepted and streamed normally until the gateway
restart at 22:37:53 KST, which coincided with the model-label deployment.
Cloudflare recorded `unexpected EOF`; the resumed session then exhausted five
reconnections. New authenticated drain controls reject new Responses and Chat
work with retryable HTTP 503 while allowing active requests to finish.
`scripts/restart-gateway-drained.sh` waits for
`active_request_count=0` before restarting the gateway and cancels drain mode
without restarting when its bounded wait fails.

An unmodified shallow clone of `https://github.com/openai/codex.git` at
`808d3c2702ce8eae007c457aa930e7c3b68dd5f6c` was built with
`cargo build -p codex-cli --bin codex`. The built CLI ran in a disposable
Ubuntu 24.04 Docker sandbox with a read-only root, all Linux capabilities
dropped, `no-new-privileges`, and only isolated `CODEX_HOME` and workspace
mounts writable. The first physical run exposed an unsupported model-generated
`read_file` call; the client had advertised only `exec_command` and goal/status
tools. Responses translation now maps that exact incompatible read to a
shell-quoted `exec_command`, and resolved goal history replaces the wrapper
prompt with the loaded objective rather than repeatedly asking the model to
read the same file.

The final physical run read `goal-objective.md` once, created `result.txt`,
ran `test "$(cat result.txt)" = CODEX_CLI_GOAL_OK` with exit code 0, and
returned the concise Korean completion message. The Docker process exited 0;
an independent host-side assertion returned `artifact=PASS`. Persisted events
recorded one `goal_objective_resolved`, one `goal_history_compacted`, three
successful tool results, and a final `finish_reasons=["stop"]`. Ruff formatting,
Ruff lint, and strict mypy over 43 source files were clean; the full
pre-deployment suite passed `876 passed` with the existing third-party
Starlette warning.

Production `main@5e950bb` was deployed after a database-backed check reported
`active_request_count=0`; only `dgx-moa-gateway.service` was restarted.
Authenticated drain verification then returned HTTP 200 for start/status and
cancel, while a new Responses request returned the expected HTTP 503
`gateway_draining`. Hermes was not restarted and retained PID 1796553.

The same built official Codex CLI then ran against production
`127.0.0.1:9000` in a fresh disposable Docker sandbox. Gateway session
`6f3d722f-a1cc-49cc-a7b8-8ef427152b97` recorded exactly one
`goal_objective_resolved`, one `goal_history_compacted`, and three
`exec_command` results with exit code 0. Its final finish reason was `stop`,
the gateway completed the final turn in 2.622 seconds, the Docker process
exited 0, the host artifact assertion passed, and the client received the
Korean completion message `완료되었습니다.` No MCP-resource call or repeated
goal-file read occurred.

## Codex progress-only stop recovery — 2026-07-24

Production session `e6205d45-765f-4671-854c-73d15fa38944` resolved a
950-character goal and successfully ran four inspection tools, but its final
upstream turn returned `finish_reason=stop` with only
`다음 도구 작업을 준비합니다.`. The session still had no completion criteria,
final status, or termination reason and retained 135,870 tokens plus 26 tool
calls. This was an invalid Executor completion, not a request-budget or
transport failure.

Responses translation now rejects a progress-only `stop`, retries it once
inside the same request with an explicit tool-or-evidence constraint, and
returns a structured incomplete-response failure if the retry is also empty.
Actual tool turns identify the selected tool instead of using the ambiguous
generic marker. Resolved goal-file rereads are converted to a bounded
continuation observation, unsupported elevation arguments are removed under
approval-never execution, and the Executor instruction requires the tool call
in the same response. The measured 1,000-character aggregate tool-observation
budget was also raised to a bounded 16,000 characters: it had truncated a
1,038-character source file and caused repeated `cat`, `head`, `od`, and
`xxd` inspections.

The isolated official Codex CLI validation used a 526-byte Korean goal. It
read the goal once, observed the full 1,038-byte `event_feed.py`, created
`test_event_feed.py`, and ran four standard-library tests with exit code 0.
Gateway session `a1245c3e-71ff-4dcc-a4a5-a9af307f86f4` recorded one resolved
goal, five successful tool results, and a concrete Korean final report; an
independent host run of the generated tests also exited 0. The full suite
passed `885 passed` with the existing third-party Starlette warning. Ruff
formatting, Ruff lint, strict mypy over 42 source files, and `git diff --check`
were clean.

Production `main@ca84bcc` was fast-forwarded after the pre-deployment checks.
The drain API reported no active request before each gateway-only restart.
Both loopback and tailnet `healthz`, `readyz`, and authenticated model checks
returned HTTP 200; Hermes remained active with PID 1796553. The first restart
also exposed a false-negative in the deployment script: its health check ran
before the approximately two-second gateway startup completed. The script now
retries the same health contract for up to 30 seconds instead of reporting a
successful restart as failed and inviting a duplicate restart.

An official Codex CLI run then targeted production `127.0.0.1:9000` from a
fresh isolated workspace. It read the Korean objective, created `result.txt`,
validated the exact `PRODUCTION_GOAL_OK` content with exit code 0, and returned
a concrete Korean completion report rather than a preparation marker. Gateway
session `f44ca58f-a31a-4e0d-9771-a767e6bfaf21` recorded six successful tool
results and seven completed streams. An independent host assertion returned
`artifact=PASS`; post-run loopback and tailnet health/readiness checks remained
HTTP 200.

## Absolute MCP path and streaming Judge recovery — 2026-07-24

Production session `2af02fc4-ddfe-46f5-942a-7e3af9a8bfe2` resolved the
5,532-character objective, then issued five parallel `read_mcp_resource`
calls against `codex_apps` with plain `/Users/...` paths. The Responses
compatibility adapter handled `file://` URIs but not absolute path strings, so
all five calls reached the unavailable MCP resource reader. The resulting
correction required selective Remote Judge validation. Chat correctly returned
`judge_non_stream_required`, but the Responses client repeated the same
streaming request five times and ended with a disconnected stream.

The existing local-file compatibility path now accepts absolute paths as well
as `file://` URIs and shell-quotes them into `exec_command`. The Responses
adapter also handles `judge_non_stream_required` once inside the original
request: it reruns Chat without streaming, preserves keepalives, then converts
the buffered Chat result through the existing Responses event translator.

The full suite passed `887 passed` with the existing third-party Starlette
warning; Ruff formatting, Ruff lint, strict mypy over 42 source files, and
`git diff --check` were clean. A physical request using
`read_mcp_resource(server=codex_apps, uri=/Users/test/work/docs/STATE.md)`
returned one `exec_command` call containing
`cat -- /Users/test/work/docs/STATE.md`; no MCP call reached the client. A
physical high-risk streaming request recorded
`responses_judge_non_stream_retried`, selected the Remote Judge, and returned
one fail-closed Responses result rather than a 409 reconnection loop. An
official Codex CLI Goal then read its objective and state document, implemented
the sanitizer, created five standard-library tests, ran them twice with exit
code 0, and returned a concise Korean evidence report. An independent host
test run also passed.

Production `main@cc77b57` was deployed through a zero-active-request drain;
the readiness retry completed successfully and only
`dgx-moa-gateway.service` restarted. Production request
`prod-absolute-mcp-map-20260724` returned an `exec_command` for the plain
absolute MCP path and a completed Responses event. Official Codex CLI session
`2460544c-66a2-49ea-bdaa-ae80f2458c6f` then resolved the Korean objective
once, read `docs/STATE.md`, implemented the sanitizer, created and ran four
tests with exit code 0, and returned a Korean evidence report. It recorded six
successful tool results and seven completed streams; an independent host test
run passed. Loopback and tailnet health/readiness remained HTTP 200, and Hermes
was not restarted and retained PID 1796553.

## Frontier usage visibility and operator OAuth flow — 2026-07-24

The production state database contained 15 completed Frontier collaborations
from 2026-07-21 with 220,699 prompt, 12,182 completion, and 232,881 total
tokens. It contained no `model_invocation_usage` row for `role=frontier`
because those calls predated the 2026-07-22 invocation-metering change. The
historical events have no API-key attribution, so they were not guessed into a
per-key graph. Later records contained 58 `FRONTIER_AUTH_ERROR`, 40
`FRONTIER_CIRCUIT_OPEN`, and two invocation-limit outcomes.

The operator model catalog now includes the configured Codex OAuth Frontier
model even when the selected API key has zero metered Frontier calls. The
daily stacked chart shows exact selected-range and per-model token totals; each
nonzero segment exposes model, exact token count, and invocation count through
its hover title.

Authenticated administrators can start the official `codex login
--device-auth` flow for only the configured primary or secondary profile. The
browser streams the one-time URL/code without receiving OAuth credentials, the
subprocess inherits the existing credential-safe environment allowlist,
concurrent use of the same profile is locked out, and file-backed credentials
remain mode `0600`. The checked-in gateway unit grants write access only to the
existing external Codex profile root. Focused API-key tests passed `3 passed`;
the combined Frontier/API-key suite passed `23 passed`. Ruff lint/format,
JavaScript syntax validation, strict mypy on the two changed source modules, and
`systemd-analyze --user verify` passed.

## Admin routing and bounded Codex custom-provider client — 2026-07-24

`/admin` now serves a no-store, same-origin operator landing page with API Key
Control routing, runtime status, read-only chat, and workspace-write agent
modes. The backend resolves agent workspaces under `~/code`, requires a Git
workspace, rejects traversal, binds a resumed thread to its original mode and
workspace, and permits one active Codex turn per gateway instance. It launches
an isolated Codex CLI with the existing Responses custom-provider shape,
loopback gateway URL, context 65,536, no tool network access, no login shell,
and a shell environment allowlist that excludes the provider credential.

The browser receives only bounded NDJSON events for thread identity, final
agent messages, command/status, file-change status, errors, and measured token
usage. A synthetic reasoning event was not emitted, and a credential-shaped
command fragment was redacted. The custom provider uses the dedicated general
`admin-codex-cli` key rather than an operator credential.

The focused admin dashboard test passed `1 passed`; the API-key and systemd
unit tests passed `11 passed`. Ruff, format, strict mypy, JavaScript syntax, and
`git diff --check` passed. The wider 32-test run reported `29 passed, 3 failed`:
all failures were existing Frontier failover assertions that expected only the
primary profile while the inspected implementation attempted the secondary
profile. A real Codex CLI config-parse probe emitted `thread.started` and
attempted the configured synthetic `http://127.0.0.1:1/v1/responses` endpoint;
the 12-second timeout intentionally stopped its retry loop. No production
gateway request, repository edit by Codex, deployment, or service restart was
performed.

## Busy-provider and Frontier context fallback — 2026-07-24

The specialist router previously reported a resident role as `BUSY` but still
treated that state as locally eligible. It also calculated local and remote
completion estimates without applying them to provider selection. The corrected
policy sends ordinary BUSY Planner/Reviewer calls directly to their pinned
OpenCode Go provider. A READY local specialist is selected only when its
queue-plus-inference estimate is within the configured cost-adjusted margin;
explicit local-only policy remains the sole queueing exception.

When Frontier is enabled, a new session arriving while the local Executor has
an active lease no longer acquires another local Executor or open-stream lease.
The entire request, including orchestration retries, final synthesis, and Judge
correction, is pinned to a remote logical Executor. Codex OAuth runs read-only,
cannot invoke host tools for that request, and can return only bounded text or
client tool-call descriptions. Streaming callers receive ten-second keepalives
while the non-streaming OAuth turn runs; a terminal remote failure becomes a
structured stream error instead of an unexplained disconnect.

Before local final-synthesis dispatch, the gateway also asks the served
Executor's real `/tokenize` endpoint for `count` and `max_model_len`. If prompt
plus requested output exceeds that measured window after normal preparation,
the undispatched local lease is released and the call is pinned to Frontier.
Tokenizer unavailability does not fabricate a result or silently claim that
the context fits. A physical loopback Executor probe returned
`executor_context_fits=true` for a 32-token output request.

OAuth failover now tries isolated `primary`, isolated `secondary`, and host
`default` profiles before considering the paid fallback. The strict Executor
schema initially failed a real Codex request because optional/defaulted schema
properties were not all listed as required. Making every top-level and tool-call
property required fixed the physical request: the full configured profile chain
returned exact Korean `정상`, `finish_reason=stop`, model `gpt-5.6-sol`, provider
`default`, with no paid fallback. The inspected primary profile was usage
limited and secondary profile authentication was invalidated.

The root `openrouter_api` file had mode `0600`, but its value did not have the
OpenRouter key shape and the real endpoint returned HTTP 401. The value was
never printed or copied to production. Synthetic transport validation proved
that Claude `anthropic/claude-sonnet-4.6` is called only after eligible OAuth
failure, excludes reasoning from the response, preserves the request language
and tool definitions, records exact provider/cost provenance, and never places
the key in the payload. Production therefore retains a working free OAuth
fallback and will fail closed at the paid tier until an operator supplies a
valid ignored key.

Ruff passed over gateway and tests, strict mypy passed over 44 source modules,
and the full automated suite passed `905 passed` with the existing third-party
Starlette warning. The focused busy/failover set passed 30 tests. The abandoned
isolated dev gateway on loopback port 19000 was identified by PID, process
group, and working directory before termination; production port 9000 and the
role-model services were not restarted during this validation.

Production `main@45192c1` was deployed after a zero-active-request drain. Only
`dgx-moa-gateway.service` changed PID, from `2812477` to `3150695`; Hermes
retained PID `1796553`, Executor `1709495`, Planner `2969174`, and Reviewer
`2969170`. Loopback and tailnet health returned HTTP 200, both administrator
pages returned HTTP 200, the API-key list omitted raw values, and its deployed
HTML contained `Qwen3-Next`, `Nemotron-30B`, and `North-Mini-30B`.

The production concurrency probe held a real local `dgx-moa-fast` request until
`active_requests=1`, then submitted a distinct Korean session. Both requests
returned HTTP 200; the second returned exact `BUSY_FALLBACK_OK`. Its stored
events reported `provider=frontier`, `routing_reason=local_busy`, and completed
OAuth provenance `default`. Executor active requests returned to zero after
both responses. The post-deployment gateway journal contained no traceback,
error, exception, 401, or disconnect entry in the inspected window.

## Codex goal loop-budget recovery — 2026-07-24

Production session `54981845-e11a-4522-9991-da99bc2b3de1` failed at
05:28 KST with `loop_budget_exhausted`, followed by five client reconnects that
received generic backend failures from the already-blocked session. Persisted
state showed 27 of 30 tool calls still available, but zero of two Frontier
calls remained. The configured Frontier client permitted three invocations per
task, so its third collaboration attempt reached the lower loop budget first
and blocked the whole session.

The loop model, settings default, production configuration, and example
configuration now all allow three Frontier calls. A regression assertion
requires the default loop budget to cover the Frontier task limit. The focused
suite passed `34 passed`; the full suite passed `906 passed` with the existing
third-party Starlette warning. Ruff lint/format and strict mypy over 45 source
modules passed.

The operator-supplied ignored `openrouter_api` replacement had the expected
OpenRouter key shape and mode `0600`. The official current-key endpoint
returned HTTP 200, and a two-token physical
`anthropic/claude-sonnet-4.6` completion returned HTTP 200. The same bytes were
installed in the production worktree with mode `0600`; the active gateway was
not restarted because the fallback reads the key file at invocation time.

Production `main@724c4cd` was deployed after the authenticated drain reached
zero active requests. Only the gateway PID changed, from `3150695` to
`3245266`; Hermes remained `1796553`, Executor `1709495`, Planner `2969174`,
and Reviewer `2969170`. Health and model discovery passed. A physical
`dgx-moa-orchestrated` Responses stream returned HTTP 200 with exactly one
`response.completed` and no `response.failed`; its persisted loop state loaded
three remaining Frontier calls. The inspected post-deployment journal contained
no traceback, exception, disconnect, budget exhaustion, backend error, or 401.

## Recovered Codex tool continuation and sanitized event feed — 2026-07-24

Production session `86981ee6-3f75-40f7-92f5-b9b2c92a66a4` failed at 05:40 KST
with `loop_budget_exhausted`, then the client exhausted five reconnects. The
session contained one earlier `NONEXISTENT_PATH` tool failure followed by
successful tool results. The Responses adapter nevertheless treated that
historical active failure as if every later tool continuation had just failed,
re-entered the Reasoner four times, and exhausted the iteration budget.

The adapter now compares the failure count before and after the current
continuation. A newly observed failure still blocks continuation, while a
successful result after a historical failure remains in the same tool loop. A
production failed-then-successful function-output probe returned HTTP 200 for
both requests with `reasoner_started=1`, `iteration=1`, and no termination.
Production `main@6f1ed54` was deployed after drain; only the gateway PID changed
from `3245266` to `3268815`.

The isolated `SanitizedEventFeed` prototype uses only Python standard-library
storage and synchronization. It emits monotonic sequence, UTC timestamp, role,
stage, status, and recursively sanitized public messages; bounds message
complexity and size; evicts the oldest retained event at capacity; and keeps
subscriber cursors and returned values independent. It adds no listener,
dependency, systemd unit, or production event-feed endpoint.

The actual local Planner was `dgx-moa-planner`
(`cyankiwi/Nemotron-Cascade-2-30B-A3B-AWQ-4bit`, displayed as
`Nemotron-30B`). The local Executor path was `dgx-moa-executor`
(`RedHatAI/Qwen3-Coder-Next-NVFP4`, displayed as `Qwen3-Next`). The first
remote Reviewer attempt returned invalid structured output while the local
Reviewer warmed independently, so Codex OAuth Frontier `gpt-5.6-sol` supplied
the bounded architecture/code-review fallback. Once ready, the real local
Reviewer `dgx-moa-reviewer`
(`CohereLabs/North-Mini-Code-1.0-w4a16`, displayed as `North-Mini-30B`)
returned `verdict=approved` with zero findings.

The Reviewer readiness investigation found that this Cohere template requires
`chat_template_kwargs.reasoning=false`; the unrelated `enable_thinking` flag
left all generated text in hidden reasoning and returned `content=null`. The
provider now applies the template's real flag for this served parser, with a
regression assertion on the outbound body.

The six focused feed tests cover normal events, recursive masking, capacity
eviction, subscriber isolation, invalid and oversized input, and concurrent
publish/read over 200 events. The final full suite passed `913 passed` with one
third-party Starlette warning and exit code 0. Ruff lint/format passed over 82
files, and strict mypy passed over 45 source modules; both exited 0.

Production `main@a250309` was deployed after the authenticated drain reached
zero active requests. Only the gateway PID changed from `3268815` to `3333227`;
Hermes remained `1796553`, Executor `1709495`, Planner `2969174`, and Reviewer
`3277489`. A post-deployment request through the deployed provider sent the real
Reviewer template flag `reasoning=false`, received non-empty public content,
and parsed `verdict=approved` with zero findings. The production checkout's six
feed tests and the healthcheck both exited 0. The inspected post-restart gateway
journal contained no traceback, exception, disconnect, loop-budget exhaustion,
backend error, 401, or 500 entry.

## Codex long tool-loop interruption recovery — 2026-07-24

Production session `46756fe5-ea16-4b1e-bdbe-e057f1741c2b` ended in
`LoopAdmissionError` after 19 Executor turns. Its 22 measured model invocations
consumed the bounded 250,000-token engineering budget even though 15 of 30 tool
calls and three of four iterations remained. Five client reconnects then
received the generic blocked-session backend error. Cumulative Responses
history also caused 19 distinct tool results to be recorded 117 times after
older deduplication facts rotated out of the 12-item observation window.

The controller now deduplicates cumulative tool results against the persisted,
100-item tool-execution window; the 30-call loop limit therefore fits within
that window. Codex wrapper argument errors beginning with
`failed to parse function arguments` are failures even when the wrapper reports
exit code 0. The bounded token allowance is 1,000,000 while iteration, tool,
role-call, wall-time, and external-cost bounds remain unchanged. Executor
instructions now prohibit MCP discovery for local paths, invented
`write_stdin` session IDs, interpreting the anonymous `external-api` trace
identity as a directory, and descending into unrelated nested repositories for
AGENTS.md.

A persisted session blocked by the former token ceiling is recoverable only
when its measured invocation total is below the new configured ceiling. The
controller restores exactly `configured - observed` tokens, preserves all
other remaining budgets, and resets the wall-clock checkpoint. A session that
has already consumed the new ceiling stays blocked.

Regression tests replayed 20 cumulative tool results and recorded exactly 20
executions, classified the observed string-session-ID wrapper error as a
failure, consumed the former full 250,000-token allowance without termination,
and proved both eligible and ineligible stored-session recovery. The focused
set passed `289 passed`; the full suite passed
`918 passed` with one third-party Starlette warning. Ruff lint/format and
strict mypy over 45 source modules exited 0. The real local
`dgx-moa-reviewer` returned `verdict=approved` with zero findings.

Production `main@f3e2443` was deployed after authenticated drains. Across the
two gateway-only restarts the gateway PID changed from `3333227` to `3511166`
and then `3514831`; Executor remained `1709495`, Planner `3491920`, Reviewer
`3491942`, and Hermes `1796553`. The deployed configuration reported a
1,000,000-token loop budget. A production-code reconstruction of the failed
250,000-token state recovered exactly 750,000 tokens, cleared termination, and
entered replanning; the six production regression cases and healthcheck exited
0. The live model manifest contained the corrected local-path and integer
session-ID instructions. The inspected post-restart journal contained no
traceback, exception, disconnect, loop-budget exhaustion, backend error, 401,
or 500 entry.

## Planned-work progress stop recovery — 2026-07-24

Production session `f8333df3-2bd9-4bef-975a-617c1cd59d48` did not disconnect
or exhaust a runtime budget. Its persisted state remained `phase=executing`
with five planned steps, deferred review, no termination reason, 892,679
tokens, and 27 tool calls available. Nevertheless, after an Executor turn
returned the Korean Planner progress sentence with `finish_reason=stop`, the
Responses adapter recorded `stream_completed` and `session_ended` with
`status=completed`.

The completion gate previously required a resolved objective before enforcing
tool continuation. Direct Codex Goal sessions can already have an active
engineering loop, plan, and deferred review while `resolved_objective` is
empty. The gate now also rejects a no-tool stop in that measured state until
review is approved. It reuses the existing single same-request retry and does
not add another orchestration loop. The observed progress sentence is also
recognized directly so an equivalent stateless response cannot be presented as
completion.

The focused reproduction passed five tests, including the exact Korean text
and an API-level planned-state retry that emits the next `exec_command` tool
call. Ruff format/lint passed, strict mypy passed over 45 source modules, and
the full suite passed `920 passed` with the existing third-party Starlette
warning; all commands exited 0. The real local `dgx-moa-reviewer`
(`CohereLabs/North-Mini-Code-1.0-w4a16`) returned `verdict=approved`, with no
important findings or residual risks.

Production `main@6761d45` was deployed after the authenticated drain reached
zero active requests. Only the gateway PID changed, from `3514831` to
`3540190`; Executor remained `1709495`, Planner `3491920`, Reviewer `3491942`,
and Hermes `1796553`. The production healthcheck and five deployed regression
cases exited 0. The inspected post-restart gateway journal contained no
traceback, exception, disconnect, loop-budget exhaustion, backend error, 401,
or 500 entry.

## Docker client quality matrix and context-fit recovery — 2026-07-25

OpenCode, Codex, and the installed Hermes were run in separate read-only,
capability-dropped Docker containers against five newly initialized Git
fixtures each. Every fixture had a failing starter, immutable task tests, a
separate hidden verifier, and a source-only change gate. These are the final
functional runs:

| Harness | Task | Run | Harness/test/hidden exit | Seconds |
| --- | --- | --- | --- | ---: |
| OpenCode | rate-limiter | `20260724-qm-final3` | `0/0/0` | 428.034 |
| OpenCode | atomic-store | `20260724-qm-final4` | `0/0/0` | 213.797 |
| OpenCode | dag-runner | `20260724-qm-final1` | `0/0/0` | 239.729 |
| OpenCode | webhook-verifier | `20260724-qm-contract4` | `0/0/0` | 171.664 |
| OpenCode | log-report | `20260724-qm-final8` | `0/0/0` | 254.556 |
| Codex | rate-limiter | `20260724-qm-final9` | `0/0/0` | 460.207 |
| Codex | atomic-store | `20260724-qm-final11` | `0/0/0` | 169.612 |
| Codex | dag-runner | `20260724-qm-final11` | `0/0/0` | 209.850 |
| Codex | webhook-verifier | `20260724-qm-contract6` | `0/0/0` | 137.393 |
| Codex | log-report | `20260724-qm-final13` | `0/0/0` | 244.026 |
| Hermes | rate-limiter | `20260724-qm-final26` | `0/0/0` | 197.382 |
| Hermes | atomic-store | `20260724-qm-final44` | `0/0/0` | 342.922 |
| Hermes | dag-runner | `20260724-qm-final28` | `0/0/0` | 249.707 |
| Hermes | webhook-verifier | `20260724-qm-contract4` | `0/0/0` | 268.365 |
| Hermes | log-report | `20260724-qm-final28` | `0/0/0` | 335.578 |

All 15 score artifacts report `status=passed`; all ten checks per row are true:
container isolation, harness exit, public and hidden validation exits, Korean
final output, clean terminal, source-only change, unchanged tests, and recorded
tool evidence. The original `gpt-5.6-sol` baseline passed four of the same five
strict task verifiers; its webhook implementation accepted invalid
configuration and failed that hidden contract check.

A blind Claude Sonnet 4.6 review (`gen-1784896025-QJZxLw4MPyEqwKO7E6Mx`)
scored the then-current task sets `214/250` for the baseline, `206/250` for
Codex, `202/250` for OpenCode, and `181/250` for Hermes. It exposed real
contract gaps that the public tests did not cover. A bounded follow-up
(`gen-1784899732-P74uQoBC5xfpCu6mP5Cx`) cost `$0.175179` and reached its
8,000-token output limit; no further paid review was used. The common quality
contract now rejects unused unbounded state and undocumented monotonic-input
restrictions (`a246909`), retains bounded implementation evidence for review
(`119dfd9`), and recognizes shell-wrapped and installed-Hermes validation
evidence (`9f5e986`).

Codex run `20260725-qm-codex-terminal1` then reproduced a terminal failure after
the implementation and tests had passed. Session
`6cb4fb70-44be-44ef-ac90-13e0d074ed45` showed repeated local Reviewer HTTP 400
responses, consumed its Reviewer-call budget, and emitted a failed Responses
terminal that Codex retried five times. The Reviewer journal supplied the root
cause: its physically served context was 8,192 tokens while the request
contained at least 8,192 input tokens plus output.

Tokenizing the exact failed-session evidence measured:

| Review evidence cap | Prompt tokens | Requested output | Total |
| ---: | ---: | ---: | ---: |
| 16,000 characters | 8,419 | 1,500 | 9,919 |
| 10,000 characters | 5,026 | 1,500 | 6,526 |
| 8,000 characters | 4,034 | 1,500 | 5,534 |

The selected cap is 10,000 characters. A direct local
`dgx-moa-reviewer` call over the failed evidence returned valid
`status=approved` JSON in 1.174 seconds with 5,026 prompt and 12 completion
tokens. Specialist routing also preflights the served tokenizer before local
dispatch: a measured overflow selects the remote Planner/Reviewer with reason
`local_context_exceeded`; an explicit local-only request fails closed. Provider
selection remains pinned after dispatch.

Fresh Docker run `20260725-qm-codex-context1` completed in 272.657 seconds with
exit `0`; public and hidden tests exited `0`, and all ten score checks passed.
Its final session `5dc7ccc8-f5bd-45a8-a39d-f8bbba51e720` recorded ten tool
results, two completed reviews with no review failure, Codex OAuth Frontier
correction, final local Reviewer approval, `finish_reason=stop`, and completed
session termination. The final local Reviewer invocation used
`dgx-moa-reviewer`, 5,869 total tokens, and 3.845 seconds. The full repository
integration worktree passed `981 passed`; the clean production checkout passed
`980 passed`. Both had one third-party Starlette warning and passed Ruff.
Production merge `970fbfc` deployed commit `749e77f`, and `/readyz` reported
Executor, Planner, Reviewer, and Reasoner ready with Judge stopped.

## Executor prefix-cache feasibility — 2026-07-25

The protected Executor baseline remains unchanged: context `65536`, one
sequence, `1700000000` KV-cache bytes, `gpu_memory_utilization=0.5`, and
MARLIN. Automatic prefix caching is not enabled. Two identical direct requests
with 32,012 prompt tokens and one output token took 7.404 and 7.438 seconds;
both reported zero prefix-cache queries and hits. The current runtime therefore
does not reuse the repeated request prefix.

An isolated vLLM 0.22.1 candidate added `--enable-prefix-caching` while keeping
the selected Executor arguments and using port 19301. Qwen3Next selected the
experimental aligned Mamba-cache path and failed before readiness with
`ModuleNotFoundError: No module named 'flash_attn.ops'`. No package was
installed, the candidate was rejected, and the exact production Executor
service was restored.

SGLang provides RadixAttention prefix reuse and continuous batching, so it is a
valid future engine candidate rather than a production toggle. It must still
physically pass the repository's Qwen3-Next NVFP4/MARLIN, 65,536-context,
one-sequence, memory, tool-calling, quality, and rollback gates. Until then,
bounded specialist evidence, compressed tool history, context-aware remote
routing, and concurrent independent-role work are the approved throughput
controls; no speculative SGLang migration is deployed.

### SGLang Planner promotion with NVIDIA Qwen3.6-27B-NVFP4 — 2026-07-25

The official Apache-2.0 `nvidia/Qwen3.6-27B-NVFP4` checkpoint at revision
`0893e1606ff3d5f97a441f405d5fc541a6bdf404` was downloaded with all three
indexed shards present. Indexed weights total 21,921,697,184 bytes. The
isolated runtime used
`lmsysorg/sglang:dev-cu13@sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0`,
loopback-only port `8112`, a 45 GiB hard limit with no extra swap, one running
request, context and total tokens `65536`, Mamba cache size `5`,
`mem-fraction-static=0.45`, ModelOpt quantization, and disabled decode/prefill
CUDA graphs.

Initialization completed without OOM beside the protected Executor. SGLang
measured 113.01 seconds to load 23.02 GB of model memory, 0.86 GB of Mamba
state, and 2.00 GB of FP8 KV for exactly 65,536 tokens.

The dense 27B candidate passed all three Planner promotion probes with valid
`PlannerPlan` JSON and no public reasoning content:

- mixed-version migration included late-writer final backfill, old-binary exit
  gate, delayed cleanup, and pre-cleanup rollback; 132.87 seconds;
- async cache repair included per-key singleflight, generation fencing,
  cancellation safety, bounded eviction, and concurrency tests; 94.11 seconds;
- cold routing included immediate remote dispatch, role+revision+runtime
  singleflight, provider pinning, real inference readiness, and high-risk
  fail-closed behavior; 94.96 seconds.

A 35,993-token repeated request measured 31.493 seconds uncached and 1.118
seconds with 35,968 cached prompt tokens, a 28.17x improvement. An independent
62,999-prompt-token request returned public content in 61.111 seconds. With the
vLLM Executor and North Reviewer simultaneously resident, real inference
probes completed in 1.08, 0.78, and 1.06 seconds for Executor, SGLang Planner,
and Reviewer; measured GPU allocations were 47,616, 25,659, and 21,235 MiB.

The model was not promoted as Reviewer: recursive-secret review passed, but
strict symlink review omitted a dirfd/openat component walk and did not fully
close the TOCTOU race. Production keeps the independent North Reviewer. The
Planner unit pins the tested image digest, model revision, loopback mapping,
memory cap, and one-request/65K settings. Rollback is an exact Planner service
stop, restoration of the previous unit and model entry, daemon reload, and
start followed by the existing inference readiness probe.

The installed unit uses `mem-fraction-static=0.68`, rather than the isolated
`0.45`, because a cold start with the Reviewer already resident exposed only
40.49 GB to SGLang. The higher fraction reserves about 27.5 GB of that visible
memory and must pass the same 65K allocation and inference probe before the
service is considered ready.

The installed cold start then physically passed with Executor and Reviewer
already resident: weight load took 102.80 seconds and 19.80 GB, Mamba state
used 0.86 GB, and FP8 KV allocated all 65,536 tokens. `/healthz` returned
`status=ok`, `/readyz` reported Executor, Planner, Reviewer, and Reasoner
`ready`, and a post-deployment structured Planner inference returned one valid
step with `finish_reason=stop` and no public reasoning in 31.86 seconds.

The post-promotion audit restored the common unit environment-file hardening
contract and reran `uv run pytest -q`: 981 tests passed with one existing
Starlette deprecation warning. A live non-thinking Planner request returned
public structured JSON with `finish_reason=stop`, zero reasoning tokens, and
166 completion tokens in 14.078 seconds. The running container remained
loopback-only with a 45 GiB hard memory/no-extra-swap limit, while measured GPU
allocation was 25,655 MiB.

## Engineering-loop wall-budget 502 recovery — 2026-07-25

Production access logs showed one `409 Conflict` at 19:56 KST followed by
repeated `502 Bad Gateway` responses at roughly 60-second client retry
intervals. The gateway process and `/v1/models` remained healthy. Content-free
state inspection found the affected loop terminated as `BUDGET_EXHAUSTED`
with five iterations, 765,889 tokens, and zero wall-clock seconds still
available. The deployed configuration allowed only 1,800 wall-clock seconds,
so the repeated 502s were a loop-admission failure rather than a model or
network outage.

The checked-in defaults now allow 43,200 wall-clock seconds, 32 iterations,
500 tool calls, 5,000,000 tokens, and 1,000 retained controller steps.
Wall-clock exhaustion may recover once per loop using a persisted
`wall_clock_recovery_count` latch; a second exhaustion remains fail-closed.
This prevents an automatic retry from creating an unbounded budget reset while
allowing the previously stranded production session to continue after the
approved limit expansion.

Validation used the production Python environment against the isolated hotfix
worktree. Focused controller, loop, and configuration tests passed 135/135.
The complete suite then passed 982/982 in 24.70 seconds with only the existing
Starlette deprecation warning. No role endpoint, model, authentication, or
systemd topology changed in this hotfix.

A SQLite backup of the live state database was opened with the hotfix code.
The affected serialized state loaded with the new field default, recovered
from zero to 43,200 wall-clock seconds, cleared `BUDGET_EXHAUSTED`, and then
refused a second recovery after the latch reached one. The live database was
not modified by this pre-deployment check.

Production `main` was fast-forwarded to `92bcc7c` and pushed. Only the gateway
service was restarted; role-model services and topology were unchanged.
`/healthz` and `/readyz` returned HTTP 200, with Executor, Planner, and
Reasoner ready. The affected live session then changed from
`blocked/BUDGET_EXHAUSTED/0 seconds` to
`replanning/no termination/43,200 seconds`, with recovery count one. A fresh
authenticated `dgx-moa-fast` inference returned HTTP 200, exact public content
`OK`, `finish_reason=stop`, 1,047 prompt tokens, and two completion tokens.

## Engineering-loop expanded-call-budget recovery — 2026-07-25

The same production session failed again after wall-clock recovery. Its local
Planner completed normally, but the loop then rejected the action because the
serialized legacy budget still had zero Planner and Frontier calls. The
gateway returned repeated 502 responses without another role-model request.
This was a second migration defect: only wall-clock and zero-token limits were
eligible for the increased checked-in defaults.

On `BUDGET_EXHAUSTED`, the Controller now counts durable successful
`engineering_loop_budget_consumed` events for the current loop and derives
each bounded call remainder as the configured limit minus actual consumption.
Iterations use the loop's persisted iteration count and tokens retain the
existing invocation-usage calculation. A value is changed only when this
calculation yields more than the persisted remainder. A session that has
already consumed the configured limit therefore remains fail-closed.

Controller and loop tests passed 106/106. The full suite passed 984/984 in
27.30 seconds with only the existing Starlette deprecation warning. A SQLite
backup of the exact failed session recovered iterations `4 -> 28`, tool calls
`97 -> 497`, Reasoner calls `3 -> 27`, Planner calls `0 -> 6`, Reviewer calls
`8 -> 32`, Frontier calls `0 -> 12`, Judge calls `2 -> 4`, and tokens
`757,501 -> 4,753,667`; termination cleared to `replanning`.

Production `main` was fast-forwarded to `b7c4f91` and pushed. Only the gateway
was restarted. The same migration was applied to the affected live session
without changing prompts, tool results, or model services. A non-streaming
authenticated continuation on that exact OpenCode session returned HTTP 200,
`finish_reason=stop`, and exact Korean content `연결 복구 확인`. A second
streaming continuation returned HTTP 200, content `스트림 정상`,
`finish_reason=stop`, and the terminal SSE `[DONE]` marker.

## Responses pending-review retry deadlock — 2026-07-26

An isolated Codex quality run completed its requested file write and all four
tests, but the production gateway emitted repeated `incomplete_response`
terminals classified as `progress_only_response`. The affected session had 42
recorded tool results, successful mutation and validation executions, no
Reviewer artifact, and `review_status=pending`. The Responses client did not
present the completed tool turn in the legacy continuation shape, so dynamic
Reviewer promotion never occurred. The completion gate correctly refused an
unreviewed result, while progress retries kept asking the Executor for another
tool call and eventually produced the client-visible 502.

The Controller now promotes the Reviewer from recorded implementation evidence
even when the client continuation marker is absent. During a progress retry,
this recovery is limited to sessions with implementation evidence and no prior
Reviewer artifact. Existing Reviewer artifacts are still reused without
another paid or local call; rejected, deferred, Frontier-correction, and
Reviewer-required paths remain fail-closed.

Focused deadlock, deferred-review, review-reuse, and completion-gate tests
passed 6/6. Controller plus streaming tests passed 151/151 after preserving the
existing artifact-reuse behavior. The complete suite passed 985/985 in 26.08
seconds with only the existing Starlette deprecation warning. Ruff and
`git diff --check` passed. The code fix is commit `24a3cc9`.

The first production canary exposed a second condition in the same gate. Its
bounded command used the prompt-required
`timeout 120s python -m unittest discover -s tests -v` form. All four tests
passed, but the validation recognizer accepted only a bare Python prefix, so
the successful retry still was not review evidence. Commit `8c16517` adds the
bounded `timeout` prefix to the existing allowlist instead of adding another
validation path. Its focused checks passed 4/4 and the complete suite again
passed 985/985 in 25.59 seconds with the same warning.

The canary's successful fallback also prefixed the bounded command with
`PYTHONDONTWRITEBYTECODE=1`. Commit `b6db4b9` accepts standard shell
environment assignments before the existing bounded validation command.
Against the exact persisted canary state, the hotfix changed both
`has_review_evidence` and `needs_reviewer` from false to true. Focused checks
passed 4/4 and the complete suite passed 985/985 in 25.25 seconds.

Production `main` was fast-forwarded to `3131e04` and pushed. Only the gateway
was restarted; startup completed in 11 seconds and `/healthz` plus `/readyz`
returned HTTP 200. The exact failed canary session was resumed with its pinned
runtime provenance and stored tool evidence. It emitted
`reviewer_required(trigger=implementation_evidence)`, completed an independent
Reviewer pass, recovered from one invalid structured Reviewer output, and
finished with `review_status=approved`, `stream_completed`, and
`session_ended=completed`. The client observed HTTP 200, one
`response.completed`, zero `response.failed`, and 6,092 SSE bytes. No
post-deployment 5xx terminal was logged.

## Codex remote-Executor stream recovery — 2026-07-26

A fresh Docker Codex canary exposed two separate compatibility failures. The
quality harness initially had no local metadata for `dgx-moa-orchestrated`.
A static replacement incorrectly selected Codex `code_mode`, which added an
`additional_tools` input item that the gateway does not support and produced
HTTP 422. Commit `886a0bb` instead fetches the authenticated gateway
`/v1/models` catalog before each isolated Codex run and pins that exact catalog
inside the container. The runtime's reviewed `direct` tool mode is now used
without duplicating model metadata or storing the API key in the catalog.
Timeout cleanup also assigns a deterministic container name and removes that
exact container after an expired run. The physical timeout check returned 124
and left no container.

The next canary completed its implementation and both public and hidden tests,
but its client log still contained one `stream disconnected before
completion`. Gateway evidence showed this was not a socket or process outage:
the remote Frontier Executor returned an `apply_patch` call whose freeform
patch was not wrapped in a JSON argument object. Validation emitted a
structured failed response, Codex retried, and the run eventually returned
zero after 555.899 seconds. The matrix correctly failed the run because
`no_bad_terminal=false`.

Commit `6ff0953` normalizes only the two known freeform client tools:
`apply_patch`/`patch` become `{"input": ...}` and
`exec_command`/`shell` become `{"cmd": ...}`. Unknown malformed tool arguments
remain fail-closed. Unit and integration coverage proves both the successful
normalization and the unknown-tool rejection. Focused tests passed 36/36,
Ruff and `git diff --check` passed, and the complete suite passed 991/991 in
24.59 seconds with only the existing Starlette deprecation warning.

After production fast-forward and a gateway-only restart, `/healthz` and
`/readyz` returned HTTP 200 with Executor, Planner, Reviewer, and Reasoner
ready. A new isolated atomic-store canary exercised the same remote Frontier
Executor path. The remote call remained open for 78 seconds, completed one
normalized `apply_patch`, ran validation, completed Reviewer and Frontier
review, and terminated in 164.360 seconds. Public and hidden validation both
returned zero. The quality score passed every check, including
`no_bad_terminal=true`; client logs contained zero metadata warnings,
reconnections, stream disconnects, 422s, 502s, `turn.failed`, or
`response.failed`. Runtime events contained one `executor_remote_completed`,
one `review_completed`, one `frontier_review_verified`, nine
`stream_completed`, and zero `executor_remote_failed` or `stream_aborted`.

This canary closes the reproduced connection-failure path. It does not by
itself establish GPT-5.6 Sol quality parity: earlier local turns still made
avoidable text-file `view_image` calls, invalid `write_stdin` calls, and
redundant patch attempts. Those remain quality and efficiency work for the
preregistered multi-harness evaluation.

## OpenCode no-progress session recovery — 2026-07-26

The production OpenCode session failed four immediate requests at
01:19:50–01:20:06 KST as HTTP 409, 409, 502, and 502. Persisted events showed
that the engineering loop had terminated with `NO_PROGRESS`; exact retries
were correctly rejected for missing new evidence, but the blocked state then
raised a generic `ValueError`, which was exposed as a misleading 502. More
importantly, novel user input was recorded as evidence without clearing the
recoverable `NO_PROGRESS` termination.

Commit `e680cef` reopens only a running `NO_PROGRESS` loop after novel user
evidence. Exact retries remain rejected, and operator, policy, provider,
duplicate-failure, and budget terminations remain closed. A terminated
no-progress state now uses the existing structured loop-admission error
instead of the generic backend-error path.

Focused Controller and API checks passed 8/8. Ruff and `git diff --check`
passed, and the complete suite passed 993/993 in 23.19 seconds with only the
existing Starlette deprecation warning. Production `main` was fast-forwarded
and the gateway alone was restarted. `/healthz` and `/readyz` returned HTTP
200.

The live OpenCode-compatible canary used the production API key, User-Agent,
session header, and `/v1/chat/completions` route without exposing the key.
Its sequence was HTTP 200 for the initial turn, HTTP 409 with
`loop_new_evidence_required` for the exact retry, and HTTP 200 after a novel
user message. The final request recorded
`engineering_loop_resumed(reason=new_user_evidence)` and completed in 1.805
seconds. No 502 occurred.

## Codex OAuth correction-result normalization — 2026-07-26

The first preregistered quality-matrix attempt exposed a later instance of the
same visible disconnect class. The gateway stayed healthy, but session
`0a18c60b-5e1e-43e2-ae14-e8c78acd7dd7` recorded
`executor_remote_failed` while dispatching a Frontier correction. The bounded
failure was a Pydantic `ValidationError` for
`FrontierExecutorResult.tool_calls[0].function`: Codex OAuth had returned a
known tool with freeform arguments.

The existing compatibility normalizer already repaired known
`apply_patch`/`patch` and `exec_command`/`shell` arguments, but the Codex OAuth
result file was schema-validated before reaching it. Commit `4c4d6c8` parses
that result as JSON, applies the existing allowlisted normalization for
Executor mode, and then performs the same strict schema validation. Unknown
tools with malformed arguments remain fail-closed.

Direct Codex OAuth regression coverage proves both the repaired known-tool
case and the rejected unknown-tool case. Frontier plus usage focused tests
passed 71/71. Two complete-suite attempts also exposed a pre-existing race in
the test that enumerated transient SQLite WAL files: `usage.db-shm` could
disappear between enumeration and reading. The test helper now ignores only a
file that has already disappeared while continuing to scan every remaining DB
and WAL file for forbidden sentinels. The final complete suite passed 998/998
in 26.79 seconds; Ruff and `git diff --check` passed. Production deployment
and a fresh, unobserved quality fixture remain required before this incident
is closed.

Production `main` was fast-forwarded to `b07c565`, pushed, and only the gateway
was restarted. Startup completed in 12 seconds; `/healthz` and `/readyz`
returned HTTP 200 with Executor, Planner, Reviewer, and Reasoner ready. A fresh
OpenCode-compatible non-streaming request returned HTTP 200 and a non-empty
`stop` response in 5.836 seconds. A separate streaming request returned HTTP
200, seven data chunks, a `[DONE]` terminator, and zero failed events in 6.395
seconds. Gateway logs contained the two HTTP 200 requests and no post-deploy
5xx, `stream_aborted`, `responses_stream_terminal`, or
`executor_remote_failed`. The OpenCode connection block is closed; the
preregistered cross-client quality comparison remains a separate active gate.

## Oversized local Executor tool-turn routing — 2026-07-26

The second preregistered Hermes attempt stayed connected but made no
implementation progress. Content-free session evidence showed the Planner
completed remotely in 24.510 seconds while its local warm-up continued
independently. The request then dispatched the resident Qwen3-Next Executor
locally. vLLM generated continuously for more than eight minutes at roughly
13–35 tokens per second without returning a tool call or stop; the client
cancelled after 535.388 seconds.

The prepared Hermes profile had no explicit model output limit, so its custom
provider requested 65,536 tokens and the gateway accepted its compatible
32,768 maximum. A controlled diagnostic set Hermes to the gateway's 4,096
default. This bounded the local turn to 115.899 seconds, but it consumed
exactly 4,096 completion tokens and ended with `finish_reason=length`, zero
tool calls, and no implementation. A simple output clamp therefore improved
latency but failed the quality contract.

Commit `d12af21` extends the existing pre-dispatch Frontier policy. When a
request includes client tools and asks for more than the validated 4,096-token
local turn budget, it is pinned to Frontier before local inference starts and
records `routing_reason=local_output_budget_exceeded`. Tool-free long answers,
the 32,768 compatibility ceiling, local requests at or below 4,096, busy
routing, and context routing remain unchanged. The selected provider is never
switched after dispatch.

Focused busy, context, repeated-failure, and oversized-tool routing tests
passed 4/4. The new regression proves a 16,384-token tool request invokes no
local Executor, preserves its requested budget for Frontier, and records the
new reason. Ruff and `git diff --check` passed; the complete suite passed
999/999 in 27.84 seconds with only the existing Starlette deprecation warning.

Production `main@95cb767` deployed the routing change and restored HTTP 200
health/readiness with all required resident roles ready. A fresh installed
Hermes canary then requested 16,384 output tokens and completed an actual
rate-limiter implementation in 604.09 seconds with process exit `0`. Every
large client-tool turn was pinned to Codex Frontier before dispatch with
`routing_reason=local_output_budget_exceeded`; the local Executor performed
only the bounded orchestration decisions. Gateway evidence contained no 5xx,
provider failure, or stream abort during the completed tool turns.

The implementation and both public and hidden tests passed, but the first
quality score was 9/10 because the evaluator recognized the legacy Hermes
`execute_code.output.unittest` field only. Installed Hermes records the same
evidence under `execute_code.output.unit_tests`; the session had four unittest
tool calls, final exit `0`, and independent checks with exit `0`. Commit
`63c1edd` accepts both field names and adds a regression fixture containing
`Ran 4 tests` and `OK`.

Before sealing new repeated runs, the quality manifest was also extended to
pin the actual client runtime: Codex and OpenCode record their version and
binary SHA-256, while Hermes records revision
`f67aae323010e32c592a185984d36b20e9fa474a` and the non-secret config SHA-256.
The manifest validator rejects a changed runtime fingerprint before execution;
Hermes `.env` is neither stored nor hashed. Focused evaluator tests passed 9/9,
Ruff and `git diff --check` were clean, and the complete suite passed 1000/1000
in 26.41 seconds with only the existing Starlette deprecation warning.

An independent OpenCode availability check used installed OpenCode `1.17.18`
through the production gateway. A text request and a five-turn file
create/readback request both exited `0`; the latter created exact `OK`, recovered
from one model-generated unavailable `shell` tool name, and finished normally.
A direct bounded OpenCode Go Planner request returned exact
`OPENCODE_GO_OK` from `deepseek-v4-pro` in 2.479 seconds. No server-side
OpenCode or OpenCode Go circuit block was present.

Post-deployment canary
`20260726-hermes-frontier-budget-canary-v2/hermes/rate-limiter` used the final
runner SHA-256 and pinned Hermes runtime fingerprint. It completed in 362.499
seconds with process exit `0`, changed only `rate_limiter.py`, and passed all
10/10 functional checks. Public and hidden validation both exited `0`; the
current `unit_tests` parser found one unittest tool call and one successful
result. This closes the earlier evaluator false negative with a fresh execution
rather than rescoring stale evidence.

## Dead local specialist readiness regression — 2026-07-26

Preregistered run
`20260726-sol-preregistered-v4-r1/codex/log-report` reproduced the apparent
client block. The implementation, public tests, and hidden validation all
passed, but the harness timed out after 1800.149 seconds with exit `124`.
Runtime evidence showed that Reviewer inference had succeeded once before its
vLLM EngineCore died at 05:05:34. The service exited, but lifecycle generation
56 remained `READY`; 22 subsequent reviews were therefore pinned to the dead
local endpoint and failed with `ConnectError`. The session reached 70 streamed
turns and 203 tool results instead of returning the already-supported final
answer.

The specialist router now atomically transitions a failed local Planner or
Reviewer from `ready` to `failed`. Provider pinning is unchanged: the failed
call is not switched after dispatch, while the next specialist call observes
the failed state, selects the configured remote provider, and may trigger the
existing singleflight warm-up. A regression test proves the dead local
provider is invoked once and the next call routes remotely. Specialist tests
passed 10/10; the complete suite passed 1001/1001 in 28.91 seconds. Ruff and
`git diff --check` passed.

Production `main@5cf1fe4` deployed the fix with a gateway-only restart.
`/healthz` and `/readyz` returned HTTP 200 on the third one-second probe.
Startup reconciliation corrected the stopped Planner and Reviewer from stale
`ready` to `cold` while preserving the resident Executor as `ready`.

A fresh isolated OpenCode `1.17.18` canary then completed the previously
timed-out `log-report` task in 178.010 seconds with process exit `0`. It changed
only `log_report.py`; public and hidden validation both exited `0`, and all
10/10 evaluator checks passed. While the Reviewer warm-up was `LOADING`, two
required review calls selected remote `deepseek-v4-flash` with
`routing_reason=local_not_ready` and both completed. The canary recorded no
failed specialist call, bad terminal, stream abort, or gateway 5xx.

## Frontier stdin transport pre-production check — 2026-08-08

The development-only Frontier runner now sends the redacted Codex request on
stdin instead of placing it in the process argument vector. A local subprocess
check transported exactly 300,000 prompt characters, returned the same byte
count, captured stdout and stderr concurrently, and confirmed that the prompt
was absent from `CompletedProcess.args`. A simulated process-spawn `E2BIG`
returned `FRONTIER_INPUT_TRANSPORT_TOO_LARGE` without retry.

Focused validation passed 35/35 tests in 0.18 seconds. Ruff format and lint,
strict mypy for `gateway/src/dgx_moa/frontier.py`, and `git diff --check` passed.
No Codex OAuth provider call, App Server session, production deployment, or
latency/quality benchmark was performed by this check; those remain separate
physical gates.

## Execution Graph core development check — 2026-08-08

The development-only `execution-graph-v1` compiler produced stable graph and
input hashes for repeated normalized inputs while excluding observation time
from graph identity. Six focused checks covered allowlisted node rejection,
undeclared-cycle rejection, three-branch fan-out/JOIN readiness, two bounded
same-node retries followed by a separately pinned fallback node, two bounded
repair traversals requiring new validated Evidence IDs, no-progress exit,
policy-owned human approval pause/resume, cancellation-to-Finalize, strict
numeric inputs, SQLite restart recovery, incompatible-checkpoint rejection,
provider/model pinning, an explicit CHECKPOINT node, artifact-hash-gated reuse,
exactly-once finalization, and descendant-only partial rerun. All 6 passed in
0.05 seconds.

The complete repository suite then passed 1009/1009 in 29.49 seconds with the
existing Starlette `httpx` deprecation warning. Project-wide Ruff lint and
strict mypy over 47 source files passed. Focused format checks for the new
Execution Graph and changed Frontier files passed, as did `git diff --check`
and the frozen Dynamic MoA v3 plan hash. A repository-wide format check still
reports six pre-existing unformatted files; no bulk formatting was applied.
No Controller default-path switch, provider call, production runtime mutation,
or graph-vs-baseline benchmark was performed by this check.

## Execution Graph common-path shadow check — 2026-08-08

The checked-in and model-default Execution Graph mode is `disabled`. With an
isolated test configuration set to `shadow`, one Chat request and one Responses
request each compiled exactly one candidate graph through the existing shared
Chat execution path. Both persisted graph IDs/hashes on session state, emitted
one sanitized shadow event, recorded the actual compatibility Executor provider
as `legacy_local_qwen`, and contained no bearer token. Shadow compilation owns
no routing or execution authority and its typed validation/SQLite failures do
not block the validated legacy request path.

After this integration, the complete suite passed 1010/1010 in 29.56 seconds
with the existing Starlette warning. Project-wide Ruff lint, strict mypy over
47 source files, `git diff --check`, and the frozen v3 plan hash passed. This is
not execution parity evidence: the legacy Controller remains authoritative and
no branches were removed or production defaults changed.

## Concurrent runtime/model mutation incident — 2026-08-08

During the development-only pinned Mistral download, a second unrequested
download appeared and the active Planner was explicitly stopped. Three paths
that the frozen inventory had classified as retained and verified present were
then absent: the rollback Executor, the installed experimental Executor, and
the active Planner Gemma model. The authorized cleanup command did not target
those paths. Both exact download process groups were terminated after the
collision was detected; a subsequent process snapshot found no remaining
download, deletion, or service-control process.

At `2026-08-08T16:49:16+09:00`, five other retained model paths remained
present. The two Mistral partial locations were preserved at `20492283799` and
`2834955254` bytes, and filesystem free space was `267652116480` bytes. The
user gateway unit remained active and loopback role-model units remained
stopped. Tailnet `/healthz` returned HTTP 200, while `/readyz` returned HTTP 503
with the resident Executor, Planner, and Reviewer stopped. Its Reasoner field
reported ready despite the inactive Reasoner unit and is therefore a recorded
state-reconciliation discrepancy, not a green result.

The incident evidence is detailed in
`docs/DYNAMIC_MOA_CONCURRENT_RUNTIME_INCIDENT_20260808.md`. No recovery,
service start, download resumption, deployment, or further deletion was
performed. Physical model gates remain paused pending an explicit recovery
decision and a stable single-actor runtime.

Later in the same validation run, `config/models.yaml` and the API-key
Dashboard Executor label changed outside the goal-controlled edit stream to
the pinned Mistral target and a tailnet Reasoner address. The exact concurrent
diff was preserved rather than reverted. A short stability recheck found no
active editor, download, or service-control process; this does not establish
the initiating actor or authorize the configured model for production.

## Execution Graph routing/refactor parity check — 2026-08-08

Review-evidence assembly moved from the Controller into one shared module while
the existing Controller method signatures remained as one-line compatibility
delegates. Execution Graph projection persistence moved into the graph module,
and the Executor local/Frontier priority contract moved from three dispersed
API branches into one pure routing function. Provider pinning remains
unchanged: an already selected Frontier provider cannot be switched during the
turn.

| File | Pre-v3 lines / branches | Candidate lines / branches | Delta |
| --- | ---: | ---: | ---: |
| `controller.py` | `4285 / 388` | `4141 / 359` | `-144 / -29` |
| `api.py` | `4468 / 466` | `4472 / 462` | `+4 / -4` |

A disabled-vs-shadow paired API regression preserved the same selected role,
Executor request contract, native tool-call ID, `finish_reason`, response, and
exactly-one terminal event. An injected SQLite graph-store failure emitted a
typed shadow failure without changing the legacy response or provider call.
Busy, context overflow, output-budget overflow, correction, repeated-failure,
and no-progress selection regressions passed. The pre-existing 10-millisecond
stream timeout test was made scheduler-robust at 200 milliseconds without
changing production timeout code; the timeout/one-attempt contract and the
updated Mistral Dashboard label passed five consecutive focused runs.

The complete suite passed `1012/1012` in 29.50 seconds with the existing
Starlette warning. Project-wide Ruff lint, strict mypy over 47 source files,
`git diff --check`, and the frozen v3 plan hash passed. This remains a shadow
parity gate only: the legacy execution path is authoritative, no physical
provider comparison has run, and the Graph Runtime is not approved as a
production default.

## Mistral cache PASS and isolated vLLM load FAIL — 2026-08-08

The pinned canonical snapshot at revision
`b1a9048590131d38491bd23a7c9f6ed0962f0358` contained `23` manifest files
totaling exactly `70846528432` bytes with zero broken symlinks. `hf cache
verify --fail-on-missing-files --fail-on-extra-files` checked `23/23` files and
exited `0`. Cache integrity is PASS.

A concurrent local vLLM `0.22.1` process then attempted the required first-load
profile on `127.0.0.1:19301`: context `65536`, one sequence, `1700000000` KV
bytes, `gpu_memory_utilization=0.5`, MARLIN MoE, TRITON_MLA attention, and
Mistral tool/reasoning parsers. It never opened the port or returned readiness.
Observed GPU allocation reached `120052` MiB, and EngineCore entered
uninterruptible `folio_wait_bit_common` sleep with 102 threads.

Kernel evidence records global OOM handling, `NV_ERR_NO_MEMORY`, unrelated
process kills, three gateway kills, the user systemd manager's death, and final
kills of EngineCore PID `3386567` and vLLM parent PID `3386426` at `17:28:42`.
The restarted gateway recovered `/healthz` HTTP `200`; `/readyz` remained HTTP
`503` with role services stopped. No canary listener or GPU compute remained.

A later check found a second direct-session attempt started at `17:29:29` with
the same pinned snapshot and core safety limits. Its EngineCore PID `3395983`
held `68256` MiB GPU memory without opening port `19301`. To prevent another
global OOM, exact process group `3395728` received `SIGTERM`; after the parent
failed to reap its zombie child, that same group received `SIGKILL`. Both PIDs,
the listener, and GPU compute allocation were absent afterward. Available
system memory was `126931980288` bytes and swap use was `944574464` bytes.

| Gate | Result |
| --- | --- |
| pinned snapshot integrity | PASS (`23/23`, `70846528432` bytes) |
| isolated load and readiness | FAIL (never listened or became ready) |
| memory isolation | FAIL (global OOM affected unrelated processes and gateway) |
| Chat, Responses, streaming, tools, long context, cache, cancellation, restart | NOT RUN (readiness prerequisite failed) |
| deployment | BLOCKED; no same-profile retry authorized |

The exact incident timeline is preserved in
`docs/DYNAMIC_MOA_CONCURRENT_RUNTIME_INCIDENT_20260808.md`. No model restart,
backend substitution, production deployment, or production worktree mutation
was initiated by the goal-controlled path after the failure; the unsafe
concurrent retry above was stopped by exact process-group scope.

## Remote roles and Codex App Server gate — 2026-08-08

An authenticated OpenCode Go `/v1/models` request returned HTTP `200` with 25
models. The catalog contained the exact target IDs `deepseek-v4-pro`,
`deepseek-v4-flash`, `glm-5.2`, `kimi-k3`, and `kimi-k2.5`; no credential value
was printed or persisted. Checked-in safe defaults remain disabled.

The first post-mapping Planner request failed after about 5.7 seconds despite a
120-second stage timeout. Root cause was the shared HTTP client interpreting
explicit `timeout=None` as HTTPX's default five-second timeout. Passing the
explicit value through to HTTPX restored the existing outer `asyncio.timeout`
contract. A regression confirms `httpx.Timeout(None)`, and this shared fix also
applies to local ModelProvider calls that already own stage deadlines.

After the fix, `deepseek-v4-pro` returned a valid `PlannerPlan` in `11.432`
seconds with `450` prompt, `743` completion, and `1193` total tokens. Planner is
PASS. `glm-5.2` returned `finish_reason=stop`, zero public content characters,
and only `reasoning_content`; a separate temperature-1 JSON-object probe again
returned zero public content. Hidden reasoning was neither parsed nor retained,
so Reviewer is FAIL.

The Kimi K3 Judge initially returned HTTP `400`: the provider accepts only
`temperature=1` for that model. Bounded probes then proved that temperature 1,
strict JSON schema, and seed 0 are accepted. A model-specific temperature fix
allowed three matrix rows to pass: supported approval, rejection of an
unsupported production claim, and detection of a failed test reported as
success. The fourth row returned empty public content. One existing bounded
retry was extended to empty content only; the rerun returned a 17-character
truncated JSON value on the same row. Retry count was not increased. Kimi Judge
is FAIL, and the sanitized partial artifact is
`data/diagnostics/opencode-completion/kimi-k3-judge-20260808.json` with
`status=failed` and `failure_class=JudgeProviderError`.

The installed Codex CLI is `0.146.0`. Its generated App Server schema confirmed
stdio JSONL, ephemeral threads, read-only sandbox, never-approval, per-turn
output schema, and token-usage notifications. The development Frontier now
uses `initialize → initialized → thread/start → turn/start → turn/completed`,
opts out of reasoning deltas, discards reasoning items, and collects only the
final public `agentMessage`. It starts a new process group and performs exact
TERM/KILL cleanup on timeout or cancellation. Stdin `codex exec` is attempted
only for typed `FRONTIER_APP_SERVER_UNAVAILABLE`; auth, usage-limit, and timeout
failures retain their existing failover/fail-closed behavior.

An OAuth primary App Server preflight reported ChatGPT auth, nine available
Codex models, and exact `gpt-5.6-sol` presence. A physical architecture turn
then completed through `transport=codex_app_server`, profile `primary`, in
`21947.105` ms with `14290` prompt, `551` completion, and `14841` total tokens.
The output validated all six required architecture fields, and only objective,
constraints, and specific questions were transmitted. No OpenAI API key,
OpenRouter fallback, host mutation, production enablement, or deployment was
used.

After these changes, the complete repository suite passed `1016/1016` in
35.53 seconds with the existing Starlette warning. Project-wide Ruff lint,
strict mypy over 47 source files, both frozen plan hashes, and `git diff
--check` passed. The remote-role stage is not green: Planner and Frontier A
pass, while Reviewer and Judge remain required physical failures.

## Reasoner pre-ablation smoke — 2026-08-08

The external Ollama catalog at `100.90.167.128:11434` returned the exact
configured `Qwythos-v2-9B:Q4` model. An intentionally small 128-token structured
request returned HTTP `200` but ended with `done_reason=length`: all 128 tokens
were thinking, public content was empty, and no tool call was emitted. This was
recorded as an output-budget failure rather than parsed from hidden thinking.

With a materially increased but still bounded 1024-token allowance, the same
read-only schema completed in `2.758` seconds with valid public JSON, `62`
prompt tokens, `242` completion tokens, and `304` total tokens. The standalone
Reasoner smoke is PASS. It is not ablation evidence: the required Mistral-only,
Qwythos→Mistral, Qwythos+Frontier→Mistral, and full parallel variants cannot run
while the local Mistral Executor gate remains failed.

## API-key Executor scheduling and Flash gate — 2026-08-08

The development candidate now has one process-local, raw-token-free Executor
scheduler. Its persisted/public fields are `request_id`, `api_key_id`,
`lease_owner_api_key_id`, `acquired_at`, `lease_state`, `queue_position`,
`round_robin_epoch`, selected provider, and reason. A different API key is
pinned immediately to OpenCode Go `deepseek-v4-flash` while local Mistral is
owned; the owning key receives at most three local waiters before low/medium
risk overflow. Per-key deques are promoted round-robin. High/critical risk is
local-only and fails closed when its bounded queue is full. Cancellation,
timeout, stream completion, and ordinary finalization release the pin.

The OpenCode Go overflow adapter preserves native `tools`, `tool_choice`,
`parallel_tool_calls`, and public OpenAI-compatible output while removing
gateway `metadata` and private underscore-prefixed fields. It performs no
silent provider switch after admission. `401`/`403`, including region opt-in
denial, is typed as pinned provider unavailable. Scheduler decisions are
emitted directly through state events and the actual `SchedulingSnapshot` is
now stored in new Execution Graph records; old v1 records without the field
retain their original hash compatibility.

Focused scheduler/provider/API/graph checks passed `11/11`. The final complete
suite passed `1022/1022` in `34.70` seconds with the existing Starlette warning.
Project Ruff check, strict mypy over 49 source files, both frozen plan hashes,
and `git diff --check` passed. All 11 scheduler-touched source/test files pass
Ruff format check. The whole-tree format check retains four pre-existing,
out-of-scope candidates (`specialists.py`, `streaming.py`,
`test_controller.py`, and `test_specialists.py`); they were not rewritten.

The authenticated physical model catalog contained exact
`deepseek-v4-flash`. The first completion was rejected before inference with
HTTP `403`; a bounded sanitized diagnostic identified provider error type
`RegionError`: the latest model is China-hosted and requires explicit workspace
opt-in. No credential was printed or persisted. No opt-in, provider
substitution, production configuration change, or deployment was performed.
Therefore Flash catalog availability is PASS, native tool-call completion is
FAIL/NOT EXECUTED, and the Executor scheduler production gate remains disabled.

## API-key privacy and live Dashboard gate — 2026-08-08

The development credential store no longer writes API-key plaintext. The
legacy `token` column is retained only as an empty compatibility tombstone;
authentication uses the existing one-way SHA-256 digest and listings retain
only a prefix/suffix mask. On opening an older database, plaintext rows are
replaced with empty values under SQLite `secure_delete`, followed by WAL
truncate and `VACUUM`. A physical-byte regression confirms that legacy,
environment, managed, and dashboard-session plaintext values are absent while
the original credential still authenticates. Creation and rotation return the
new value once. The former admin reveal endpoint now returns HTTP `410` and
records `reveal_denied`. The internal Admin Codex key is process-memory-only and
rotates on first use after restart.

The new Dashboard remains behind `dashboard_enabled: false`. When enabled in an
isolated development gateway, a bearer credential is exchanged for a one-day,
HttpOnly, SameSite=Strict session. WebSocket origin and session are checked
before accept. Runtime `StateStore` events feed one bounded process-local hub:
general keys receive only their own session events and history; cross-key lease
owners render as `other`. Operators receive aggregate allowlisted fields by
default, without session ID, prompt, output, or tool arguments. Opening another
key's request detail requires an 8-256 character reason and creates a redacted
`dashboard_raw_view` audit event. Queue overflow drops the oldest live item and
marks the successor with `gap=true`; durable history remains queryable.

An isolated uvicorn server on loopback port `19091` physically completed HTTP
session exchange, real TCP WebSocket upgrade, and live event delivery. The
general-key socket reported `scope=private`, exact synthetic session ownership,
and its own prompt. The operator socket reported `scope=operator_aggregate`, no
session ID, and only `{"provider":"local"}`. The isolated server was stopped;
production services and worktrees were untouched.

The complete repository suite then passed `1026/1026` in `37.14` seconds with
the existing Starlette warning. Ruff check, strict mypy over 51 source files,
both frozen plan hashes, and `git diff --check` passed. All nine files touched
by this Dashboard/privacy slice pass Ruff format check; the four unrelated
whole-tree format candidates recorded above remain unchanged.

## Execution Graph compact-state and training projection — 2026-08-08

The development shadow now persists a content-addressed
`session-active-state-v1` object and links it from an immutable Graph checkpoint
with graph hash, parent checkpoint, durable event cursor, and measured
before/after byte sizes. Model-relevant top-level fields retain at most the
existing observation window; any individually oversized field is redacted and
replaced by a SHA-256 plus bounded JSON summary. The total active-state byte
ceiling is `max_tool_output_characters * max_retained_observations`. Exceeding
that ceiling fails shadow projection closed; durable session events are neither
rewritten nor deleted.

Agent trace remains `agent-trace-v3`. Its existing `metrics` object carries only
Graph ID/hash/template/checkpoint/active-state references. After all existing
training eligibility, repository policy, opt-out, privacy, and license gates
pass, the disabled-by-default collector resolves those references and validates
their integrity. It then creates a sanitized routing candidate containing graph
state, available/selected edges, node attempt results, Evidence references,
latency, and cost. No quality improvement was measured in this slice, so
`quality_delta=null` and `quality_delta_status=not_measured`; no benchmark value
was synthesized.

Focused Graph/trace/training/API checks passed `53/53` with the existing
Starlette warning. Ruff check, touched-file format, and strict mypy over the
three changed source modules passed.

An isolated physical harness used the same SQLite `StateStore`,
`ExecutionGraphStore`, restart loader, and `TrainingCollector` with 10,000
durable tool-output events. A 26,485,228-byte serialized working state compacted
to 93,367 bytes (ratio `0.003525`) under the 192,000-byte ceiling. All 10,000
events and cursor 10,000 survived restart. Checkpoint lineage was
`cp_000001 -> cp_000002` (automatic resume record) `-> cp_000003` (continued
checkpoint), with the same immutable object reference
`sha256:38aebaa57a6c66df82e6aa5d84374536abcff80693c72317032bebd521262627`.
The final sanitized Graph routing candidate was 95,792 bytes and retained exact
`stdlib-v1` compiler provenance, observed resume checkpoint `cp_000002`, and an
honest `partial_rerun_result=not_observed`. Elapsed time was 12.079 seconds,
maximum process RSS was 237,648 KiB, and the operational database was
33,181,696 bytes.

The first harness assertion expected direct `cp_000001 -> cp_000002`
continuation and stopped. Inspection confirmed that restart intentionally
creates its own immutable resume checkpoint; the corrected lineage assertion
passed without changing runtime behavior. This validates bounded storage and
restart linkage only. Execution Graph remains shadow/non-authoritative, and
Mistral, Flash, Reviewer, Judge, client-matrix, blind evaluation, canary, and
rollback production gates remain red or unrun.

After this slice, the final complete repository suite passed `1028/1028` in 40.78
seconds with the existing Starlette warning. Project-wide Ruff check, strict
mypy over 52 source files, touched-file Ruff format, both frozen plan hashes,
and `git diff --check` passed. The four unrelated whole-tree format candidates
recorded above remain unchanged.

## Cache null/zero and multi-invocation accounting — 2026-08-08

The prior Responses translator converted both an absent cache measurement and
an invalid one to `cached_tokens=0`. The development candidate now emits
`null` when the provider did not supply a valid measurement and preserves an
explicit integer zero. The same nullable value is retained in each
`model_invocation_usage` row, agent trace/training event, and Execution Graph
node attempt. The existing append-only per-invocation store remains the source
for aggregates; no last-call overwrite path was added.

Focused streaming/usage/controller/training/Graph/API checks passed `226/226`
with the existing Starlette warning. Ruff check and strict mypy passed over the
five changed source modules. An isolated physical SQLite/Responses harness
recorded two `deepseek-v4-pro` Planner calls as `(10, 5, null, 15)` and
`(20, 7, 0, 27)` for prompt/completion/cache/total. The all-time and API-key
Dashboard aggregates reported two invocations, 30 prompt tokens, 12 completion
tokens, explicit cached zero, and 42 total tokens. Responses independently
returned `null` for unreported cache and `0` for measured zero. This is gateway
accounting evidence, not a Mistral prefix-cache hit measurement; the latter
remains NOT RUN behind the failed Executor readiness gate.

After cache accounting integration, the complete repository suite passed
`1030/1030` in 37.40 seconds with the existing Starlette warning. Project-wide
Ruff check, strict mypy over 52 source files, touched-file Ruff format, both
frozen plan hashes, and `git diff --check` passed.

## Direct ExecutionGraph Dashboard projection and replay — 2026-08-08

The development Dashboard no longer has to infer Graph execution from generic
StateStore event names. `ExecutionGraphStore` publishes a non-blocking delta
only after graph, attempt, or checkpoint persistence succeeds. Listener failure
is isolated from Graph execution. Private events contain the owning key's
redacted graph topology and attempt/checkpoint records; operator events omit
graph/request IDs and content, retaining only aggregate or allowlisted runtime
metadata. REST request detail and `/v1/dashboard/snapshot` load the same
persisted graph records. Operator snapshot exposes only template, terminal,
active, and pending counts.

The live hub now assigns independent monotonic sequences per private key scope
and operator scope, retains a bounded replay window, replays events after
`last_seq`, and returns `RESYNC_REQUIRED` for stale, future, or queue-oversized
cursors. The browser reloads REST state on resync and renders compiler nodes,
parallel groups, conditional outgoing edges, providers, attempt state, and
latency in the fixed role lanes using `textContent` only.

An isolated uvicorn gateway on `127.0.0.1:19093` physically completed bearer to
HttpOnly-cookie exchange, real TCP WebSocket upgrade, and direct persisted
Graph delivery. `graph_saved` arrived at seq 1; a running node attempt and its
checkpoint advanced the cursor to seq 3. The socket disconnected, the attempt
completed while offline, and reconnect with `last_seq=3` replayed exactly seq 4
and 5. The replayed attempt was `SUCCEEDED` with measured 6.5 ms latency; REST
snapshot returned the identical attempt and graph
`graph_28d9a4334ce19b8d58dc5473`. The synthetic bearer secret was absent from
the snapshot. The isolated server stopped cleanly; production services and
runtime data were untouched.

Focused Dashboard/Graph/API checks passed `12/12` with the existing Starlette
warning. Ruff and strict mypy passed over all four affected source modules.
This proves direct projection and bounded reconnect behavior for the isolated
candidate, not production enablement or authoritative Graph execution.

After direct Graph Dashboard integration, the complete repository suite passed
`1031/1031` in 37.81 seconds with the existing Starlette warning. Project-wide
Ruff check, strict mypy over 52 source files, touched-file Ruff format, both
frozen plan hashes, and `git diff --check` passed.

## Actual Executor attempt projection — 2026-08-08

The disabled-by-default Execution Graph shadow now records actual node attempts
for the bounded request shape whose legacy execution order exactly matches the
compiled graph: no collaborator, approval, tool, test, Reviewer, or Judge node.
The compiler no longer creates a meaningless one-branch fan-out/join when no
collaborator is enabled. Chat Completions and Responses both persist the same
`CLASSIFY -> EXECUTOR_SELECT -> primary EXECUTOR -> FINALIZE` attempt sequence.
The primary attempt starts immediately before the pinned provider call and is
finished only from the common request-finalization boundary. It references the
real final-synthesis Evidence node and observed latency/token/cache/cost fields.
Because this bounded path has generated output but no independent validation,
successful HTTP completion is honestly recorded as Graph terminal `degraded`,
not falsely as verified `completed`.

An injected actual Executor `StageTimeout` preserved the existing HTTP `504`
response and recorded `REQUEST_TIMED_OUT` on the primary attempt followed by
`FINALIZE` with terminal `failed`. Graph persistence/finalization errors remain
isolated as `execution_graph_shadow_failed` and do not alter inference. Dynamic
collaboration, tool/test continuation, review, Judge, repair, and cancellation
attempts are not backfilled; those request shapes remain topology-only shadow
projections until their real stage boundaries are moved under the runtime.

Focused Graph/API success and failure checks passed `9/9`. The complete suite
passed `1032/1032` in 39.17 seconds with the existing Starlette warning. Ruff,
strict mypy over 51 source files, both frozen plan hashes, and
`git diff --check` passed. This is isolated development evidence only; Graph
mode remains disabled by default and no production service was changed.

## Runtime-owned orchestration policy — 2026-08-08

The prior orchestrated path asked the Executor model for an
`orchestration_decision`, retried malformed JSON once, and allowed the parsed
`required_agents` list to add roles. That made model output an authority over
runtime topology and consumed an extra pinned Executor call before synthesis.
The development candidate removes that provider request and retry path. Role
selection is now deterministic from the existing route, request class, risk,
explicit architecture/review signals, bounded implementation evidence, and
active failure count. Reasoner agent recommendations remain advisory and are
recorded as accepted or rejected against this policy; they cannot add a role.

Unclear explicit-orchestrated, multi-file, recovery, escalation, and high-risk
requests select Planner. Review-only requests do not load Planner. Reviewer is
selected by an explicit review signal, a high-risk implementation, or bounded
implementation evidence paired with an actual change objective. Frontier and
Judge retain their deterministic architecture/review/high-risk/disagreement
conditions. Multiple independent Planner/Reviewer/Frontier roles are marked
parallelizable. The existing `agent-trace-v3` role allowlist and schema were not
changed: the decision keeps its compatible Executor decision role while its
structured type, Evidence source, and event payload identify
`authority=runtime_policy`.

Focused tests prove that malformed or low-confidence Reasoner output cannot
change policy roles, no Executor invocation has orchestration mode, and a
multi-file request now calls `reasoner -> planner -> executor` instead of
spending an extra Executor orchestration call. Lifecycle loading/unmanaged,
remote specialist, review, streaming, and timing contracts were revalidated.
The API now evaluates the same pure policy before any role model call. A cold
or unmanaged policy-selected Planner/Reviewer returns its existing typed `503`
without spending a Reasoner call; ready requests pass the preselected roles
unchanged into `prepare_executor()`. Focused Controller/API/Policy checks passed
`338/338`. The complete suite passed `1031/1031` in 38.38 seconds with the existing
Starlette warning. Ruff, strict mypy over 51 source files, both frozen plan
hashes, and `git diff --check` passed. No production service, configuration,
branch, worktree, credential, or model was changed.

## Early scheduled Graph and collaborator attempts — 2026-08-08

With API-key scheduling enabled in an isolated development app, Runtime Policy
roles and the pinned scheduling snapshot now compile the shadow Graph before
the first Reasoner provider call. A scheduled multi-file request persisted the
actual attempt sequence `CLASSIFY -> REASONER -> PLANNER -> executor evidence
preparation -> JOIN -> EXECUTOR_SELECT -> primary EXECUTOR -> CHECKPOINT ->
FINALIZE`. Reasoner, Planner, and primary Executor attempts referenced their
real generated Evidence node IDs; executor preparation stored a SHA-256
artifact hash. The successful but independently unvalidated request retained
terminal `degraded`, and the session referenced the latest persisted terminal
checkpoint.

The existing concurrent Planner/Frontier check now runs against the same
runtime boundary. A successful `FRONTIER_A` attempt references its real
`external_expert_finding` Evidence node. When the parallel Planner fails, the
Graph fail-closes the already-running Frontier attempt as `CANCELLED` while the
legacy request preserves the completed Frontier artifact for diagnosis. This
is mocked-provider stage-boundary evidence, not a new physical Codex OAuth
provider result.

Focused checks passed `3/3`. The complete suite passed `1031/1031` in 36.68
seconds with the existing Starlette warning. Project-wide Ruff, strict mypy
over 51 source files, both frozen plan hashes, and `git diff --check` passed.
Execution Graph remains shadow/disabled by default; hard rejection, Frontier B,
streaming continuation, and all physical promotion gates remain open.

## Reviewer, Judge, tool, and test attempt ownership — 2026-08-08

The non-streaming success boundary now closes the primary Executor attempt as
soon as its final-synthesis Evidence is persisted. A high-risk request then
recorded the actual `EXECUTOR -> REVIEWER -> JUDGE -> CHECKPOINT -> FINALIZE`
sequence. Reviewer and remote Judge attempts referenced their generated
Evidence and the Executor Evidence they independently validated. Only this
straight-through dual-approved path used Graph terminal `completed`; generated
but unvalidated paths remain `degraded`.

Client-owned tool execution now pauses at a persisted `WAITING_TOOL` attempt
instead of forcing a false terminal. A matching same-session tool result loads
the existing runtime/checkpoint, preserves the provider/model pins, attaches
the observed tool Evidence, and starts attempt two of the same primary Executor
node. A tool result whose normalized command is `pytest` additionally records a
distinct `TEST` attempt before the Executor resumes. Tool and test repair edges
permit
at most two traversals and select `ON_BUDGET` afterward. The focused API path
persisted `CLASSIFY -> EXECUTOR_SELECT -> EXECUTOR(a001) -> TOOL -> TEST ->
EXECUTOR(a002) -> FINALIZE` under one Graph ID with no inferred history.

Focused checks passed `9/9` for the Graph runtime, `1/1` for tool/test resume,
and `2/2` for Reviewer/Judge selection. After one full-suite regression was
fixed at the Graph boundary, the complete suite passed `1033/1033` in 37.81
seconds with the existing Starlette warning. Project-wide Ruff and strict mypy
over 51 source files passed before that final focused fix; touched-source Ruff
and strict mypy passed afterward. This is in-process/mock-provider development
evidence, not physical Mistral, Flash, Reviewer, Judge, or client-matrix proof.

## Bounded Judge correction and failed-tool fallback — 2026-08-08

For the critical template without Frontier B, a non-approving Judge verdict now
selects a bounded `ON_FINDING` edge back to the pinned primary Executor. The
successful correction check persisted `EXECUTOR(a001) -> REVIEWER(a001) ->
JUDGE(a001) -> EXECUTOR(a002) -> REVIEWER(a002) -> JUDGE(a002) -> CHECKPOINT
-> FINALIZE`. The first Judge attempt referenced the contradicted draft and its
finding Evidence; the second Reviewer/Judge pair validated only the corrected
Executor Evidence. The terminal checkpoint was honestly `completed` after the
second approval. Minor corrections that do not require Judge recheck use the
explicit Reviewer `ON_APPROVAL` bypass to the checkpoint.

Failed client tools now persist their failure fingerprint and tool Evidence,
then select a bounded `ON_FALLBACK` edge to a new attempt of the same primary
Executor. Both successful tool/test repair and failed-tool fallback permit two
traversals; the third selects the existing terminal failure/budget edge rather
than opening another agent loop. No provider/model pin or API-key ownership is
changed during these cycles.

Focused Graph/API checks passed `13/13`. The complete suite passed `1034/1034`
in 34.57 seconds with the existing Starlette warning. Project-wide Ruff and
strict mypy over 51 source files passed. These are in-process/mock-provider
development checks. Frontier B, hard rejection, streaming tool continuation,
physical provider/client runs, blind evaluation, soak, canary, rollback, and
production promotion remain unproven.

## Hard rejection, Frontier B, and streaming Graph continuation — 2026-08-08

The Remote Judge boundary now classifies `approve`/`accept` as success,
`approve_with_edits`/`revise`/`retry_with_evidence` as bounded findings, and
all hard rejection verdicts as `ON_REJECTION`. The mocked `reject` request made
no correction provider call and persisted `CLASSIFY -> EXECUTOR_SELECT ->
EXECUTOR -> REVIEWER -> JUDGE -> FINALIZE` with terminal `failed` and no
`execution_graph_shadow_failed` event.

The critical conditional Frontier B path uses the existing configured
OpenRouter transport directly, not a new provider implementation. An isolated
mocked-provider request persisted an
actual Frontier A architecture call followed by Judge `revise`, Frontier B
disagreement, pinned Executor correction, targeted Reviewer, Judge recheck,
checkpoint, and finalization in one Graph. Frontier B Evidence opened a bounded
`ON_FINDING` repair edge, and its structured adjudication was present in the
correction request. A disabled OpenRouter transport fails closed before network
access; Frontier A remains on the existing Codex OAuth provider.

A streaming client tool call now closes the primary Executor on `ON_FINDING`
and persists `TOOL` as `WAITING_TOOL` before request cleanup. The existing
authenticated matching tool-result path loads that same Graph/checkpoint; no
parallel streaming-only continuation mechanism was added. Post-stream
Reviewer/Judge work remains honestly deferred.

Project-wide Ruff passed, strict mypy passed over 51 source files, and the full
repository suite passed `1038/1038` in 37.27 seconds with the existing
Starlette warning. `git diff --check` and frozen-plan hashes are checked
separately. This
is in-process/mock-provider development evidence only; no physical provider,
client matrix, deployment, blind evaluation, soak, canary, rollback, or
production promotion gate was claimed.

## Early Graph compilation and human approval continuation — 2026-08-08

Execution Graph shadow compilation now occurs after deterministic Runtime
Policy for every request, before `prepare_executor()` dispatches collaborators;
API-key scheduling still adds its pinned admission snapshot when enabled. This
removes the former scheduler-only ownership split without changing the
disabled checked-in default or making shadow failures authoritative.

A declarative policy requiring `operator` approval returned the unchanged HTTP
`403`, while the Graph persisted `CLASSIFY -> POLICY_GATE ->
HUMAN_APPROVAL(WAITING_APPROVAL)` rather than emitting a false terminal. The
existing admin observation command required an admin token, allowlisted user,
role permission, request-scoped nonce, and idempotency key. Approval recorded a
policy Evidence node, selected `ON_APPROVAL`, recovered only the matching
`PERMISSION_REQUIRED` loop state, and the retried request resumed the same Graph
through `EXECUTOR_SELECT -> EXECUTOR -> FINALIZE` with terminal `degraded`.
No `execution_graph_shadow_failed` event occurred.

Project-wide Ruff format/check and strict mypy over 51 source files passed. The
full repository suite passed `1039/1039` in 38.10 seconds with the existing
Starlette warning. This is isolated development evidence; production controls
remain disabled and no operator command was sent to production.

## Common Execution Graph attempt adapter consolidation — 2026-08-08

`ExecutionGraphRuntime` now owns node-type/purpose lookup, observed
token/cache/cost/latency normalization, and deterministic role failure codes
and fingerprints. Controller collaborator boundaries and API Reviewer/Judge/
Frontier boundaries call the same methods; their duplicate normalization and
SHA-256 construction branches were removed. A focused runtime check covered
metrics and the exact `EXECUTOR_TIMEOUTERROR` fingerprint, and the broader
Graph/API selection passed `26/26`.

The complete suite passed `1040/1040` in 38.30 seconds with the existing
Starlette warning; Ruff and strict mypy remained clean. The honest source audit
against starting `dev@f2c20a7` is not a completion pass: `controller.py` moved
from 4,285 to 4,152 lines (`-133`), `api.py` from 4,468 to 5,728 (`+1,260`),
and total `gateway/src/dgx_moa` Python source from 27,842 to 32,622 lines
(`+4,780`). New Graph/Dashboard/data capabilities explain additions but do not
satisfy the requested net source reduction; legacy authority/refactor work
remains open.

## Static release gate and physical readiness audit — 2026-08-08

The development worktree passed Ruff format check over 93 files, project-wide
Ruff check, strict mypy over 51 source files, and `1038/1038` pytest checks in
37.27 seconds with the existing Starlette warning. `bash -n scripts/*.sh` and
`systemd-analyze --user verify systemd/*.service systemd/*.socket` both exited
zero. The trace audit found 67 complete sessions, zero incomplete/legacy
sessions, and 100% mandatory-field completeness.

The production runtime was inspected read-only. User services
`dgx-moa-gateway.service`, `dgx-moa-loopback.service`, and the loopback socket
were active; PID `3392930` had served the gateway since 17:28:42 KST. The
tailnet listener remained `100.125.239.72:9000`, loopback `127.0.0.1:9000`
returned health `ok`, and `/readyz` returned HTTP `503`: Reasoner ready while
Executor, Planner, Reviewer, and Judge were stopped. The production source was
`main` at `396e0458f25977293281b953d2c804cf5b689970` and already dirty; it was
not modified.

Because readiness failed, no physical Mistral/Flash/Planner/Reviewer/Judge,
Frontier B, client-matrix, Dashboard, blind-evaluation, ablation, canary,
rollback, or post-deploy claim was attempted. Starting services, changing the
dirty production worktree, merging, deploying, and rollback rehearsal remain
approval-gated.

The official OpenRouter catalog resolved the frozen Frontier B target to
`anthropic/claude-opus-5` on this date. Both inspected worktrees still configure
`anthropic/claude-sonnet-4.6`; production additionally keeps
`openrouter_fallback_enabled: false`. The configured key files exist with mode
`0600` and their contents were not read or emitted. No paid request or config
promotion was attempted because the provider/readiness gate and approval are
still open.

## Persistent Codex App Server session contract — 2026-08-08

The installed Codex `0.146.0` generated protocol schema exposes the required
`thread/start`, `thread/resume`, `turn/start`, `turn/interrupt`, and
`thread/compact/start` methods. The development adapter now reuses Codex's
native profile-specific daemon through `codex app-server proxy`; it does not add
or manage another long-lived process. New threads are non-ephemeral and
read-only. A mode-`0600` bounded mapping stores only the SHA-256 of API-key plus
session scope, opaque thread ID, and turns since compaction. Raw scope and
prompt are absent. Timeout and client cancellation send an exact interrupt
before proxy process-group cleanup; typed proxy unavailability alone retains
the stdin `codex exec` fallback.

Focused subprocess tests exercised start, restart-backed resume, one-turn
compaction, cancellation interrupt, bounded mapping eviction, permission
rejection, structured public output, and proxy command selection: `42/42`
passed. The full repository suite passed `1043/1043` in 40.27 seconds with the
existing Starlette warning; Ruff and strict mypy over 51 source files passed.
No daemon was started. Read-only `daemon version` found no primary or secondary
profile socket and found the already-running default daemon at Codex `0.146.0`.
One bounded structured architecture turn was sent through that default daemon;
it produced no public result before the exact 300-second deadline and returned
`FRONTIER_PROVIDER_TIMEOUT`. The adapter sent `turn/interrupt`, removed its
short-lived proxy process, left the pre-existing daemon running, and did not
retry or change transport. Because the first turn failed, physical resume and
compaction were not attempted and the persistent transport gate is FAIL.

The development Frontier B target is now the official OpenRouter slug
`anthropic/claude-opus-5`; its model page reported `$5` input and `$25` output
per million tokens on this date, and accounting defaults were updated to those
values. Production remains on Sonnet with paid fallback disabled. No credential
contents were read and no paid request was sent.

The source audit remains a completion failure. Against starting
`dev@f2c20a7`, `api.py` is `4468 -> 5564` (`+1096`), `controller.py` is
`4285 -> 4163` (`-122`), `frontier.py` is `1407 -> 1945` (`+538`), and all
gateway Python source is `27842 -> 32765` (`+4923`). Persistent transport closes
a required functional gap but does not satisfy the requested net reduction.

## Graph-owned continuation and terminal consolidation — 2026-08-08

The Execution Graph runtime now owns successful/failed tool continuation,
validation-command TEST projection, approval continuation, external wait
detection, checkpoint emission, and terminal transition. API retains the
request/Evidence lookup and fail-soft event boundary but no longer traverses or
mutates those Graph nodes directly. Reviewer/Judge/Frontier attempt failure
handling also emits the shadow failure event from one helper instead of six
caller-local exception blocks.

The tool success/failure continuation, human approval, correction/recheck,
hard rejection, terminal, and SQLite shadow-degradation focused checks passed.
The final repository suite passed `1043/1043` in 38.16 seconds with the existing
Starlette warning; Ruff format/check, strict mypy over 51 source files, and
`git diff --check` passed. This moved 164 lines out of `api.py`, but the common
runtime remains required source, so the total delta is still `+4923` and the
net-reduction completion gate remains open.

## Reasoner/Planner/Frontier A three-way fan-out — 2026-08-08

`prepare_executor()` now applies deterministic Runtime Policy and lifecycle
admission before provider use, then starts Planner, Frontier A, and the optional
Reasoner as independent tasks before joining their public artifacts. The former
post-Reasoner Planner/Frontier launch branches and unreachable deferred Frontier
path were removed. A synchronization-barrier regression test proved all three
tasks entered concurrently; the Planner-failure case also preserved completed
Frontier evidence while the Graph cancelled the failed join branch.

The focused Controller/API/Graph suite passed `344/344`; four cold/unmanaged
lifecycle checks passed; the full repository suite passed `1043/1043` in 42.29
seconds with the existing Starlette warning. Ruff, strict mypy over 51 source
files, frozen plan hashes, and `git diff --check` passed. This is isolated mock
runtime evidence only: actual provider overlap and local compute contention are
not measured, Graph remains shadow-only, and production was not touched.

## Common Execution Graph shadow-failure boundary — 2026-08-08

API and Controller now call one `record_shadow_failure()` boundary for Graph
start/finish/resume/approval/tool/finalize persistence errors. Eighteen repeated
event-construction blocks were removed while preserving each stage name,
failure class, fail-soft behavior, and legacy client response. Internal-only
review-evidence forwarding methods were also removed in favor of their existing
shared functions. The focused Graph/approval/tool/SQLite degradation set passed
`18/18`, review/fan-out checks passed `6/6`, and the full repository suite passed
`1043/1043` in 37.99 seconds with the existing Starlette warning. Ruff and
strict mypy over 51 source files passed.

Against starting `dev@f2c20a7`, `api.py` is now `4468 -> 5528` (`+1060`),
`controller.py` is `4285 -> 4126` (`-159`), `frontier.py` is `1407 -> 1945`
(`+538`), and all gateway Python source is `27842 -> 32696` (`+4854`). This is
69 fewer lines than the preceding checkpoint, but the required net reduction
and legacy-authority removal gates remain open.

## Discord observation compatibility removal — 2026-08-08

The operator had excluded Discord from release scope on 2026-07-22, neither
development nor inspected production config contains a Discord key, and
production observation uses Telegram. The development-only Discord provider,
config model, English card renderer, metric, and compatibility tests were
removed. Observation control now accepts only `provider=telegram`; its nonce,
allowlist, role permission, audit, and idempotency contract is unchanged.
The unreferenced 80-line `scripts/opencode-completion-fake.py` launcher was also
removed. The earlier isolated removal evidence remains reachable at experiment
commit `681f1dd`; historical Discord/fake validation evidence remains in this
document and Git history.

Telegram transport, batching, provider failure isolation, secret-backed config,
and Graph approval resume checks passed `13/13`. The full suite passed
`1042/1042` in 38.19 seconds with the existing Starlette warning; Ruff, strict
mypy over 51 source files, frozen plan hashes, and `git diff --check` passed.
Source/config/test reference scan returned no Discord symbols. Against starting
`dev@f2c20a7`, API is `+1050`, Controller `-159`, and all gateway Python source
is `27842 -> 32586` (`+4744`). Production files and services were not changed.

## Rejected legacy context tuner retirement — 2026-08-08

Reference scan found `dgx_moa.context_tuning` reachable only from the retired
`scripts/tune-context.sh` and its unit test. That path restarted legacy
`resident`/`judge` targets and therefore conflicted with the current fixed Phase
3 Executor baseline and exact stop/start-only lifecycle contract. Its 300-line
module, 10-line launcher, and dedicated tests were removed using the preserved
experiment verdict at `ce2f212`. `docs/CONTEXT_TUNING.md`, benchmark results,
failure measurements, and Git history remain as historical evidence.

The full suite passed `1037/1037` in 36.75 seconds with the existing Starlette
warning; Ruff, strict mypy over 50 source files, frozen plan hashes, and
`git diff --check` passed. Gateway Python source is now `27842 -> 32286`
(`+4444`), so this removes another 300 runtime lines but does not satisfy the
overall net-reduction gate. Production files and services were not changed.

The dry-run Mistral command initially depended on an external environment value
to make the required MARLIN backend explicit. `serve.py` now defaults only the
Executor to `MARLIN` while retaining `DGX_MOA_EXECUTOR_MOE_BACKEND` as the
calibration override. Without any backend override, `--print` emitted the pinned
Mistral revision with context `65536`, `max_num_seqs=1`, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, and `--moe-backend MARLIN`. The focused launcher
suite passed `8/8`; the full suite passed `1038/1038` in 41.60 seconds. This is
command-construction evidence, not a model-load or readiness pass. Current
gateway Python source is `32288` lines (`+4446` from the starting epoch).

The reserved `OpenAIAPIProvider` Frontier scaffold had zero references outside
its own definition and could only raise a disabled-provider error. It was
removed because Frontier collaboration is Codex OAuth-only and must never
require an OpenAI API key. The single-implementation `FrontierProvider`
Protocol and unused `PromptRegistry.active_template()` wrapper were removed in
the same reference-backed pass. The full suite remained `1038/1038` in 38.81
seconds; Ruff and strict mypy over 50 source files passed. Gateway Python source
is now `32254` lines (`+4412` from the starting epoch). These deletions do not
satisfy the overall net-reduction gate.

The 192-line `sanitized_feed.py` prototype had no runtime, script, or config
import; only its 148-line dedicated test remained. The live API-key-scoped
Dashboard already owns the connected redaction, replay/RESYNC, bounded queue,
gap, and subscriber-isolation path. The disconnected prototype and its test
were removed, while historical evidence remains in this document and commit
`3b34e32`. Live Dashboard tests remain in the suite. The full suite passed
`1032/1032` in 40.71 seconds; Ruff and strict mypy over 49 source files passed.
Gateway Python source is now `32062` lines (`+4220` from the starting epoch), so
the overall net-reduction gate remains open.

## Frozen paired-bootstrap evaluator — 2026-08-08

`scripts/evaluate-paired-noninferiority.py` implements the preregistered
stdlib-only target-minus-comparator statistic, strict `-0.10` margin, 10,000
paired resamples, fixed seed `20260808`, and two-sided 95% percentile interval.
It fails closed to `INCONCLUSIVE` for missing/unexpected pairs, fewer than 30
pairs, mixed epochs, mismatched condition hashes, incomplete telemetry,
non-blind scoring, failed reliability, or incomplete client/category coverage.
Failed runs must remain present with success `0`; a success `1` additionally
requires completed status, passed hidden tests, and no false completion. Input
and score-freeze hashes are retained without copying raw prompts or outputs.

The preserved `auto/evaluation/frontier-noninferiority-v1` experiment at
`5133cfc` was inspected before adding this tool. Its five-task panel, quality
margin `-5`, seed `56052026`, and one-sided 90% bounds conflict with the current
seven-category, `-0.10`, seed `20260808`, two-sided 95% frozen contract, so it
was retained as historical evidence rather than reused or merged.

Two focused checks proved deterministic `[1.0, 1.0]` CI for a complete covered
30-pair fixture and `INCONCLUSIVE` without dropping a missing, 29-pair,
telemetry-incomplete fixture. The full suite passed `1034/1034` in 37.00
seconds before the hidden-test/false-completion consistency check was added.
The final full suite passed `1034/1034` in 43.37 seconds; Ruff and strict mypy
over 49 source files passed. This is protocol
implementation evidence only: neither required comparator has a current
physical 30-pair dataset or CI result, so non-inferiority remains unproven.

## Promotion readiness recheck — 2026-08-09

The production runtime was re-inspected read-only after the blocked Goal was
resumed. `/readyz` again returned HTTP `503` with Reasoner `ready` and Executor,
Planner, Reviewer, and Judge `stopped`; the gateway unit was active and all four
local role units were inactive. Production remained the existing dirty
`main@396e0458f259`. No service, credentialed provider, paid transport, config,
production file, branch, or worktree was changed. Physical role/client/
evaluation/canary/rollback promotion remains blocked on explicit approval and
readiness.

## Atomic specialist live-validation checkpoints — 2026-08-09

`scripts/validate-specialist-routing.py` now requires an explicit output path
and atomically checkpoints Planner and Reviewer progress after each role. The
artifact contains only schema/status/provider, model, structured-output status,
latency, token usage, and exception class. It never persists prompts, raw
content, hidden reasoning, credential values, or exception messages. A mocked
Planner success followed by Reviewer failure retained the passed Planner row,
recorded only `RuntimeError` for Reviewer, removed the temporary file, and did
not retain the injected raw error detail. Focused specialist checks passed
`11/11`; the full suite passed `1035/1035` in 35.67 seconds. Ruff and strict
mypy over 49 source files passed. No credentialed request was sent.

## Approved isolated physical validation — 2026-08-09

The operator approved physical validation. The approval was applied only to
isolated model/provider, Frontier, client, and Dashboard gates; it did not
authorize production worktree changes, service topology changes, deployment,
merge, canary, or rollback rehearsal. The inspected production gateway stayed
active and unchanged at dirty `main@396e0458f259`; `/readyz` remained HTTP
`503` with only Reasoner ready. Executor, Planner, Reviewer, and Judge units
remained stopped.

The host had `126465490944` available memory bytes and no model GPU compute.
The pinned Mistral snapshot at revision
`b1a9048590131d38491bd23a7c9f6ed0962f0358` again passed the authoritative Hugging
Face cache verification with all `23/23` files. Dry-run command construction
again emitted the exact Phase 3 contract: context `65536`, one sequence,
`1700000000` KV bytes, GPU utilization `0.5`, and MARLIN. The same physical load
was not repeated because the already-recorded identical-profile attempts caused
global OOM, killed unrelated processes, and never listened. Cache integrity is
PASS; model load/readiness and every Mistral-dependent gate remain FAIL/NOT RUN.

An authenticated OpenCode Go catalog returned HTTP `200` with 25 models and all
five exact targets. The atomic specialist run retained these sanitized results:
DeepSeek V4 Pro Planner passed schema validation in `14.257` seconds with
`450/812/1262` prompt/completion/total tokens; GLM 5.2 Reviewer returned no
usable public structured output and failed. DeepSeek V4 Flash completion was
typed `OverflowExecutorUnavailable`, consistent with the previously measured
workspace region/opt-in gate; native tool continuation remains FAIL. No raw
credential, prompt, response, or hidden reasoning was persisted.

Kimi K3 Judge reproduced truncation at the former 1,024-token output ceiling.
At 2,048 tokens it passed the failed-test row but truncated the next structured
row after another near-ceiling response. The ceiling was therefore calibrated
to 4,096 without increasing retry or call budgets. The final sanitized matrix
passed valid approval, unsupported-claim rejection, failed-test detection,
missing-criterion detection, bounded correction, corrected recheck, and the
maximum two-call enforcement. Invalid structured-output exceptions now suppress
their raw validation context so provider content cannot leak through a CLI
traceback. Focused Judge checks passed `7/7`.

The required role-independence reverse comparison used Kimi K2.5 Reviewer and
GLM 5.2 Judge. Kimi Reviewer passed a valid approval in `2.805` seconds and
rejected failed-test evidence with one important finding in `11.060` seconds.
GLM Judge rejected the failed-test claim in `25.447` seconds but failed its
valid-result approval case with invalid structured output. Combined with the
primary GLM Reviewer failure, this is not enough to promote a replacement
Reviewer/Judge pair: Kimi K3 Judge is PASS, while Reviewer selection and pair
independence remain INCONCLUSIVE.

One bounded Frontier A architecture call passed schema validation on OAuth
profile `primary` in `30135.776` ms with `19553/804/20357` tokens. Its transport
was `codex_exec_fallback`, proving the read-only stdin fallback but not the
persistent App Server gate. Resume and compaction remain unproven.

The first paid Frontier B request returned HTTP `400`. Current OpenRouter model
metadata showed nine Opus 5 endpoints but only one advertising the unnecessary
`temperature` sampling parameter; `require_parameters=true` therefore excluded
the other endpoints. Removing that single nonessential field preserved high
reasoning and strict structured output. The one approved retry passed in
`43616.312` ms with `826/2554/3380` tokens and calculated cost `$0.06798`; all
six architecture fields validated and only the five allowlisted evidence
categories were transmitted. Frontier B is PASS in isolation.

At this checkpoint the repository suite passed `1036/1036` in `36.28` seconds
with the one existing Starlette warning. Ruff format/check, strict mypy over 49
source files, shell syntax, frozen plan hashes, and `git diff --check` passed.
The target client matrix, cross-key Flash overflow, Reasoner ablation, paired blind
non-inferiority, long-horizon Goal, canary, deployment, and rollback were not
run because their Mistral/Flash readiness prerequisites remain red.
The Dashboard remains disabled; its earlier isolated TCP WebSocket/replay
physical evidence was not promoted to production evidence.

## Reviewer replacement and real collaborator overlap — 2026-08-09

The GLM 5.2 Reviewer failure was isolated from the generic specialist adapter.
The model's documented `thinking.type=disabled` parameter produced one valid
approval probe in `3177.929` ms with 346 tokens, but the complete specialist
validator again returned reasoning-only empty public output twice under the
same parameter and bounded retry. GLM Reviewer therefore remains a measured
availability failure rather than a parser workaround.

Kimi K2.5 Reviewer passed one valid approval and one failed-test rejection, but
the model is a deprecated candidate and would reduce independence from Kimi K3
Judge. DeepSeek V4 Pro Reviewer instead passed the same two directions: approval
in `4358.089` ms with 547 tokens and failed-test rejection in `10314.595` ms
with 943 tokens. The disabled development mapping was changed from GLM 5.2 to
this measured replacement. The final atomic specialist validator then passed
both configured roles on their first attempts: Planner in `11.919` seconds with
1,032 tokens and Reviewer in `4.071` seconds with 516 tokens. No provider output
or hidden reasoning is present in the artifacts.

The Runtime already retries invalid Reviewer structured output once. The live
validator now mirrors that bound, aggregates both attempts' usage, records the
attempt count, and suppresses raw validation context on final failure. A mocked
empty-then-valid case proved exactly two attempts and accumulated usage; provider
exceptions are still not retried.

A separate physical fan-out started external Qwythos Reasoner, OpenCode Go
Planner, and OAuth Frontier A within 14 ms. Reasoner completed at `10203.415`
ms, Planner at `25169.162` ms, and Frontier at `25288.465` ms; all three
intervals overlapped and total wall time was `25288.575` ms. All public schemas
validated. Frontier used the read-only `codex_exec_fallback` transport, so this
is physical collaborator parallelism evidence but still not a persistent App
Server resume/compaction pass or an end-to-end Mistral synthesis pass.

Controller also contained six disconnected Frontier candidate-management
wrappers whose only callers were two dedicated tests; the actual implementation
and tests already live in `frontier.py`. Removing those wrappers and their
self-tests reduced Controller from the starting 4,285 lines to 3,994 (`-291`).
Total gateway Python source is now 31,931 lines versus 27,842 at the epoch start
(`+4089`), so the requested overall net reduction remains unmet. The full suite
passed `1034/1034` in `37.96` seconds with the existing Starlette warning. Ruff
format/check, strict mypy over 49 source files, shell syntax, frozen plan hashes,
and `git diff --check` passed.

## Physical Execution Graph partial rerun — 2026-08-09

The first isolated SQLite harness exposed that `partial_rerun()` accepted a
`SKIPPED` TEST node. Because that node had never been on the selected execution
path, its existing Reviewer-to-FINALIZE edge allowed finalization without
running the purportedly invalidated TEST. The initial artifact was overwritten
and was not accepted as evidence.

The Runtime now rejects empty invalidation sets, unknown nodes, and nodes not in
`SUCCEEDED`, `DEGRADED`, or `FAILED`. The corrected physical harness completed
an engineering Graph, verified the primary Executor artifact SHA-256, and
invalidated the successful Reviewer. Exactly Reviewer and FINALIZE reran; the
unaffected Planner attempt IDs remained unchanged. The persisted checkpoint
reason was `partial_rerun`, the mode-`0600` SQLite runtime reloaded with terminal
`completed`, and the post-rerun final emitted exactly once. Elapsed time was
`67.378` ms. The focused Graph/training check passed. The final full suite passed
`1034/1034` in `45.82` seconds with the existing Starlette warning; Ruff,
strict mypy, shell syntax, frozen plan hashes, and `git diff --check` passed.

## Final external-state blocked audit — 2026-08-09

The third consecutive resumed Goal turn rechecked the external prerequisites.
Available host memory was `126571020288` bytes with `322412544` swap bytes in
use; GPU compute utilization was zero. The gateway unit was active while
Executor, Planner, Reviewer, and Judge units were inactive, and loopback
`/readyz` remained HTTP `503`. Repeating the identical fixed Mistral load is
still rejected by the recorded global-OOM incident and would not constitute a
new experiment.

One minimal authenticated DeepSeek V4 Flash completion again failed with the
typed `OverflowExecutorUnavailable` region/opt-in boundary. Therefore the
Mistral primary, Flash overflow, target client matrix, paired blind evaluation,
Reasoner ablation, long-horizon Goal, canary, rollback, deployment, and final
branch normalization cannot proceed without an external hardware/runtime change
and operator workspace opt-in. Production files and services were not changed.

## Mistral NVFP4 memory differential and Flash 403 reclassification — 2026-08-09

This physical follow-up supersedes the terminal conclusion of the preceding
blocked audit without deleting its evidence. The Goal, all prior failures, and
protocol epoch `dynamic-moa-v3-20260808` remain preserved and active.

The pinned Mistral snapshot contains 13 consolidated shards. Its index reports
`70801904048` tensor bytes and direct safetensors inspection reports
`70801959560`: `58435043328` U8 weight bytes, `7304380416` float8 scale bytes,
`5062424792` BF16 bytes, and `111024` F32 bytes. A vLLM meta-model allocation
reports `70801959776` parameter bytes. These independent values place the static
checkpoint/model near 66 GiB, not the historical `120052` MiB allocation.

Three isolated SGLang `dev-cu13` probes used the same revision, context `65536`,
one running request, and no chunked prefill. The preserved default-TRITON probe
loaded weights in `354.60` seconds, reported `67.96` GB weights, allocated
exactly 65,536 BF16 KV tokens in `1.41` GB, and retained `43.90` GB available;
it then failed CUDA graph compilation with incompatible dimensions `256` and
`512`. The explicit CUTLASS_MLA probe loaded in `273.38` seconds, reported
`67.88` GB weights and the same `1.41` GB KV allocation, then failed warmup at
`D_q_nope == D_latent`. Neither probe showed abnormal post-load growth. Source
inspection also established that this SGLang compressed-NVFP4 MoE scheme
selects FlashInfer CUTLASS unless TRTLLM is requested; its `marlin` CLI value did
not produce a true MARLIN MoE run. SGLang is therefore stable memory evidence,
not a functional or MARLIN qualification PASS.

A follow-up general FlashInfer-attention probe used the same fixed profile,
dense FP4 `marlin`, and explicit FlashInfer CUTLASS MoE. It preserved the
`68137` MiB weight allocation and passed the two earlier MLA attention failure
sites, but its first dense FFN invocation failed with
`mm_fp4 does not support backend 'marlin' with capability 121`. The container
exited without OOM and the gateway remained healthy. This separates another
runtime-compatibility blocker: the current SGLang/FlashInfer image cannot
execute its advertised dense MARLIN path on GB10 SM121.

The corrected vLLM `0.22.1` probe forced both dense and MoE MARLIN with the exact
Phase 3 profile: context `65536`, `max_num_seqs=1`, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, lazy safetensors loading, and TRITON_MLA. Static
allocation stayed at `68256` MiB throughout the 392.44-second load. Immediately
after the MARLIN weight-only FP4 warning and
`MoEPrepareAndFinalizeNoDPEPModular`, allocation rose past the 96 GiB guard
before KV allocation; the exact unit was stopped. This locates the historical
growth in vLLM's post-load NVFP4-to-MARLIN packing phase, not checkpoint size,
lazy shard staging, KV, CUDA graph capture, or the steady CUDA context.

Changing only `PYTORCH_CUDA_ALLOC_CONF` to `backend:cudaMallocAsync` completed
the 422.23-second load and MARLIN preparation. vLLM reported `66.06 GiB` model
memory; sampled allocation was `71671` MiB, the guard did not fire, and vLLM
reserved the exact `1.58 GiB` KV budget with 73,776 tokens. CUDA graph warmup
then failed separately with `CUDA driver error: invalid argument`. Repeating
with native allocator `expandable_segments:True` loaded in `417.74` seconds but
crossed the guard at exactly `100868` MiB five seconds after MARLIN preparation.
Thus allocator selection alone controls the abnormal packing peak on this host:
native caching retains/fragments MARLIN repack allocations, while
cudaMallocAsync releases them but is not yet CUDA-graph compatible in this
runtime. Eager mode was not used or accepted as evidence.

Two native-allocator automatic-reclamation calibrations kept every model,
backend, context, sequence, KV, and loader argument unchanged. A
`garbage_collection_threshold` of `0.70` loaded in `409.19` seconds and crossed
the guard at `98626` MiB five seconds after MARLIN preparation. Lowering the
threshold to `0.60` loaded in `434.25` seconds but crossed at `99546` MiB ten
seconds after preparation. Both had zero swap growth and exact-unit cleanup.
Threshold-only reclamation is therefore non-monotonic and insufficient; neither
run reached KV allocation or readiness.

Adding native `max_split_size_mb:128` to the `0.60` threshold loaded in
`482.58` seconds but crossed the guard at `101866` MiB six seconds after MARLIN
preparation. Native expandable segments, garbage-collection thresholds, and
large-block split control therefore all fail the 96 GiB safety contract; no
further native-allocator tuning was accepted.

With cudaMallocAsync, changing the supported vLLM CUDA graph mode from default
`FULL_AND_PIECEWISE` to `PIECEWISE` preserved `enforce_eager=False`, completed
MARLIN packing at `71671` MiB, reserved the exact 1.58 GiB KV budget, and
reported 73,776 KV tokens. Piecewise capture still failed in the same static
Triton launcher with `CUDA driver error: invalid argument`; PyTorch immediately
warned about an uncaptured free of a captured cudaMallocAsync allocation.
Enabling PyTorch's `graph_capture_record_stream_reuse` option reproduced that
same warning and failure. This isolates the remaining failure to
cudaMallocAsync captured-allocation lifetime in this PyTorch/vLLM CUDA-graph
path, not full-graph selection.

The supported compiled path with cudaMallocAsync and
`cudagraph_mode=NONE` retained `enforce_eager=False`; torch.compile remained
active and no eager flag was used. It loaded weights in `466.05` seconds,
completed MARLIN preparation, allocated the fixed KV cache, initialized the
engine in `18.25` seconds, and opened loopback port `19301`. Steady sampled GPU
allocation was `72986` MiB. `/health` and `/v1/models` returned HTTP `200` with
`max_model_len=65536`.

The same isolated server then passed a Chat completion (`READY`, 24 total
tokens), a forced native `lookup_weather` tool call with JSON arguments, a
same-call-ID tool-result continuation, a completed Responses request
(`RESPONSE_OK`, 28 total tokens), and a streaming Chat response with seven data
chunks, usage, and `[DONE]`. The Responses usage reported 16 cached input
tokens, directly exercising prefix caching. GPU allocation remained `72986`
MiB and the unchanged production gateway returned `/healthz` HTTP `200` after
each gate. Exact service stop removed the model process and listener. This is a
65K memory/readiness/API PASS and establishes the backend for isolated 128K
qualification; it is not production promotion or performance-equivalence
evidence.

The isolated 128K qualification kept the same revision, one sequence,
cudaMallocAsync, compiled no-cudagraph path, dense/MoE MARLIN, lazy loader, and
TRITON_MLA. Only `max_model_len=131072` and the approved initial
`kv_cache_memory_bytes=3400000000` changed. Weight loading took `498.10`
seconds; vLLM again reported `66.06 GiB` model memory. The fixed KV allocation
was `3.17 GiB`, exactly 147,568 tokens, giving `1.13x` concurrency for a
131,072-token request. Engine initialization took `18.47` seconds and
`/health` plus `/v1/models` returned HTTP `200` with
`max_model_len=131072`. Sampled steady GPU allocation was `74714` MiB.

At 128K the server passed Chat (`CHAT128_OK`), Responses
(`RESPONSE128_OK` with 16 cached input tokens), streaming with usage and
`[DONE]`, a forced native tool call, and same-call-ID tool continuation. A
tokenizer-counted near-limit request then completed with `125026` prompt tokens,
`125033` total tokens, output `LONG128_OK`, and 58.359-second wall time. GPU
allocation after the long request was `75994` MiB and the production gateway
remained healthy. A distinct 120K-prefix streaming request was disconnected by
the client after one second; six seconds later running requests, waiting
requests, and KV-cache usage were all exactly zero while model and gateway
health remained HTTP `200`. Restart and longer-horizon soak gates remain
separate requirements; this row alone does not authorize production promotion.

An exact second stop/start used the identical revision and 128K invocation.
Weight loading again reported `66.06 GiB` and took `504.05` seconds. The engine
reserved the same fixed `3.17 GiB` KV allocation, exposed 147,568 KV tokens and
`1.13x` concurrency, and initialized in `6.49` seconds using the cached compiled
graph while retaining `enforce_eager=False`. Readiness returned HTTP `200`, the
model list again reported `max_model_len=131072`, steady GPU allocation was
`74714` MiB, and a post-restart completion returned exactly `RESTART128_OK`.
The unchanged gateway returned `/healthz` HTTP `200`. Exact service stop then
removed the model GPU process and listener; the gateway remained healthy and
`/readyz` honestly returned HTTP `503` because the isolated Executor was stopped.
This repeat clears the Mistral abnormal-memory/backend-readiness blocker for the
qualification backend; it does not clear the independent soak, performance,
coding-task quality matrix, canary, rollback, or promotion gates.

The checked-in development candidate now represents the physically qualified
profile rather than the former 65K placeholder. Command generation selects
context 131,072, one sequence, 3.4 GB KV, dense and MoE MARLIN, TRITON_MLA,
lazy safetensors, compiled `cudagraph_mode=NONE`, and no eager flag; the Executor
unit supplies cudaMallocAsync. The generated command matched the successful
probe invocation. Focused configuration and unit checks passed `49/49`.

A third exact 128K transient start then drove an isolated authenticated live
client matrix without binding the production Executor port. The first retained
matrix generation passed raw generic/primary, OpenCode, and Hermes but exposed
Codex Responses HTTP 400 because Mistral rejects the OpenAI `developer` role.
The shared provider-body path now maps that role to `system` only for a Mistral
Executor without mutating the client request. The next generation produced the
requested Codex marker but exposed assistant-final continuation: Mistral requires
native `continue_final_message=true` and `add_generation_prompt=false` together.
Both intermediate failure generations are retained rather than overwritten.

After those protocol fixes, Codex received the marker but its strict
`ResponseCompleted` parser rejected an unmeasured
`input_tokens_details.cached_tokens=null`. The internal usage, CSV, trace,
Dashboard, and training representations still preserve null as unmeasured; the
Responses wire adapter now omits the entire optional detail object when the
provider did not measure it and still emits integer zero when zero was measured.
The diagnostic generation retained only event types and the typed parse error;
raw client artifacts were deleted by the harness.

The final `mistral-128k-20260809-v6` matrix passed. Raw generic and primary Chat
requests returned valid HTTP 200 JSON; installed Codex completed its Responses
turn and observed `CODEX_CLIENT_OK`; installed OpenCode and Hermes exited zero
with their exact markers. The isolated metrics recorded six Executor invocations
and one Qwythos Reasoner invocation. Production Git was byte-for-byte unchanged,
the isolated gateway stopped, and all raw client directories were removed. The
candidate remained at `74716` MiB during the matrix. Exact model/watchdog stop
removed the GPU process; the unchanged gateway returned `/healthz` HTTP 200 and
honest stopped-profile `/readyz` HTTP 503. This clears the live protocol matrix,
not the broader coding-task quality/noninferiority matrix.

The post-fix full suite passed `1036/1036` in `36.14` seconds with the existing
Starlette warning. Ruff check/format, strict mypy over 49 source files,
`git diff --check`, and both frozen protocol-epoch hashes passed.

All probes were loopback-only transient units or isolated containers with a
96 GiB exact-unit watchdog. After cleanup no model GPU process or listener
remained, swap did not increase, the production gateway returned `/healthz`
HTTP `200`, and role services retained their prior stopped state. No production
configuration, service topology, or deployment changed. The 65K abnormal-memory
cause is diagnosed and the compiled no-cudagraph vLLM backend passed readiness,
inference, and repeated 131,072-context startup with the target 3.4 GB initial
KV budget. Longer-horizon qualification remains pending.

The OpenCode Go differential reused endpoint `https://opencode.ai/zen/go`, the
same safely fingerprinted key/workspace identity found in the protected runtime,
and the exact catalog model ID `deepseek-v4-flash`. The catalog returned HTTP
`200` with Flash present. Minimal messages-only, the historical successful JSON
shape, and native-tools request shapes all returned the same HTTP `403`
`RegionError`. With the same endpoint and key, `deepseek-v4-pro` returned HTTP
`200`. Earlier validation records multiple successful Flash completions with
that same endpoint and identity. Request shape, native tools, and general key
authentication are therefore excluded; model-specific regional routing,
workspace policy regression, and provider incident remain unresolved
possibilities. A China-hosted workspace opt-in is not established as the cause
or a mandatory prerequisite. Native tool continuation, provider pinning,
cross-key overflow, same-key queue/fairness, and recovery remain pending until
a minimal Flash completion succeeds again.

### Qualification-scope correction — 2026-08-09

The 96 GiB watchdog above was a host-protection threshold for those isolated
runs, not a hard product memory limit. The approximately 96 GiB steady-state
footprint remains an optimization target with system-headroom requirements.
Likewise, the compiled `cudagraph_mode=NONE` result clears abnormal-memory,
readiness, and API questions only. It does not satisfy the final NVFP4
performance gate. Production qualification additionally requires an active,
physically measured CUDA Graph path and sustained long-output decode evidence
under the pinned 128K, one-sequence, NVFP4/MARLIN contract. Historical rows are
retained unchanged; this paragraph governs their current interpretation.

## Mistral 128K client-quality matrix and Flash recovery check — 2026-08-09

The fresh frozen `mistral-128k-v9-full-20260809` matrix completed all 20
scheduled Docker-isolated cells. Its immutable schedule used seed
`74d3de357c0ae2b0314fb68df330b4dba3e4f3cbd7b8f7bdd5fa68c45adfd12c`,
schedule SHA-256
`88884649e03ffc552dfea7284904e0a3ddc3336ed8361a14a9c8d40a0643f213`,
and harness SHA-256
`37183fd36ae6b44c83e1760e3a063a657e78a6409d9baf877bf0f1f3b12111a2`.
The isolated vLLM backend remained on the pinned Mistral revision, context
131,072, one sequence, fixed 3.4 GB KV, dense/MoE MARLIN,
cudaMallocAsync, compiled `cudagraph_mode=NONE`, lazy safetensors, and
TRITON_MLA throughout the run.

The matrix result is intentionally retained as incomplete qualification:
baseline passed `5/5`, OpenCode `4/5`, Codex `2/5`, and Hermes `2/5`, for
`13/20` total. Every baseline cell passed. OpenCode failed only atomic-store,
where the generated source contained an unterminated string at line 111 and
both public and hidden validation failed. Codex webhook-verifier treated the
documented string timestamp, nonce, and signature arguments as bytes, failed
three of four public tests, repeated the failed action, and ended after five
stream reconnection attempts. Codex log-report passed public and hidden
validation but its stream disconnected before terminal completion. Codex
dag-runner eventually passed all public and hidden checks after repair, but
the frozen scorer retained a bad-terminal failure; atomic-store and
rate-limiter passed all checks.

Hermes rate-limiter and webhook-verifier passed all checks. Hermes dag-runner
and log-report returned HTTP 409 after exhausting the bounded engineering-loop
budget. Their usage records consequently contained a null session ID and no
successful unittest tool-result evidence. Hermes atomic-store emitted a
validation tool call but ended before receiving its tool result or producing a
final response, so its source passed public and hidden validation while the
tool-evidence gate failed. These failures are classified separately from the
two incorrect source implementations; they remain gateway/session engineering
failures, not evidence that the backend is unstable in memory.

Before the full matrix, the retained Codex v6 canary exposed a fail-open review
readiness defect: a Reviewer transport failure was incorrectly treated as
unfinished implementation work and repeatedly forced another tool call. The
controller now permits completion when review failed and `review_fail_closed`
is false, while preserving fail-closed behavior when that flag is true. The
next canary exposed a second independent defect: malformed optional Frontier
architecture output raised `ValueError` outside the existing `RuntimeError`
degradation path. Optional malformed Frontier output now degrades confidence
and continues; required Frontier and Judge paths remain fail-closed. The
targeted `mistral-128k-v8-canary-20260809` Codex rate-limiter rerun then passed
all ten checks in 116.612 seconds, and the fresh full-matrix copy passed again
in 91.058 seconds.

Post-run regression checks passed: full pytest `1041/1041` in 36.35 seconds,
Ruff check over the changed gateway, harness, and test files, and strict mypy
over 49 source files. Both frozen protocol-plan hashes remained unchanged:
`41e16b4f2fb8f442d8da3065ba53eacb317fc9a68333e63c02253784bcf1a4bd`
and `bd69063dbd20891349ea459b6ecff4a6cb53ac17f88359d1df47e1b6fb29a668`.

The Mistral abnormal-memory/backend-readiness blocker remains cleared because
the stable backend completed the entire matrix without OOM or allocator
growth. Client-quality/noninferiority approval is not cleared: the minimum
rerun gate is a fresh frozen matrix in which every client stratum passes all
five tasks, with no loop-budget exhaustion, stream disconnect, missing tool
result, false completion, or public/hidden validation failure. Blind paired
evaluation, canary, and promotion remain downstream and were not started.

A new bounded minimal Flash request used the same official
`deepseek-v4-flash` model ID, protected credential/workspace identity, and
messages-only request shape. It again returned HTTP 403 `RegionError`, while
the catalog and earlier same-identity success remain preserved. No minimum
completion recovery occurred, so native tool continuation, provider pinning,
cross-key overflow, same-key queue/fairness, and recovery were not rerun. The
remaining hypotheses are still runtime regression, model-specific regional
routing, workspace-policy regression, and provider incident; China-hosted
workspace opt-in is neither proven nor declared mandatory.

### Client-quality recovery canaries — 2026-08-09

Trace inspection of the failed v9 Hermes dag-runner and log-report sessions
showed that their configured loop budgets were not exhausted. A parallel local
Reviewer HTTP failure and optional Frontier HTTP failure escaped the optional
degradation path, reached the generic API exception handler, and terminated the
engineering loop as `INTERNAL_FAILURE`. The next request then rejected
Frontier and Reviewer admissions with the misleading text `loop budget
exhausted` despite substantial remaining budget. The shared optional Frontier
await now treats `httpx.HTTPError` and `StageTimeout` like the already handled
runtime and parse failures: confidence degrades and execution continues.
Required Frontier and Judge paths retain their existing fail-closed behavior.

The fresh `mistral-128k-v10-canary-20260809` Hermes dag-runner canary used a
new gateway DB and workspace and passed all ten gates in 206.489 seconds. The
prior HTTP 409 did not recur. A second fresh Hermes log-report canary likewise
avoided the 409 and returned in 67.975 seconds, but exposed a separate client
failure: Hermes received a valid `terminal` tool call and ended after one API
call without executing it, producing no source change or unittest evidence.
That cell remains failed rather than being credited to the HTTP fix.

The v9 Codex log-report trace exposed another independent continuation defect.
After several successful tool turns, adjacent Responses `function_call` items
were converted into separate assistant messages. Mistral rejected the resulting
history with HTTP 400 `Not the same number of function calls and responses`.
The converter now batches only adjacent function/custom calls into one
assistant tool-call message and leaves interleaved call/result turns separate.
The fresh `mistral-128k-v11-codex-log-20260809` canary then passed all ten gates
in 75.289 seconds with no 400 or stream disconnect.

The fresh v11 Codex webhook-verifier canary did not pass. It continued beyond
the earlier failure point, but implemented invalid signatures, stale timestamps,
and replay detection as exceptions rather than false returns. Its tests failed,
and a later unavailable `git` command in the minimal Docker image was not
recovered. This is retained as a model/tool-strategy quality failure. It does
not reverse the two physically verified gateway protocol fixes.

After both fixes, full pytest passed `1043/1043` in 34.60 seconds, Ruff passed,
and strict mypy passed over 49 source files. The quality blocker remains open
until a new complete frozen matrix passes every client/task cell; the Goal
itself remains active and is not classified as externally blocked.

### CUDA Graph argument-isolation epochs v24-v34 — 2026-08-09

All epochs used snapshot `b1a9048590131d38491bd23a7c9f6ed0962f0358`,
context 131,072, one sequence, 3,400,000,000 fixed KV bytes, dense and MoE
MARLIN, lazy safetensors, and loopback port 19301. Production was unchanged.

`FULL_AND_PIECEWISE` v24 failed in an Inductor pointwise kernel with
`CUDA driver error: invalid argument`. `FULL_DECODE_ONLY` v25 reproduced the
capture failure. Disabling compilation in v27 moved the first exception to
TRITON_MLA: `Pointer argument (at 0) cannot be accessed from Triton (cpu
tensor?)`. Limiting capture sizes to `[1]` in v29 reproduced it, excluding the
inferred size-2 capture. `FLASHINFER_MLA` v28 was rejected before loading due
to unsupported measured device capability.

Piecewise v30 enabled `cudagraph_copy_inputs=true` but retained the static
Triton launcher's invalid-argument failure. v31 reused an old AOT artifact and
was not accepted as clean evidence. Fresh-cache v32 disabled the static
launcher and failed in Triton's dynamic launcher with `Pointer argument (at 1)
cannot be accessed from Triton (cpu tensor?)`. Fresh-cache v34 repeated it with
`cudagraph_copy_inputs=false`. In every cudaMallocAsync case, uncaptured-free
and final invalid-argument cleanup followed the first kernel/pointer error and
remain secondary symptoms.

Native v26 retained MARLIN materialization buffers and crossed 120 GiB before
capture. Native v33 added `garbage_collection_threshold:0.5`; memory still rose
from 68,128 MiB through 86,734 MiB to 119,994 MiB during packing and the OOM
killer fired. Native allocator GC is therefore not a viable argument fix;
cudaMallocAsync remains the stable no-graph allocator.

No graph-active candidate reached readiness, so restart, repeated decode, long
prefill, tool continuation, streaming, and cancellation were not credited.
The blocker is runtime compatibility among this PyTorch/Triton/vLLM stack,
cudaMallocAsync captured buffers, and TRITON_MLA/Inductor capture paths, not a
model-size memory requirement. It clears only when a graph-active backend
reaches readiness under the frozen 131K/seq1/3.4GB/MARLIN contract and passes
the full physical matrix without pointer/launcher errors, uncaptured-free
cleanup, or abnormal memory growth. The Goal remains active and is not marked
externally blocked.

### Stable 131K recovery and Codex sandbox isolation v35-v35j — 2026-08-09

The stable v35 Executor reached readiness on snapshot
`b1a9048590131d38491bd23a7c9f6ed0962f0358` with context 131,072, one
sequence, 3,400,000,000 fixed KV bytes, dense/MoE MARLIN, TRITON_MLA,
cudaMallocAsync, and `cudagraph_mode=NONE`. Readiness memory was 74,714 MiB.
Repeated canary traffic raised the measured allocation to 76,412 MiB without
OOM, `invalid argument`, uncaptured-free warnings, or retained KV usage.

The first validation-gateway failure was an argument mismatch: serve-only
Frontier mode disabled `/v1/admin/codex`, so the Codex cell returned HTTP 404.
The isolated gateway now enables the admin route only with Frontier validation
and assigns the ephemeral key the operator token identity. The next physical
run proved that admin Codex still advertised a 65,536 context window; it is now
pinned to 131,072 and the observed process command contained the corrected
value.

Host tool execution then isolated three sandbox outcomes. Workspace-write with
network disabled failed in bubblewrap while creating loopback; enabling network
moved the first failure to `bwrap: setting up uid map: Permission denied`.
The deprecated Landlock candidate panicked because the current direct-enforcement
permission profile is incompatible with `use_legacy_landlock`. The only working
local Codex 0.146 mode was `danger-full-access`: shell reads, edits, and unittests
then executed normally. This mode is not a production default. It requires the
explicit `DGX_MOA_ADMIN_CODEX_UNSANDBOXED=true` opt-in; otherwise admin agent
mode remains workspace-write with network disabled.

The v35i webhook canary completed its original turn in 434.856 seconds and
changed only `webhook.py`. Public validation passed. Hidden validation first
found uppercase signature acceptance and then bool-as-int constructor
acceptance. A native same-thread continuation reproduced recovery transport but
made no change after a 175K accumulated input. Two bounded fresh correction
turns in the same fixture added lowercase-hex enforcement and exact-int checks;
public and hidden validation then both exited zero. All functional checks except
`docker_isolation` were true. The cell therefore remains failed rather than
being promoted: authenticated disposable-fixture execution is not equivalent
to an externally enforced container boundary.

The fresh full client matrix was not started because its preregistered canary
gate requires every check, including Docker isolation. The next engineering
gate is an externally sandboxed Codex admin runner that preserves operator
authentication, 131K context, fixture-only writes, secret filtering, and the
passing continuation/recovery behavior. This is an engineering blocker, not a
Goal-level blocked or external-host prerequisite.

### Docker client matrix v36-v37 and Flash recovery v38 — 2026-08-09

The existing Docker client runner was reused as the external sandbox boundary.
Its relative state directory produced Docker exit 125 because Docker interpreted
the source as a named volume. Resolving and creating that directory before
building the mount fixed the shared root cause. A fresh v36 webhook canary then
passed all ten checks, including public/hidden validation and
`docker_isolation`, in 171.071 seconds.

The preregistered v37 matrix executed all 20 cells against snapshot
`b1a9048590131d38491bd23a7c9f6ed0962f0358`, context 131,072, one sequence,
3,400,000,000 fixed KV bytes, dense/MoE MARLIN, TRITON_MLA, cudaMallocAsync,
and `cudagraph_mode=NONE`. All harness processes returned zero. Functional
scoring was baseline 4/5, Codex 2/5, Hermes 5/5, and OpenCode 5/5. Baseline
atomic-store and Codex rate-limiter, atomic-store, and webhook-verifier failed
public or hidden validation. Docker isolation passed in every cell. GPU memory
remained approximately 74.7-74.8 GiB and the Executor journal contained no OOM,
invalid-argument, or uncaptured-free error. The gateway and Executor were then
stopped in that order; both ports closed and GPU allocation returned to zero.
Codex noninferiority remains open while the external Docker sandbox blocker is
cleared.

After the operator enabled China-hosted models, a fresh v38 request used the
same OpenCode Go endpoint, credential/workspace identity, exact
`deepseek-v4-flash` model, and messages-only shape. Catalog availability was
true and the completion returned `FLASH_OK`, `finish_reason=stop`, and 111 total
tokens. A native tool request initially returned HTTP 400 because Flash thinking
mode does not support `tool_choice=required`; removing only that parameter
produced `get_temperature({"city":"Seoul"})`, `finish_reason=tool_calls`, and a
successful tool-result continuation pinned to the same model. A complete stream
ended with `[DONE]` after 128 chunks. A separate long stream was closed by the
client after two chunks in 1.527 seconds. The former 403 availability blocker is
cleared as workspace-policy evidence. Physical same-key queue/fairness,
cross-key overflow, and failure-recovery gates remain before scheduler approval.

A direct isolated scheduler/provider integration then held `key-a` as the local
owner. `key-b` selected `opencode_go` for `cross_key_overflow` and returned
`CROSS_OK` from exact model `deepseek-v4-flash`. After three same-key requests
queued, the fourth selected the same pinned provider for
`same_key_queue_limit` and returned `OVERFLOW_OK`. Releasing the owner promoted
the queued requests in order 1, 2, 3; the final snapshot had no owner and zero
queued requests. The earlier unsupported tool-choice 400 was followed by
successful requests, so provider recovery after a request-shape failure also
passed.

Fresh v39b exercised the authenticated `/v1/chat/completions` ASGI path with
two API-key identities and the live Flash provider. While `key-a` held the local
lease, `key-b` returned HTTP 200 from exact model `deepseek-v4-flash`, content
`HTTP_CROSS_OK`, selection `opencode_go`, and reason `cross_key_overflow`. A
high-risk `key-b` request instead remained in the local queue with `queued=1`;
after releasing the owner it returned HTTP 200 `LOCAL_OK`, selection
`local_mistral`, and reason `round_robin_promoted`. Only the local request
reached the local provider and the final scheduler snapshot was idle with zero
queued requests.

Fresh v39c held a high-risk local owner and filled the same-key queue to exactly
three authenticated HTTP requests. A fourth high-risk request failed closed
with HTTP 503, type `executor_admission_error`, code
`executor_queue_unavailable`, and message `high-risk Executor queue is full`;
it was not sent to Flash. Releasing the owner completed the first three requests
with HTTP 200 and returned the scheduler to idle/zero queued. The isolated
authenticated scheduling, fairness, provider-pinning, and high-risk fail-closed
gates are cleared. Checked-in scheduling remains disabled pending broader
release gates.

### Targeted Docker quality rerun v40 — 2026-08-09

The first retained v40 unit failed before shard loading with
`ModuleNotFoundError: flash_attn.ops` because its transient environment omitted
the repository compatibility path. The corrected v40b unit added only
`PYTHONPATH=.../compat` and reached readiness on snapshot
`b1a9048590131d38491bd23a7c9f6ed0962f0358` with context 131,072, one
sequence, 3,400,000,000 fixed KV bytes, dense/MoE MARLIN, TRITON_MLA,
cudaMallocAsync, and `cudagraph_mode=NONE`. Readiness was 74,714 MiB; observed
traffic reached 76,412 MiB without OOM, `invalid argument`, uncaptured-free, or
retained-KV errors.

Run `mistral-128k-v40-targeted-docker-20260809` reran only the four v37 failure
cells against fresh Docker fixtures. Baseline atomic-store passed all ten checks
in 149.553 seconds. Codex atomic-store passed in 1,155.828 seconds. Codex
webhook-verifier passed in 1,365.517 seconds after bounded correction of the
timestamp/nonce/signature string contract and hexadecimal HMAC representation;
public and hidden validation both exited zero. Thus every v37 generated-code
failure was recovered.

Codex rate-limiter returned zero and passed public and hidden validation in
1,138.807 seconds, but remained failed because `no_bad_terminal=false`. Its
client trace recorded three reconnects: idle timeout, stream close before
`response.completed`, then a second idle timeout. The final response and all
four tests succeeded after recovery. The common gateway path sends a comment
keepalive every 15 seconds but buffers non-comment translated Responses events
until terminal validation. The physical Codex 0.146 trace demonstrates that
those comment frames do not satisfy its continuity contract. This is the sole
remaining v40 targeted blocker; it is a gateway/client streaming issue rather
than model code quality, memory, or Docker isolation. No heartbeat format change
is credited without a fresh physical zero-reconnect rerun.

### Responses inner-heartbeat recovery v41-v44 — 2026-08-10

Two isolated 80-second fake Responses servers separated frame acceptance from
gateway behavior. Codex 0.146 completed once with repeated valid
`response.in_progress` events and once with repeated `event: ping` frames;
neither run reconnected. The gateway therefore changed its Responses heartbeat
from an SSE comment to the named ping while retaining comments as the default
Chat heartbeat. Fresh v41 Codex rate-limiter then passed all ten checks in
169.974 seconds with zero reconnects, compared with three reconnects and
1,138.807 seconds in v40.

The preserved v42 full matrix exposed a second layer. OpenCode passed `5/5`,
baseline `4/5`, Hermes `4/5`, and Codex `1/5`. Codex rate-limiter,
atomic-store, and webhook-verifier recorded zero reconnects, but dag-runner and
log-report each exhausted five reconnects after 1,271.799 and 1,245.751
seconds. Their traces showed completed tool work followed by a disconnect
before terminal completion. Inspection found that the inner
`keepalive_sse(responses_sse(...))` produced the named ping correctly, but the
Responses adapter treated every non-comment frame as terminal material and
buffered that ping in `translated`.

The root fix changes only that classification: SSE comments and frames starting
with `event: ping` bypass the terminal-validation buffer; all model and terminal
events remain buffered. A regression test injects an immediate inner ping and
proves that both outer and inner pings reach the response body. The focused run
passed `5/5`, and Ruff passed the touched API and test files.

Fresh v44 Docker fixtures against the unchanged revision, 131K context, one
sequence, fixed 3.4 GB KV, dense/MoE MARLIN, TRITON_MLA, cudaMallocAsync, and
compiled `cudagraph_mode=NONE` physically recovered both disconnect cells.
Codex dag-runner passed all ten checks in 151.850 seconds; log-report passed all
ten in 505.383 seconds. Both client traces contained zero reconnect, idle
timeout, or stream-close records. GPU allocation after the long v42 plus v44
traffic was 82,236 MiB, with no `invalid argument`, uncaptured-free, CUDA OOM,
or service restart. The v42 failures remain preserved; a targeted recovery is
not a replacement for the still-open full-matrix noninferiority gate.

### Fresh matrix and invalid-session recovery v45-v46 — 2026-08-10

The v45 transient epoch reused exact revision
`b1a9048590131d38491bd23a7c9f6ed0962f0358`, context `131072`, one sequence,
fixed `3400000000` KV bytes, dense/MoE MARLIN, TRITON_MLA,
cudaMallocAsync, and compiled `cudagraph_mode=NONE`. Readiness was 74,714 MiB.
The fresh 20-cell randomized matrix used seed
`afae47aabf8b5b6157fc81d87fa5f170c24c251654240a1388df4ee0f6469f4d`
and measured baseline `4/5`, Codex `1/5`, Hermes `5/5`, and OpenCode `5/5`.
Codex therefore failed paired noninferiority; the other two clients passed.
GPU allocation after the matrix was 84,668 MiB with no reported CUDA error.

Trace inspection found that the shared Responses compatibility path rewrote an
invalid or invented `write_stdin` session into a successful `exec_command`
whose only output was `No active process session; use exec_command or
apply_patch.` The message appeared 12 times in v45 rate-limiter and 18 times in
dag-runner, reinforcing a non-progressing tool loop. The minimal fix preserves
the requested `write_stdin` call and replaces only the invalid session ID with
sentinel `0`, allowing the client to receive a real tool failure and correct
its action.

The separate v46 gateway epoch physically reran the affected Codex cells.
Rate-limiter passed all ten checks in 155.862 seconds, dag-runner in 817.715
seconds, and log-report in 629.233 seconds; each returned zero and the old
successful no-op string was absent. Webhook-verifier changed only `webhook.py`
and passed public and hidden validation, but the harness reached the exact
1,800.101-second limit with return code 124 and no terminal response. Thus the
invalid-session root fix is physically accepted for the three recovered cells,
while webhook terminal convergence and fresh full-matrix Codex noninferiority
remain open. The repository suite passed 1,050 tests; Ruff passed and mypy
reported no issues in 49 source files.

### Completion-aware retry and v48 partial matrix — 2026-08-10

The v46 webhook trace had already completed implementation and repeated public
tests, but every progress-only retry still injected the implementation-only
instruction `Call the required tool`. That instruction forced redundant tool
and plan cycles instead of final synthesis. The shared Responses retry now
checks the persisted implementation/review evidence. Missing evidence retains
the fail-closed tool instruction; completed evidence receives a bounded request
for the concrete final result without another progress update or redundant
tool call. Four focused API tests passed, including a completed-evidence
regression. The full repository result was 1,051 tests passed, Ruff passed, and
mypy reported no issues in 49 source files.

The v47 physical epoch used the unchanged pinned revision, context `131072`,
one sequence, fixed `3400000000` KV bytes, dense/MoE MARLIN, TRITON_MLA,
cudaMallocAsync, and compiled `cudagraph_mode=NONE`. Weight loading took 412.29
seconds; readiness was 74,714 MiB. Codex webhook-verifier passed every check in
588.653 seconds with return code zero. The same cell independently passed in
v48 in 609.751 seconds. GPU allocation reached 79,708 MiB after the v48 traffic,
with no `invalid argument`, uncaptured-free, CUDA OOM, or service restart.

The v48 randomized matrix schedule is immutable and uses seed
`ac5cd8d40cccb13a2f3bfa59fd381bca835b569839b6d2144df6052220e480fb`.
Baseline, Hermes, and OpenCode each completed `5/5`. Codex rate-limiter,
webhook-verifier, and log-report passed; atomic-store passed public and hidden
validation but timed out at 1,800.102 seconds without terminal completion. The
outer orchestration session received SIGTERM during the final Codex dag-runner
cell. Its exact test container was allowed to reach the original 1,800-second
boundary and then stopped, but no synthetic run or score record was created.
The v48 summary therefore correctly reports baseline `5/5`, Hermes `5/5`,
OpenCode `5/5`, Codex `3/4`, and `matrix_complete=false`.

Atomic-store completed six loop iterations before client cancellation;
dag-runner completed eight. Both had successful test evidence but continued
through repeated review/correction. The dag reviewer explicitly rejected an
empty `changed_paths` projection because `git` was unavailable in the client
container, while the client had performed file replacement through shell
redirection. The atomic trace similarly ended after reviewer approval by
requesting another implementation action. This evidence separates the
remaining blocker from CUDA memory and from the recovered Responses heartbeat,
invalid-session, and completion-aware retry defects. A trustworthy
shell-mutation/change-scope projection and bounded reviewer convergence must be
validated before another full noninferiority epoch.

### Reviewer convergence fix and CUDA Graph isolation v49-v53 — 2026-08-10

The v48 SQLite session payloads proved that shell mutation targets were retained
(`atomic_store.py` and the absolute `dag_runner.py` path); the trace-level empty
change set was not a parser loss. Two independent convergence defects remained.
Correction-pending sessions could start a parallel Frontier architecture call
before local review, preventing the required Frontier code-review verification
from replacing it, and path extraction scanned free-form `justification` text as
if it were a mutation target. Pending correction verification now forces the
initial Frontier mode to `code_review`; reviewer and Frontier evidence merge
persisted implementation targets; and path extraction is limited to command,
patch, and explicit path/URI fields. Full pytest passed `1051/1051`, Ruff passed,
and mypy passed 49 source files.

CUDA Graph epochs v49-v53 preserved revision
`b1a9048590131d38491bd23a7c9f6ed0962f0358`, context `131072`, one sequence,
fixed `3400000000` KV bytes, dense/MoE MARLIN, and loopback port 19301. v49
selected `CUTLASS_MLA + FULL_DECODE_ONLY` but was rejected before weight loading:
the backend supports capability major 10 while GB10 reports 12.1. v50 used the
native allocator with `expandable_segments`, `max_split_size_mb=128`, and GC
0.5 under a 110 GiB guard. It loaded all 13 shards in 443.80 seconds, then the
guard killed it during MARLIN packing, reproducing native allocator retention.

An isolated v51 overlay backported upstream TRITON_MLA decode-workspace
preallocation without changing the installed package. Original source SHA-256
was `fcaa82edd4835f11617cfa6a6783d04914006a5d85915663b0b5a014f42588e0`;
patched source SHA-256 was
`5b2c8622f0d9ab77f59570ac00e01604bcd2617130f455a3514f9cfca81689d9`.
v51 still failed the Inductor pointwise static launcher with `CUDA driver error:
invalid argument`. v52 combined the backport, a fresh cache, and dynamic Triton
launcher; its capture allocation `buf9` failed as an inaccessible pointer. v53
disabled Inductor compilation while retaining FULL decode capture and the
workspace backport; it advanced past that point but the MoE
`_fwd_grouped_kernel_stage1` first pointer failed identically. In each
cudaMallocAsync case, uncaptured-free and final invalid-argument cleanup followed
the first pointer error.

These results narrow the active CUDA Graph blocker to the general interaction of
cudaMallocAsync capture allocations with Triton launch on SM121/CUDA 13, rather
than one MLA scratch buffer or one launcher implementation. Native allocation
avoids that pointer class but still cannot survive MARLIN materialization within
host headroom. SGLang remains ineligible under the frozen contract because its
measured compressed NVFP4 MoE path was not true MARLIN and its dense MARLIN path
failed on capability 121. No graph-active backend reached readiness, so the
client matrix was not resumed and no production change was made. The Goal
remains active; the next gate is an isolated runtime-stack candidate that fixes
SM121 capture allocation visibility or native MARLIN packing retention.

### Native layer-wise reclamation CUDA Graph qualification v54 — 2026-08-10

Source inspection rejected the proposed packed `sharded_state` shortcut before
writing a 66 GiB artifact: the saver records the post-processed `weight` keys
and shapes, while a fresh compressed-tensors model initializes checkpoint
`weight_packed` parameters and unconditionally runs MARLIN post-processing after
every loader. It therefore cannot bypass repacking without a new loader format.

The smaller root fix was isolated in the v54 overlay. vLLM's shared
`process_weights_after_loading` loop now calls `torch.cuda.empty_cache()` after
each quantized module on CUDA, releasing dead native-allocator repack blocks
before the next layer. The original utility SHA-256 was
`55b03cc8443e66f482340790a42b16fa3be4df692eb9db42e0103f52e266dc80` and the
patched SHA-256 is
`ab77d138e910b5444ab4a8922e2615df33f9f27d9198597b032bac755a6db9bf`.
The overlay also changed the optional FlashAttention probe from
`find_spec("flash_attn")` to `find_spec("flash_attn.ops")` because the installed
namespace contains only the CUTLASS DSL package; its patched source SHA-256 is
`b101f8e9ad71a107b2323135459af4cac9cc4b1530a759de0e0858445be57223`.

v54 preserved revision `b1a9048590131d38491bd23a7c9f6ed0962f0358`, context
`131072`, one sequence, fixed `3400000000` KV bytes, dense and MoE MARLIN,
TRITON_MLA, native allocator, and `FULL_DECODE_ONLY`. A dedicated process group
was sampled every two seconds and limited to 110 GiB. The first cold load read
all 13 shards in 484.14 seconds. MARLIN processing completed in 24 seconds and
vLLM reported 66.06 GiB model memory instead of v50's 100-120 GiB growth. It
reserved exactly 3.17 GiB KV, captured the decode graph in two seconds using
0.01 GiB, and reached loopback readiness. The steady first-request allocation
was 72,890 MiB.

Physical traffic passed an exact short response, five repeated decode calls, a
48,024-token prefill, a required native function call and tool-result
continuation, and a one-second streaming disconnect followed by successful
cancellation recovery. KV usage returned from 30.5% to zero and sampled GPU
memory settled at 73,428 MiB. No `invalid argument`, inaccessible Triton
pointer, uncaptured-free warning, CUDA OOM, or guard action occurred.

The exact v54 process group was then stopped; port 19301, GPU allocation, and
host paging were observed released. A second cold start re-read all 13 shards
in 480.75 seconds, again completed MARLIN at 66.06 GiB, reserved the same fixed
KV cache, captured the decode graph in one second using 0.09 GiB, reached
readiness, and returned `V54_RESTART_OK`. Post-canary allocation was 72,890 MiB.

The CUDA Graph engineering blocker is therefore cleared for this isolated
backend: native allocator plus layer-wise MARLIN cache reclamation satisfies the
frozen graph-active physical contract and the requested restart, repeated,
long-prefill, tool, stream, cancel, and memory-stability gates. v54 remains a
transient validation runtime on loopback 19301 for the resumed client matrix;
the installed package and production services remain unchanged.

### Client/provider resumption probes v55-v58 and Flash — 2026-08-10

The v55 Codex atomic-store probe preserved the unavailable local Planner failure.
v56 then isolated role convergence by mapping Planner and Reviewer to v54, but
failed because their Qwen/Cohere reasoning-parser request shape was incompatible
with Mistral. v57 changed only those transient parser settings to Mistral and
passed all ten atomic-store harness checks. This is targeted controller-path
evidence, not qualification of the required remote-role matrix.

The v58 DAG probe completed with harness exit zero and passed its public tests,
but failed the hidden validator. Its implementation returned results in global
node-name order (`a,done,z`) instead of deterministic execution-layer order
(`a,z,done`). The correction history, including the initial test-process exit
137 and Frontier correction limit, remains under
`data/diagnostics/client-quality/mistral-128k-v58-local-role-dag-canary-20260810`.

The operator reconfirmed that the China-hosted-provider control is enabled and
that `deepseek-v4-flash` is available. One fresh local OpenCode CLI probe using
`opencode/deepseek-v4-flash-free` established provider TLS connections but
produced no completion bytes within the five-minute bounded canary and was
interrupted with exit 130. A clean diagnostic retry then returned exact
`FLASH_OK` with exit zero. A second run emitted a native `bash` tool call,
observed exact tool output `FLASH_TOOL_OK`, continued on the same model, and
returned exact `FLASH_TOOL_OK`; explicit continuation of the same session then
returned `FLASH_CONTINUE_OK`, also with exit zero.

These fresh confirmations are consistent with, and do not replace, the earlier
v38-v39c physical gateway evidence above. That evidence already cleared minimum
completion, native tool continuation, complete streaming, cancellation,
provider pinning, cross-key Flash overflow, same-key FIFO/fairness, recovery
after request-shape failure, and high-risk fail-closed behavior. The former 403
is therefore not an active provider blocker. The isolated OpenCode snapshot
index-lock warnings did not prevent inference, tools, or continuation and are
client-local observation noise rather than a Flash failure.

Fresh preregistered v59 and v60 Codex canaries then reran the other two v37
Codex failures against graph-active v54 through the targeted v57 controller.
The v59 rate-limiter task passed all ten harness checks in 157.157 seconds. The
v60 webhook-verifier task reached the bounded 24-step correction path, exhausted
optional Frontier invocations, recovered through the local route, and passed
all ten checks in 757.391 seconds. Together with v57 atomic-store, all three
Codex cells that failed in v37 now pass public and hidden validation, Docker
isolation, terminal-output, tool-evidence, and source-only checks. v58
dag-runner remains a separate hidden-validation failure and prevents treating
these targeted rows as a complete or noninferior matrix.

Fresh v61 reran the identical preregistered Codex dag-runner task without
altering the v58 artifact. It completed in 640.418 seconds and passed all ten
checks, including the hidden execution-layer ordering contract. The run also
exercised bounded recovery after a closed Codex transport and optional Frontier
invocation exhaustion. v58 remains the retained failed attempt; v61 is the
successful retry. The targeted Codex recovery set is now green, but a fresh
randomized full client matrix remains mandatory.

The target-topology v62 gateway then loaded the protected OpenCode Go credential
from the existing mode-0600 production environment without copying or printing
it, while overriding the validation listener back to loopback and using a new
SQLite state database. A remote `deepseek-v4-pro` Planner completed alongside
the local Reasoner and Frontier fan-out. The first Frontier attempt reproduced
a raw closed `WriteUnixTransport` exception. The shared App Server boundary now
normalizes write/drain failures to `FRONTIER_APP_SERVER_UNAVAILABLE` and
suppresses the same cleanup-only close exception, allowing the existing bounded
stdin fallback contract to operate. The focused suite passed 44 tests plus Ruff
and strict mypy. After the exact transient gateway restart, Frontier A completed
through primary in 60.235 seconds while the remote Planner completed in 38.727
seconds; the joined local Executor then completed. Production was unchanged.

Fresh randomized v63 preregistered all 20 baseline/Codex/OpenCode/Hermes cells
against v62 and graph-active v54. Its immutable schedule seed is
`78125677e3afa95e5600188e769966469825222ea9a6fbbc8c3e52192d188dfa`.
The matrix is in progress and has no verdict yet.

### Blackwell native NVFP4 qualification v64 — 2026-08-10

The exact revision `b1a9048590131d38491bd23a7c9f6ed0962f0358` was tested at
context 131,072, one sequence, fixed 3.4 GB KV, TRITON_MLA, and
`FULL_DECODE_ONLY`. The explicit candidate selected
`FlashInferB12xNvFp4LinearKernel` for dense layers and `FLASHINFER_B12X` for
MoE. It loaded 66.09 GiB in 398.75 seconds, compiled in 11.54 seconds, reserved
3.17 GiB KV, captured the decode graph in 12.01 seconds, and reached readiness
with a 72,430 MiB startup peak. Chat, Responses, single and parallel native
tools, tool-result continuation, streaming disconnect recovery, cold prefill
through 128,000 tokens, 4,096-token decode, and exact restart passed. Sustained
4,096-token decode measured 29.52 output tokens/s and no `invalid argument` or
uncaptured-free warning occurred. The exact restart reloaded in 387.22 seconds,
used cached compile in 1.62 seconds, captured in 10.68 seconds, and returned
`RESTART_OK`.

The `auto` candidate physically selected `FlashInferCutlassNvFp4LinearKernel`
and `FLASHINFER_CUTLASS`; it did not fall back to MARLIN. Weight load remained
66.09 GiB and compile completed in 11.34 seconds. Initial warmup then caused
rapid host/unified-memory growth while GPU usage remained below 70 GiB. The
original 8 GiB host-floor guard logged at 7,669,180 KiB available, but its
termination did not occur: dash's `kill` builtin rejected `-- -PGID`, and the
ignored exit status left the entire process group running while CUDA `cicc`
children kept allocating. The kernel recorded global OOM kills, including unrelated processes,
the production `dgx-moa-gateway.service`, and the user systemd manager. The
candidate was forcibly killed; GPU allocation cleared and host availability
recovered to 94 GiB. This rejects the installed auto-CUTLASS path and invalidates
any earlier no-impact interpretation. It does not establish MARLIN as generally
optimal on Blackwell. Further backend runs are paused pending production
recovery authority; guards now stop at 24 GiB available with immediate
process-group `SIGKILL`. Raw logs, telemetry, hashes, and the corrected incident
record are under
`data/diagnostics/runtime-overlays/mistral-128k-v64-blackwell-native-b12x`.
Installed FlashInfer 0.6.12 reads `MAX_JOBS` for ninja `-j`; when it is unset,
ninja uses host-default parallelism. It was unset here and `nproc` is 20. The
kernel OOM tables show many concurrent `nvcc`/`cicc` children with individual
RSS ranging from hundreds of MiB to over 6 GiB. Thus the direct cause is
uncapped SM121 CUTLASS JIT compile fan-out, not the 65.95 GiB checkpoint or
3.4 GB KV allocation. A serialized `MAX_JOBS=1` retry remains a verifiable
engineering path after production recovery is explicitly authorized.
Both qualification launchers now call checked `/bin/kill -KILL -- -PGID` at the
24 GiB host floor. `test-run-qualified.sh` forced that branch with a dummy
process group and passed in under one second with exit 137 and no surviving
`sleep 300` process. This validates containment control only; it does not
retroactively validate the failed auto-CUTLASS candidate.

The remaining serialized retry is preregistered separately at
`data/diagnostics/runtime-overlays/mistral-128k-v65-blackwell-auto-serialized`.
It fixes `MAX_JOBS=1` as the only candidate change, retains the v64 model,
context, KV, parser, attention, and CUDA Graph contracts, and requires actual
dense/MoE kernel identity from runtime logs. Its status is waiting for explicit
production-recovery approval; no model process has been started for this epoch.

On 2026-08-11 the operator approved production recovery. Read-only inspection
showed that `user@1000.service` and `dgx-moa-gateway.service` had already
recovered at 07:16 KST. The gateway had `NRestarts=0`, tailnet `/healthz`
returned 200, and unauthenticated `/v1/models` returned 401. No restart was
repeated. The exact observation is preserved in the v66
`production-recovery.json` artifact.

Protocol epoch `mistral-128k-v66-sglang-native-auto-20260811` preregisters the
SGLang native challenger without changing qualified vLLM B12x candidate A.
Installed source inspection, before weight load, found SGLang 0.5.13.post1,
sglang-kernel 0.4.3, FlashInfer 0.6.12, torch 2.11/cu130, transformers 5.8.1,
and cuDNN 9.19 on GB10/SM121. Its registry logic resolves FP4 GEMM auto to
`flashinfer_cutlass`; the compressed-tensors NVFP4 MoE scheme uses native
CUTLASS when the MoE runner remains auto; default MLA attention is `triton`.
The Mistral-native parser derives 128000 context by default, so the registered
131072 contract requires the installed, explicit
`SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1` override. The KV pool is fixed to
147568 tokens: 36 layers * (256 KV LoRA + 64 rope) * BF16 equals 23040 bytes per
token and 3,399,966,720 bytes total. These are registry and configuration
facts, not readiness or quality evidence; runtime kernel identity must still be
confirmed from the isolated service logs.

### SGLang native candidate B physical result v66 — 2026-08-11

Attempt 1 failed before Python because the transient unit lacked a Python path;
the next attempt changed only to the installed absolute interpreter. Attempt 2
loaded all 13 shards, reported 64.39 GB of weights and the fixed 147,568-token
3.17 GB KV pool, then failed during batch-one CUDA Graph capture in
`decode_attention.py::_fwd_grouped_kernel_stage1` with
`Cannot make_shape_compatible: incompatible dimensions at index 1: 256 and
512`. The post-error exit 137 was process-tree cleanup, not cgroup OOM.

Attempt 3 changed only MLA attention from Triton to FlashInfer. It loaded 64.42
GB in 365.72 seconds. Runtime JIT physically compiled FlashInfer
`fp4_gemm_cutlass_sm120` with `compute_121a/sm_121a`,
`FLASHINFER_ENABLE_FP4_E2M1`, CUTLASS, `MAX_JOBS=1`, and one NVCC thread. Auto
MoE used `CompressedTensorsW4A4Nvfp4MoE` native CUTLASS. Batch-one CUDA Graph
capture completed in 729.82 seconds and used 1.19 GB; piecewise graph remained
disabled. The default LRU RadixCache initialized at page size one. Final
telemetry contained 1,531 samples: GPU peak 72,556 MiB, host-available floor
38,418,064 KiB, host-used peak 89,116,280 KiB, swap-used peak 4,111,300 KiB,
GPU-utilization peak 96%, and power peak 36.61 W. No guard or OOM fired.

Health became 200 after SGLang's own VLM warmup. Exact Chat returned
`SGLANG_NATIVE_OK` in 0.560 seconds. Single `add(17,25)` and parallel
`add(2,3)`/`multiply(4,5)` native tool calls passed. Chat SSE assembled exact
`STREAM_OK`, emitted usage and `[DONE]`, and a 0.5-second disconnect recovered
with exact `RECOVERED` plus health 200.

Two mandatory compatibility gates failed. The server's native tool-call message
contains `content:""`; continuing that exact returned message with tool result
`42` reissued `add(17,25)`. Changing only assistant content to JSON `null`
produced a correct final answer, proving a serialization-sensitive tool
continuation regression. A standard Responses request with string `input`
returned HTTP 400, `input_ids should be a list of lists for batch processing`,
from the Pixtral multimodal prompt path. PyPI reported SGLang 0.5.17 as latest;
official tag commit `29481685462732237d80d86076d6563e1f658102` retains the
empty-string serialization and the same multimodal Responses wrapping, so an
unjustified full runtime replacement was not performed.

The isolated unit stopped with result success, released port 19301 and model
memory, and left production tailnet health at 200. Candidate B is rejected for
this protocol epoch on client-visible semantics, not native FP4, MLA, CUDA
Graph, memory, or HTTP readiness. Cold and 80K-100K agent-prefix performance
lanes were not run after the mandatory correctness gate failed and therefore
must not be inferred. Candidate A remains the backend decision; MARLIN remains
compatibility rollback evidence only. Frozen artifacts and hashes are under
`data/diagnostics/runtime-overlays/mistral-128k-v66-sglang-native-auto`.

### SGLang released-runtime retry preregistration v98 — 2026-08-12

The operator restored SGLang native NVFP4 to backend-qualification priority
without changing the vLLM B12x decision. The approved production gateway was
already active in the user manager with `NRestarts=0`; candidate A and its
persistent validation gateway were also active, so no redundant restart was
performed. Current package inspection found installed SGLang `0.5.13.post1`
and released latest `0.5.17`. Pip resolution for the isolated challenger keeps
torch `2.11.0+cu130` and cuDNN `9.19.0.56`, while selecting sglang-kernel
`0.4.5`, FlashInfer `0.6.15.post1`, and transformers `5.12.1`.

Official tag commit `b6a09f38fcc5e96574324b4acc19d421c539cfc6` was inspected
before installation. On SM121, its actual registry rules resolve dense FP4
auto to `flashinfer_cutlass`, compressed NVFP4 MoE auto to
`flashinfer_trtllm`, and MLA attention auto to `triton`. Registered alternatives
are evidence of availability only, not capability qualification. The Responses
engine-prompt path changed since the installed v66 runtime, while non-stream
tool-call messages still serialize empty content. Therefore v98 first replays
auto and the three mandatory correctness regressions; only a known Triton MLA
failure permits a single-variable FlashInfer-attention retry. Cold and
80K-100K RadixAttention lanes remain forbidden until Chat, Responses, verbatim
tool continuation, streaming, cancel/recovery, and exact restart all pass.
The frozen preregistration is
`data/diagnostics/runtime-overlays/mistral-128k-v98-sglang-0.5.17-native/protocol.json`.

The physical v98 runs reject native SGLang candidate B for this pinned runtime
and model contract. Auto loaded native SM121 FlashInfer CUTLASS dense FP4 and
TensorRT-LLM fused-MoE FP4, then reproduced the Triton MLA CUDA-Graph 256/512
shape failure without OOM. Explicit FlashInfer compiled SM121 FP4 kernels,
reached readiness, and passed Chat, Responses, single/multiple native tools,
verbatim tool-result continuation, streaming, cancellation, and recovery. Its
MLA wrapper selected FA2 on SM121, however, so it is not the requested native
attention challenger. With `--max-total-tokens 147568` and allocator headroom
0.615, that path allocated the exact 3,399,966,720-byte BF16 MLA KV pool and
captured decode graph in 4.79 seconds.

The first explicit `trtllm_mla` run exposed an SGLang/FlashInfer API-default
mismatch: SGLang omitted `backend='trtllm-gen'` but supplied its multi-CTA-only
buffer while FlashInfer auto selected XQA. A one-line patch in the isolated venv
only proved the next physical gate, where `TllmGenFmhaRunner` rejected SM121 as
`Unsupported architecture`; the patch was then reverted. Stock `cutlass_mla`
was the only remaining static candidate: registry import passed and the
installed `sgl-kernel` image contains `sm_121a`. It reached decode graph capture
but failed `cutlass_mla_decode` at `D_q_nope == D_latent`, demonstrating a model
shape-contract mismatch rather than OOM. `flashmla` was rejected before launch
because its installed binary has no SM121 image; `cutedsl_mla` is SM100-gated;
`tokenspeed_mla` requires FP8 KV and violates the pinned BF16 KV contract.

No cold or 80K-100K Radix-prefix measurements were run because native readiness
and correctness did not pass; no warm-prefix sample is mixed into a cold lane.
The failed TRTLLM and CUTLASS journal hashes are respectively
`b335099a9fcd4bb975da90f80be811805af56a2c757eb58bd6e757373a773012`
and `c1d956bea9f0371f0c454707955da0920070791b3f05d165311b0d0a498b275a`.
Candidate A remains unchanged and exact-restarted from its frozen v64 contract.
It loaded 66.09 GiB in 393.77 seconds, allocated 147,568 KV tokens from the
fixed 3.4 GB pool, captured decode graph in 11.92 seconds, and peaked at 72,430
MiB. Chat, Responses, single/multiple native tools, continuation, streaming
`[DONE]`, a 20,425-byte canceled stream, and immediate recovery passed. The
validation gateway returned `/readyz` 200 and authenticated
`GATEWAY_RECOVERY_OK`. The production gateway remained active with
`NRestarts=0` and `/healthz` 200; its unchanged stopped production roles explain
the existing `/readyz` 503. This result does not generalize SGLang or native
Blackwell performance and does not establish MARLIN as optimal.

### Candidate-A-pinned client-quality matrix v67 — 2026-08-11

Protocol epoch `mistral-128k-v67-b12x-full-matrix-20260811` reused the frozen
v63 schedule while pinning the physically qualified vLLM candidate A: exact
model revision `b1a9048590131d38491bd23a7c9f6ed0962f0358`, context 131072,
one sequence, 3.4 GB KV, dense `FlashInferB12xNvFp4LinearKernel`, MoE
`FLASHINFER_B12X`, TRITON_MLA, and `FULL_DECODE_ONLY`. The isolated executor
and gateway stayed loopback-only on ports 19301 and 19310. Production remained
active and healthy; it was not restarted or mutated.

All 20 immutable cells ran. Baseline passed `5/5` in 911.283 seconds, OpenCode
passed `5/5` in 1,437.785 seconds, Codex passed `5/5` in 3,729.525 seconds, and
Hermes passed `4/5` in 4,273.550 seconds. The sole failure was Hermes
atomic-store: return code 124 at 1,800.141 seconds. Its only changed source was
`atomic_store.py`; public and hidden validation both exited zero. The failed
checks were harness exit, Korean final, terminal, and tool evidence. The next
scheduled OpenCode webhook cell passed, providing immediate recovery evidence.

Read-only inspection of Hermes `state.db` found one session with 52 messages:
one user message, 25 assistant messages, and 26 tool results. Every assistant
message ended with `finish_reason=tool_calls`; none was terminal. Tests first
passed about four minutes into the run, but the client continued cross-instance,
failure-atomicity, JSON-boundary, Git-scope, and duplicate implementation work.
Its last successful unittest/UTF-8 check completed 27.813 seconds before the
frozen timeout. During the cell the isolated gateway logged successful HTTP 200
chat completions and no provider/backend error. This classifies the cell as a
Hermes terminal-convergence quality regression, not CUDA Graph, memory,
candidate-A, or gateway failure. It was not rerun or excluded.

The summary correctly records `matrix_complete=true`, `complete=false`, total
`19/20`, and Hermes usability below baseline. Schedule SHA-256 is
`0c94909a906c299a7e8ee6321f79ddba8adabcd7c624e37ee934fa711cacdc5d`;
summary SHA-256 before the protocol-result annotation is
`3e90ba98ae2225521a84e469b753a9a0bc4e02394ea5a38ab3e9af7d9e450549`.
Frozen run, score, session, trace, telemetry, infrastructure-retry, and focused
failure-analysis artifacts remain under the epoch root. The functional gate is
failed, so blind noninferiority, Reasoner ablation, long-horizon, canary, and
release promotion do not resume until a separate targeted recovery demonstrates
bounded Hermes terminal convergence without weakening correctness or tool
evidence.

Targeted recovery v68 changed only the copied Hermes profile's
`agent.max_turns` from 90 to 20. Two pre-request 401 launches were preserved as
infrastructure retries; neither reached the model. The corrected launch used
the isolated gateway's active `physical` key identity without printing or
copying its value. The configured limit was not effective for this `-z`
execution path: Hermes persisted 36 assistant messages, all ending in tool
calls, and 40 tool results before the unchanged 1,800.101-second timeout. Only
`atomic_store.py` changed and both public and hidden validation passed, but no
terminal response or `usage.json` was written. Production, candidate A, and the
isolated gateway remained HTTP 200; candidate A remained at 72,428 MiB. v68 is
therefore failed evidence against the config-only control, not a backend
regression. v69 preregisters explicit CLI `--max-turns 20` as the next single
variable because the installed client gives that argument priority over config.

v69 then proved that priority is unavailable to oneshot: top-level `hermes -z`
does not register `--max-turns`, so the attempted explicit argument exited 2 in
0.389 seconds before any model request. Source inspection found the direct
cause: `hermes_cli.oneshot._run_agent()` constructs `AIAgent` without passing
`cfg.agent.max_turns`; the constructor therefore uses its default 90. The
`--max-turns` option exists only on the `chat` subparser. v70 preserves all
prior failures and preregisters an isolated one-line bind-mounted overlay that
passes the configured value as `max_iterations`; it does not mutate the
installed Hermes tree.

The v70 overlay made the configured limit effective. The run stopped after 20
assistant tool-call messages, wrote one terminal assistant message, exited zero
in 996.819 seconds, changed only `atomic_store.py`, retained successful unittest
tool evidence, and passed public plus hidden validation. It still failed the
matrix cell because the terminal text was English. The tool-free summary call
used `dgx-moa-orchestrated`, whose required Frontier correction could not run
without client tools and returned 503 `frontier_required_unavailable`; Hermes
then emitted its English error fallback. v71 retains the proven turn fix and
changes only the max-iteration summary model to the existing Executor-only
compatibility path `dgx-moa-fast`.

v71 physically sent that fast summary request. Gateway usage recorded model
alias `dgx-moa-fast`, fast mode, and Executor-only routing, but the full-history
request failed after 19.148 seconds with `backend_error`; Hermes retried through
the original orchestrated model and again emitted the English fallback. Small
direct `dgx-moa-fast` probes immediately afterward passed both nonstream and
stream with HTTP 200, so the model alias and candidate-A backend remained
available. v72 retains both prior overlay fixes and changes only summary context
to the first two API messages plus the latest twelve followed by tool-pair
sanitization.

v72 passed the targeted Hermes atomic-store cell in 389.044 seconds. The
read-only transient overlay left installed Hermes unchanged; the task changed
only `atomic_store.py`, exited zero, emitted a Korean terminal response, retained
successful unittest tool evidence, and passed public plus hidden validation and
all ten matrix checks. Its state database contains seven assistant messages and
six tool results. Gateway evidence contains seven matching orchestrated
requests, all completed, with no failed request. Candidate A and both isolated
services remained healthy. Hermes converged before the configured 20-turn
limit, so no `dgx-moa-fast` summary request was sent and the compact-summary
branch itself is not physically validated. This is sufficient targeted
terminal-convergence recovery evidence, but it does not alter frozen v67 or
substitute for a fresh full client-quality matrix.

Fresh candidate-A-pinned matrix v73 completed all 20 cells. Baseline and
OpenCode passed `5/5`, Codex passed `3/5`, and Hermes passed `4/5`, totaling
`17/20`. The recovered Hermes atomic-store cell passed all checks in 552.221
seconds. Codex log-report instead crashed with rc 139 after 48.679 seconds and
before changing source; its gateway interval contained three completed and no
failed requests. Codex rate-limiter changed only `rate_limiter.py`, passed
public and hidden validation and retained unittest evidence, but timed out
without a terminal response at 1,800.094 seconds; 31 requests completed and one
was cancelled. Hermes log-report changed only `log_report.py` and passed both
validation layers, but its terminal was `API call failed after 3 retries:
remote Executor fallback unavailable`; four gateway requests completed and
three were cancelled, with none recorded failed. The matrix summary SHA-256 is
`628e561608d0a20251d2da23eeeaf21ca01db3aa7ea8400bcb200ac2e73c18e4`.
After completion all three services were active and HTTP 200, candidate A used
72,430 MiB, and host headroom remained above the 24 GiB guard. These failures
are client process/convergence evidence, not an NVFP4 backend or memory
regression. The full functional gate remains failed.

### Hermes bounded-output and fast-mode recovery v74-v77 — 2026-08-11

v74 reduced only the copied Hermes output budget to 4,096 tokens. It passed all
ten matrix checks, but emitted 49,418 bytes of multilingual repetitive output;
the scorer pass is retained but rejected as production quality. v75 bounded
the copied oneshot loop to eight turns and v76 additionally bounded the summary
to 256 tokens. Both failed only the Korean-terminal check because the
`dgx-moa-fast` summary returned a backend error. Exact v76 tracing showed the
root cause: `prepare_executor()` dynamically injected Reviewer after fast mode
had already selected Executor-only roles, then a revise verdict required an
unavailable correction tool path.

v77 fixes that shared root with one guard: dynamic Reviewer injection is skipped
when `runtime_mode == "fast"`. Controller tests passed `101/101`, focused fast,
alias, tool-continuation, and reviewer API tests passed `11/11`, and Ruff
check/format passed. An isolated direct request containing implementation and
tool-result evidence returned HTTP 200 in 1.388 seconds. Usage recorded
`model_alias=dgx-moa-fast`, `runtime_mode=fast`, `roles_required=["executor"]`,
and completed status. Its exact event window contained only local Executor role
events and zero `reviewer_required`, `review_started`,
`frontier_collaboration_started`, or `executor_remote_selected` events. The
short Korean response had no repetition corruption. Production, candidate A,
and both gateways were HTTP 200 during the check.

The v77a Hermes log-report cell separately failed task correctness: the model
changed only `log_report.py` and produced a Korean terminal, but public and
hidden validation both exited 1 and unittest tool evidence did not pass. Its
fast summary itself completed Executor-only with 5,211 prompt and 143 completion
tokens in 18.302 seconds. Therefore v77 passes the gateway compatibility
contract while v77a remains failed client-quality evidence; neither frozen v73
nor the broader client gate is rewritten. After evidence capture, only
`dgx-moa-v77-gateway-attempt04.service` was exactly stopped; port 19311 was
released while candidate A, its gateway, and production remained active and
HTTP 200.

### Codex rc139 exact replay v78 — 2026-08-11

Read-only reconstruction of v73 showed that candidate A and the gateway had
completed all three Responses/tool-call turns before Codex exited 139. The
third turn contained two pending tool calls, but no core dump, kernel segfault
record, provider failure, or backend failure artifact survived. A preregistered
v78 cell therefore changed no code or protocol input: the same Codex 0.146.0
binary and SHA-256, prompt hash, log-report fixture, Docker controls, gateway,
and candidate A were exact-replayed in a fresh workspace.

v78 exited zero after 1,240.068 seconds and passed all ten matrix checks. It
changed only `log_report.py`; public and hidden validation exited zero, unittest
tool evidence was retained, and the terminal was Korean. All 29 gateway requests
completed, with zero failed or cancelled request, so the v73 signal-11 exit did
not reproduce and is not a deterministic gateway wire or tool-payload failure
under this replay. The run was still inefficient: three completions reached the
4,096-token ceiling and the model required multiple failed patch/tool attempts
before converging. This is targeted recovery plus residual convergence evidence,
not a rewrite of v73 or a fresh matrix pass. Candidate A, its gateway, and
production remained active and HTTP 200; candidate A used 72,596 MiB after the
run.

### Codex relative change-evidence recovery v79 — 2026-08-11

The v73 Codex rate-limiter timeout was reconstructed as an evidence handoff
failure, not a backend timeout. After the client changed `rate_limiter.py` and
passed tests, the first Reviewer received empty changed paths/no diff summary,
issued a false critical missing-implementation finding, and opened
`frontier_correction_required`. The session then accumulated 18 Frontier
correction-tool retries, 20 remote-Executor selections, and 32 steps before the
1,800-second timeout.

Current shared path extraction records relative source names from bounded
`cmd`, `command`, `input`, and `patch` payloads. The existing focused regression
for shell redirection records `app.py`, and the controller suite passes 101/101.
An isolated v79 gateway physically recorded a synthetic relative
`cat > rate_limiter.py` continuation as `target_paths=["rate_limiter.py"]`.
Reviewer evidence referenced the actual observed stub content instead of
claiming no change/diff; the intentionally empty stub then failed closed with
HTTP 409, which is correct functional rejection and not evidence loss.

The fresh v79 Codex rate-limiter cell terminated normally in 166.959 seconds.
All six gateway requests completed; Reviewer ran once, approved once, and no
Frontier correction retry occurred. The cell nevertheless failed 9/10 because
hidden validation found an accepted invalid constructor input. Public tests,
tool evidence, source scope, and Korean terminal passed. Thus the v73 correction
loop root cause is closed, but Codex rate-limiter quality is still failed and
the full client gate remains open. Only the v79 transient gateway was then
exactly stopped; port 19312 was released while candidate A, its 19310 gateway,
and production remained active and HTTP 200.

### Fresh fixed-gateway full matrix v80 — 2026-08-11

Protocol epoch `mistral-128k-v80-fixed-gateway-full-matrix-20260811` executed
all 20 frozen cells with candidate A and the v77/v79 code. Baseline passed all
five cells. Codex, Hermes, and OpenCode passed none, so the frozen result is
`5/20` and the functional gate failed. Summary SHA-256 is
`e696e49c5eae60385b6b05160f53c646dffe30f85c4ff5229df2299ed9fc5d50`;
schedule SHA-256 remains
`ccd47f52217dca9a0870e8936f09924d8659735178a318cb2e0cd3e38d83b2bb`.

The broad failure has a shared infrastructure explanation. The transient
gateway process `PATH` omitted `/home/kotori9/.local/bin`, the location of the
installed `codex` launcher. Frontier configuration invokes bare `codex`;
runtime events therefore recorded `FRONTIER_PROCESS_SPAWN_FAILED`. OpenCode and
Hermes commonly terminated with `remote Executor fallback unavailable`, and
several Codex Responses streams failed after the same unavailable correction
path. This prerequisite failure means v80 is not a clean client noninferiority
result and is not a Candidate-A backend failure. Individual task-quality
failures remain preserved rather than discarded.

Before cleanup Candidate A used 72,596 MiB, host available memory was
45,606,052 KiB, and the isolated, candidate, and production gateways all
returned HTTP 200. Only `dgx-moa-v80-gateway.service` was exactly stopped; port
19312 was released while candidate A, its gateway, and production stayed active
and HTTP 200. The next admissible single variable is the transient launcher
`PATH`, with a direct Codex OAuth Frontier spawn/completion gate before another
full matrix.

### Frontier PATH qualification v81 — 2026-08-11

Protocol epoch `mistral-128k-v81-frontier-path-qualification-20260811`
changed only the isolated gateway launcher `PATH`, prepending
`/home/kotori9/.local/bin`. The service environment resolved the expected
`/home/kotori9/.local/bin/codex` launcher. One normal orchestrated request
returned HTTP 200 and recorded `frontier_collaboration_completed` for
`codex_oauth`, profile `primary`, model `gpt-5.6-sol`, with 28,873.862 ms
latency, 19,551 prompt tokens, and 1,048 completion tokens. The epoch recorded
zero `FRONTIER_PROCESS_SPAWN_FAILED` events.

Candidate A remained at 72,596 MiB and host available memory was 45,639,668
KiB. Candidate A and production remained HTTP 200. The isolated v81 service
was exactly stopped and port 19312 released. State DB SHA-256 is
`a73f0c193d58984367f88b0450608d9b0b3addcb2317fe1b1d69fd01e08174d3`.
This passes only the v80 common prerequisite and authorizes a new full matrix;
it does not relabel v80 or pass the client-quality gate by itself.

### Corrected-PATH full matrix v82 — 2026-08-11

Protocol epoch `mistral-128k-v82-frontier-path-fixed-full-matrix-20260811`
executed all 20 frozen cells with the v81-qualified PATH as its only common
change. Baseline and Hermes passed `5/5`, Codex passed `2/5`, and OpenCode
passed `3/5`, totaling `15/20`; the functional gate therefore remains failed.
Summary SHA-256 is
`86443c82a0a272f86aace2e158ade1dafca70d4b0ae744a807134eae493e23c6`,
schedule SHA-256 is
`16c6ddf10745747d0ff1cacb9f3399688e539154f2a016e696c9c5efac14c427`,
and the checkpointed state DB SHA-256 is
`a2c7946e302fbfbea4e1a9626673f17dbcdcad3658bffdd97c2c5cf225df724e`.

The v80 systemic failure did not recur: the v82 state DB contains zero
`FRONTIER_PROCESS_SPAWN_FAILED` events and zero payloads containing `remote
Executor fallback unavailable`. Codex log-report passed in 360.085 seconds and
webhook-verifier passed in 816.871 seconds. Codex rate-limiter, atomic-store,
and dag-runner reached the 1,800-second limit; OpenCode atomic-store also timed
out, while OpenCode dag-runner completed public and hidden validation but
failed only the Korean-final check. These five cells remain frozen as distinct
task-quality/convergence evidence rather than a shared transport or backend
failure.

Before cleanup candidate A used 72,776 MiB, host available memory was
45,452,932 KiB, swap use was 2,248,468 KiB, and candidate, isolated, and
production gateways all returned HTTP 200. Only
`dgx-moa-v82-gateway.service` was exactly stopped; port 19312 was released and
the three persistent services remained active. Do not rerun v82 in place.
Investigate its failures in separately named targeted epochs, then require a
new full matrix before blind noninferiority or release gates.

### OpenCode dag-runner Korean-final replay v83 — 2026-08-11

Protocol epoch `mistral-128k-v83-opencode-dag-korean-replay-20260811`
exact-replayed the v82 OpenCode dag-runner cell with repetition as the only
variable. The client exited zero in 204.123 seconds, changed only
`dag_runner.py`, passed public and hidden validation, retained tool evidence,
and produced a Korean terminal response, for 10/10. Candidate A and production
remained active and HTTP 200 at 72,776 MiB, with 45,513,612 KiB host memory
available. The v82 English-only final was not reproduced; retain it as a
stochastic observation rather than changing the prompt or gateway from one
miss.

### OpenCode atomic-store timeout replay v84 — 2026-08-11

Protocol epoch `mistral-128k-v84-opencode-atomic-timeout-replay-20260811`
exact-replayed the v82 OpenCode atomic-store cell without changing backend,
client, prompt, task, timeout, or scoring. It exited zero in 489.769 seconds,
changed only `atomic_store.py`, and passed all 10 checks. Candidate A and
production remained active and HTTP 200 at 72,776 MiB, with 45,604,976 KiB
host memory available. The v82 timeout was not reproduced; preserve it as one
slow non-convergent execution and make no OpenCode-specific change from this
pair of observations.

### Codex atomic-store timeout replay and latest-evidence recovery v85/v86 — 2026-08-11

v85 exact-replayed Codex atomic-store and reproduced the timeout at 1,800.097
seconds. Public and hidden validation passed, but all 33 client-visible agent
messages were progress-only. The gateway session made 36 requests, five
Reviewer rejections, and 18 Frontier correction-tool retries. Direct event
evidence showed that `review_tool_results` retained the first four stub/deadlock
failures alongside the latest four results, so superseded failures kept
`frontier_correction_required` open.

v86 changed only review evidence selection to the latest eight results after
339/339 focused controller/API tests passed. In an isolated port-19312 gateway,
the stale Frontier correction loop disappeared: zero correction-tool retries
occurred. The cell nevertheless timed out at 1,800.203 seconds with the same
8/10 score. Its final state showed two current passing test runs, but the
eight-result window still included two earlier failures and the last Reviewer
rejection occurred before the passes. Candidate A, isolated, and production
gateways were HTTP 200 before exact v86 cleanup; candidate A used 72,776 MiB
and host memory available was 45,478,724 KiB. v86 is failed evidence and does
not authorize deployment. The next isolated single variable is the latest four
review results; contract evidence remains independently preserved.

### Latest-four Codex atomic-store recovery v87 — 2026-08-11

v87 changed only `review_tool_results` from latest eight to latest four, while
the separate contract-document evidence path remained unchanged. Focused
controller/API tests passed 339/339. The isolated Codex atomic-store cell then
completed in 1,058.352 seconds and passed all 10 checks. This was not a review
bypass: the state DB recorded one Frontier rejection, four requested/completed
correction-tool retries, one applied correction, and one
`frontier_correction_verified` event. Before exact cleanup candidate,
transient, and production gateways were HTTP 200, candidate A used 72,776 MiB,
and host available memory was 45,339,480 KiB. Only v87 was stopped and port
19312 released. Latest-four is now the targeted recovery candidate; it remains
undeployed pending the other failed Codex cells and a fresh full matrix.

### Latest-four Codex rate-limiter v88 — 2026-08-11

v88 reused the physically passed latest-four review evidence policy for the
v82 Codex rate-limiter failure. The cell exited zero in 457.669 seconds and
recovered terminal convergence, but scored 9/10: hidden validation showed that
the implementation rejects valid positive float `window_seconds=2.5`.
Runtime evidence explains why review assurance missed the boundary. Four
Frontier architecture calls completed during tool continuation, consuming the
entire task budget; seven subsequent paths recorded
`FRONTIER_INVOCATION_LIMIT`, including the clean-local-review assurance
trigger. Candidate, isolated, and production gateways stayed HTTP 200,
candidate A used 72,778 MiB, and host available memory was 45,433,560 KiB.
Only v88 was stopped. Preserve the quality failure; next test architecture
artifact reuse as a single variable so code-review assurance retains budget.

### Frontier architecture-reuse rate-limiter replay v89 — 2026-08-12

v89 exact-replayed Codex rate-limiter with latest-four review evidence and the
preregistered architecture-artifact reuse candidate. The cell exited zero in
742.760 seconds and passed all 10 checks, including hidden validation. Runtime
evidence does not establish the candidate branch as the cause: all three
Frontier completions were `code_review`, zero were `architecture`, and zero
`frontier_architecture_reused` events occurred. One existing progress-retry
path reused prior Reviewer and Frontier artifacts, while two Frontier
corrections and one correction verification completed within budget. Preserve
the 10/10 task recovery, but classify the architecture-reuse acceptance as not
exercised rather than qualified. Candidate A, isolated, and production
gateways were HTTP 200 before cleanup; candidate A used 72,778 MiB and host
available memory was 45,498,024 KiB.

### Latest-four Codex dag-runner recovery v90 — 2026-08-12

v90 applied only the physically passed latest-four review evidence policy to
the remaining v82 Codex dag-runner failure; the unexercised v89 architecture
reuse branch was removed before preflight. After 339/339 focused tests, the
isolated cell exited zero in 864.933 seconds and passed all 10 checks, including
public and hidden validation. It made 33 request/tool-result continuations and
completed one review. Four repeated architecture calls exhausted the Frontier
budget, followed by 20 `frontier_unavailable` events, but the cell still
converged to a correct Korean terminal. Record this as task-quality recovery
and as a separate orchestration-efficiency observation, not a Candidate-A
failure. Before cleanup all three gateways were HTTP 200, candidate A used
72,778 MiB, and host available memory was 45,405,976 KiB.

### Latest-four fresh matrix v91 and targeted recovery v92 — 2026-08-12

Epoch `mistral-128k-v91-latest-four-full-matrix-20260812` was safely paused
after two cells and must not be interpreted as a completed matrix. Its first cell, Codex
rate-limiter, timed out after 1,800.213 seconds. Public and hidden validation,
source scope, tool evidence, and Korean output checks passed; only harness exit
and terminal failed. The runtime had falsely derived `/non-string` from the
implementation docstring phrase `empty/non-string`, so Frontier rejected the
otherwise allowed scope and correction did not converge.

The second OpenCode atomic-store cell exposed the same evidence-class
bug through a different input: a `state.json` file created under
`TemporaryDirectory` by an independent validation command was reported as a
repository change. Frontier then rejected the permitted single-file scope.
Both cells timed out at 1,800 seconds after their public and hidden validations
passed. The pause monitor then stopped only the v91 matrix and gateway; the
remaining 18 cells were not started. These are controller evidence-extraction
failures, not Candidate-A kernel or memory failures.

The separate new-process v92 epoch narrowed relative-path extraction to actual
command arguments or mutation targets and excluded tempfile validation writes.
OpenCode atomic-store passed 10/10 in 231.803 seconds with Frontier verification,
physically clearing its v91 failure. Codex rate-limiter exited normally in
451.399 seconds, clearing the timeout/terminal failure, but passed only 9/10:
hidden validation showed that the generated implementation incorrectly rejected
a valid non-integer `window_seconds`. Therefore v92 is a partial failure and does
not authorize a full matrix. It also exposed `bool:`/`int:` false paths because
the shell-redirection matcher interpreted Python `->` annotations as redirects;
the shared matcher now excludes `->` and `>=`. Focused controller/API tests pass
341/341 and Ruff passes after that source-only correction; physical replay remains
required. Candidate A remained at 72,778 MiB and both persistent gateways were
HTTP 200 after transient cleanup.

V93 then replayed Codex rate-limiter with the first redirect-boundary fix. The
cell passed all 10 functional checks in 1,137.327 seconds, including hidden
validation and verified Frontier correction. It is not parser qualification:
the raw implementation evidence still contained false paths `/remaining(` and
`cutoff`, caused respectively by slash-separated method prose and a Python `>`
comparison. The next source candidate limits redirect parsing to explicit
`cat`/`echo`/`printf` shell commands and excludes parenthesized slash prose;
341 focused tests, Ruff, and a direct combined regression pass. A new-process
physical replay remains required before a full matrix.

V94 performed that new-process replay with conservative command-specific path
extraction. Codex rate-limiter passed all 10 checks in 714.089 seconds; public
and hidden validation, Korean terminal, and verified Frontier correction all
passed. Every recorded implementation target path was exactly
`rate_limiter.py`, with none of the v91-v93 false tokens. Candidate A remained
72,778 MiB and both persistent gateways were HTTP 200 after cleanup. This
qualifies the common parser prerequisite and authorizes a separately named
fresh 20-cell matrix; it does not substitute for that matrix.

Fresh matrix v95 used frozen schedule SHA-256
`9b63d1ce3883e06debd2794358856c776fbfb2fcff580ac4f38e4f08396a081c`
against a new isolated gateway. Its first cell, Hermes
atomic-store, passed 10/10 in 303.809 seconds. No matrix verdict exists yet.
Candidate A and both persistent gateways remained immutable.
The monitor's first version misclassified systemd `activating` as terminal and
briefly stopped the isolated gateway during cell 02, Codex log-report. The
gateway was immediately recreated, the incident is recorded in the protocol,
and the monitor now checks explicit active-state values. Cell 02 cannot be
called a clean result without inspecting its transport evidence. Persistent
services and Candidate A were unaffected. Cell 02 completed in 636.803 seconds
but failed hidden validation because `sample_limit=True` was accepted and also
failed bad-terminal due to the reconnect records. The pause race started cell
03 before stopping it, so OpenCode log-report has no score. V95 is frozen as an
invalid interrupted matrix: two scored cells, one pass, one fail, and 17 cells
not started. The common quality contract now explicitly requires bool rejection
for `limit` and names ending in `_limit`; 341 focused tests and Ruff pass, but
this is source evidence pending a new-process targeted replay.

V96 was that new-process Codex log-report replay. It ran without an automatic
gateway stop monitor. Hidden validation passed, physically recovering boolean
`sample_limit`, but the cell timed out at 1,800.145 seconds and failed harness
exit plus terminal. All four Frontier completions were architecture calls; no
code-review call occurred, followed by 18 unavailable events and eight local
review attempts. Direct control-flow inspection showed that architecture
fanout occupied the Frontier task before local implementation review, so later
reviewer findings could not start code-review escalation. A source candidate
now defers architecture when implementation evidence and a reviewer are
present; the existing shared fanout/code-review test was strengthened and all
341 focused tests plus Ruff pass. Physical convergence remains unqualified.

V97 physically qualified the convergence candidate. Launch attempt 1 stopped
before a request because the quality workspace lacked the runner's prepare
step; that setup failure is preserved. Attempt 2 changed only that setup step,
then Codex log-report passed all 10 frozen checks in 329.680 seconds. Runtime
events contained two `code_review` collaborations and zero `architecture`
collaborations, two completed local reviews, one Frontier rejection, one
correction application, and `frontier_correction_verified`; no
`frontier_unavailable` event occurred. Public and hidden validations returned
zero and only `log_report.py` changed. The isolated gateway was stopped after a
SQLite WAL checkpoint, while candidate A and both persistent gateways remained
healthy. Frozen evidence is under
`data/diagnostics/client-quality/mistral-128k-v97-review-first-codex-log-20260812`.

### Authenticated LAN ingress — 2026-08-11

An address-specific systemd socket proxy was enabled at
`192.168.0.42:9000`, forwarding to the unchanged authenticated gateway at
`100.125.239.72:9000`. After activation, loopback `127.0.0.1`, tailnet
`100.125.239.72`, and LAN `192.168.0.42` each returned HTTP `200` for
`/healthz` and HTTP `401` for an unauthenticated `/v1/models` request. The
gateway remained active with `NRestarts=0`; role-model listeners were not
changed. No wildcard `0.0.0.0:9000` listener was introduced.

UFW was active with the configured default input policy `DROP`. The unprivileged
session could not inspect or add its root-owned rules, so reachability from a
second LAN host remains unverified until the documented subnet-scoped rule is
applied by an operator. This does not alter the verified address-specific bind
or authentication behavior above.

### Candidate-A post-SGLang full matrix v99 — 2026-08-12

V99 completed all 20 frozen cells against the preserved vLLM Blackwell-native
Candidate A and scored `18/20`: Hermes and OpenCode passed `5/5`; baseline and
Codex passed `4/5`. Candidate A remained at 72,428 MiB and the matrix and
gateway recorded zero restarts. Exact cleanup stopped only the transient v99
matrix and gateway; Candidate A and the production gateway remained active.

Codex log-report passed public validation and review but rejected valid
`sample_limit=0` in hidden validation. Baseline, Hermes, and OpenCode log-report
all passed, so this is a Codex trajectory failure rather than a shared backend
verdict. Baseline atomic-store passed public validation but accepted an invalid
boolean expected version (`True == 1`); the other three clients passed that
task. The frozen summary SHA-256 is
`675977f1d5ae1326a83ffb1654f7eb9e05af1575f9128ab5996d54f52063cb60`.
V99 is complete failed evidence. Recover both cells in separately named epochs,
then require a fresh full matrix before blind noninferiority or later gates.

V100 targeted both v99 failures in fresh workspaces. Codex log-report converged
through repeated review/correction and passed all ten checks in 1,482.571
seconds. Baseline atomic-store passed public validation but failed hidden
validation in 107.525 seconds: `expected_version=True` raised
`VersionConflict`, while the invalid-input contract requires `TypeError` or
`ValueError`. V100 is partial failed evidence; replay only baseline atomic-store
in a new epoch before authorizing another full matrix.

V101 exact-replayed baseline atomic-store at the unchanged `high` reasoning
effort and reproduced the hidden `invalid update accepted` failure in 117.656
seconds. Repetition at the same setting is exhausted. The next isolated single
variable is baseline reasoning effort `high` to `xhigh`; the common runner keeps
`high` as its default and accepts only those two values. Focused matrix tests
passed 13/13 and Ruff passed before physical v102 execution.

V102 changed only baseline reasoning effort to `xhigh`. Its generated
atomic-store validated expected-version type before CAS comparison, rejected
boolean input correctly, and passed all ten frozen checks in 190.610 seconds.
This qualifies the baseline configuration candidate but does not replace the
required fresh 20-cell matrix. The next matrix must pin baseline xhigh while
leaving Candidate A and all non-baseline harness contracts unchanged.

### Baseline-xhigh fresh full matrix v103 — 2026-08-12

V103 completed all 20 frozen cells against unchanged Candidate A with only
baseline reasoning effort changed to `xhigh`. Baseline, Hermes, and OpenCode
passed `5/5`; Codex passed `3/5`, for `18/20`. The frozen summary SHA-256 is
`efb6c530703cf8f44f10cf5dac368280de7e2075fc9345382a8de5db319e9a4a`.

Codex rate-limiter passed public validation but hidden validation terminated in
its constructor with `TypeError: window_seconds must be an integer`. Baseline
and OpenCode passed the same rate-limiter contract. Codex atomic-store also
passed public validation but hidden validation raised
`AssertionError: invalid update accepted`; baseline, Hermes, and OpenCode
passed that task. Codex log-report passed in 504.676 seconds, confirming the
v100 recovery in a fresh matrix. These two failures are client trajectories,
not shared model-runtime, memory, or gateway failures.

The matrix, gateway, and cleanup-monitor units all ended `success`, inactive,
with zero restarts. Candidate A remained active at 72,430 MiB, and the
production gateway remained active. Frozen failure hashes and cleanup state are
recorded in the epoch's `finalization.json`. V103 is complete failed evidence;
blind noninferiority and later gates remain unstarted pending targeted recovery
of both Codex cells and another fresh full matrix.

V104 replayed the two v103 Codex failures without changing the model, backend,
harness, reasoning setting, or scoring contract. Attempt 1 created no score and
made no model request because the launcher omitted `prepare`; attempt 2 added
only that required setup action. Codex rate-limiter passed all ten checks in
302.828 seconds, and Codex atomic-store passed all ten in 386.212 seconds.
All three transient units then ended `success`, inactive, with zero restarts.
This is targeted recovery evidence; a fresh 20-cell matrix remains mandatory.

### Pilot-first transition, containment, and runtime contract — 2026-08-12

The active Goal policy changed from completion-first to Pilot-first without
altering any frozen plan, hash, protocol epoch, success, or failure artifact.
The v105 client-quality matrix was safely paused after preserving eight scored
cells (four pass, four fail); it is now `POST_PILOT_VALIDATION`, not discarded evidence. The
frozen completion-plan SHA-256 still equals
`41e16b4f2fb8f442d8da3065ba53eacb317fc9a68333e63c02253784bcf1a4bd`.

Protocol `pilot-v1-transition-20260812` first tested OOM blast-radius isolation.
A transient pressure unit in `dgx-moa-qualification.slice` used
`MemoryMax=134217728`, zero swap, `OOMPolicy=stop`, and control-group kill. Its
second run allocated 8 MiB increments through 120 MiB and then ended
`oom-kill`/SIGKILL; slice `MemoryPeak` was 134,258,688 bytes. Across 320 health
samples there were zero production or validation gateway failures. The user
manager PID `3107444`, production gateway PID `3107456`, and Candidate A PID
`2383374` were unchanged. Candidate A then received live limits of 12 GiB high,
16 GiB max, and 4 GiB swap max; it remained active with 8,295,600,128-byte host
memory peak. Exact measurements are frozen in `containment-result.json`.

An isolated loopback gateway on port 19320 then used one validation key,
Candidate A, `execution_graph.mode=shadow`, and a dedicated SQLite DB. Attempt
01 preserved a pre-inference `invalid trace_origin` failure; attempt 02 changed
only `pilot_validation` to the supported `validation` value. It passed Chat
(`PILOT_OK`), Responses, completed SSE (`STREAM_OK`), a forced native
`get_status` tool call, and same-session tool-result continuation. After exact
gateway stop/start the DB retained four graphs. Enabling only the Pilot
destructive-operation policy returned HTTP 403 with `approval_required` and a
`HUMAN_APPROVAL/WAITING_APPROVAL` attempt; a subsequent normal request returned
HTTP 200 and `RECOVERY_OK`.

The finalized DB contains six graphs, 25 attempts, 57 checkpoints, six active
states, one `execution_graph_resumed` event, and zero
`execution_graph_shadow_failed` events. Its SHA-256 is
`37e6dac4cf4c752ce1d8618ec0187f4612f86084fca7de4c544649405fadfa31`.
The transient gateway was stopped and its WAL checkpointed; Candidate A and
both persistent gateways remained HTTP 200.

Inspection also found that scheduler-disabled graph projection labeled the
actual Mistral Candidate A as `legacy_local_qwen`. The shared projection branch
now records `local_mistral`; its focused test passed, and a new-process physical
attempt recorded both `scheduling.selected_executor` and the Executor node
provider as `local_mistral`. That DB SHA-256 is
`82525b4614ddb4234c88225f39df95b5cf4503d898b3a79ec214310704f195da`.

The checked-in launcher now expands to the fixed revision, context 131072,
seq1, KV 3.4 GB, TRITON_MLA, lazy safetensors, `FULL_DECODE_ONLY`, and
`flashinfer_b12x`, with no MARLIN linear override. The Executor unit encodes
`VLLM_NVFP4_GEMM_BACKEND=flashinfer-b12x`, long-context permission, and the
measured 12/16/4 GiB cgroup limits. MARLIN plus graph `NONE` remains an explicit
rollback environment. Focused validation passed 39 tests. The complete current
worktree gate then passed Ruff check and format, strict mypy on 49 source files,
`1059 passed` in pytest, and `systemd-analyze --user verify`. These are
checked-in release-candidate facts, not an
installed production deployment. Remaining Pilot gates are reviewed revision,
installed exact restart, rollback rehearsal, and limited developer canary.

### Limited Pilot deployment and rollback — 2026-08-12

A temporary Git index captured the validated source/docs without modifying the
pre-existing dirty worktree or its AvatarForge-staged index. Clean branch
`codex/pilot-v1-release-candidate` points to commit
`1384c319dc76d5f3aa07693da6380a0cf9a4826a` and tree
`5c4ed368296d5144477490b6a171669e349819b9`. Its separate clean worktree passed
Ruff check/format, strict mypy on 49 source files, pytest `1059/1059`, systemd
verify, and the frozen plan hash. Raw benchmark DB/log artifacts and credentials
were excluded from the commit; five bounded Pilot summary JSON files were
included.

The first encrypted-credential preflight failed before service creation because
the user manager could not read the host credential secret. A mode-0600
volatile credential plus systemd `LoadCredential` replaced only that transport.
Launch attempt 01 then failed closed because unescaped `$` expansion emptied the
Flash credential; attempt 02 loaded correctly but its standard config expected
the not-yet-installed Executor on port 8101. Attempt 03 changed only the model
config to the frozen Candidate A listener on 19301 and became ready on the
tailnet-only address `100.125.239.72:19000`. All failure classes remain in
`pilot-active-result.json`.

The authenticated canary returned 401 without a key and 200 with its only key.
It passed Chat `PILOT_ACTIVE_OK`, completed Responses and SSE, native
`get_status`, semantic same-session tool-result continuation `STATUS_READY`,
high-risk HTTP 403 `approval_required`, and a live DeepSeek V4 Flash minimum
completion `FLASH_PILOT_OK`. The durable store reached ten graphs, 43 attempts,
99 checkpoints, ten active states, and zero shadow failures. An initial
adversarial continuation structurally resumed the graph but echoed the original
instruction; it is preserved separately and the explicit semantic continuation
is the accepted canary.

Exact restart changed the Pilot gateway PID from 3492952 to 3496804 while graph
count stayed 10 and authenticated readiness returned 200. Exact stop then closed
port 19000 while production and validation remained 200 and the production
gateway, Candidate A, and user manager PIDs stayed 3107456, 2383374, and
3107444. The checkpointed DB SHA-256 was
`1a75f68b5b8cacf390b64370b9f34d1dc546eefe25af1002dc2386ca4cda0494`.
Attempt 04 redeployed the same release and reused all ten graphs. It is active
with PID 3498366, zero restarts, and the 1/2/0.5 GiB cgroup limits. A post-
redeploy Candidate A request returned `PILOT_REDEPLOY_OK`; 120 paired
Pilot/production health samples had zero failures. Durable totals then reached
11 graphs, 47 attempts, 108 checkpoints, 11 active states, zero shadow
failures, and a 59,916,288-byte Pilot gateway peak. This advances the operating stage to `PILOT_ACTIVE`;
the Goal remains active for bounded real-use telemetry and post-Pilot gates.

### Pilot real-use Graph recovery — 2026-08-12

`real-use-codex-01` made five completed requests (31,215 tokens) before one
bounded cancellation. The client emitted five progress-only messages and no
final audit. All shell attempts failed in the client sandbox with
`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`. Durable Graph
evidence additionally recorded three `reasoner`, one `tool`, and one
`stream_tool_wait` shadow `ValueError`; the raw client event and stderr hashes
are frozen in `real-use-result.json`.

The minimal fix was validated in the clean release worktree: Ruff check/format,
strict mypy over 49 source files, and `1061 passed`. Release commit `c96ace60`
changed only Graph reprojection after failed tool continuation and effective
Frontier availability in projection, plus two regressions. Deployment attempt
05 failed closed before readiness because the transient command expanded the
Flash credential expression incorrectly. Attempt 06 reused the proven escaped
command and became healthy without restarting production or Candidate A.

Physical session `pilot-graph-reentry-canary-20260812-01` produced a native
`shell` tool call, submitted a synthetic nonzero tool result, and received a
normal final completion. It recorded two compiled graphs, one resume, one
preserved failed TOOL attempt, zero Frontier nodes, and zero
`execution_graph_shadow_failed` events. Pilot, production, and Candidate A all
returned HTTP 200; exact evidence is in
`graph-reentry-fix-20260812/result.json`. This closes that failure family only;
it did not by itself convert the interrupted Codex task into a successful
real-use canary.

Codex canary 02 disabled the broken client bwrap boundary and completed seven
read-only commands but did not finalize. It had zero Graph shadow failures;
durable events showed the remaining cause was
`implementation_tool_action_required`, because Korean `수정하지 마라` still
contained the naive `수정` marker. Canary 03 added a read-only intent guard and
did finalize, but executed zero commands and therefore failed for false
completion. Both failures and hashes remain frozen.

Commit `0f170c02` separates the two contracts: explicit read-only intent cannot
trigger the file-change gate, while an objective naming `exec_command` requires
at least one successful tool execution before final output. API/controller
regression passed `341/341`; final clean release validation passed Ruff check,
Ruff format over 93 files, strict mypy over 49 source files, and pytest
`1061/1061`. Codex canary 04 then completed all three requested commands with
exit zero, emitted an evidence-backed PASS, and exited zero. Its two Gateway
requests used 13,041 tokens in 23.785 active seconds; the durable Graph compiled
once, resumed once, and recorded zero shadow failures. Attempt 08 remained
active with zero restarts; Pilot, production, and Candidate A returned 200.
Exact hashes and runtime identities are frozen in `real-use-codex-04/result.json`.

OpenCode `real-use-opencode-01` subsequently executed exactly two requested
`bash` commands with exit zero, returned `PASS`, and exited zero. Its two
Gateway requests used 20,340 tokens in 23.851 active seconds; the Graph compiled
once, resumed once, and had zero shadow failures. The client emitted one host
warning: adding an inotify watch on the development `.git` directory returned
`ENOSPC`. It did not alter the result but remains actionable operational
evidence. Read-only `/proc` inspection attributed 65,448 of the 65,536 user
watches to `zed-remote-serv` PID `3393658`; Codex used 35. This rules out the
Pilot gateway and Candidate A as the source. Restarting the developer's Zed
session or changing host sysctl was not authorized, so neither was performed.
The exact count is preserved in `inotify-watch-audit-20260812/result.json`.

Hermes `real-use-hermes-01` executed exactly two requested `terminal` commands,
returned exactly `PASS`, and exited zero. Its usage artifact reports two API
calls, 30,786 tokens, completed true, and failed false; Gateway accounting
matches 30,786 tokens over 39.273 active seconds. Its Graph compiled once,
resumed once, and had zero shadow failures. Pilot attempt 08 stayed active with
zero restarts. Exact logs, usage, and hashes are stored beside each result.

### Instruction-scoped tool evidence and Codex canary 05 — 2026-08-12

Codex review `real-use-codex-review-01` exited zero but violated its requested
JSON schema and returned plain-text `FAIL`. The proposed Graph finding was not
accepted because the focused regression and physical Graph continuation canary
demonstrated the opposite behavior. The invalid review, rejection reason, and
raw hashes remain in `real-use-codex-review-01/result.json`.

Independent inspection instead reproduced a false-completion boundary in the
shared controller: a successful tool from any earlier instruction in the same
session satisfied a later explicit tool request. Commit
`40fddc0b2e05520117fdfc93d4247528ebe86406` scopes evidence with a persisted
instruction hash and tool-execution cursor. Ruff check/format, strict mypy over
49 source files, and pytest `1061/1061` passed in the clean release worktree.

Physical session `pilot-request-scoped-tool-evidence-20260812-01` first
completed an unrelated `noop`, then submitted a new instruction explicitly
requiring `exec_command`. The prior success did not count: the gateway emitted
and completed `printf SCOPED_OK`, then finalized. The DB retained cursor `1`,
two tool executions, one `implementation_tool_action_required` event, and zero
`execution_graph_shadow_failed` events. Four completed requests used 6,105
tokens over 14.497 active seconds. Exact evidence is in
`request-scoped-tool-evidence-20260812/result.json`.

Codex `real-use-codex-05` then read the release HEAD and located the new cursor
field with exactly two successful commands, returned `PASS`, and exited zero.
Its two Gateway requests used 12,157 tokens over 21.640 active seconds; the
Graph compiled once, resumed once, and recorded zero shadow failures. Pilot
attempt 09 runs the committed release with PID `3628923`, zero restarts, and
unchanged 1/2/0.5 GiB limits. Production PID `3107456` and Candidate A PID
`2383374` remained unchanged. Exact client/session IDs and SHA-256 hashes are in
`real-use-codex-05/result.json`.

### Exhausted TOOL-graph reprojection and write canary — 2026-08-12

Codex write attempt 01 never reached the Pilot: `OPENAI_BASE_URL` alone left
the client on `api.openai.com`, which returned 401. Attempt 02 reached
`dgx-moa-fast`, issued ten tool results, and reproduced four
`execution_graph_shadow_failed` events after the bounded TOOL repair edge was
exhausted. Its 11 requests used 103,991 tokens over 136.800 active seconds.

Commit `ed9f3d943d8f3c8b6877293472cef2d6c6db4140` fixes the shared boundary. If
`resume_tool_result()` selects an exhausted `ON_BUDGET` edge, the API preserves
the completed attempt, emits a `tool_cycle_budget_exhausted` reprojection event,
and compiles a new immutable Graph. It does not increase the Graph repair limit
or the engineering-loop tool budget. The clean release gate passed Ruff check
and format, strict mypy on 49 source files, and pytest `1062/1062`.

After attempt 10 deployed that commit, attempt 03 physically crossed the same
boundary with two Graph compiles, four resumes, one reprojection, and zero
shadow failures. Later probes also reprojected without a shadow failure. A
persistence round-trip regression for the instruction-scoped tool cursor passed
`tests/test_controller.py` `103/103` plus Ruff check/format and is stored by
test-only commit `eaaa4e0f5`.

The client catalog is part of the physical contract. A catalog file merely
present under `CODEX_HOME` did not advertise `apply_patch`; Codex must receive
an explicit `model_catalog_json` path to the authenticated `/v1/models`
artifact. With that pin, `client_tools_available` contained `apply_patch` for
both `dgx-moa-fast` and primary `dgx-moa`. Nevertheless, neither completed the
requested two-line test change. The primary path made seven tool calls, then
returned `PATCH_MARKER_NOT_FOUND` and an `AttributeError` from two shell rewrite
attempts before cancellation. The canary worktree remained clean, so the write
quality gate remains `FAILED_OPEN`. Full counters, client/gateway session IDs,
raw hashes, and the unchanged-worktree verdict are frozen in
`real-use-codex-write-01/result.json`.

Service observation after evidence capture: production gateway PID `3107456`,
Pilot PID `3704865`, both active with zero restarts; production and Pilot
`/healthz` and Candidate A loopback `/health` returned HTTP 200. This result
does not change the already qualified vLLM native-NVFP4 candidate A, the v66/v98
SGLang candidate-B rejection for this exact epoch, or MARLIN's rollback-only
status.

### Primary Codex write recovery epochs 02–04 — 2026-08-12

Epoch 02 (`54cb7eb5-f337-4872-ac4c-e0a321a4b376`) returned a false completion
after a failed patch was normalized as exit code zero. Commit `b6912a119`
corrects that envelope. Epoch 03 (`c715880e-b680-4f52-816c-401ea68f9328`)
physically classified six malformed/tool parse failures and Reviewer rejected
the unchanged worktree, but scoped text `Do not modify any other file` still
disabled the write gate.

Commit `2a3afdce826b7fbc4e5cf3d682085b427ebcfa22` corrects that classification.
Ruff check/format, strict mypy over 49 source files, and pytest `1062/1062`
passed with zero JUnit failures/errors. Epoch 04
(`c6e01c18-662b-4bb3-b363-baddb7ceb14e`) then passed: exact two-line diff,
`103 passed`, Reviewer approved/no-findings, seven requests, 35,542 tokens,
94.253 active seconds, three Graph compiles, six resumes, and zero shadow
failures. Each epoch retains its own raw hashes and `result.json`.

Attempt 11 stopped with `success`; attempt 12 is active at PID `3790208`, zero
restarts. Production, Pilot, and Candidate A remained HTTP 200. This authorizes
only a fresh client-quality epoch, not blind or later gates.

### Client-quality v106 and targeted v107 recovery — 2026-08-12

The frozen v106 20-cell result was baseline `5/5`, OpenCode `5/5`, Codex
`0/5`, Hermes `0/5`. Summary SHA-256 is
`c1dd1ffe64fdbcd3a48ade5e41a4090a120526b1135a7b630d7a48542852b45d`;
execution-log SHA-256 is
`b065ebe1f2b8f08f816bfda2fa5cce08a159ced8cc81c98da56b75f6588dcd41`.
Hermes passed visible/hidden validation but lacked native unittest evidence in
all five cells. Codex recorded mutations but failed visible/hidden validation
in all five cells.

State inspection proved Korean scoped write text was treated as global
read-only, and `write_stdin failed: Unknown process id 0` was normalized as
success. Commit `60f7a236e` fixes those common guards. Targeted tests passed
`105/105`; clean Ruff, strict mypy on 49 files, and pytest `1062/1062` passed.
Isolated v107 passed the identical Codex webhook task after native unittest
exits `1, 1, 0`; duration was 434.176 seconds and all ten scoring checks
passed. Attempt 01 preserved the missing-`WorkingDirectory` launch failure;
attempt 02 passed. Cleanup succeeded and production, Pilot, and Candidate A
each returned HTTP 200.

Hermes targeted v108 passed the webhook cell in 343.912 seconds. Its evidence
records one unittest tool call and one successful result; all ten scoring
checks passed. Summary SHA-256 is
`b26dc42b03ff499100e6ae1c8b11367bee23d5b36a1de53cd61580f0f4526ad9`.

### Runtime Dashboard 완성형 UI 개발 검증 — 2026-08-12

기존 API-key scoped REST/WebSocket/ExecutionGraph projection을 그대로 사용해
`runtime_dashboard.py`의 placeholder 여섯 화면을 실제 UI로 교체했다. 구현 범위는
LIVE workflow/timeline, REQUESTS 목록, MODELS token/cache/fallback 집계, SYSTEM
runtime/telemetry, INCIDENTS failure/recovery, EVALUATION review/Judge/test, AUDIT
privacy contract와 사유 필수 cross-key 조회다. Request Inspector는 SUMMARY, PROMPT,
LIVE, OUTPUT, EVIDENCE, EXECUTION, LOGS 일곱 탭을 제공한다. 모든 동적 값은
`textContent`로만 렌더하며 API key는 기존 HttpOnly session 교환 경계를 유지한다.
Private request 목록에는 기존 `api_token_dashboard(name=api_key_id)` 집계를 추가해
다른 key의 usage가 섞이지 않게 했다.

Dashboard/API-key/usage/Admin 관련 테스트는 `47 passed`였고 Ruff, JavaScript
`node --check`, Python compile, `git diff --check`가 통과했다. 임시 loopback 정적
서버와 synthetic redacted snapshot을 Chromium headless로 렌더해 로그인 화면과
인증 후 KPI, 8-lane ExecutionGraph canvas, timeline을 육안 확인했다. 임시 포트는
종료됐고 production, v118 gateway/matrix, Candidate A gateway는 모두 active,
`NRestarts=0`; production `/healthz`는 HTTP 200이었다.

전체 pytest는 두 번 동일하게 61% 이후 shell exit marker 없이 종료되어 full-suite
PASS로 기록하지 않는다. 두 실행에서 Dashboard 관련 실패는 없었지만 원인은 이
epoch에서 규명하지 않았다. 이 변경은 개발 worktree에만 있으며
`dashboard_enabled=false` 기본값, production/Pilot configuration과 systemd topology를
변경하거나 배포하지 않았다.

### Runtime Dashboard role topology and current-runtime audit — 2026-08-12

The Dashboard snapshot now reports the seven requested role slots separately:
Reasoner, Planner, Frontier A, Executor, Reviewer, Judge, and Frontier B. Local
roles use bounded loopback model probes. Remote specialists and Frontier roles
remain explicitly `configured_unprobed` unless the runtime has a trustworthy
provider probe; configuration is never converted into a false availability
claim. The MODELS view renders model, provider, enablement, measured
availability, and evidence basis.

The LIVE view now distinguishes fixed control nodes as `Static Skeleton` from
role/tool/test nodes in the runtime-created request subgraph. The label is
deliberately request-compiled, not runtime-mutable: the deterministic compiler
selects an allowlisted simple/engineering/complex/critical topology and the
persisted graph remains immutable. Live Graph events update the canvas, paused
views retain their bounded buffer, graph cards open a node inspector, and an
open owner-scoped request inspector refreshes on matching runtime events.

`GET /v1/dashboard/runtime` adds authenticated content-free telemetry from the
local GB10 and the fixed `ssh mathcat` host. Both probes physically succeeded:
GB10 reported 130,595,168,256 total and 46,593,409,024 available memory bytes;
mathcat reported 32,702,402,560 total and 18,742,693,888 available bytes plus
one RTX 3080. The response records only bounded memory/GPU measurements and
failure classes. Durable Dashboard events have a 90-day minimum-retention
contract and no automatic purge; this does not authorize a retention delete.

The current deployed topology does not pass the seven-role gate. The fixed
production gateway remained active with zero restarts and `/healthz` HTTP 200,
but `/readyz` returned 503: Reasoner was ready while Executor, Planner,
Reviewer, and Judge were stopped. The limited Pilot had a healthy loopback
Mistral Executor and role-conditioned ExecutionGraphs, but Planner/Reviewer
reused that model, Frontier A was disabled in the active path, and no current
Judge or Frontier B node was present. Production `/dashboard` and its snapshot
route returned 404 because the deployed revision predates this development UI;
no deployment, service restart, or topology change was performed.

A Codex App harness failure at 22:47 KST was reproduced without a service exit.
Production `:9000` accepted the Responses stream but returned a terminal
`response.failed` with `backend_error`; the same `dgx-moa-fast` request against
the approved Pilot `:19000` returned exact `RUNTIME_OK` and
`response.completed`. Gateway logs also showed the harness retrying unsupported
model `gpt-5.5`, which returned 404. The immediate client correction is to use
the Pilot `/v1` endpoint with `dgx-moa-fast`; changing or restarting production
requires separate deployment approval.

Focused Dashboard, ExecutionGraph, runtime telemetry, and Admin tests passed
`20/20`. Ruff, JavaScript `node --check`, and `git diff --check` passed. The
complete suite then passed `1064/1064` in 44.23 seconds with only the existing
Starlette TestClient deprecation warning; this supersedes the earlier 61%
full-suite interruption for the current development worktree.

### Dashboard production-address validation deployment — 2026-08-12

The operator approved a production change after the failed Codex App harness
request. The fixed `main` gateway was drained to zero active requests and
stopped. A rollback-preserving transient validation gateway now serves the same
authenticated tailnet address `100.125.239.72:9000` from the tested development
source with `runtime_channel=dev`, `trace_origin=validation`, Dashboard enabled,
and ExecutionGraph shadow mode. The fixed gateway unit remains installed and
inactive for exact rollback. Candidate A remained loopback-only on `19301` and
was not restarted.

The common terminal finalizer retained the ExecutionGraph runtime while an
observed-attempt shadow failure is recorded; an injected SQLite finish failure
now still returns one client terminal response and one `session_ended` event.
Dashboard model readiness now checks the exact served model ID. System telemetry
is single-flight cached for five seconds, audited cross-key reasons use a POST
body, snapshot ordering retains the newest 500 events, and queue gaps force a
full resync.

Frontier A is configured and physically invoked through Codex OAuth with model
`gpt-5.6-sol` and reasoning effort `xhigh`. The bounded read-only smoke completed
on profile `primary` through the Codex exec fallback transport and reported
15,323 tokens. Both primary and secondary profiles reported authenticated.

Post-deployment physical checks passed: `/healthz`, `/readyz`, `/dashboard`, the
private Dashboard snapshot, and runtime telemetry returned HTTP 200. The
Responses-compatible `dgx-moa-fast` stream returned exact `RUNTIME_OK` and a
terminal `response.completed`. The resident readiness profile reported the
exact Executor and Reasoner endpoints ready. The snapshot exposed all seven
role slots and `static_skeleton+runtime_created_request_subgraph`. Direct bounded
specialist probes returned non-empty responses from Planner
`deepseek-v4-pro` and Reviewer `deepseek-v4-flash`. Judge passed its model-list
startup probe but an actual structured `glm-5.2` verdict returned empty output;
the validation runtime therefore disabled Remote Judge. Frontier B remained
unavailable because no OpenRouter credential file exists in any configured
Codex profile, and its fallback was disabled without attempting a remote call.
The gateway and Candidate A each remained active with zero restarts.

After the stream-finalization regression and review corrections, strict mypy on
49 source files, Ruff, shell syntax, and `git diff --check` passed. The complete
test suite passed `1064/1064` in 44.23 seconds with only the existing Starlette
TestClient deprecation warning.

### Seven-role Dashboard gate correction and fixed-service deployment — 2026-08-12

The earlier Frontier B and Judge conclusions above were superseded by direct
inspection and fresh inference. A root-owned `0600` OpenRouter credential was
already present; no credential was created or copied. Frontier B completed a
bounded structured call through `anthropic/claude-opus-5`. The authoritative
Remote Judge mapping is OpenCode Go `kimi-k3`, not the rejected GLM probe. Its
fresh six-case validation matrix passed approval, unsupported-claim, failed-test,
missing-criterion, correction, and corrected-recheck cases; a third call was
blocked by the two-call budget. The sanitized matrix hash is
`5f0126c1d64514d8398d9e36d1d4764768d46189c883848c9970e764199bf34c`.

`scripts/validate-runtime-roles.py` then issued content-free structured probes
to Planner `deepseek-v4-pro`, Reviewer `deepseek-v4-flash`, Judge `kimi-k3`,
Frontier A `gpt-5.6-sol` with configured `xhigh` reasoning, and Frontier B
`anthropic/claude-opus-5`. All five succeeded. The runtime artifact stores no
prompt or model output and has SHA-256
`c0d3d6501ac24a96c3c9368b66362a713cf33f5c7d6adaf3db73b364e50d0124`.
Dashboard availability accepts only fresh, exact-model, structured-probe
records; the Reasoner and Executor retain their exact endpoint probes. The
deployed snapshot consequently reports all seven roles `available=true`, with
the external Ollama Reasoner correctly distinguished from local GB10 service.

The transient gateway was replaced by the fixed `dgx-moa-gateway.service`
using a user-service validation drop-in. It was drained to zero before each
restart. The fixed gateway, loopback proxy, and Candidate A remained active
with zero restarts; tailnet, loopback, and LAN health checks returned HTTP 200.
An authenticated `dgx-moa-fast` Responses stream returned exact `RUNTIME_OK`
and terminal `response.completed`. Its persisted request-created
`engineering-v1` graph contained four runtime nodes and seven edges; CLASSIFY,
EXECUTOR_SELECT, EXECUTOR, and FINALIZE all reached `SUCCEEDED`.

The first physical WebSocket upgrade found that the deployment lacked a
Uvicorn WebSocket protocol implementation and therefore returned HTTP 404.
Adding the minimal `wsproto` runtime dependency and restarting corrected the
root cause. A raw TCP upgrade then returned HTTP 101 and the authenticated
`connected` event with operator scope and `current_seq=0`. The snapshot-to-live
client handshake now refreshes at that cursor and reconnects with replay,
closing the former REST/subscribe race. Ruff, strict mypy over 50 source files,
focused Dashboard/runtime tests `9/9`, `git diff --check`, and the complete test
suite `1065/1065` passed.

Two production gates remain open and are not claimed as complete. Execution
Graph is physically generating immutable request subgraphs from the static
allowlisted skeleton, but the deployed mode is still `shadow` and therefore
non-authoritative. No approved HTTPS ingress is installed. Tailscale Serve has
no configuration, and the current `docs/OPERATIONS.md` network authority
explicitly prohibits both Serve and Funnel. The deployed gateway rejects every
plain-HTTP Dashboard route with `426 dashboard_https_required` and rejects
non-WSS live connections while leaving Chat/Responses and health routes intact.
Dashboard access therefore remains safely closed until a separately reviewed
HTTPS ingress decision and subsequent authenticated HTTPS/WSS gate pass.

An isolated application-level TLS gate subsequently used a one-day loopback
certificate, disposable state database, and test-only key on `127.0.0.1:19443`.
Verified-certificate HTTPS returned `200` for `/dashboard`; the session exchange
returned an HttpOnly `Secure` cookie; and a raw TLS WebSocket upgrade returned
HTTP `101` followed by authenticated `connected`, operator scope, and
`current_seq=0`. The server and all temporary certificate/state material were
then removed. A WebSocket cancelled during server shutdown is now treated as
normal disconnect cleanup instead of producing an ASGI error. This proves the
application HTTPS/WSS behavior, but does not substitute for the still-missing
approved production ingress.

A fresh physical disabled-versus-shadow comparison then sent the same bounded
`dgx-moa-fast` request twice through disposable state databases to the active
Candidate A endpoint. Both returned HTTP `200`, exact `GRAPH_PARITY_OK`, finish
reason `stop`, one Executor invocation, and exactly one terminal event. Disabled
elapsed time was 0.506 seconds and shadow elapsed time was 0.538 seconds. The
shadow request compiled `engineering-v1`, persisted successful CLASSIFY,
EXECUTOR_SELECT, local-Mistral EXECUTOR, and FINALIZE attempts, and recorded zero
shadow failures. This is direct simple-path contract parity evidence only; it
does not satisfy the frozen all-template, failure-injection, or authoritative
Graph Engine paired-comparison gate.

The validation launcher was also corrected to stop pointing shadow Graph writes
at `/home/kotori9/dgx-moa-agent/data/state/gateway.db`. After an authenticated
drain, only the fixed gateway restarted against the dedicated
`data/diagnostics/runtime-overlays/dashboard-production-20260812/state/gateway.db`.
The new directory is mode `0700`, the SQLite database is `0600`, and the
124,891,136-byte production database was neither copied nor migrated. An actual
post-restart request returned exact `ISOLATED_STATE_OK`; only the validation DB
received its four-node `engineering-v1` shadow graph. Health/model checks passed
and the gateway retained zero restarts.

Two further authenticated requests exercised runtime template selection in the
dedicated validation database. Clear one-file metadata selected `simple-v1`
with five nodes and nine edges and returned exact `SIMPLE_GRAPH_OK`. High-risk
metadata selected `critical-v1` with seven nodes and 21 edges and returned exact
`CRITICAL_GRAPH_OK`. The latter physically persisted successful CLASSIFY,
EXECUTOR_SELECT, local-Mistral EXECUTOR, OpenCode Go Reviewer, OpenCode Go Kimi
Judge, CHECKPOINT, and FINALIZE attempts. Neither request recorded a shadow
failure. This proves request-created subgraph selection and actual observed
critical-stage projection; the legacy Controller still owns dispatch until the
separate enforced-promotion gates pass.

### Authenticated wildcard gateway ingress — 2026-08-13

The operator corrected the repository network policy to expose the authenticated
gateway directly on `0.0.0.0:9000`. Role-model inference endpoints remain
loopback-only. Checked-in model defaults, examples, installer/uninstaller,
README, security/operations authority, and systemd tests were updated; the four
obsolete loopback/LAN socket-proxy units were removed.

The live gateway was drained to zero active requests before the proxy sockets
were disabled and removed. The fixed gateway then restarted with one listener,
`0.0.0.0:9000`, PID-owned by `dgx-moa`; no socket-proxy listener remains.
Loopback `127.0.0.1`, LAN `192.168.0.42`, tailnet `100.125.239.72`, and Docker
host `172.17.0.1` each returned health HTTP `200` and Dashboard HTTP `200`.
An unauthenticated LAN `/v1/models` request returned `401`, preserving the
mandatory authentication boundary.

The LAN Dashboard exchanged an authenticated HttpOnly session, returned a
snapshot with all seven roles available and the static-skeleton/request-subgraph
contract, and completed a raw WebSocket upgrade with HTTP `101`, operator scope,
and `current_seq=0`. An authenticated LAN Responses stream returned exact
`BIND_ALL_OK` and terminal `response.completed`. The fixed gateway and Candidate
A were active with `NRestarts=0`. Focused systemd/config/Dashboard tests passed
`45/45`; Ruff, strict mypy, unit verification, shell syntax, and diff checks
passed before the runtime transition.

After the transition, the complete repository suite passed `1064/1064` in
34.18 seconds with only the existing Starlette TestClient deprecation warning.

### Runtime-owned evidence projections and current-source canary — 2026-08-13

An isolated current-source gateway ran on `127.0.0.1:19010` with a disposable
SQLite database while reusing the production model configuration and existing
credentials. No production service, tailnet setting, or role-model endpoint was
changed. Its authenticated Dashboard snapshot reported all seven roles ready:
Reasoner `Qwythos-v2-9B:Q4`, Planner `deepseek-v4-pro`, Frontier A
`gpt-5.6-sol` at `xhigh`, Executor `dgx-moa-executor`, Reviewer
`deepseek-v4-flash`, Judge `kimi-k3`, and Frontier B
`anthropic/claude-opus-5`. The same snapshot reported the four allowlisted
static templates and `static_skeleton+runtime_created_request_subgraph` in
shadow mode.

One authenticated `dgx-moa-orchestrated` architecture request selected
`complex-v1`. The request-created graph placed Reasoner, Planner, Frontier A,
and the evidence-stage Executor in `parallel_0`; the three model evidence nodes
completed with 2,733, 4,582, and 17,013 tokens respectively. Reasoner, Planner,
and Frontier A each received a role-specific projection derived from the exact
same immutable snapshot hash
`4ccb2d10af76e673b2324c1380d4721540ae6cb13c3d0bd5614b8c259c00b03f`.
After all three completed, Runtime created a separate fan-in snapshot hash
`e367181123139ef14f8309df6edcbec5cddcafae9d92c19a72f2e4be897f4dc8`.
Its Executor projection listed the Reasoner, Planner, and Frontier A outputs as
separate `model_contribution:*` categories and named all three source attempt
IDs. All ten graph nodes reached `SUCCEEDED`, and the client-visible output was
persisted in both Dashboard `current_draft` and `final_output` with transport
status `completed`.

The same canary then exercised both streaming adapters. Chat Completions
reconstructed exact `STREAM_CURRENT_SOURCE_OK` from deltas and ended with
`[DONE]`. Responses API reconstructed exact `RESPONSES_STREAM_OK`, emitted
exactly one `response.completed`, and emitted no `response.failed`. Dashboard
persisted the latter draft and final output, six owner-scoped output-delta
events, and `client_response_status=completed`. The isolated graph terminal
was marked degraded only because the unprivileged canary could not write the
production trace archive; every execution attempt itself was `SUCCEEDED`.

Source validation after the evidence-space integration passed the complete
suite `1073/1073`, Ruff, strict mypy over 50 source files, and
`git diff --check`. The canary process was then shut down normally.

### Evidence-boundary correction and loopback Reasoner gate — 2026-08-13

Three independent Round-1 audits rejected the preceding candidate and that
round was discarded. The audits reproduced a partial-delta upstream SSE ending
without a terminal marker being promoted to completion, a Remote Judge package
that reread mutable state after projection, the absence of aggregate context
bounds in the staged index, and the configured Reasoner's use of a native
tailnet Ollama endpoint. None of those findings was waived.

The shared SSE forwarding boundary now accepts clean EOF only after an observed
finish reason; partial EOF raises a backend failure and never promotes
`current_draft` to `final_output`. A composed `/v1/responses` regression test
physically feeds one partial Chat delta followed by EOF and verifies exactly one
`response.failed`, no `response.completed`, empty `final_output`, and transport
status `failed`. Normal current-source streaming returned exact
`FINAL_STREAM_OK`, exactly one `response.completed`, and no failure event.

Canonical snapshots and projections now reject an aggregate encoding above
1,000,000 bytes in addition to their per-item limits. Judge packages are frozen
at the model boundary and independently enforce the same aggregate ceiling.
The Judge package is derived only from the immutable Judge projection:
constraints, criteria, observed tool/failure/policy evidence, Executor draft,
Reviewer findings, diff/test/build metadata, hashes, and attempt provenance are
no longer reread from mutable state after projection. Canonical full snapshots
are persisted with their creation events while active state retains only the
latest copy and bounded manifests. Reviewer and Judge projections now receive
their actual ExecutionGraph target attempt IDs.

The exact `Qwythos-v2-9B:Q4` Ollama manifest and its 6,825,527,040 referenced
blob bytes were copied from the previously validated mathcat runtime into the
local model store without committing weights. A dedicated Ollama instance on
`127.0.0.1:11435` completed a schema-constrained response with `{"ok":true}`
at context 65,536. `ss` reported only the loopback listener, and a LAN request
to port 11435 was refused. With Candidate A and Qwythos loaded, measured
`MemAvailable` was 39,108,018,176 bytes, above the 10 GiB safety floor. The
checked-in Reasoner unit has 12/16 GiB high/max memory limits, 4 GiB swap max,
`OOMPolicy=stop`, an exact local model store, and the loopback bind. The
authenticated gateway remains the only wildcard listener at `0.0.0.0:9000`.

A fresh content-free role validation artifact then passed Planner
`deepseek-v4-pro`, Reviewer `deepseek-v4-flash`, Judge `kimi-k3`, Frontier A
`gpt-5.6-sol`/`xhigh` through Codex OAuth, and Frontier B
`anthropic/claude-opus-5`. The current-source Dashboard consequently reported
all seven requested roles available, including local loopback Qwythos and the
loopback Candidate A endpoint at 19301. A high-risk physical request persisted
successful CLASSIFY, EXECUTOR_SELECT, EXECUTOR, REVIEWER, KIMI JUDGE,
CHECKPOINT, and FINALIZE attempts; its Reviewer projection named the Executor
attempt contribution and its Judge projection independently named the Executor
and Reviewer contributions. Both gates approved.

One architecture canary independently proved identical pre-dispatch snapshot
hash `21711382fa20f4b9cf99a427330f2a6c02e4b5d98f2234c796daff2c1b66ee11`
for Reasoner, Planner, and Frontier A. Reasoner and Planner completed, while
Frontier A hit its bounded provider timeout during concurrent Codex load; the
graph recorded `FRONTIER_PROVIDER_TIMEOUT` and Runtime produced the Executor
fan-in snapshot from the two completed contributions. This is preserved as a
degraded-request result, not a Frontier success claim. The fresh independent
structured role probe and the earlier successful architecture canary remain the
availability evidence.

After all corrections, the complete repository suite passed `1078/1078` in
37.03 seconds with only the existing Starlette TestClient deprecation warning.
Ruff, format check, strict mypy over 50 source files, shell syntax, systemd unit
verification, the frozen-plan checksum, and `git diff --check` also passed.

### Production Frontier spawn-path correction — 2026-08-13

Three authenticated production requests recorded
`FRONTIER_PROCESS_SPAWN_FAILED`. The running gateway process had no
`/home/kotori9/.local/bin` entry in `PATH`; reproducing that exact environment
raised `FileNotFoundError: [Errno 2]` for `codex`. The gateway unit now includes
the installed Codex directory in its explicit service `PATH`.

After unit verification, deployment, and a clean gateway restart, `/readyz`
returned HTTP 200. An authenticated Frontier-required
`dgx-moa-orchestrated` request returned HTTP 200 and recorded
`frontier_collaboration_completed` for `gpt-5.6-sol` through the `primary`
Codex OAuth profile: 15,663 prompt tokens, 702 completion tokens, and measured
Frontier latency 24,886.194 ms. The request recorded no
`FRONTIER_PROCESS_SPAWN_FAILED` event.

### Role Context production epoch and rollback — 2026-08-13

Release `ffdf006a4` passed Ruff/format, strict mypy on 50 source files, and
pytest `1087/1087`. The first production request preserved a real stale-local
Planner failure. The shared specialist boundary now treats an unprovable local
context/readiness probe as unavailable before dispatch, marks the stale state
failed, and selects the already configured remote provider. Focused coverage
passed `119/119`.

The retried authenticated request returned 200. The durable log recorded one
pre-dispatch snapshot shared independently by Reasoner, Planner, and Frontier A,
then a distinct fan-in snapshot for Executor. Frontier A completed through
Codex OAuth `primary` using `gpt-5.6-sol` with 15,819 prompt and 966 completion
tokens in 24,569.716 ms. `complex-v1` persisted 10 successful attempts and 21
checkpoints with no client-visible provider provenance.

Fresh structured probes passed Planner, Reviewer, Judge `kimi-k3`, Frontier A,
and Frontier B; live endpoint probes and the successful request covered
Reasoner and Executor. Dashboard reported all seven available and the exact
static-skeleton/runtime-subgraph contract. A prior v1 probe using the stale
`glm-5.2` override failed Judge and remains rejected evidence; v2 hash is
`06abb808412bcb446f016ee7c4a37b1da2b2963931a83338acab68025e2c8fe3`.

Rollback physically checked out `88f553dec`, restarted, and passed an
authenticated canary at PID 2985632. Redeploy to `ffdf006a4` passed the same
content hash at PID 2985816 with restart 0. A separate high-risk request did
not pass: Reviewer rejected insufficient evidence, Judge and Frontier B ran,
but correction exceeded 300 seconds and finalized failed. This is a preserved
long-path latency/termination gap, not a success claim.

### Pilot feedback closure — 2026-08-13

Runtime release `fd658a1e8` closes that gap and three real-use failures:
non-stream cancellation reaches the owner task, terminal usage cannot overwrite
a verdict, Flash overflow requires public content, and the final allowed loop
iteration records `BUDGET_EXHAUSTED`. The final high-risk production canary
returned exact `CRITICAL_FINAL_OK`; Frontier A `gpt-5.6-sol`/Codex OAuth
completed in 14,808.631 ms, Reviewer approved, and Judge approved. Rollback to
`90e838742` and redeploy produced an identical authenticated canary hash. Full
details are in `docs/DYNAMIC_MOA_PILOT_FEEDBACK_EPOCH_20260813.md`.

The final deployed-code canary additionally persisted
`blocked/BUDGET_EXHAUSTED` after completed iteration 1. Frontier A completed in
21,458.606 ms and Reviewer/Judge each approved once; the HTTP request itself
returned 200. Gateway restart count remained zero.

### Reviewer/Flash role correction — 2026-08-13

Operator clarification establishes Reviewer as OpenCode Go `glm-5.2` and
DeepSeek V4 Flash as Executor-only overflow/fallback. The production override,
checked-in defaults, and active-validation contract were corrected together.
Older DeepSeek Reviewer measurements remain historical observations and are not
current topology authority.

The first full gateway request selected `glm-5.2` correctly but failed closed
after two `invalid_structured_output` results. A content-free parameter matrix
identified the root cause: `thinking.disabled`, `reasoning_effort=low`, no
control, and `enable_thinking=false` all returned empty public content with only
reasoning output; `reasoning_effort=none` returned public JSON. Runtime release
`a1ea6d7b2` applies only that GLM Reviewer correction.

The fresh five-role structured artifact at production
`data/run/role-validation.json` has SHA-256
`8a7dae0bc1eb7b97e2a57999e91ca59240293ba494e5485e08d0cf72bb7e2773` and
passes Planner `deepseek-v4-pro`, Reviewer `glm-5.2`, Judge `kimi-k3`, Frontier
A, and Frontier B. Authenticated session
`prod-reviewer-glm-public-final-20260813` returned HTTP 200; its durable state
records Reviewer `glm-5.2`/OpenCode Go completed in 1,275.51 ms with 2,791/10
tokens and approved, while Executor remained `dgx-moa-executor`. Dashboard
reports all seven roles available. Gateway restart count is zero. Ruff, format,
strict mypy over 50 source files, focused tests `36 passed`, and the complete
suite `1092 passed` all succeeded.

Runtime release `269313420` closes the remaining explicit-disable mismatch.
Focused API/scheduler tests prove `local_unavailable` selects OpenCode Go Flash
for low/medium risk while high risk fails closed; the complete suite passed
`1094`. After production deployment, an isolated call using the deployed
scheduler and protected provider selected `opencode_go`, reason
`local_unavailable`, model `deepseek-v4-flash`, and returned 17 public bytes
with SHA-256
`0ce5802a580738ec0a4d6d0e752cb5cfbcde384e8af8942a2af3cb7fc1bd6a34`.
The production Executor was not stopped. A subsequent authenticated local
canary returned HTTP 200; the gateway remained active with restart count zero.

The Codex harness regression at 15:04 KST was not a Frontier result: six
client requests arrived at `/v1/responses` with the stale model name
`gpt-5.5` and failed with `invalid_request`/404. The operator clarified the
current contract as `gpt-5.6-sol` with `high` reasoning. Both checked-in
Frontier configs and the production override now use that exact pair. After
the fixed gateway restart, authenticated `/v1/admin/frontier-auth` returned
`model=gpt-5.6-sol` and `reasoning_effort=high`; the service was active on
`0.0.0.0:9000` with restart count zero. Config parsing and
`test_frontier_config` passed. A direct CLI canary was intentionally rejected
before model invocation because the safety boundary requires a registered
isolated `frontier/*` worktree; it is not evidence of an inference failure.

The external Codex custom-provider model is `dgx-moa-orchestrated`; internal
Frontier A remains `gpt-5.6-sol`/high and is not a gateway client model. With
the external model set correctly, production Responses session
`prod-harness-stream-fix-20260813` emitted `HARNESS_STREAM_OK` and a terminal
`response.completed`. Frontier OAuth failover now covers auth, usage, rate,
busy, timeout, and provider-unavailable failures across the configured
`primary`, `secondary`, then `default` profiles. If all Frontier profiles are
unavailable, ordinary orchestration continues with available roles at low
derived confidence; only an explicit policy `frontier_required=true` remains
fail-closed. Ruff and format checks passed, and the full suite passed `1096`.

The first public post-deploy canary then exposed an independent Planner HTTP
failure: the older controller degraded optional malformed Planner output but
still propagated optional transport and timeout failures. That shared boundary
now degrades every optional Planner failure, records `planner_degraded`, and
continues to the Executor; high-risk mandatory Planner requests remain
fail-closed. Focused API tests passed `7`, and the complete suite passed `1097`.
Production release `f28f879` then returned exact `PUBLIC_HARNESS_OK` through
`https://aipi.kotori9.dev/v1/responses` with terminal `response.completed` for
session `prod-public-harness-final-v2-20260813`. The gateway remained active
with restart count zero.

The pre-cleanup authenticated `/v1/models` response advertised five historical
aliases and hard-coded every context to 65,536. Direct Candidate A evidence
reported `dgx-moa-executor` with `max_model_len=131072`, matching the checked-in
Executor configuration and running vLLM command. The catalog now derives its
context from that runtime configuration and exposes only the production
`dgx-moa` and Executor-only `dgx-moa-fast` aliases. Historical input aliases
remain accepted only for existing continuation compatibility and are not
discoverable. Ruff, format, focused catalog tests `17 passed`, and the complete
suite `1097 passed` succeeded before deployment.
After production deployment, authenticated `https://aipi.kotori9.dev/v1/models`
returned exactly `dgx-moa` and `dgx-moa-fast`, each with context 131,072 and
`comp_hash=dgx-moa-131072-v1`; the retired public aliases returned no matches.
The loopback vLLM model endpoint independently reported
`dgx-moa-executor/max_model_len=131072`. Public Responses session
`prod-canonical-model-catalog-20260813` returned exact `CANONICAL_MODEL_OK` and
terminal `response.completed` using `model=dgx-moa`. Gateway restart count was
zero.

At 15:53 KST the Codex 0.147.0 client fetched the canonical catalog but still
sent six Responses requests with its stale default `model=gpt-5.5`; every one
ended in `response.failed` after the gateway's internal 404. The authenticated
gateway now normalizes that exact unadvertised harness fallback to `dgx-moa`,
returns the canonical model name, and records `client_model_fallback` with both
names. Near matches remain rejected, and `gpt-5.5` is not advertised. Focused
tests passed `3`; the full suite passed `1098` before deployment.
Production session `prod-stale-codex-model-recovery-20260813` then sent the
observed stale `model=gpt-5.5` through the public Responses endpoint. The stream
identified `model=dgx-moa`, returned `STALE_MODEL_RECOVERED.`, and ended with
`response.completed`; durable state recorded `client_model_fallback | gpt-5.5 |
dgx-moa`. Gateway restart count remained zero.

### Qwythos structured-output recovery — 2026-08-13

The failed Codex session `ecf09e1a-e87d-49f9-a9f0-15d29a050666` was traced on
the external `mathcat` host. Ollama accepted a 64,919-token Reasoner prompt in a
65,536-token slot, generated only the remaining 617 tokens, and logged
`truncated=1` on both attempts. The resulting incomplete JSON caused the two
gateway `JSONDecodeError` events and the `gpt-5.6-sol` Reasoner fallback; the
Qwythos process itself did not fail.

Production release `98be5de` extends projection trimming to oversized request
input history after preserving bounded Evidence and contributions, dropping the
oldest inputs only when the immutable snapshot still exceeds the role target.
The original failing snapshot now projects to 84,361 bytes rather than 217,836
bytes. The complete suite passed `1099`; focused projection/API tests passed
`255` after correcting Reasoner provider telemetry to report the actual
configured provider.

Oversized production session `qwythos-fix-20260813-1645` projected the Reasoner
context to 92,681 of 98,304 bytes. The external server measured a 12,918-token
prompt, generated 760 tokens, and logged `truncated=0`; no structured retry or
Frontier fallback occurred, and the client received exact `QWYTHOS_FIXED`.
Final session `qwythos-direct-final-20260813` durably records
`reasoner_started` and `reasoner_completed` with provider `ollama`, model
`Qwythos-v2-9B:Q4`, zero retry/unavailable/fallback events, and exact
`QWYTHOS_DIRECT_OK`. The authenticated gateway remains active with restart
count zero.

### Executor synthesis recovery — 2026-08-13

The repeated Codex session `9061b378-b096-4b19-8caf-348fc67f0a8b` confirmed
that Qwythos completed directly without fallback, but final synthesis received
a 120,186-token Executor prompt and returned only two completion tokens,
`arab`, with `finish_reason=stop`. The Responses translator accurately carried
those bytes; the failure was duplicated harness context in both the direct
message history and Runtime projection, followed by acceptance of a degenerate
near-context-limit completion.

Production release `bc56beb` deduplicates system, developer, and user messages
semantically while ignoring transient Responses IDs, applies the same rule to
role projections, and retries an unrequested four-token-or-shorter completion
when input usage is at least 85% of the physical Executor context. Explicitly
requested short outputs remain valid. The failed snapshot now contains four
direct messages rather than 16 and an 80,315-byte Executor projection rather
than 233,520 bytes. Ruff and focused tests passed `81`; the complete suite
passed `1103`.

Production replay `executor-tool-recovery-20260813` used the original 16 Codex
inputs. The first turn used 37,804 prompt tokens and emitted a proper
`exec_command` function call. Its tool-result continuation used 27,694 prompt
tokens and 36 completion tokens, returned one final message with an 88-character
Korean explanation, and emitted no further tool call. The gateway remained
active with restart count zero.

### Client workspace inspection recovery — 2026-08-13

Codex session `667a0b4f-f231-460a-bba7-fb2e8b5a8dfb` carried the client cwd
`/Users/choiyunhyuk/Documents/Playground` inside its environment context and
advertised `exec_command`, but emitted a Bash code block rather than a function
call. No filesystem access was attempted; the gateway's repository identity
remained `external-api` because Codex did not send the optional workspace
header. Client-owned tool execution does not require that path to exist on the
gateway host.

Production release `85b5361` requires tool evidence for `dgx-moa` workspace,
project, repository, platform, directory, or folder inspection/evaluation
requests until one successful client tool result exists. General questions and
the Executor-only `dgx-moa-fast` compatibility path retain `tool_choice=auto`.
Ruff and focused controller/API/streaming tests passed `416`; the complete suite
passed `1103`.

Production session `workspace-tool-required-20260813` replayed the actual Codex
inputs. The first response emitted an `exec_command` function call for
`ls -la /Users/choiyunhyuk/Documents/Playground`. After a tool result showing
the `rust-mcu-ide` directory, the continuation emitted a second
`exec_command` for a bounded file listing inside that directory instead of
claiming it was unavailable. Durable events record two `tool_calls` finishes,
and the gateway remained active with restart count zero.

### Korean mixed-script output recovery — 2026-08-13

The same failed workspace response mixed unrequested Han characters and
Japanese kana into Korean prose despite the prompt-level Korean-only contract.
Production release `9d4045b` adds a Responses terminal validator: for a Korean
objective, unrequested Han, hiragana, or katakana outside fenced and inline
code causes the buffered answer to be discarded and retried up to the existing
bounded retry limit. The retry has a dedicated Korean-only instruction and
durable `language_mismatch_response_retried` event. Foreign script explicitly
present in the objective or required inside code remains allowed.

Ruff and focused API/streaming tests passed `308`; the complete suite passed
`1107`. Production session `korean-script-validation-20260813` ended with
`response.completed`; its Korean two-sentence answer contained zero Han,
hiragana, or katakana characters outside code. The gateway remained active
with restart count zero.

### Codebase evaluation evidence recovery — 2026-08-13

Codex session `419d915b-9788-4e3e-9f1d-4c07d8c9b871` completed a platform
evaluation after directory listings and a README read. Its filtered `find`
returned only `README.md`, but the Executor treated README claims as verified
implementation and produced a positive functionality assessment without source,
build, or test evidence.

Production release `751f586` derives response language from the current user
objective while keeping role reasoning in English. For codebase evaluation it
now requires a bounded inventory or target-directory traversal plus reads of
discovered implementation and available tests or build configuration. README
alone cannot satisfy the completion gate; a genuinely documentation-only
inventory permits only an explicit implementation-unverified conclusion.
Related tool calls are batched where dependencies allow. Client-visible progress
guidance asks for one substantive five-to-seven-line phase summary instead of a
generic sentence per command; it is not a total-output limit.

The complete suite passed `1109`. Authenticated production session
`codebase-evidence-canary-v3-20260813` used synthetic client-workspace results
to isolate the orchestration contract. It recorded nine successful
`exec_command` executions: three bounded directory listings, `rg --files`, and
parallel reads of README, Cargo configuration, two Rust sources, and one test.
The runtime did not finalize after README; it finalized only after source and
verification evidence, with `finish_reason=stop`, a 613-character Korean
assessment, one direct Qwythos Reasoner completion, and no language retry or
Frontier fallback. The gateway remained bound to `0.0.0.0:9000`, active with
restart count zero.

The progress-length requirement was subsequently clarified as a quality rule,
not a total-output cap. Production releases `5bce20a` and `563dc3e` remove the
Responses translator's generic per-command placeholder, preserve substantive
model commentary, and otherwise derive a concrete description from the actual
tool and target. The complete suite passed `1111`. Authenticated streaming
session `substantive-progress-canary-v2-20260813` called `ls -la` and emitted
`현재 작업 디렉터리의 파일 구조를 확인해 실제 평가 대상을 정합니다.` before the
function call; the rejected generic sentence did not appear. The request ended
with `response.completed`; the gateway remained active with restart count zero.

### API key dashboard recovery — 2026-08-13

The dashboard now exposes newly created or rotated API key plaintext once in a
read-only field with an explicit copy action; persisted keys remain masked and
unrecoverable. Usage charts filter historical invocation rows against the
runtime's active role/model catalog rather than displaying retired models.

Focused API-key and usage tests passed `42`. After production restart, the
authenticated catalog contained Qwythos Reasoner, OpenCode Go Planner/Reviewer,
Kimi Judge, resident Executor, Executor Flash, and Codex OAuth fallback roles.
An authenticated historical sample retained its raw rows while the chart filter
excluded `dgx-moa-executor-candidate` and the retired Reviewer use of
`deepseek-v4-flash`. The gateway was active and bound to `0.0.0.0:9000`.
An authenticated live canary then created a one-day general key, received its
plaintext once, used it successfully against `/v1/models` (`200`), and removed
it through revoke/delete (`200`/`204`); the temporary key count returned to zero.

### Bounded codebase-evaluation recovery — 2026-08-13

Reported session `b1e4c7d1-1c5e-4e77-9e09-ba2a3e34a11a` took 44 Executor
steps and 16 tool results. The runtime failed to recognize `git -C <target>
ls-files` and compound source reads as complete evaluation evidence, treated
temporary output files as implementation completion, allowed read-only scope to
expand into project generation/stash/delete attempts, and eventually returned
an incomplete Responses stream after repeated language/progress retries.

The evaluation path now promotes a single-directory `ls` to a complete tracked
inventory, distinguishes recorded inventory from pending source/test evidence,
suppresses tools as soon as both are present, and never treats evaluation output
files as implementation completion. Read-only evaluations reject mutation and
pure output tool calls. Mixed-language tool commentary and internal provider
tokens are replaced or retried before reaching the client.

The full suite passed `1126`. An official Codex CLI canary used the exact Korean
objective against a four-file synthetic `rust-mcu-ide` Git repository. Session
`3c92d70a-e921-47ca-8781-99b6a1566af8` completed with four Executor steps and
two successful tools: one `git ls-files` inventory and one batch source/test
read. One local language mismatch was caught and routed to Codex OAuth Frontier;
the client received a concise Korean verdict followed by `turn.completed`, with
no reconnect or workspace mutation. The production gateway remained active on
`0.0.0.0:9000` with restart count zero.

### Operator Executor ON/OFF dashboard — 2026-08-14

The authenticated admin Dashboard now drives the existing fixed/adaptive
lifecycle coordinator instead of a second service-control path. A focused
integration test physically exercised the fake driver's exact stop/start:
OFF persisted Executor state `disabled`, a low-risk request completed through
the pinned `deepseek-v4-flash` provider without reloading Mistral, and ON
returned to `ready`. The status projection exposed generation, lifecycle
state, weight progress, progress quality, overall phase progress, and ETA;
unknown weight progress remained `null` until trustworthy evidence existed.

Lifecycle and admin Dashboard tests passed `265`; administrator-boundary and
disabled-local Flash routing tests passed `43`. Ruff passed for all touched
Python files, strict mypy passed for `lifecycle.py` and `api.py`, and the full
suite passed `1136`. These are isolated test results only; no production
service was stopped, started, or reconfigured by this validation.

The high-risk OFF-state route was then changed from local-only rejection to the
existing Codex OAuth Frontier Executor. A focused test held local Executor
unavailable, classified an authentication change as high risk, completed it
through `gpt-5.6-sol`, recorded routing reason
`local_unavailable_high_risk`, and made no local model call. Flash remained the
low/medium-risk route. Frontier failure remains typed fail-closed. Focused
routing and remote-failure tests passed `3`; Ruff and strict API mypy passed,
and the full suite passed `1139`. No production mutation was performed.

### Batched general workspace execution — 2026-08-14

General repository work now normalizes bare or filtered file discovery to one
tracked-file inventory, batches independent source/test reads named by that
inventory, suppresses Executor `update_plan` duplication unless planning was
explicitly requested, and rejects an exact successful inspection repeated
before a file change. Single-command tool UI narration is empty unless it adds
batch or prerequisite context. Existing Python tests replace ad hoc inline
assert scripts, while repeated three-word synthesis phrases are stopped after
six occurrences and routed through the existing quality fallback.

The final full suite passed `1145`. Production commits through `c6df9d2` were
deployed to the fixed gateway. Official Codex CLI thread
`019ffbf9-009f-7de1-856d-5f8857738a8c`, gateway session
`ed851517-0c35-42f2-99ed-359eb941ff33`, completed the synthetic `add` bug fix
with exactly four successful tool executions: one `git ls-files` inventory,
one compound `app.py` plus `test_app.py` read, one `apply_patch`, and one
`python -m pytest -q` run (`1 passed`). It emitted `turn.completed`; the trace
contains no response retry, remote Executor selection, or aborted stream.
Planner and Reviewer completed normally, including one bounded Frontier
collaboration artifact; this was not an Executor fallback.

The final service process was PID `235390`, active with `NRestarts=0`, bound to
`0.0.0.0:9000`. `/v1/models` returned `401` without authentication and `200`
with the production bearer credential. One intermediate manual restart hit the
configured systemd start-rate limit after repeated deployment restarts; the
rate-limit latch was reset, and the same checked-in service then started and
passed the checks above.

### Runtime completion 재감사 기준선 — 2026-08-14

기존 완료 표시는 사용하지 않고 clean `dev@43826ccee`와 실제 fixed gateway를 다시
측정했다. Production checkout과 실행 프로세스는 clean `main@59bcb54e5`였고
`ffdf006a4`, `fd658a1e8`, `a1ea6d7b2`, `269313420`, `90e838742`를 모두 포함한다.
Gateway는 PID `235390`, restart `0`, `0.0.0.0:9000`이며 unauthenticated
`/v1/models`는 `401`, authenticated health/models/ready는 모두 성공했다. Candidate A만
`127.0.0.1:19301`에 bind됐다.

Git 기준선은 local branch `13`, registered worktree `10`, stash `5`다. Root local
`main@60921c3f3`은 fetched `origin/main@59bcb54e5`보다 `37` commit 뒤이고,
`origin/main...dev`는 `47/42`로 갈라져 있다. Production checkout은
`origin/main@59bcb54e5`와 일치한다. 고유 commit 수는
`archive/local-main-before-normalization=1`, `auto/controller/IMP-2026-0001=1`,
`auto/evaluation/frontier-noninferiority-v1=2`, `auto/integration/sglang-topology-v1=9`,
`auto/runtime/sglang-gemma4-v1=294`, `codex/pre-rebase-dynamic-moa=2`이며 삭제하지 않았다.

실제 production DB의 content-free 집계는 canonical snapshot `279`, role projection
`297`, ExecutionGraph `164`, attempt `797`, checkpoint `1998`, tool request `3632`,
stream complete/abort `3270/96`, review `232`, Judge `7`이다. 일곱 projection role이
모두 존재하지만 기존 invocation `5402`건 중 `provider_prompt_tokens` 명시 기록은
`0`이었다. 기존 projection은 `reasoner`에서 evidence `9`건을 drop했지만 이유를
저장하지 않았다. 따라서 Role Context 전달은 `PARTIALLY_WIRED`로 재분류했다.

Production override는 현재 repository policy와 달리 Loop Engineering, Runtime
Skills/Knowledge/Evolution, training, weekly jobs를 enable한다. 이 차이는 삭제하거나
현재 권위로 재해석하지 않았고 production 변경 승인 전까지 policy/security finding으로
보존한다. 현재 key 집계는 active environment admin `1`, environment general `3`,
managed general `3`; evaluation-scoped short-TTL kind는 production에 없다.

격리 branch `auto/audit/runtime-completion-20260814`는 단순 순서 기반 evidence drop을
관측 순서가 있는 deterministic priority selector로 교체하고 snapshot/projection/rendered
prompt/provider prompt token/drop reason을 기존 state manifest에 기록한다. 기존 operator
key API에는 5분 이상 short-TTL `evaluation` kind와 Chat/Responses/model-list allowlist를
추가했다. Raw token은 한 번만 반환되고 SQLite에는 hash/mask만 남으며 revoke 직후
`401`이 되는 테스트를 추가했다. 누락된 CI는 formatting, Ruff, strict mypy, full pytest,
schema JSON을 강제한다. Candidate 결과는 Ruff/format/schema/workflow PASS, strict mypy
`51` source PASS, full pytest `1146` PASS다. 이 증거는 isolated source validation이며 아직
배포·실 client matrix·canary·rollback 승인이 아니므로 상태는 `IN_PROGRESS`다.

같은 candidate source를 isolated SQLite와 loopback `127.0.0.1:19001` gateway로
실행하고 기존 live-client smoke harness를 재사용했다. Raw Chat과 primary `dgx-moa`,
Codex Responses, OpenCode, Hermes가 모두 성공했고 Executor invocation `6`, Reasoner
invocation `1`이 기록됐다. 네 client는 각각 다른 5분 evaluation key를 사용했다.
모든 key는 DB에 plaintext 길이 `0`, hash 길이 `64`로 저장됐고 종료 전에 revoke된 뒤
각각 `/v1/models` `401`을 반환했다. Candidate DB의 Executor projection/invocation
`6/6`, Reasoner `1/1` 모두 snapshot/projection/rendered prompt bytes와
`provider_prompt_tokens`를 기록했다. `19001` listener와 raw client artifact는 제거됐고
production checkout/hash와 `:9000` health는 변하지 않았다. 이 batch는 protocol/key
lifecycle smoke이며 아직 3~5개 coding-task batch 결과가 아니다.

Codex coding batch v1의 첫 `rate-limiter` task는 Runtime verdict 전에 중단했다.
Docker image `python:3.11-slim`에 `git`과 `rg`가 없어 required inventory call이
반복해서 exit `127`이 됐고 recovery 중 잘못된 workspace 철자까지 생성됐다. 분류는
`HARNESS`; 다른 네 task는 시작하지 않았다. Interrupt 뒤 exact child/container를
종료했고, gateway가 먼저 내려가 admin revoke를 수행할 수 없어서 stopped isolated DB의
hash-only key를 직접 revoke했다. Production listener/state에는 접근하지 않았다.

수정 hypothesis는 "fixture가 명시한 Git/ripgrep tool contract를 제공하면 같은 task가
정상 inventory→source/test→implementation→validator 경로로 진행한다"다. 새 image를
빌드하거나 내려받지 않고 기존 local quality image
`sha256:324178f308d1fd4385a0ab8b3f5a9d1ba68f831afc7139f249eade9dfaf385b5`
를 pin했다. 이 image의 Git `2.47.3`을 확인했고 pinned Codex ripgrep `15.2.0` binary를
read-only `/tools/rg`로 mount했다. 다음 epoch는 새 fixture hash/run ID에서 failed task를
먼저 replay한다.

Codex coding batch v2는 같은 `rate-limiter` task에서 Git/ripgrep inventory, source/test
read, 실패하는 초기 unit test, patch 적용 복구, 최종 unit test 성공까지 진행했다. 즉
v1의 tool-image hypothesis는 물리적으로 확인됐다. 그러나 구현 증거가 생긴 뒤 Runtime이
요구한 Reviewer를 격리 launcher가 무조건 disable했고 local Reviewer도 실행 중이 아니어서
`review_status=failed`와 client cancellation로 끝났다. 중간 Reasoner JSON decode 실패
한 건은 `RESOURCE` 증거로 보존했으며 이후 Reasoner 호출은 복구됐다.

v2도 candidate 품질이 아닌 `HARNESS` 실패다. 아직 보지 않은 두 task는 시작하지 않았다.
정확한 child/container를 종료하고 stopped isolated DB의 evaluation key를 직접 revoke했으며
production listener/state는 변경하지 않았다. 다음 replay는 launcher 기본값을 계속 disabled로
유지하되 명시적인 `--specialists-enabled`에서만 기존 provider 설정을 사용한다. Gateway
process에만 물리 검증 대상 OpenCode Planner/Reviewer credential을 제공하고 client Docker에는
core environment와 client별 evaluation key만 전달한다. Production DB, `.env`, Hermes
credential은 mount하거나 전달하지 않는다.

Codex coding batch v3는 새 isolated DB와 loopback `127.0.0.1:19002` gateway에서
`--specialists-enabled`를 명시해 v2의 failed task를 replay했다. Evaluation key는 models
`200`, admin/metrics `403` 경계를 통과했다. Client Docker는 pinned image와 Git/ripgrep,
Codex binary, workspace/state만 mount했고 `DGX_MOA_API_KEY`만 전달받았다. Production DB와
provider credential은 전달하거나 mount하지 않았다.

`rate-limiter` client는 `1091.024`초 뒤 exit `0`과 Korean terminal을 반환했고 공개 unit
test, source-only change, test immutability와 tool evidence를 통과했다. 그러나 hidden validator는
생성 코드의 `float.is_finite()`에서 `AttributeError`로 실패했다. Client log에는 두 번의
`stream disconnected before completion` reconnect가 남아 `no_bad_terminal=false`였다.
따라서 deterministic verdict는 `failed`다. 다음 unseen task는 시작하지 않았다.

v2의 Reviewer availability hypothesis 자체는 통과했다. OpenCode Go Reviewer는 remote provider로
invocation `21`건을 모두 completed했고 review cycle `12`, structured retry `9`를 기록했다.
하지만 같은 diff에서 rejection과 progress retry `10`, stream abort `11`이 반복됐고 hidden defect는
수정되지 않았다. Raw remote review output은 Git에 기록하지 않았다. 현재 분류는 생성 결함
`MODEL_CAPABILITY`, review→correction 비수렴 `LOOP_CONVERGENCE/TOOL_SEMANTICS` 후보다. 아직
한 task/client의 증거이므로 Runtime 수정은 보류하고 별도 client/task 재현 기준을 유지한다.

이 epoch의 물리 Role Context 집계는 다음과 같다. Executor projection `31`건은 snapshot
`11093..48055` bytes, projection `11860..49580`, rendered prompt `19796..57852`, provider
prompt tokens 합계 `233476` (`6718..18139`)다. Reasoner `7`건은 각각
`10289..40361`, `10953..42357`, `14315..46119`, 합계 `58362` (`3440..13287`)다.
Reviewer projection `12`건은 각각 `61020..75394`, `54080..63098`,
`60755..69868`; provider invocation `21`건의 prompt token 합계는 `245064`
(`3913..18662`)다. 모든 projection은 objective/original input/request constraint와 해당 시점의
tool/failure evidence를 포함했고 dropped evidence는 `0`이었다.

Evaluation key는 종료 전에 revoke `200`, 이후 models `401`을 반환했다. Isolated DB record는
kind `evaluation`, plaintext length `0`, hash length `64`, revoked true이고 DB/WAL에서 raw key가
검출되지 않았다. Gateway exit는 `0`, port `19002`와 container는 해제됐고 production health는
`200`, production checkout은 clean `main@59bcb54e5`를 유지했다.
