# Live Observation

The Phase E foundation is disabled by default. `StateStore.event()` publishes a
sanitized subset of existing runtime events to a bounded in-memory queue. Queue
insertion is non-blocking; queue saturation or provider failure affects only
observation and never waits in the request path.

Discord uses a configured webhook and optional thread ID. Telegram uses a bot
token, chat ID, and optional message-thread ID. Events are batched and contain
only allowlisted status fields. Prompts, repository contents, credentials,
environment data, token deltas, and hidden reasoning are never selected for
publication. Provider secrets use Pydantic `SecretStr` and must arrive through a
protected runtime configuration source.

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
idempotent replay. The runtime has not sent a message to an actual Discord or
Telegram platform account; real thread lifecycle and platform identities remain
the external physical-validation gate.
