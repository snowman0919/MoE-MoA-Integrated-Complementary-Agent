# Live Observation

The Phase E foundation is disabled by default. `StateStore.event()` publishes a
sanitized subset of existing runtime events to a bounded in-memory queue. Queue
insertion is non-blocking; queue saturation or provider failure affects only
observation and never waits in the request path.

The reviewed production selection uses Telegram with a bot token, chat ID, and
optional message-thread ID. The implementation also retains an optional Discord
webhook transport for isolated compatibility tests, but the operator explicitly
excluded Discord from production and release gating on 2026-07-22. Events are
batched and rendered
as readable multi-line cards. The allowlist covers request, Reasoner, Planner,
Executor, Knowledge, Skill, Reviewer, Frontier, Judge, tool, loop, failure,
policy, approval, and terminal lifecycle events. Judge cards expose only the
verdict/risk/recheck state, never finding or correction prose. An operator may
separately enable the bounded user prompt and the
Reasoner's structured artifact (assumptions, constraints, conclusions,
hypotheses, evidence references, recommended actions, and a confidence
category). Hidden model reasoning is never available to this path. Credentials,
environment data, and token deltas
remain excluded, and the selected content is still passed through secret
redaction. Telegram and Discord are external processors even when the gateway
itself is tailnet-only. Provider secrets use Pydantic `SecretStr` and must arrive
through a protected runtime configuration source.

Optional controls are separately disabled. The only accepted commands are
`approve`, `reject`, `pause`, `resume`, `terminate`, `show-status`,
`show-findings`, and `show-budget`; arbitrary commands and shell payloads have
no schema path. The admin-authenticated command API additionally requires a
provider/user allowlist, role permission, request-scoped expiring nonce, and
idempotency key. Nonces and command audit rows use the existing SQLite WAL
database. Observation remains usable with controls disabled.

```yaml
gateway:
  live_observation:
    enabled: false
    level: normal
    include_prompt: false
    include_reasoner_artifact: false
    max_content_characters: 2000
    queue_size: 256
    batch_size: 10
    batch_interval_seconds: 2
    request_timeout_seconds: 10
    controls:
      enabled: false
      nonce_ttl_seconds: 300
      allowed_users: {}
      role_permissions: {}
```

An isolated 2026-07-22 physical check sent Discord- and Telegram-shaped requests
through a real loopback HTTP server, including thread targets, safe payload
projection, HTTP 429, connection outage, and non-blocking failure isolation.
Separate checks passed allowlist denial, scoped nonce, expiration, audit, and
idempotent replay.

The real Telegram bot `@kodex9_AI_observer_bot` then authenticated, discovered
one user-initiated private target, and accepted a safe validation event. Its
token and target live only under `/home/kotori9/.config/dgx-moa/` and the ignored
0600 production environment; no credential or chat ID is tracked or documented.
Production Telegram observation is enabled with controls disabled. A real core
request produced three sent events, zero drops, and zero Telegram errors.
Discord remains unconfigured by design and is not a production release gate.
