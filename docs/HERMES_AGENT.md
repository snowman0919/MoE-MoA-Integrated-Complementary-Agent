# Hermes Agent

Keep the gateway credential in the Hermes process environment. Do not put a
credential value in a configuration file. Hermes Agent `0.18.2` reads the
following structure from `$HERMES_HOME/config.yaml`; the `api_key` value is an
environment reference, not the credential itself.

```yaml
model:
  default: dgx-moa-agent
  provider: custom
  base_url: http://100.125.239.72:9000/v1
  api_key: ${DGX_MOA_API_KEY}
  context_length: 65536
  max_tokens: 16384

platform_toolsets:
  cli:
    - file
```

Hermes owns the native tool loop: it supplies tool schemas, executes returned
native tool calls, and sends each matching tool result in the next request. The
`dgx-moa-agent` uses the always-active Reasoner + Executor core; the gateway does not insert a
planner or reviewer into that loop.

This exact configuration was measured on 2026-07-18 with Hermes Agent `0.18.2`.
A documented one-shot invocation returned `HERMES_OK` in one streaming API call.
A second invocation issued native `read_file`, received the isolated fixture,
and continued with `HERMES_TOOL_OK`; those historical gateway requests recorded executor-only
roles and `stream_completed`. Supplying only `OPENAI_API_KEY` did not authenticate
this non-OpenAI custom host in version `0.18.2`; the explicit environment
reference under `model.api_key` is required for this gateway.

During model loading or a profile transition, the gateway can return HTTP 503
with `Retry-After`. Wait for the indicated interval before retrying.
