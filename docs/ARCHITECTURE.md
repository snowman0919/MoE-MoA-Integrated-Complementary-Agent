# Architecture

OpenCode connects directly over tailnet TCP to the configurable gateway port
`9000`. Deterministic controller stores session state in SQLite and calls
loopback-only role servers on ports `8101`, `8102`, `8103`, or `8110`.
Resident and judge profiles are mutually exclusive systemd targets.

The public aliases separate client policy without adding gateways:
`dgx-moa-chat` and `dgx-moa-agent` call only the executor, while
`dgx-moa-orchestrated` deterministically selects executor-only, planner/executor,
or planner/executor/reviewer roles from the request class. External agents own
the native tool-call/result loop. Standard OpenAI fields are forwarded to the
executor; project metadata remains optional.

Streaming is a bounded forwarding path, not a review buffer. Complete SSE events
are released immediately, native deltas are preserved, duplicate DONE events
are filtered, and clean EOF receives one DONE. Capture and per-event bounds are
both 1,000,000 bytes. Streaming review is deferred. Non-streaming review uses at
most 16,000 characters of external evidence; low-risk review failure preserves
valid executor output, while high-risk orchestration may fail closed.

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
