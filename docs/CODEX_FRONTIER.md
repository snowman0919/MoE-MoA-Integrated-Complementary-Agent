# Codex frontier escalation

Optional only. Local MoA is default; Mistral is local heavy judge. Frontier uses
bounded `codex exec --json`, not experimental App Server. Installed CLI verified:
`codex-cli 0.144.1`; device auth and JSONL are available. Official OpenAI model
documentation identifies GPT-5.6 Sol as `gpt-5.6-sol`; runner passes
`model_reasoning_effort="high"`, verified from installed Codex configuration.
Profile smoke still confirms account entitlement before first real run.

Profiles live outside repository under `~/.local/share/dgx-moa/codex-profiles`.
Run `scripts/codex-profile.sh login primary` or `login secondary`; profile directories
are owner-only and credentials are neither read nor logged by project code.

`scripts/run-frontier-codex.sh` requires explicit profile, task, worktree, model, and
uses `codex exec --json --sandbox workspace-write`. It has one nonblocking lock per
profile, accepts only a Git worktree registered by production repository on a
`frontier/` or `auto/frontier/` branch, and never rotates accounts, pushes, merges,
deploys, or changes systemd/network/config secrets. Session state enforces one
frontier invocation and at most three recursive cycles.

The systemd template is disabled by default. An operator starting it must provide
`DGX_MOA_FRONTIER_TASK` and `DGX_MOA_FRONTIER_WORKTREE` for that one run; absent
values fail closed. `DGX_MOA_CODEX_MODEL` may override reviewed default.

Each candidate needs focused tests, benchmark, scope validation, secret scan, local
review, and human approval. Usage-limit, auth, timeout, protocol, scope, and validation
failures are explicit trace classes. No remote frontier administration endpoint exists.
