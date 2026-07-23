# API client modes

The authenticated gateway exposes one OpenAI-compatible API at
`http://100.125.239.72:9000/v1` on the tailnet. Keep `DGX_MOA_API_KEY` in the
client environment and discover the available aliases before selecting one:

Clients on the gateway host may instead use `http://127.0.0.1:9000/v1`. The
loopback socket proxies to the same gateway, so authentication is still
required.

```bash
export DGX_MOA_BASE_URL=http://100.125.239.72:9000/v1
curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY}" \
  "${DGX_MOA_BASE_URL}/models"
```

`GET /v1/models` returns the current aliases with `context_length: 65536`.

| Model alias | Gateway policy | Tool-loop owner |
| --- | --- | --- |
| `dgx-moa` | Default Reasoner + Executor core | Client, when tools are supplied |
| `dgx-moa-fast` | Explicit Executor-only compatibility path | Client, when tools are supplied |
| `dgx-moa-agent` | Reasoner + Executor native agent turns | External agent client |
| `dgx-moa-orchestrated` | Executor-directed dynamic Planner, Reviewer, Frontier, and Judge selection | Client executes native tool calls |

`dgx-moa-fast` is always Executor-only. Other MoA profiles invoke the Reasoner;
the default does not silently bypass it. In agent mode the gateway preserves
native OpenAI tool-call IDs, function names,
and JSON arguments; the client executes each call and sends the assistant
`tool_calls` message plus the matching `tool` result in its next request. The
gateway does not run that tool loop for the client.

Orchestrated mode always begins with Reasoner + Executor. The Executor returns a
structured routing decision; deterministic safety policy may require Planner,
Reviewer, Frontier, or Heavy Judge. A low-risk optional review failure preserves
valid evidence and lowers confidence; a required Frontier/review failure fails
closed with a typed error. Streaming review remains deferred from the response
path.

## Request contract

`POST /v1/chat/completions` requires `model` and a non-empty `messages` list. It
accepts and forwards the standard executor request fields:

- `stream`
- `tools`
- `tool_choice`
- `parallel_tool_calls`
- `temperature`
- `top_p`
- `max_tokens`
- `stop`
- `stream_options`
- `response_format`

Other OpenAI-compatible fields, such as `seed`, are also preserved for the
executor. `tool_choice` and `parallel_tool_calls` require `tools`, while
`stream_options` requires `stream: true`.

Project `metadata` and `X-Session-ID`/provenance headers are optional. Standard
clients do not need them. The executor output budget defaults to 4,096 tokens;
`max_tokens` may raise it to at most 16,384. The public executor context remains
65,536 tokens.

Training eligibility is the exception: clients must send a stable
`X-Workspace-ID` plus `X-Workspace-Path`, and the operator must map that exact
ID to `training_allowed` in `gateway.training_data.repository_policies`.
Requests without those headers remain the shared `external-api` identity and
fail closed as `unknown`. `X-Repository-Branch`, `X-Repository-Commit`, and
`X-Dirty-State` add reproducibility metadata but do not grant eligibility.

```bash
curl -fsS -H "Authorization: Bearer ${DGX_MOA_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"dgx-moa","messages":[{"role":"user","content":"Hello"}]}' \
  "${DGX_MOA_BASE_URL}/chat/completions"
```

The official OpenAI Python client can use the same standard shape:

```python
import os

from openai import OpenAI

client = OpenAI(
    base_url=os.environ["DGX_MOA_BASE_URL"],
    api_key=os.environ["DGX_MOA_API_KEY"],
)
response = client.chat.completions.create(
    model="dgx-moa",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

OpenCode uses the same direct agent contract:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "dgx-moa": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DGX MoA",
      "options": {
        "baseURL": "http://100.125.239.72:9000/v1",
        "apiKey": "{env:DGX_MOA_API_KEY}"
      },
      "models": {
        "dgx-moa-agent": {"name": "DGX MoA Agent"}
      }
    }
  },
  "model": "dgx-moa/dgx-moa-agent"
}
```

## Errors

Errors use the OpenAI envelope `error.message`, `error.type`, `error.code`, and
`error.param`. For example, `max_tokens: 16385` returns HTTP 400:

```json
{
  "error": {
    "message": "max_tokens exceeds server maximum 16384",
    "type": "invalid_request_error",
    "code": "invalid_request",
    "param": "max_tokens"
  }
}
```

Authentication failures return 401, unknown models return 404 with
`code: model_not_found`, invalid field combinations return 422, repeated failed
tool calls return 409, backend failures return 502, and attributed stage
timeouts return 504 with a stage-specific code. Coding requests unavailable
during model/profile loading return 503 with `Retry-After`; clients should wait
for that interval before retrying.

## Streaming

With `stream: true`, each complete upstream SSE event is forwarded immediately
as it arrives; the gateway does not wait for executor completion or reviewer
completion. Native assistant and tool-call deltas remain byte-preserved. The first upstream
`data: [DONE]` ends the response, later duplicates are discarded, and a clean
upstream EOF without DONE gets exactly one synthesized DONE.

Observation capture is bounded to 1,000,000 bytes and a single SSE event is
bounded to 1,000,000 bytes. These bounds do not delay normal event forwarding.
Upstream completion IDs, timestamps, model fields, usage, finish reasons, and
tool-call fields are preserved. `finish_reason=length` is returned unchanged,
recorded as truncation, and never treated as completed work.
