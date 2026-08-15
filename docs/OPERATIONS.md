# Operations

## Dynamic MoA operational boundary

Current operations follow `docs/STATE.md`. The fixed authenticated Gateway is a
`PILOT_ACTIVE` release on `0.0.0.0:9000`; the overall project is
`IN_PROGRESS`. The operator intentionally stopped the local Executor, so the
active low/medium-risk Executor path is the reviewed
`opencode_go/deepseek-v4-flash` fallback. Lifecycle is fixed and maps only the
Executor service; ExecutionGraph, specialist routing, and Remote Judge remain
disabled. Dashboard ON/OFF controls the loopback Executor on port `9001`.

The public catalog reports context `131072`. If the local candidate is later
approved for reactivation, its checked-in target is the qualified fixed-revision
131K/seq1/3.4-GB-KV B12x profile. Phase 3 65K/1.7-GB-KV MARLIN remains the
preserved rollback baseline. Neither inactive local profile is the current
production provider.

Before starting the checked-in Executor for a Pilot, verify the unit resolves
`MemoryHigh=12G`, `MemoryMax=16G`, `MemorySwapMax=4G`, `OOMPolicy=stop`, and
`KillMode=control-group`. A qualification service must use its own capped slice.
Do not run an uncapped compiler/kernel challenger in `app.slice`: v64 proved
that a global user-session OOM can kill the gateway and user manager. The
physical containment record is
`data/diagnostics/pilot/pilot-v1-transition-20260812/containment-result.json`.

The primary model alias is `dgx-moa`; it uses the external Qwythos Reasoner and
local Executor. `dgx-moa-fast` is the explicit Executor-only compatibility
alias. Do not silently reroute a failed default Reasoner request to fast mode.

`dgx-moa-fast` must remain Executor-only even when a continuation contains
implementation, changed-file, validation, or tool-result evidence. Audit
`request_usage.runtime_mode=fast`, `roles_required=["executor"]`, and the exact
request event window; any Reviewer, Frontier, or remote-Executor selection is a
contract regression. Use exact service stop/start for isolated gateway rollback;
do not alter candidate A or the production gateway for this compatibility path.

The deployed Frontier uses an existing Codex OAuth profile and read-only
`codex exec`; no OpenAI API key is configured. The current development config
instead connects through `codex app-server proxy` to an operator-managed,
profile-specific persistent daemon. It starts/resumes non-ephemeral read-only
threads, compacts after eight completed turns, and stores only a hashed
API-key/session scope plus the opaque thread ID in a mode-`0600` bounded state
file. The gateway never starts or stops the daemon. It falls back to stdin
`codex exec` only when the proxy reports typed App Server unavailability.
Authentication, usage-limit, and timeout failures do not trigger that transport
fallback. Enablement still requires both the gateway feature gate and a
reviewed Frontier config. Safe checked-in defaults remain disabled. See
`FRONTIER.md`.

The 2026-07-21 production deployment passed that gate and enables Frontier.
Current failover order is isolated `primary`, isolated `secondary`, then the
host `default` Codex OAuth profile. A new request arriving while the local
Executor already owns an active lease is pinned to this remote logical-Executor
path; Frontier cannot execute host tools and may only return client tool calls
through the authenticated gateway. When all OAuth profiles fail for an approved
mandatory call, the optional OpenRouter Claude fallback is attempted at most
once per correlation ID. It requires a valid ignored `openrouter_api` file with
mode `0600`; missing or rejected credentials fail closed. Safe gateway defaults
remain disabled; production enablement stays in the ignored 0600 environment
file.

Gateway authentication may use legacy `DGX_MOA_API_KEY` or the preferred JSON
mapping `DGX_MOA_API_KEYS`, whose keys are non-secret usage IDs. Rotate values
outside Git. `/v1/runtime-status` exposes content-free aggregate usage by ID.
The production IDs are `legacy`, `opencode`, `hermes`, and `operator`; never put
their values in Git, logs, traces, or documentation.

When the admin API is enabled, `DGX_MOA_ADMIN_TOKEN_IDS` selects the configured
keys that initially receive administrator authority. General keys can call only
the authenticated AI API. Administrator keys can also open `/admin/api-keys`
and call `/v1/admin/api-keys`; `DGX_MOA_MAX_ADMIN_API_KEYS` bounds active
administrator keys. The operator UI supports named creation, one-time value
return on creation or rotation, expiry, revocation, cumulative request/token
limits, and content-free request-class/model usage charts filtered by key and
date. Existing values are never revealed. It also renders
measured model tokens as an OpenCode-style daily stacked bar chart; it does not
estimate cost when invocation-level cost is unavailable.

The key registry stores only a one-way credential digest, an empty legacy
column tombstone, and a display mask. Its database mode is forced to `0600`;
responses use `no-store`, and management events contain names/actions but no
key values. Login exchanges the operator credential for a hashed server-side
session and a 30-day HttpOnly, SameSite-Strict cookie; the raw credential is
not kept in browser storage. A limit reached response is `429`; expired or
revoked keys receive the same `401` as an unknown key.

`/admin` is the operator landing page. It links to API Key Control and includes
an independent Codex CLI client configured against the loopback gateway as a
Responses custom provider. Chat mode is read-only. Agent mode is
`workspace-write`, accepts only a selected Git workspace whose resolved path
remains below `~/code`, keeps tool network access disabled, and serializes turns
through one gateway-local lock. Codex sessions use a separate ignored
`CODEX_HOME` below `data/run`; browser-held session IDs can resume only the same
mode and workspace until the gateway restarts.

The client lazily creates `admin-codex-cli` as a general, never-admin API key
with a 365-day expiry, 10,000-request limit, and 100,000,000-token limit. The
provider key exists only in the Codex process environment; Codex tool
subprocesses inherit only core non-secret environment names. The UI and safe
NDJSON adapter expose final agent messages, command names/status, file-change
status, and token usage, but not reasoning items or raw command output.
Because no plaintext recovery path exists, the managed key is rotated into
process memory on first use after a gateway restart.

For isolated Codex Responses qualification, do not treat SSE comment
keepalives (`: keep-alive`) as proof of client continuity. Codex 0.146 can
reconnect with `idle timeout waiting for SSE` while those comments are flowing,
and can then report `stream closed before response.completed`. Acceptance
requires a zero-reconnect client trace ending in exactly one
`response.completed`; public and hidden fixture success alone is insufficient.
Named `event: ping` frames must also be emitted immediately from both the outer
Chat wait and the inner Responses translation loop. If inner pings are appended
to the translated terminal buffer, short requests can pass while long tool
continuations still disconnect around the client idle boundary.

## Gateway and systemd

```bash
scripts/install-systemd-user.sh
systemctl --user status dgx-moa.target
journalctl --user -u dgx-moa-gateway.service -f
scripts/healthcheck.sh
```

### Superseded limited Pilot endpoint (historical evidence)

This `:19000` transient was an earlier Pilot validation epoch. It is not the
current public endpoint or runtime authority; use the authenticated fixed
`:9000` Gateway described above. The commands below remain rollback evidence
for that isolated transient only.

