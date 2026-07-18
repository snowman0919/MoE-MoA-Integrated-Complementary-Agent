# Hermes Agent

Keep the gateway credential in the Hermes process environment. Do not put a
credential value in a configuration file.

```yaml
provider: custom_openai
base_url: http://100.125.239.72:9000/v1
api_key: ${DGX_MOA_API_KEY}
model: dgx-moa-agent
```

Hermes owns the native tool loop: it supplies tool schemas, executes returned
native tool calls, and sends each matching tool result in the next request. The
`dgx-moa-agent` alias is a direct executor path; the gateway does not insert a
planner or reviewer into that loop.

During model loading or a profile transition, the gateway can return HTTP 503
with `Retry-After`. Wait for the indicated interval before retrying. Physical
validation of this phase-one Hermes configuration is deferred to Task 9; this
document does not claim a measured client completion.
