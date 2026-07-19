# Security

- Role-model endpoints bind to loopback. The gateway binds only the configured
  tailnet address and is the sole inference ingress.
- Direct tailnet TCP is the ingress; Tailscale Serve and Funnel are not used.
- Tailnet ACL and optional gateway bearer authentication protect inference.
- API key lives only in untracked `.env` and client environment variables.
- Authentication compares tokens in constant time.
- Trace export recursively redacts token, password, secret, and API-key fields.
- Production traces default to `requires_review`; collection never implies export.
- Recursive worktrees cannot edit the production working tree, and candidate MoA
  code is never the primary executor for its own change.
- Profile switching is file-locked and mutually exclusive.
- Heavy judge switching is bounded to once per task in controller state.
- Model repository trust and runtime support are recorded before use.

## Phase 4 isolated evidence

- OpenCode and Hermes received disposable `HOME`, XDG data/cache/config/state,
  and temporary directories below the validation root. Hermes also received a
  disposable `HERMES_HOME`.
- The random validation credentials existed only in owned process
  environments. Retained OpenCode/Hermes stores, databases, logs, and
  unparseable telemetry were removed after metadata extraction.
- A recursive retained-root audit found zero forbidden prompt/output/tool/key
  fields or values, zero JSON parse errors, and zero raw DB/log files.
- Warm and lifecycle production snapshots were identical across Git/index,
  tracked-file metadata, units, listeners, and runtime inventory. Production
  mutation count was zero.
- Independent review concluded `Critical=0` and `Important=0`. This permits
  only the draft PR boundary and grants no merge, deploy, topology-change, or
  production-restart authority.

Rotate the key by replacing `DGX_MOA_API_KEY` in `.env` and restarting:

```bash
systemctl --user restart dgx-moa-gateway.service
```