The last qualified limited Pilot canary was release
`2a3afdce826b7fbc4e5cf3d682085b427ebcfa22`, transient unit
`dgx-moa-pilot-v1-release-attempt12.service`, and authenticated tailnet endpoint
`http://100.125.239.72:19000`. On 2026-08-15 the superseded transient was
stopped through the exact rollback below and collected; `:19000` now fails
closed while production `:9000` remains healthy. It had exactly one key ID,
`pilot`. The key value
is not in Git or unit metadata; systemd receives it through `LoadCredential`
from the mode-0600 volatile file
`/run/user/1000/dgx-moa/pilot-v1/pilot_api_key`. Do not print, copy into shell
history, or move that value into a repository file.

The Pilot gateway was capped at 1 GiB high, 2 GiB max, and 512 MiB swap max. It
used the preserved Candidate A listener on loopback 19301, durable state at
`~/.local/share/dgx-moa/pilot-v1/state.db`, shadow ExecutionGraph, DeepSeek V4
Flash overflow availability, and the `pilot-v1` destructive-operation approval
policy. Runtime Skills, Knowledge, Evolution, training, weekly jobs, remote
Judge, and observation controls remain disabled.

Exact Pilot rollback is scoped to the transient gateway:

```bash
systemctl --user stop dgx-moa-pilot-v1-release-attempt12.service
curl --connect-timeout 1 http://100.125.239.72:19000/healthz  # must fail closed
scripts/healthcheck.sh                                         # production stays healthy
```

Stopping this unit does not stop Candidate A or the production gateway. Because
the unit uses `--collect`, it is removed after stop; redeploy from the frozen
release command/artifact rather than assuming `systemctl start` can resurrect
the collected name. The physical stop/redeploy record and all launch failures
are in `pilot-active-result.json`.

Explicit client instructions that name a tool require successful evidence from
that instruction, not merely from the same session. The gateway persists a hash
of the latest explicit instruction and the tool-execution cursor observed when
it arrived. A continuation of the same instruction may reuse its post-cursor
success; a changed instruction resets the cursor and requires fresh evidence.
Do not manually clear these fields during recovery: they are part of durable
false-completion prevention.

Gateway binds `0.0.0.0:9000` directly. Tailnet, LAN, and loopback clients reach
that single authenticated listener without systemd socket proxies. Local model
servers bind only ports `9001`, `8102`, `8103`, `8110`, and Ollama Reasoner
port `11435` on loopback. The gateway does not expose or proxy any native role
API.

```bash
scripts/runtime-status.sh
scripts/audit-trace-completeness.sh data/traces
```

Runtime status reports service state/restarts, recent gateway/model failures,
SQLite session counts, profile rollback events, and measured current memory.
Unknown measurements remain explicit; they are not inferred.

For a Responses disconnect, correlate the client session header with the safe
terminal record:

```bash
journalctl --user -u dgx-moa-gateway.service --since=-30m \
  | rg 'responses_stream_terminal'
```

Every translated Responses failure logs `status=failed` at warning level;
successful terminal summaries use info level and are available when that logger
is enabled. Records include only bounded, control-character-cleaned `session_id`,
`model`, `source`, HTTP status where available, error type, code, and safe counts.
They never include prompts, generated reasoning, tool arguments, upstream
response bodies, or exception messages. `source=chat_http_exception` and
`source=chat_non_stream_response` identify failures before streaming;
`source=upstream_iterator` identifies an error frame, truncated EOF, buffer
limit, or iterator failure after streaming began.
`source=chat_unhandled_exception` identifies an unexpected failure before the
Chat stream exists and includes only its exception class. Responses clients may
receive `: keep-alive` SSE comments while Reasoner or routing work is pending;
these are transport heartbeats, not model output.

An optional role that is genuinely loading is retried inside that same Responses
stream until `model_load_timeout_seconds`; heartbeat comments keep the transport
alive. A terminal `response.failed` is emitted only after the loading deadline
or for a non-loading failure. A newly arriving request also cancels a stale
`unload_queued` transition before readiness is evaluated.

The gateway atomically maintains the model invocation report at:

```text
<gateway.run_dir>/model-invocation-rates.csv
```

In the checked-in configuration this resolves under `data/run/`. The report has
`all_time` and `last_hour` rows for every configured or historically observed
role/model pair. `invocation_rate_percent`
is the percentage of distinct gateway request IDs that invoked that model in the
window; `invocation_count` separately preserves repeated calls within one
request. The report also includes recorded success/failure counts, average
latency, and token totals. Rates across roles may exceed 100% in aggregate
because one request can invoke several models. The CSV contains no prompts,
reasoning, tool arguments, response bodies, credentials, or OAuth material. It
starts with the first invocation after the running gateway contains this change;
historical rates are not reconstructed.

Local files and `file://` attachment paths are native filesystem inputs. Use
Codex file or shell tools for them. Call `read_mcp_resource` only with the exact
server identifier and resource URI returned by MCP discovery; a connector's
display name such as `local_filesystem` is not evidence that such an MCP server
exists.

Lifecycle states and safety rules are canonical in
`docs/MODEL_LIFECYCLE.md`.

## Isolated Loop Engineering development

The development loop implementation is disabled in checked-in configuration and is not
production-authorized. An isolated development gateway may enable it with a
complete JSON policy:

```bash
DGX_MOA_LOOP_ENGINEERING='{"enabled":true,"defaults":{"iterations":4,"tool_calls":100,"reasoner_reentries":4,"planner_calls":2,"reviewer_calls":2,"frontier_calls":3,"judge_calls":2,"tokens":1000000,"external_cost_usd":10,"wall_clock_seconds":1800},"duplicate_fingerprint_limit":2,"no_progress_iteration_limit":2,"local_failures_before_frontier":2,"request_class_overrides":{},"risk_level_overrides":{}}'
```

Use an isolated state database, run directory, loopback port, and development
runtime channel. The source admits model and tool actions through the configured
budgets, but physical client/provider validation is incomplete. Do not enable
it in production.
See `docs/LOOP_ENGINEERING.md`.

## Isolated runtime Skills development

The checked-in `gateway.runtime_skills.enabled` value is `false`. For isolated
development only, set a separate writable root:

```bash
DGX_MOA_RUNTIME_SKILLS='{"enabled":true,"root":"/tmp/dgx-moa-skills","retrieval_limit":3,"max_context_characters":6000}'
```

Do not point experiments at a production registry. Promotion and rollback are
new-version operations and require evidence plus explicit approval. Set
`require_signature` at the pack import boundary when unsigned packs must be
rejected. See `docs/SKILLS.md` and `docs/SKILL_GOVERNANCE.md`.

## Isolated Runtime Knowledge development

The checked-in Knowledge registry is disabled. Use a development-owned SQLite
path and never point an experiment at production state:

```bash
DGX_MOA_RUNTIME_KNOWLEDGE='{"enabled":true,"state_db":"/tmp/dgx-moa-knowledge.db","retrieval_limit":3,"max_context_characters":6000}'
```

Promotion, conflict resolution, lifecycle changes, and rollback require a new
immutable version and explicit approval. See `docs/KNOWLEDGE_BASE.md`.

## Isolated OpenCode Go specialist and Remote Judge development

Remote Judge defaults are disabled and require no credential. Keep the endpoint
and `OPENCODE_GO_API_KEY` outside Git, use only bounded sanitized synthetic
evidence, and do not enable production until the physical matrix passes. See
`docs/REMOTE_JUDGE.md` and `docs/SPECIALIST_ROUTING.md`.

