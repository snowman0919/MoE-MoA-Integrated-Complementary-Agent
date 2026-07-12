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

Rotate the key by replacing `DGX_MOA_API_KEY` in `.env` and restarting:

```bash
systemctl --user restart dgx-moa-gateway.service
```
