# Operations

## Dynamic MoA operational boundary

The primary model alias is `dgx-moa`; it requires the external Ollama Reasoner
and local Executor. `dgx-moa-fast` is the explicit degraded/low-latency
Executor-only alias. Do not silently reroute a failed default Reasoner request
to fast mode. `dgx-moa-agent` keeps the Reasoner + Executor core while OpenCode
or Hermes owns native tool execution. See `MOA_ORCHESTRATION.md`.

Frontier uses an existing Codex OAuth profile and read-only `codex exec`; no
OpenAI API key is configured. Enablement requires both the gateway feature gate
and a reviewed Frontier config. Safe checked-in defaults remain disabled. See
`FRONTIER.md`.

The 2026-07-21 production deployment passed that gate and enables Frontier with
ordered `primary`/`secondary` OAuth profiles. Safe checked-in defaults remain
disabled; production enablement stays in the ignored 0600 environment file.

Gateway authentication may use legacy `DGX_MOA_API_KEY` or the preferred JSON
mapping `DGX_MOA_API_KEYS`, whose keys are non-secret usage IDs. Rotate values
outside Git. `/v1/runtime-status` exposes content-free aggregate usage by ID.
The production IDs are `legacy`, `opencode`, `hermes`, and `operator`; never put
their values in Git, logs, traces, or documentation.

When the admin API is enabled, `DGX_MOA_ADMIN_TOKEN_IDS` selects the configured
keys that initially receive administrator authority. General keys can call only
the authenticated AI API. Administrator keys can also open `/admin/api-keys`
and call `/v1/admin/api-keys`; `DGX_MOA_MAX_ADMIN_API_KEYS` bounds active
administrator keys. The operator UI supports named creation, raw-value viewing,
rotation, expiry, revocation, cumulative request/token limits, and content-free
request-class/model usage charts.

Raw key viewing is an explicit internal-only tradeoff. The key registry is in
the state database, whose mode is forced to `0600`; responses use `no-store`,
the UI keeps the entered operator credential only in memory, and management
events contain names/actions but no key values. State database backups must be
treated as secrets. A limit reached response is `429`; expired or revoked keys
receive the same `401` as an unknown key.

## Gateway and systemd

```bash
scripts/install-systemd-user.sh
systemctl --user status dgx-moa.target
journalctl --user -u dgx-moa-gateway.service -f
scripts/healthcheck.sh
```

Gateway binds the configured tailnet address on port `9000`. Local model servers
bind only ports `8101`, `8102`, `8103`, and `8110` on loopback. The configured
Ollama Reasoner is an external dependency and must remain protected by its own
network boundary; this gateway does not expose or proxy its native API.

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
DGX_MOA_LOOP_ENGINEERING='{"enabled":true,"defaults":{"iterations":4,"tool_calls":30,"reasoner_reentries":4,"planner_calls":2,"reviewer_calls":2,"frontier_calls":2,"judge_calls":2,"tokens":250000,"external_cost_usd":10,"wall_clock_seconds":1800},"duplicate_fingerprint_limit":2,"no_progress_iteration_limit":2,"local_failures_before_frontier":2,"request_class_overrides":{},"risk_level_overrides":{}}'
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

## Live observation operations

Checked-in `gateway.live_observation.enabled` remains `false`. Supply webhook and
bot credentials only through the protected
`DGX_MOA_LIVE_OBSERVATION` runtime object. Never commit them. Controls require
both `admin_api_enabled` and `live_observation.controls.enabled`, plus an empty-
by-default user/role policy. Issue request-scoped nonces through
`POST /v1/admin/observation/nonces` and submit bounded commands through
`POST /v1/admin/observation/commands`. See `docs/LIVE_OBSERVATION.md`.

The reviewed production override currently enables only Telegram observation;
Discord and controls remain disabled. The token and target are 0600 files outside
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
DGX_MOA_LIFECYCLE_UNIT_MAP='{"executor":"dgx-moa-dev-executor.service","planner":"dgx-moa-dev-planner.service","reviewer":"dgx-moa-dev-reviewer.service","reasoner":"dgx-moa-dev-reasoner.service"}'
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

## Phase 3 measured runtime decision

The selected executor command remains `--max-model-len 65536`,
`--max-num-seqs 1`, `--kv-cache-memory-bytes 1700000000`,
`--gpu-memory-utilization 0.5`, and `--moe-backend MARLIN`. Do not add the
rejected FP8, eager, prefix, chunked-prefill, CPU-offload, or KV-offload settings
to production from this study.

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
started separately. The external Ollama Reasoner is not a member of the local
target and must be healthy for default product readiness. Existing stop
verification still checks the legacy local Reasoner unit/port as cleanup along
with Executor/Planner/Reviewer; it never targets the external Ollama service.

The reviewed target and exact adaptive unit map are installed in production;
safe checked-in lifecycle defaults remain disabled. Do not change the installed
target or unit map in place. Any later topology change still requires a reviewed
PR/deployment that verifies the installed diff, daemon reload, profile
transition, readiness, typed cold-role behavior, and rollback. A cold required
optional role currently receives the typed retryable loading/unavailable `503`
contract.

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

## Tailscale

Set `DGX_MOA_BIND_HOST` to the resolved tailnet IPv4 address. Never use
Tailscale Serve or Funnel; tailnet ACLs and bearer auth remain administrator-controlled.

## OpenCode

Set `DGX_MOA_API_KEY` on the client, then copy
`config/opencode.example.json` into the OpenCode configuration directory.
Configuration is identical on macOS and Linux; only environment setup differs.
The live validation harness explicitly selects `dgx-moa-agent` for both its
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

Use `/v1/models` to discover `dgx-moa`, `dgx-moa-fast`, `dgx-moa-agent`, and
`dgx-moa-orchestrated`. Direct external agents should select `dgx-moa-agent` and
own the native tool loop. Select `dgx-moa-fast` only for an intentional
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
scripts/tune-context.sh resident
scripts/tune-context.sh judge
```

Downloads are pinned, resumable, lock-protected, and never remove unrelated caches.

To use a prepared executor LoRA, set `models.executor.lora_adapter` to its local
path. Omit it for the validated original post-trained checkpoint. This project
does not train adapters.

Production deployment is a fast-forward/pull of reviewed `main` into
`/home/kotori9/dgx-moa-agent`, followed by proportional checks. `dev` may be
deployed there only as an explicitly identified validation runtime; its traces
must use `runtime_channel=dev` and must never be labeled production.
## Runtime metrics

The gateway exposes the Goal-specific fixed metric set at
authenticated `GET /metrics`. Metrics are label-free: request IDs, user IDs,
repository paths, prompts, and failure text are never accepted or retained by
the collector. Loop counters are fed by the append-only event boundary; Skill,
observer, and training counters are overlaid from their bounded stores.
Not-yet-run weekly operations report zero. The authenticated production endpoint
has physical Training counter evidence.

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