The production mapping is Planner `deepseek-v4-pro`, Reviewer `glm-5.2`, and
Judge `kimi-k3` through OpenCode Go. DeepSeek V4 Flash belongs only to Executor
overflow/fallback scheduling and must never be configured as Reviewer. Earlier
GLM and DeepSeek Reviewer probes remain historical evidence; never treat hidden
`reasoning_content` as a role artifact.
After approval, write the retry to a durable sanitized checkpoint rather than
terminal-only output:

```bash
uv run python scripts/validate-specialist-routing.py \
  --output data/diagnostics/opencode-completion/specialists-YYYYMMDD.json
```

The file is replaced atomically after each role and never contains prompts,
raw content, reasoning content, credentials, or exception messages.

Executor API-key scheduling and `deepseek-v4-flash` overflow are also disabled.
The operator enabled China-hosted models and the same endpoint, key/workspace
identity, and exact model then completed successfully. Native tool continuation,
stream completion, and client cancellation also passed. Treat the earlier
`RegionError` as resolved workspace-policy evidence, not a provider or runtime
regression. Provider pinning, same-key depth three/FIFO fairness, cross-key
overflow, request-shape recovery, and high-risk fail-closed behavior
subsequently passed in isolated direct and authenticated HTTP gates. Keep
scheduling disabled because the broader full-matrix, evaluation, release, and
promotion gates remain open.

The live Runtime Dashboard is separately controlled by
`gateway.dashboard_enabled` / `DGX_MOA_DASHBOARD_ENABLED`; the checked-in safe
default remains false. The 2026-08-13 validation overlay enables the feature
on the authenticated `0.0.0.0:9000` gateway. Enabling it requires same-key/cross-key isolation,
operator aggregate redaction, audited raw-view reason, reconnect/gap recovery,
and inference-independence checks. HTTPS/WSS remains preferred when an approved
ingress exists. Never pass API keys in a WebSocket URL; the browser must exchange
a bearer credential for the HttpOnly dashboard cookie.

When both Dashboard and Execution Graph shadow mode are enabled in an isolated
development runtime, `GET /v1/dashboard/snapshot` returns persisted graph,
attempt, checkpoint, and compact active state only to the owning API key.
Operator scope receives aggregate template/terminal/active/pending counts, not
graph IDs, request IDs, paths, prompt, output, or active-state content. An
audited request-detail raw view remains the only cross-key content path.

`WS /v1/dashboard/live` sends committed `graph_saved`, `node_attempt`, and
`graph_checkpoint` deltas with a scope-local monotonic `seq`. Reconnect with
`?last_seq=N`; an in-window cursor receives only later events. A stale or future
cursor receives `RESYNC_REQUIRED` and must reload the REST snapshot. Queue gaps
are explicitly marked and never block Graph persistence or inference. The UI
renders compiler nodes in fixed role lanes with parallel group, conditional
edge, provider, attempt state, and latency metadata. Checked-in Dashboard and
Graph defaults remain disabled.

The development API-key schema also scrubs historical plaintext and makes
admin reveal permanently unavailable. Do not deploy that migration without
separate approval, a tested upgraded rollback build, and an operator plan for
the process-memory-only `admin-codex-cli` key. Authentication hashes and key
IDs survive, but rolling back to older code after the scrub would leave its
plaintext-dependent admin Codex helper unavailable. Do not copy the old raw
key column into a backup or training artifact to preserve that obsolete path.

## Isolated runtime evolution development

Prompt, Policy, Routing, failure-handling, and Judge-prompt candidates remain
disabled. Use only a development-owned registry:

```bash
DGX_MOA_RUNTIME_EVOLUTION='{"enabled":true,"state_db":"/tmp/dgx-moa-evolution.db"}'
```

No candidate can bypass replay, regression, Reviewer, applicable Judge, canary,
approval, and rollback-target gates. See `docs/RUNTIME_SELF_IMPROVEMENT.md`.

## Isolated declarative policy development

The checked-in `gateway.declarative_policy.enabled` value is `false`. Use only
an isolated gateway and pass a complete versioned policy object through
`DGX_MOA_DECLARATIVE_POLICY`. Approval IDs belong in authenticated request
metadata; do not store credentials or approval secrets inside a policy file.
See `docs/POLICY_ENGINE.md` for the implemented and missing enforcement edges.

## Isolated Execution Graph shadow development

The checked-in `gateway.execution_graph.mode` value is `disabled`. `shadow` may
be used only with a development-owned state database; it compiles and persists
candidate topology beside the legacy Controller but owns no routing, tools, or
final response. Restore rollback behavior by setting the mode to `disabled` and
restarting only the development gateway. There is intentionally no `enforced`
mode until paired parity, fault-injection, long-horizon, Dashboard, and human
approval gates pass. Never point a shadow experiment at the production state
database or describe its candidate graph as the active workflow.

Shadow projection stores a content-addressed `session-active-state-v1` object
and an immutable checkpoint with event cursor and before/after byte sizes. The
active-state byte ceiling is the existing tool-output character budget times
the retained-observation count; oversized fields retain a SHA-256 and bounded
redacted summary. Durable `events` rows are not compacted or deleted. Resume
must validate graph/compiler/policy/snapshot hashes and records a new checkpoint
before continuation.

Trace v3 is not extended. Graph ID/hash/template/checkpoint/object references
live inside its existing `metrics.execution_graph` object. When training is
explicitly enabled, only an already-eligible request may resolve those
references into a sanitized routing candidate. Hash, template, checkpoint, and
active-state mismatches fail the collector closed. Measured attempt latency and
cost are retained; absent quality delta is recorded as `not_measured`, never
inferred. Checked-in Graph and training gates remain disabled.

## Live observation operations

Checked-in `gateway.live_observation.enabled` remains `false`. Supply Telegram
bot credentials only through the protected
`DGX_MOA_LIVE_OBSERVATION` runtime object. Never commit them. Controls require
both `admin_api_enabled` and `live_observation.controls.enabled`, plus an empty-
by-default user/role policy. Issue request-scoped nonces through
`POST /v1/admin/observation/nonces` and submit bounded commands through
`POST /v1/admin/observation/commands`. See `docs/LIVE_OBSERVATION.md`.

The reviewed production override enables Telegram observation; the excluded
Discord compatibility transport has been removed from `dev`. Controls remain
disabled. The token and target are 0600 files outside
the worktree and are injected into the ignored 0600 environment. Rollback is to
remove `DGX_MOA_LIVE_OBSERVATION` from that environment, restart the fixed
gateway unit, wait for resident restoration, and verify observer metrics stop
changing. Never print the effective JSON because it contains the bot token and
chat ID.

## Training collection

Checked-in `gateway.training_data.enabled` remains `false`. The reviewed
production override enables collection with only `moa-production` mapped to
`training_allowed`; clients must send that ID and the production workspace path.
The training database remains separate from `gateway.state_db`, with a separate
object root and 10 GB free-space floor. `external-api` and external-provider
output remain ineligible. Roll back by removing `DGX_MOA_TRAINING_DATA`,
restarting the fixed gateway unit, and verifying the training counters stop.
Collection failure is sanitized and cannot fail inference. See
`docs/TRAINING_DATA.md` and `docs/PRIVACY_AND_RETENTION.md`.

## Weekly packaging

