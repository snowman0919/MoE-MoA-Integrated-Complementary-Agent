# Architecture

OpenCode connects directly over tailnet TCP to the configurable gateway port
`9000`. Deterministic controller stores session state in SQLite and calls
loopback-only role servers on ports `8101`, `8102`, `8103`, or `8110`.
Resident and judge profiles are mutually exclusive systemd targets.

Resident runs the Qwen3-Coder-Next executor, 30B planner, and 30B reviewer.
Judge runs only `nvidia/Mistral-Medium-3.5-128B-NVFP4`; coding requests return
retryable `503` while judge profile is active. Health is public; inference uses
`DGX_MOA_AUTH_ENABLED`, and admin profile switching is disabled by default.
