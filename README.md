# DGX MoA Agent 2.0

OpenAI-compatible, Executor-directed dynamic Mixture-of-Agents gateway. OpenCode
and other clients connect to one authenticated tailnet or LAN endpoint. The primary
`dgx-moa` path always combines a loopback-only Ollama Reasoner with the local
Executor. The Executor owns routing, native tool calls, and final synthesis; it
adds Planner, Reviewer, Codex OAuth Frontier collaboration, or the mutually
exclusive Heavy Judge only when the task and evidence require them.

`dgx-moa-fast` is the explicitly named Executor-only compatibility path.
These are the only public model paths; `dgx-moa` dynamically selects bounded
specialist and Frontier collaboration when configured and permitted.

```bash
uv sync
cp .env.example .env
uv run dgx-moa
```

Production is the human-reviewed `main` branch deployed at
`/home/kotori9/dgx-moa-agent`. `dev` is integration; recursive experiments use
isolated `auto/<layer>/<proposal-id>` worktrees created from `dev` and driven by
the stable `main` runtime.

The authenticated gateway binds `0.0.0.0:9000`, so tailnet clients use
`http://<DGX_TAILSCALE_IP>:9000/v1`, LAN clients use the host LAN address, and
local clients use `http://127.0.0.1:9000/v1`. Managed role-model inference
endpoints remain loopback-only. The currently configured external Reasoner uses
a tailnet address and is preserved as a topology audit finding, not an approved
exception. Tailscale Serve and Funnel are not required.

See `docs/API_CLIENT_MODES.md` for the model aliases, standard request and SSE
contracts, typed errors, curl/OpenAI SDK/OpenCode examples, and output limits.
See `docs/HERMES_AGENT.md` for the environment-only Hermes configuration.

The production `main` runtime implements the MoA contracts and role-aware
request statistics. Safe checked-in lifecycle control is `disabled` with an
empty unit map, and the 2026-08-14 production inspection observed the same
state. Optional-role on-demand loading is therefore not a current runtime
capability. Historical fixed/adaptive lifecycle experiments remain evidence in
`docs/VALIDATION.md`; they do not override the inspected configuration.

`dev` also contains disabled, unit-tested bounded Loop Engineering, runtime
Skills and canaries, a separate Runtime Knowledge registry, OpenCode Go GLM-5.2
Remote Judge transport, remote-first cold-start routing for local Planner and
Reviewer specialists, declarative policy, typed Evidence Graph/replay, safe
Telegram observation, privacy-filtered training candidates, and Seoul
weekly 7z packaging/retention workflows. These are not production capabilities
until the physical client/provider/archive gates in `docs/VALIDATION.md` pass.
The inspected production override currently enables several of these gated
features contrary to repository policy; that mismatch is an audit finding, not
promotion evidence.

See `docs/MODEL_LIFECYCLE.md` for model states, role policies and statistics,
retryable loading responses, blockers, status routes, circuit breaker, and
rollback. Safe checked-in lifecycle control is deliberately `disabled` with an
empty unit map; production authorization remains an ignored operator-owned
override and must never be copied into Git.

Authoritative references: `docs/STATE.md` for current state,
`docs/OPERATIONS.md` for operation, `docs/VALIDATION.md` for measured evidence,
`docs/MOA_ORCHESTRATION.md` for collaboration, `docs/FRONTIER.md` for Codex OAuth,
`docs/TRACE_SCHEMA.md` for logging, `docs/LOOP_ENGINEERING.md` for the disabled
loop foundation, `docs/SKILLS.md`, `docs/KNOWLEDGE_BASE.md`,
`docs/REMOTE_JUDGE.md`, `docs/SPECIALIST_ROUTING.md`, `docs/LIVE_OBSERVATION.md`,
`docs/TRAINING_DATA.md`, and `docs/WEEKLY_PACKAGING.md` for the new disabled
workflows, `docs/RUNTIME_SELF_IMPROVEMENT.md` for governed Prompt/Policy/Routing
candidates, and `docs/RECURSIVE_IMPROVEMENT.md` for the branch workflow.
