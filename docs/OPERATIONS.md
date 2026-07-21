# Operations

## Dynamic MoA operational boundary

The primary model alias is `dgx-moa`; it requires the external Ollama Reasoner
and local Executor. `dgx-moa-fast` is the explicit degraded/low-latency
Executor-only alias. Do not silently reroute a failed default Reasoner request
to fast mode. `dgx-moa-agent` keeps the Reasoner + Executor core while OpenCode
or Hermes owns native tool execution. See `MOA_ORCHESTRATION.md`.

Frontier uses an existing Codex OAuth profile and read-only `codex exec`; no
OpenAI API key is configured. Enablement requires both the gateway feature gate
and a reviewed Frontier config. Keep it disabled until the physical matrix in
`VALIDATION.md` passes. See `FRONTIER.md`.

Gateway authentication may use legacy `DGX_MOA_API_KEY` or the preferred JSON
mapping `DGX_MOA_API_KEYS`, whose keys are non-secret usage IDs. Rotate values
outside Git. `/v1/runtime-status` exposes content-free aggregate usage by ID.

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

Lifecycle states and safety rules are canonical in
`docs/MODEL_LIFECYCLE.md`.

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

Do not copy the target into production or restart production units as part of
this repository change. Migration requires a later human-reviewed PR/deployment
that verifies the installed unit diff, daemon reload, profile transition,
readiness, typed cold-role behavior, and rollback. Checked-in lifecycle remains
disabled, so this target change alone does not provide on-demand optional-role
startup. With a separately approved fixed/adaptive lifecycle and validated unit
map, a request that requires a cold optional role receives the typed retryable
loading/unavailable `503` contract.

Rollback restores the previous resident target requirements for gateway,
executor, planner, and reviewer, restores the previous readiness/stop script
arrays, reloads units, and verifies the prior profile. Rollback must be reviewed
and deployed through the same production process; do not edit installed units
in place.

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