Checked-in weekly jobs remain disabled. The reviewed production override enables
the bounded in-process scheduler: Skill reporting Sunday 03:00 and packaging
Monday 02:00 in `Asia/Seoul`. No timer is installed. Packaging requires a real
`7zz` or `7z`, the 10 GB reserve, a complete prior week, and only eligible,
tombstone-free candidates. Retention apply and archive export remain separately
approval-gated. Roll back by removing `DGX_MOA_WEEKLY_JOBS`, restarting the
fixed gateway unit, and verifying no scheduler jobs remain. See
`docs/WEEKLY_PACKAGING.md`.

## Isolated execution replay

Use exact replay only with complete structured mock outputs for every invoked
role. Live comparative replay is nondeterministic and must run against an
isolated state, Skill registry and provider configuration. Do not point a replay
at the production worktree or allow it to mutate Frontier hosts. See
`docs/EXECUTION_REPLAY.md`.

## Isolated lifecycle development

Use these only with an isolated development config and development-owned
process. The 2026-07-20 validation exercised this shape through runtime-linked
user-systemd units; the literal values below remain examples:

```bash
DGX_MOA_CONFIG=/path/to/dev-models.yaml
DGX_MOA_RUNTIME_CHANNEL=dev
DGX_MOA_STATE_DB=/path/to/isolated-dev/gateway.db
DGX_MOA_BIND_HOST=127.0.0.1
DGX_MOA_BIND_PORT=19000
DGX_MOA_LIFECYCLE_MODE=adaptive
DGX_MOA_LIFECYCLE_POLL_SECONDS=30
DGX_MOA_LIFECYCLE_UNIT_MAP='{"executor":"dgx-moa-dev-executor.service","planner":"dgx-moa-dev-planner.service","reviewer":"dgx-moa-dev-reviewer.service"}'
```

`DGX_MOA_CONFIG` selects the development YAML. Set the isolated run directory
there; no run-directory environment override is implemented:

```yaml
gateway:
  run_dir: /path/to/isolated-dev/run
```

Use unique validated `dgx-moa-dev-*` units, a loopback port, state database, and
run directory that share nothing with production. `DGX_MOA_ADMIN_API_ENABLED`
remains false unless the isolated test needs protected admin routes.

Do not set lifecycle environment overrides when using the rollback command;
they intentionally make validation fail if they defeat the file change. For one
explicit reviewed configuration, rollback is:

```bash
scripts/rollback-lifecycle.sh /absolute/path/to/models.yaml
```

The script atomically writes mode `disabled` and `{}` unit map with file and
directory fsync, validates the result, resets the automation latch while
retaining failure history, restarts only `dgx-moa-gateway.service`, restores the
resident profile, runs health, and verifies protected model status. It is
idempotent. It does not authorize a production invocation.

Use `GET /v1/model-status` for safe role state, generation, progress, idle
decisions, and circuit status. Runtime reporting adds content-free role request
counts, last-used time, UTC hourly/weekday-hour distribution, EWMA/percentile
gaps, and cold/load timing statistics.

## Phase 4 validation and PR boundary

The passing ignored Phase 4 summary is
`/tmp/dgx-moa-phase4-s5gy6ydh/summary.json`, SHA-256
`5249dd396c4ac8b6ed85e4474fb7c631f504055685138be90791999f03928a8f`.
The isolated executor/gateway and lifecycle stub used loopback ports
`19301`/`19300`/`19302`; no production or tailnet listener was opened.

Every owned process was stopped after identity revalidation. The full
production Git, index, tracked-file metadata, user-unit, port, and runtime
snapshots were equal before and after both warm and lifecycle runs. The
validation harness is not a production runbook: do not point it at production
units or copy its two-second idle threshold into production configuration.

This gate authorizes only a draft `dev`-to-`main` PR. Merge, deployment,
systemd installation, lifecycle enablement, resident-target activation, and
production restart remain separate operations requiring explicit approval.

## Measured Executor runtime decision

Phase 3's 65K/1.7 GB baseline remains historical rollback evidence. The
subsequent fixed-revision qualification passed that contract and repeated exact
stop/start at `--max-model-len 131072`, `--max-num-seqs 1`, and
`--kv-cache-memory-bytes 3400000000`. Candidate A subsequently qualified native
FlashInfer B12x dense/MoE, TRITON_MLA, lazy safetensors, cudaMallocAsync, and
`FULL_DECODE_ONLY` CUDA Graph on that fixed revision. This is now the checked-in
default. `DGX_MOA_EXECUTOR_LINEAR_BACKEND=MARLIN`,
`DGX_MOA_EXECUTOR_MOE_BACKEND=MARLIN`, and
`DGX_MOA_EXECUTOR_COMPILATION_CONFIG='{"cudagraph_mode":"NONE"}'` select the
known rollback profile explicitly. Do not add the rejected FP8, eager, prefix,
chunked-prefill, CPU-offload, or KV-offload settings.

Pilot installation is still a release operation: confirm the deployed config
does not retain old environment overrides such as context `65536` or MARLIN,
inspect the fully expanded command, perform exact stop/start, and compare the
revision, kernel identity, KV bytes, graph mode, cgroup limits, health, memory,
and tool semantics with the Candidate A evidence before admitting traffic.

Do not repeat v49-v53 argument combinations. `CUTLASS_MLA` is capability-10
only on this stack; native allocator fragmentation tuning still crosses the
MARLIN packing safety guard; and cudaMallocAsync FULL decode capture fails when
Triton receives capture-created pointers on SM121/CUDA 13. The upstream MLA
workspace-preallocation backport alone does not fix the general pointer class.
Those are historical MARLIN/early-graph failures, not a contradiction of the
later explicit B12x Candidate A success. Any future challenger must remain in a
capped isolated runtime and cannot displace A without equivalent evidence.

Client-quality diagnosis must preserve failed tool semantics. Do not rewrite an
invalid or invented Responses `write_stdin` session into a successful shell
no-op; retain the tool name and use invalid sentinel session `0` so the client
can recover from an actual failure. The v46 physical rerun recovered three
Codex cells, but webhook-verifier still timed out at 1,800.101 seconds after
passing its public and hidden tests. Do not claim full-matrix noninferiority
until that terminal-response path and a fresh randomized full matrix pass.

For progress-only Responses retries, request another implementation tool only
when the persisted state still lacks change/test/review evidence. When that
evidence already exists, request a concrete final result and do not induce a
redundant validation loop. Physical v47/v48 webhook runs passed this terminal
path twice. Full-matrix promotion is still prohibited: v48 Codex atomic-store
timed out after successful validation, and the interrupted dag-runner trace
showed reviewer/correction churn when shell writes had no trustworthy
changed-path projection and `git` was unavailable in the client container.

Exact full service stop/start is the selected unload and mandatory fallback.
The original isolated lifecycle row measured a `942.7537190914154`-second cold
load, `273.00104479002766`-second warm reload, and
`1.361647605895996`-second executor unload. The separate mechanism matrix
measured full-stop times `1.146820979192853` and `1.118467804044485` seconds.
Sleep level 1 slept in `21.733480336144567` / `2.1252455201465636` seconds and
woke in `38.78946190699935` / `7.454574962845072` seconds, but returned only
47.12% of full-stop memory and was unstable. Those timings do not authorize a
sleep deployment.

The selected three-cycle transient-unit result reached ready in
`938.3187154009938`, `270.0974161340855`, and `274.08552565216087` seconds and
left exact owned PSS/RSS zero after every stop. The operational source of truth
for limitations and artifact hashes is `docs/MEMORY_OPTIMIZATION.md`; these
numbers are evidence, not an instruction to act on production units.

