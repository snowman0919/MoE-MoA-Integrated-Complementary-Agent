# Operations

## Gateway and systemd

```bash
scripts/install-systemd-user.sh
systemctl --user status dgx-moa.target
journalctl --user -u dgx-moa-gateway.service -f
scripts/healthcheck.sh
```

Gateway binds the configured tailnet address on port `9000`. Model servers bind
only ports `8101`, `8102`, `8103`, and `8110` on loopback.

```bash
scripts/runtime-status.sh
scripts/audit-trace-completeness.sh data/traces
```

Runtime status reports service state/restarts, recent gateway/model failures,
SQLite session counts, profile rollback events, and measured current memory.
Unknown measurements remain explicit; they are not inferred.

## Profiles

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
