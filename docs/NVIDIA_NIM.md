# NVIDIA NIM Remote Judge

Configure NVIDIA NIM only through the protected runtime environment:

```bash
DGX_MOA_REMOTE_JUDGE='{"enabled":true,"provider":"nvidia_nim","mode":"selective","model":"z-ai/glm-5.2","endpoint":"${NVIDIA_NIM_BASE_URL}","api_key_env":"NVIDIA_API_KEY","timeout_seconds":120,"max_retries":1,"max_calls_per_request":2}'
```

Set `NVIDIA_NIM_BASE_URL` and `NVIDIA_API_KEY` outside Git. Never print the
effective object or environment. The provider calls only the configured HTTPS
OpenAI-compatible `/v1/models` and `/v1/chat/completions` routes. NVIDIA details
do not enter the controller. The endpoint accepts either the service root
(`https://integrate.api.nvidia.com`) or NVIDIA's documented OpenAI base URL
(`https://integrate.api.nvidia.com/v1`) and normalizes both to one `/v1`.

The current official references are NVIDIA's
[GLM-5.2 inference API](https://docs.api.nvidia.com/nim/reference/z-ai-glm-5.2-infer)
and [NIM LLM API reference](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html).

Startup construction rejects unresolved endpoint variables. Availability is a
credentialed, five-second-bounded model-catalog probe. `/healthz` and `/readyz`
report `disabled`, `available`, or `unavailable` without exposing credentials.
A successful health probe does not prove
judgment quality; the full physical matrix in `docs/REMOTE_JUDGE.md` is the
enablement gate.

After placing a fresh credential only in the process environment, run the live
matrix without printing either variable:

```bash
uv run scripts/validate-remote-judge.py \
  --output /tmp/dgx-moa-live-remote-judge/validation.json
```

The validator records only verdict categories, criterion states, counts, and
token usage. It never records evidence text, endpoints, headers, or credentials.
It requires valid approval, unsupported-claim rejection, failed-test detection,
missing-criterion detection, bounded edits, corrected recheck approval, and
local third-call rejection before writing `status=passed`.

Rollback is removal of `DGX_MOA_REMOTE_JUDGE` followed by a fixed gateway-unit
restart and authenticated health verification. The disabled configuration does
not require an NVIDIA key and leaves the existing local Heavy Judge profile
available as an operator-only compatibility path.