## Profiles

The local resident target requires `dgx-moa-gateway.service` and
`dgx-moa-executor.service`. Planner and Reviewer remain optional and retain
`PartOf=dgx-moa-resident.target`, so stopping resident cleans up either role if
started separately. The loopback Ollama Reasoner is also started separately and
must be healthy for default product readiness; stop verification checks its
`11435` listener together with Executor, Planner, and Reviewer.

The inspected production override uses lifecycle mode `disabled` with an empty
unit map. Safe checked-in defaults match that state. Any later topology change
requires a reviewed PR/deployment that verifies the installed diff, daemon
reload, profile transition, readiness, typed cold-role behavior, and rollback.

Rollback uses the one-config atomic disabled/empty-map path documented above,
then restores and verifies the fixed resident services. A production rollback
still requires separate approval; do not edit installed units in place.

```bash
scripts/switch-profile.sh resident
scripts/switch-profile.sh judge
scripts/stop-resident.sh
scripts/stop-judge.sh
```

Profile changes use systemd targets and `data/run/profile.lock`, stop the old
profile first, wait `DGX_MOA_MEMORY_SETTLE_SECONDS` for unified-memory reclaim,
check readiness and memory headroom, then record state. Failed starts roll back
to the previous resident profile.

```bash
systemctl --user start dgx-moa-resident.target
systemctl --user stop dgx-moa-resident.target
systemctl --user start dgx-moa-judge.target
systemctl --user start dgx-moa.target
systemctl --user status dgx-moa.target
scripts/switch-profile.sh resident
scripts/switch-profile.sh judge
scripts/switch-profile.sh restore
scripts/switch-profile.sh status
```

## Network ingress

Set `DGX_MOA_BIND_HOST=0.0.0.0`. Never use Tailscale Serve or Funnel. Gateway
bearer authentication remains mandatory on every interface; role-model servers
remain loopback-only. Scope external reachability with the host firewall.
On hosts using UFW with inbound deny, admit only the local subnet and gateway
address:

```bash
sudo ufw allow from 192.168.0.0/24 to 192.168.0.42 port 9000 proto tcp \
  comment 'DGX MoA authenticated LAN gateway'
```

## OpenCode

Set `DGX_MOA_API_KEY` on the client, then copy
`config/opencode.example.json` into the OpenCode configuration directory.
Configuration is identical on macOS and Linux; only environment setup differs.
The live validation harness explicitly selects `dgx-moa` for both its
tool-continuation and streaming requests. It keeps the request body
OpenAI-compatible and sends validation provenance in the existing headers.

For a persistent local client UI, start OpenCode in a named tmux session:

```bash
tmux new-session -d -s dgx-opencode -c "$PWD" "$HOME/.opencode/bin/opencode"
tmux attach -t dgx-opencode
```

Keep the API key in the process environment; do not write it into project config.

With auth enabled:

```bash
curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY}" \
  "http://${DGX_MOA_BIND_HOST}:9000/v1/models"
```

With auth disabled, omit the header. Admin profile endpoints stay disabled
unless `DGX_MOA_ADMIN_API_ENABLED=true`.

## API clients

Use `/v1/models` to discover `dgx-moa` and `dgx-moa-fast`. Direct external
agents should select `dgx-moa` and own the native tool loop. Select
`dgx-moa-fast` only for an intentional
Executor-only request. Standard OpenAI request fields are sufficient; project
metadata and provenance headers are optional.

The default executor output budget is 4096 tokens and the server cap is 16384.
SSE is forwarded event-by-event with one DONE. A model/profile-loading 503 is
retryable after the `Retry-After` interval. Full examples and typed errors are
in `docs/API_CLIENT_MODES.md`; Hermes configuration is in
`docs/HERMES_AGENT.md`.

## Models

```bash
scripts/verify-models.sh executor reviewer planner
scripts/verify-models.sh executor reviewer planner judge
scripts/estimate-model-storage.sh judge
```

Downloads are pinned, resumable, lock-protected, and never remove unrelated caches.
The legacy context/profile tuner is retired; preserve `docs/CONTEXT_TUNING.md`
as historical evidence and use only a separately approved isolated protocol for
new context experiments.

For the graph-active 131K validation runtime, v54 established that native
allocator retention must be reclaimed inside vLLM's shared quantized-module
post-load loop. Do not repeat cudaMallocAsync graph variants v24-v25 or v49-v53,
and do not create a post-MARLIN `sharded_state` checkpoint: its keys do not match
fresh compressed-tensors initialization and repacking still runs. The validated
isolated candidate is native allocation, dense/MoE MARLIN, TRITON_MLA,
`FULL_DECODE_ONLY`, fixed 3.4 GB KV, and `empty_cache()` after each quantized
module. This is validation evidence, not production deployment authority.

For Blackwell native qualification, do not use the installed `auto` NVFP4
selection on this host. It selects FlashInfer CUTLASS for both dense and MoE
and caused a global-OOM warmup incident in v64. The physically passing native
candidate is explicit FlashInfer B12x; it is still a qualification candidate,
not production deployment authority. Any further large-runtime experiment must
use the checked external `/bin/kill` qualification guard (the dash builtin does
not accept the required `-- -PGID` form), retain the 24 GiB host floor, and
pass `test-run-qualified.sh` before launch. It must run in an isolated process
group with immediate `SIGKILL` and verify the production listener before and after.
Do not restart the production gateway after an OOM incident without separate
operator approval.

Blackwell backend qualification now keeps vLLM explicit FlashInfer B12x v64 as
immutable known-good candidate A and evaluates SGLang only as isolated candidate
B. Use a loopback-only transient process group, `MAX_JOBS=1`, the checked
qualification guard, context 131072, one running request, and
`--max-total-tokens 147568` (3,399,966,720-byte MLA BF16 KV pool). Do not expose
the SGLang role endpoint or alter the authenticated production gateway. Keep
cold runs prefix-clean and separate from the 80K-100K RadixAttention agent-prefix
lane. A readiness response alone is not a promotion gate.

The v66 SGLang epoch is now closed as a failed challenger: native SM121 FP4,
FlashInfer MLA, batch-one CUDA Graph, RadixCache, Chat, tools, streaming, and
cancel recovery ran, but verbatim tool-result continuation and standard
Responses string input failed. Do not run cold or agent-prefix performance
lanes for that exact runtime or promote it from tok/s. A future SGLang retry
must identify a source revision that changes both failed API paths, register
that revision as the single runtime variable, and rerun correctness before any
performance comparison. Keep vLLM B12x candidate A unchanged and MARLIN as
rollback only.

The separately named v98 SGLang `0.5.17` epoch is closed as a failed native
challenger. Preserve its auto Triton 256/512 graph failure, TRTLLM-Gen
`Unsupported architecture`, and CUTLASS MLA `D_q_nope == D_latent` failure.
The ready FlashInfer wrapper used non-native FA2 attention and is not a native
promotion candidate. Do not run its cold or Radix-prefix performance lanes or
cycle additional registered backend names. Keep the dedicated venv and frozen
artifacts for reproduction, candidate A as the selected backend, and MARLIN as
rollback only. Before resuming a new client matrix, require candidate A loopback
health plus Chat, Responses, native tool continuation, streaming recovery, and
both authenticated gateway health checks.

