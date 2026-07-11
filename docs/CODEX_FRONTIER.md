# Codex frontier escalation

Optional only. Local MoA is default; Mistral is local heavy judge. Frontier uses
bounded `codex exec --json`, not experimental App Server. Installed CLI verified:
`codex-cli 0.144.1`; device auth and JSONL are available. CLI help does not expose
a verified GPT-5.6 Sol model ID, so `config/codex-frontier.example.yaml` leaves it
unset. Operator records supported ID after interactive login, with `reasoning_effort: high`.

Profiles live outside repository under `~/.local/share/dgx-moa/codex-profiles`.
Run `scripts/codex-profile.sh login primary` or `login secondary`; profile directories
are owner-only and credentials are neither read nor logged by project code.

`scripts/run-frontier-codex.sh` requires explicit profile, task, worktree, model, and
uses `codex exec --json --sandbox workspace-write`. It has one nonblocking lock per
profile, rejects production worktree, requires a verified model ID, and never rotates
accounts, pushes, merges, deploys, or changes systemd/network/config secrets.

The systemd template is disabled by default. An operator starting it must provide
`DGX_MOA_FRONTIER_TASK`, `DGX_MOA_FRONTIER_WORKTREE`, and `DGX_MOA_CODEX_MODEL` for
that one run; absent values fail closed.

Each candidate needs focused tests, benchmark, scope validation, secret scan, local
review, and human approval. Usage-limit, auth, timeout, protocol, scope, and validation
failures are explicit trace classes. No remote frontier administration endpoint exists.
