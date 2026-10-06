# Hermes Agent

Keep the gateway credential in the Hermes process environment. Do not put a
credential value in a configuration file. Hermes Agent `0.18.2` reads the
following structure from `$HERMES_HOME/config.yaml`; the `api_key` value is an
environment reference, not the credential itself.

```yaml
model:
  default: dgx-moa
  provider: custom
  base_url: http://100.125.239.72:9000/v1
  api_key: ${DGX_MOA_API_KEY}
  context_length: 131072
  max_tokens: 16384

platform_toolsets:
  cli:
    - file
```

Hermes owns the native tool loop: it supplies tool schemas, executes returned
native tool calls, and sends each matching tool result in the next request. The
`dgx-moa` uses the Reasoner + Executor core with runtime-selected optional roles.

This exact configuration was measured on 2026-07-18 with Hermes Agent `0.18.2`.
A documented one-shot invocation returned `HERMES_OK` in one streaming API call.
A second invocation issued native `read_file`, received the isolated fixture,
and continued with `HERMES_TOOL_OK`; those historical gateway requests recorded executor-only
roles and `stream_completed`. Supplying only `OPENAI_API_KEY` did not authenticate
this non-OpenAI custom host in version `0.18.2`; the explicit environment
reference under `model.api_key` is required for this gateway.

During model loading or a profile transition, the gateway can return HTTP 503
with `Retry-After`. Wait for the indicated interval before retrying.

For a Hermes client that supports `model.default_headers`, send the actual
client workspace to the Gateway preflight boundary. Keep the local file-tool
anchor and HTTP workspace identity consistent:

```yaml
model:
  default_headers:
    X-Workspace-Path: /absolute/client/workspace
    X-Workspace-ID: hermes-workspace
```

Set `TERMINAL_CWD=/absolute/client/workspace` in the Hermes process environment.
These identify the client tool workspace; the Gateway does not execute those
file tools. An invented tool name or a path outside the declared workspace
still fails preflight. Tool streams permit one bounded Executor correction and
then return an explicit failure; reconnects must not be treated as completion.

When no workspace header is available, the Gateway can use this session's
successful native terminal `pwd` observation as its client workspace boundary.
`pwd -P` and the historical `pwd && ls -a` probe are also recognized. The first
successful probe establishes the fallback scope; later `cd`/`pwd` commands do
not expand it. Failed probes, arbitrary file text, model-suggested paths, `/`,
and observations from another session never establish a workspace. Explicit
workspace metadata or configured roots take precedence. The Executor receives
the resulting allowed roots; absolute paths inside them pass normal preflight
and paths outside them remain rejected. This does not execute client tools on
the Gateway host.

After an earlier provider failure has paused a Hermes goal, retry or resume that
goal after the Gateway fix is deployed; restarting the Gateway does not resume
a paused client goal. Do not add a fallback provider to mask a workspace
identity failure.