Those post-v98 recovery checks passed for the validation topology. Candidate A
is active on loopback port 19301 with the exact v64 backend contract; the
validation gateway is ready and authenticated traffic passed. The production
gateway service is healthy but its unchanged production roles remain stopped,
so do not reinterpret its expected `/readyz` 503 as a Candidate A failure or
start production roles without separate deployment approval.

The candidate-A-pinned v67 full matrix is also closed for execution, not
promotion: 20/20 cells ran and 19 passed. Preserve the failed Hermes
atomic-store cell exactly; do not rerun it in place, extend its frozen timeout,
or discard it because its implementation and validations passed. Its failure
class is bounded terminal convergence: every assistant turn requested another
tool and no final response appeared. Investigate that behavior in a separately
named targeted recovery epoch while leaving candidate A, v66, the v67 schedule,
and all score artifacts immutable. Do not begin blind noninferiority or later
release gates until the targeted recovery passes the same final-response,
tool-evidence, source-scope, public-test, and hidden-test contract.

Targeted Hermes recovery v72 now passes that contract, but it converged before
the 20-turn maximum and therefore did not exercise its compact fast-summary
fallback. Preserve v68-v71 failures and v72's limitation. Resume with a new,
candidate-A-pinned full matrix; do not edit or relabel v67, and do not start
blind noninferiority or release gates until the new matrix passes in full.

That fresh matrix is v73 and is now frozen at `17/20`. Do not rerun its three
failed cells in place. Recover Codex rc-139 startup/process failure, Codex
terminal convergence, and Hermes cancelled-request terminal fallback in
separately named epochs. Keep candidate A resident and unchanged: v73 ended
with all services HTTP 200 and stable GPU memory. Blind noninferiority and
release gates remain unstarted.

Fresh matrix v80 is frozen at `5/20`, but its common prerequisite was invalid:
the isolated gateway launcher omitted `/home/kotori9/.local/bin` from `PATH`,
so the configured bare `codex` command could not spawn and runtime events
recorded `FRONTIER_PROCESS_SPAWN_FAILED`. Do not rerun or relabel v80. For the
next isolated epoch, prepend that exact directory to the transient gateway
`PATH`, verify `command -v codex` from the service environment, and require one
direct Codex OAuth Frontier completion before any client cell. Do not alter
Candidate A or production, and do not treat v80 as an NVFP4 backend failure.

The separate v81 prerequisite epoch has now passed that exact contract:
the service environment resolved `/home/kotori9/.local/bin/codex`, one normal
Codex OAuth Frontier collaboration completed, and no
`FRONTIER_PROCESS_SPAWN_FAILED` event occurred. v81 was exactly stopped after
verification. A new full client-quality epoch may reuse the v80 contract with
the corrected PATH; never edit or relabel v80, and retain the direct Frontier
completion as its prerequisite artifact.

The corrected-PATH full matrix v82 is now frozen at `15/20`: baseline and
Hermes `5/5`, Codex `2/5`, OpenCode `3/5`. Its state DB records no Frontier
spawn failure and no remote-Executor-fallback-unavailable payload, so do not
repeat the PATH prerequisite or relabel v80. Preserve v82 and use separately
named targeted epochs for Codex rate-limiter/atomic-store/dag-runner and
OpenCode atomic-store/dag-runner. Treat the first four as convergence/timeout
failures and the OpenCode dag-runner result as a Korean-final-format failure
unless newer direct evidence narrows them further. Keep Candidate A unchanged,
stop only each transient unit, and require every failed cell's original scoring
contract before starting a new full matrix. Blind noninferiority and release
gates remain unstarted.

Targeted v83 exact-replayed OpenCode dag-runner and passed 10/10 in 204.123
seconds, including the Korean-final check. Do not change prompt or gateway
behavior from the single v82 language miss. Preserve both epochs and continue
the remaining v82 failed cells in separately named targeted epochs.

Targeted v84 exact-replayed OpenCode atomic-store and passed 10/10 in 489.769
seconds. The v82 timeout was not reproduced. v83 and v84 therefore require no
OpenCode prompt/client/gateway change; retain their passing evidence alongside
v82 and continue the three Codex targeted recoveries.

Codex atomic-store v85 reproduced the timeout and isolated stale review
evidence as its direct loop driver. v86 selected the latest eight results and
eliminated all Frontier correction retries, but still timed out because earlier
failing tests remained in that window beside newer passes. Do not deploy v86.
The next admissible single variable is latest-four review results in another
isolated gateway; retain separately extracted contract evidence and require the
unchanged 10-check cell contract.

v88 recovered Codex rate-limiter terminal behavior but failed hidden quality
at 9/10 because positive float windows were rejected. Four repeated Frontier
architecture calls exhausted the task budget before clean-local-review
assurance. Do not weaken hidden validation. Reuse a prior architecture artifact
in the next isolated epoch and require the same 10-check rate-limiter contract.

v87 physically passed that latest-four candidate: Codex atomic-store completed
10/10 in 1,058.352 seconds, including a real rejected review, applied
correction, correction verification, public/hidden validation, and Korean
terminal. Keep the code undeployed and validate Codex rate-limiter and
dag-runner in separately named isolated epochs before any fresh full matrix.

A passing targeted cell qualifies a preregistered controller branch only when
its event is physically observed. v89 passed Codex rate-limiter 10/10 but
emitted no architecture collaboration or architecture-reuse event, so retain
it as replay success only. Stop only its named transient gateway and preserve
candidate A plus both persistent gateways.

v90 passed the remaining Codex dag-runner target 10/10 with latest-four alone.
Its 4 architecture calls and 20 post-budget unavailable events remain evidence;
do not infer that targeted passes replace the fresh full-matrix requirement.

V91 is frozen after the second cell and its transient services are stopped.
False changed
paths derived from prose slashes or files created inside `TemporaryDirectory`
are evidence-extraction failures. V92 physically recovered the tempfile case
but failed Codex rate-limiter hidden validation and exposed Python return
annotations as false redirect paths. Retain both epochs; validate the corrected
redirect matcher and Codex cell in a separately named new-process epoch before
another full matrix.

V93 passed the functional Codex cell but failed its parser-specific acceptance
because `/remaining(` and `cutoff` remained false targets. Do not promote that
epoch as parser qualification. Replay the conservative command-specific
redirect matcher in a new process before starting the full matrix.

V94 passed that replay 10/10 and recorded only `rate_limiter.py` as an
implementation target. Preserve v91-v93 failures and use the v94-loaded source
for the next separately named full matrix; do not treat the targeted pass as
matrix noninferiority.

V95 is frozen and all its transient units are inactive. It is not a clean full
matrix because its initial stop monitor interrupted cell 02 and the pause race
started cell 03 before termination. Treat its partial scores as evidence only.
Validate the explicit `limit`/`*_limit` bool-rejection contract in a separate
new-process cell before creating another clean full matrix.

V96 physically cleared the bool-limit hidden check but timed out because
architecture fanout preempted every code-review escalation. Do not start the
full matrix. First replay Codex log-report with architecture deferred whenever
implementation evidence and the reviewer role are both present; verify that
the observed Frontier mode is code-review, not architecture.

V97 passed that replay 10/10 in 329.680 seconds. The preserved first launch
attempt was a pre-request setup error; attempt 2 included runner preparation,
observed two code-review and zero architecture Frontier calls, verified the
applied correction, and had no unavailable or bad-terminal evidence. The
convergence correction is qualified. Do not start the full matrix yet: the
operator-prioritized v98 SGLang backend qualification now runs first, after
which the selected backend receives a separately named clean matrix epoch.

