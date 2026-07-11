# Architecture

OpenCode connects directly over tailnet TCP to the configurable gateway port
`9000`. Deterministic controller stores session state in SQLite and calls
loopback-only role servers on ports `8101`, `8102`, `8103`, or `8110`.
Resident and judge profiles are mutually exclusive systemd targets.

Resident runs the Qwen3-Coder-Next executor, 30B planner, and 30B reviewer.
Judge runs only `nvidia/Mistral-Medium-3.5-128B-NVFP4`; coding requests return
retryable `503` while judge profile is active. Health is public; inference uses
`DGX_MOA_AUTH_ENABLED`, and admin profile switching is disabled by default.

`main` is the reviewed production control plane and trace producer. `dev` is the
integration branch. Future recursive work follows `main` MoA -> OpenCode -> an
isolated `auto/*` worktree created from `dev`; candidate code runs only as an
evaluation target and never edits the production worktree.

Primary session state and event references live in SQLite. Append-oriented v2
JSONL traces are date-partitioned by runtime channel and origin and indexed from
SQLite. State persistence fails closed; secondary trace failure degrades
observability without discarding an otherwise safe coding task.
