# NVIDIA NIM Remote Judge

Configure NVIDIA NIM only through the protected runtime environment:

```bash
DGX_MOA_REMOTE_JUDGE='{"enabled":true,"provider":"nvidia_nim","mode":"selective","model":"z-ai/glm-5.2","endpoint":"${NVIDIA_NIM_BASE_URL}","api_key_env":"NVIDIA_API_KEY","timeout_seconds":120,"max_retries":1,"max_calls_per_request":2}'
```

Set `NVIDIA_NIM_BASE_URL` and `NVIDIA_API_KEY` outside Git. Never print the
effective object or environment. The provider calls only the configured HTTPS
OpenAI-compatible `/v1/models` and `/v1/chat/completions` routes. NVIDIA details
do not enter the controller.

Startup construction rejects unresolved endpoint variables. Availability is a
credentialed model-catalog probe. A successful health probe does not prove
judgment quality; the full physical matrix in `docs/REMOTE_JUDGE.md` is the
enablement gate.

Rollback is removal of `DGX_MOA_REMOTE_JUDGE` followed by a fixed gateway-unit
restart and authenticated health verification. The disabled configuration does
not require an NVIDIA key and leaves the existing local Heavy Judge profile
available as an operator-only compatibility path.