To use a prepared executor LoRA, set `models.executor.lora_adapter` to its local
path. Omit it for the validated original post-trained checkpoint. This project
does not train adapters.

Production deployment is a fast-forward/pull of reviewed `main` into
`/home/kotori9/dgx-moa-agent`, followed by proportional checks. `dev` may be
deployed there only as an explicitly identified validation runtime; its traces
must use `runtime_channel=dev` and must never be labeled production.

## Blind paired evaluation statistics

After blind scores and their assignment mapping are frozen, run:

```bash
scripts/evaluate-paired-noninferiority.py input.json result.json
```

The input is one comparator matrix using schema `paired-noninferiority-v1`.
It must name all preregistered pair IDs, contain at least 30 observed pairs,
cover all seven task categories and Codex/OpenCode/Hermes/raw client strata,
match the protocol epoch and condition hashes, retain failed runs as success
`0`, carry complete telemetry and quality-evidence hashes, and attest that
implementation identities were hidden during scoring. Success `1` also
requires completed status, passed hidden tests, and no false completion. A
missing/unexpected pair, mismatched condition, mixed epoch, incomplete telemetry, failed
reliability gate, or insufficient coverage returns `INCONCLUSIVE` with exit 2.
The fixed statistic is target minus comparator task success, margin `-0.10`,
10,000 paired resamples with seed `20260808`, and a two-sided 95% percentile
interval using linear interpolation at rank `(n-1)q`. Only a lower bound
strictly greater than the margin returns `PASS`. Run separate frozen inputs for
GPT-5.6-sol High and Claude Opus 5-class; never combine comparators or epochs.

## Runtime metrics

The gateway exposes the Goal-specific fixed metric set at
authenticated `GET /metrics`. Metrics are label-free: request IDs, user IDs,
repository paths, prompts, and failure text are never accepted or retained by
the collector. Loop counters are fed by the append-only event boundary; Skill,
observer, and training counters are overlaid from their bounded stores.
Not-yet-run weekly operations report zero. The authenticated production endpoint
has physical Training counter evidence.

Invocation cache accounting is nullable. `cached_tokens=null` means the
provider did not report a cache measurement; `cached_tokens=0` means it
explicitly measured zero reuse. Do not coerce the former to zero in clients,
CSV consumers, Dashboard summaries, traces, or training data. Every role call
gets a separate `model_invocation_usage` row, so repeated Planner, Reviewer,
Frontier, Judge, or Executor calls must be summed rather than taking the last
row. Legacy invocation tables gain only the nullable `cached_tokens` column on
open; request-level token totals are unchanged. Responses wire output omits the
optional `input_tokens_details` object when cache measurement is unavailable;
strict clients therefore receive neither a false zero nor an invalid null
integer. A measured zero or positive value still emits the detail object.

Execution Graph remains disabled by default. In an isolated development
runtime with `execution_graph.mode: shadow`, requests compile after Runtime
Policy and API-key admission but before Reasoner dispatch; scheduler-enabled
requests additionally persist the pinned API-key admission snapshot.
Reasoner, Planner, `FRONTIER_A`, executor preparation, primary Executor, and
matching control/checkpoint/terminal nodes persist actual attempts. The
straight-through high-risk path also records actual Reviewer and Judge
attempts. A client tool call persists `WAITING_TOOL`; a matching same-session
result resumes the same checkpoint, and an observed validation command records
`TEST` before the primary Executor retries. Tool/test cycles stop after two
traversals. Generated Evidence without independent validation still terminates
as `degraded`. A Judge `revise` and a failed tool can return to the same pinned
primary Executor through bounded repair/fallback edges; a targeted Reviewer and
optional Judge recheck close the corrected path. `reject`/`escalate` instead
select `ON_REJECTION` and fail closed without a correction call. When compiled,
`FRONTIER_B` uses the existing configured OpenRouter transport directly,
records disagreement Evidence, and opens the bounded Executor repair. A
disabled transport, missing credential, or provider failure fails closed;
Frontier A remains Codex OAuth. Streaming client tool calls pause at the persisted
`WAITING_TOOL` boundary used by non-streaming continuation. General post-stream
Reviewer/Judge execution remains deferred because output has already been
delivered. `execution_graph_shadow_failed` is observational degradation only;
investigate it without retrying or changing the pinned inference provider.

Declarative-policy approval pauses persist `HUMAN_APPROVAL` as
`WAITING_APPROVAL`. The existing nonce-, allowlist-, role-, request-, and
idempotency-scoped observation `approve` command records operator policy
Evidence, clears only a matching `PERMISSION_REQUIRED` stop, selects
`ON_APPROVAL`, and lets the retried request resume that Graph. Rejection and
termination remain fail-closed.

Execution attempt accounting is runtime-owned: node-type lookup, observed
token/cache/cost/latency normalization, and deterministic role failure
fingerprints use the same `ExecutionGraphRuntime` methods from API and
Controller stage boundaries. Provider invocation accounting remains the source
of observed metrics; Graph code does not infer missing usage. All shadow
persistence exceptions must use `record_shadow_failure()` so the stage and
exception class retain one fail-soft event contract.

For a failed TOOL result in an orchestrated session, finish and persist the
old Graph's TOOL attempt first. If that failure causes Reasoner, Planner, or
Frontier re-entry, compile a new Graph for the new orchestration iteration;
never start a completed collaborator node in the resumed Graph. Compile
Frontier nodes only when both the role is requested and `frontier_enabled` is
true. Audit a recovery with two `execution_graph_shadow_compiled` events, one
failed TOOL attempt, and zero `execution_graph_shadow_failed` events.

Explicit read-only intent (`read-only`, `do not modify`, `수정하지 말*`, or
`변경하지 말*`) must not enter the implementation change/validation/review
gate. When that objective explicitly names `exec_command`, however, require one
successful client tool result before accepting final output. This prevents both
the repeated-inspection loop and a prompt-echo false completion without forcing
file mutation or redundant reads.

Orchestrated role selection is Runtime Policy-owned. Do not expect or configure
an Executor `orchestration_decision` model call. Planner is selected for
unclear explicit-orchestrated, multi-file, recovery, escalation, or high-risk
work; review-only requests skip Planner. Reviewer requires an explicit review
signal, high-risk implementation evidence, or bounded implementation evidence
paired with a change objective. Reasoner recommendations cannot add roles.
Audit `executor_orchestration_decided.payload.authority`; the current value must
be `runtime_policy`. Lifecycle admission for policy-selected roles occurs before
the Reasoner call, so a typed cold/unmanaged response must have no model usage.
After admission, optional Reasoner, Planner, and Frontier A tasks start before
the join; none waits for another role's output. Their inputs therefore contain
only the pre-fan-out active state. A completed sibling artifact remains durable
when another branch fails, while the failed join still prevents synthesis.

## Weekly and training administration

When both the existing admin boundary and feature gates are enabled, candidate
inspection/state transitions and request/repository/user exclusions live under
`/v1/admin/training/*`. Retention endpoints are dry-run unless `apply=true`.
Weekly package verify/revoke/regenerate/retention lives under
`/v1/admin/weekly-packages/*`; exact/audit replay is `/v1/admin/replay`. Package
jobs use the configured Seoul schedules and emit only allowlisted summaries.
These routes remain `404` under checked-in defaults. The reviewed production
feature gates are enabled; retention stays dry-run unless `apply=true`, and
export is not authorized.

## V99 client-quality recovery boundary

V99 completed all 20 cells but failed the functional gate at `18/20`. Preserve
the exact Codex log-report `sample_limit=0` rejection and baseline atomic-store
boolean-version acceptance. Do not rerun either cell in place. Use separately
named targeted recovery epochs, then a new full-matrix epoch. Keep Candidate A
fixed and do not start blind noninferiority, Reasoner ablation, long-horizon,
canary, or release gates until that fresh full matrix passes.

V100 recovered Codex log-report but baseline atomic-store still classified a
boolean expected version as `VersionConflict`. Preserve that score. Replay only
the baseline cell in a new epoch; do not restart the full matrix yet.

V101 reproduced the baseline failure. V102 passed the same cell at xhigh.
Freeze `DGX_MOA_BASELINE_REASONING_EFFORT=xhigh` for the next fresh matrix;
retain high as the checked-in default and do not alter other harness settings.

V103 completed that fresh matrix at `18/20`. Keep its three transient units
stopped and preserve the Codex rate-limiter constructor failure and Codex
atomic-store invalid-update acceptance. Do not retry either workspace in place.
Use separately named targeted recovery epochs with Candidate A and baseline
`xhigh` fixed, then require another fresh 20-cell matrix before starting blind
noninferiority or any later release gate.

V104 recovered both Codex failures at `10/10` after preserving a request-free
setup attempt that lacked `prepare`. Keep v104 transients stopped. Start only a
new full-matrix epoch with Candidate A and baseline `xhigh` fixed; do not treat
the two targeted passes as authorization for blind noninferiority.

## Codex Pilot write-canary launcher contract

For a Codex write canary, pin both the custom provider and
`model_catalog_json` to the model catalog fetched from the authenticated Pilot
`/v1/models` endpoint. A catalog copied under `CODEX_HOME` is not sufficient.
Reject the run before scoring if the durable `client_tools_available` event
does not include `apply_patch`; otherwise a read-only tool surface can be
misclassified as Executor write quality. Preserve the failed client logs and
start a new attempt rather than editing an earlier artifact.

When a resumed Graph reports an exhausted `ON_BUDGET` TOOL repair edge, keep
the two-repair bound, persist
`execution_graph_shadow_reprojected(reason=tool_cycle_budget_exhausted)`, and
compile a new immutable Graph. Do not resume the exhausted Graph and do not
raise the repair budget to mask the projection error.

The Qwen Executor candidate order is fixed: `Qwen/Qwen3.8-27B`, multimodal LoRA
qualification, merged target, isolated SGLang plain decode, then
Chat/Responses/native-tool/image qualification. Only after that contract passes
may a separately named epoch test NVFP4 and then DSpark. Do not use MTP for this
Qwen lineage. A DSpark failure falls back to the same Qwen plain-decode slot;
local candidate failure or busy state falls back through the existing bounded
DeepSeek V4 Flash overflow. The qualified Mistral service remains the rollback
Executor. Candidate units and inference listeners stay isolated and loopback-
only; do not add them to the production lifecycle unit map or restart `:9000`
until isolated validation, a separately approved bounded canary, and rollback
rehearsal pass.

Runtime selection and provenance use `engine` (`vllm`, `sglang`, `remote`),
`executor_slot` (`local_primary`, `local_candidate`, `remote_overflow`), and
declared capabilities. Model names remain deployment data, not routing
authority. Media state stores bounded identity/provenance metadata only; never
copy inline image bytes into durable SessionState.

Treat `apply_patch verification failed:` without an explicit numeric exit code
as failure evidence. Do not treat `Do not modify any other file` as global
read-only intent; it scopes an explicit write. Accept completion only after a
successful change-capable tool, post-change validation, and configured review.

## Superseded fixed production release — 2026-08-13

This section preserves the 2026-08-13 operational epoch. It is not current
release authority; use `docs/STATE.md` and the 2026-08-14 append-only evidence
in `docs/VALIDATION.md`.

The authenticated fixed gateway runs production `main@ffdf006a4` directly on
`0.0.0.0:9000`; role inference endpoints must remain non-wildcard. The former
Dashboard validation drop-in is retained as
`200-dashboard-validation.conf.disabled-20260813` and must not be renamed to a
`.conf` file during normal operation. Dashboard and ExecutionGraph shadow are
explicit production environment overrides; checked-in defaults remain safe.

Before gateway rollback, POST the authenticated `/v1/admin/drain`, wait for
`active_request_count=0`, stop the fixed unit, checkout the exact reviewed
release, run `uv sync --frozen`, and start/healthcheck. The measured rollback
target `88f553dec` and redeploy target `ffdf006a4` both passed the same
authenticated fast-canary hash. Do not use checkout rollback to change or
restart Candidate A.

Judge production mapping is `kimi-k3`; `glm-5.2` is rejected stale override
evidence. A structured Judge probe can pass while a multi-iteration high-risk
request still exceeds the client deadline. Keep that path fail-closed and do
not promote beyond `PILOT_ACTIVE` until its bounded termination gate passes.

The feedback epoch runtime release `fd658a1e8` supersedes that open termination
gate. Production high-risk requests use one iteration, at most two Reviewer and
Frontier calls, one Judge call, and 240 wall-clock seconds. A nonterminal final
iteration is explicitly closed as `BUDGET_EXHAUSTED`; late provider accounting
cannot replace an existing terminal verdict. The measured rollback pair is now
`90e838742` → `fd658a1e8`. Live observation remains disabled until its external
credential is rotated; do not re-enable it from repository configuration.

For enabled Executor scheduling, low/medium-risk admission uses
`deepseek-v4-flash` when the local Executor is busy or its lifecycle state is
unavailable after an explicit operator/automation disable. High/critical-risk
admission never uses Flash; when local Mistral is unavailable it uses the
configured Codex OAuth Frontier Executor, and remains fail-closed if Frontier
is unavailable. This fallback does not authorize automatic stopping of the
normally resident Executor.

When Flash omits a native tool call that the request or a required correction
demands, the Runtime retries Flash once, then makes one bounded Codex OAuth
Frontier Executor attempt. If Frontier also omits the tool call or is
unavailable, the request remains fail-closed. The client still owns tool
execution.

An authenticated operator may explicitly switch Mistral from `/admin` only
when `/v1/admin/executor` reports `control_available=true`. OFF performs the
selected exact service stop and persists lifecycle state `disabled`; active
leases or guards reject the change. Low/medium-risk requests then use
`deepseek-v4-flash`, while high/critical-risk requests use Codex OAuth Frontier
or fail closed when it is unavailable. ON starts the existing lifecycle load,
and the page polls its state, generation, ETA, and honest weight progress. A
missing trustworthy journal counter is shown as unavailable, never estimated
from elapsed time. Checked-in lifecycle, scheduling, and Dashboard defaults
remain disabled.

A Gateway restart during a lifecycle-owned load can leave durable state failed
while systemd is still activating. Do not start a second model process. Allow
the exact stop to finish, verify the unit is inactive, preserve failure events,
reset only the automation latch and role retry state with the existing
LifecycleStore recovery operations, then use authenticated `/on` once.
Readiness requires both loopback `9001` health and Dashboard state `ready`.
