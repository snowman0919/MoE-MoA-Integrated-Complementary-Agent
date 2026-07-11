# Validation

## Environment

- `docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L`: exit `0`; detected NVIDIA GB10.
- `hf auth whoami`: exit `0`; authenticated.
- Required ports are unoccupied.

Gateway, resident systemd, model, integration, and profile evidence is recorded
below. Heavy-judge validation is appended after its first isolated startup.

## Executor Runtime

- vLLM startup: `435` seconds; readiness and `/v1/models` passed.
- Model memory: `44.31 GiB` reported by vLLM; measured available-memory drop
  `53276835840` bytes; remaining available memory `67773710336` bytes.
- Completion: `READY`; warm latency `0.103836927` seconds; `2` output tokens.
- Tool call: valid `read_file` call; ID `chatcmpl-tool-95e68c30eba02ec8`;
  arguments decoded to `/tmp/example.txt`; latency `0.828135645` seconds.
- Clean stop restored available memory to `122827276288` bytes.

## Reviewer Runtime

- First startup attempt failed: `Value error, The checkpoint you are trying to
  load has model type cohere2_moe but Transformers does not recognize this architecture.`
- vLLM `0.22.1` contains native `Cohere2MoeForCausalLM`; compatible HF config
  alias loaded all original MoE fields. `cohere_melody 0.10.0` installed per model card.
- Startup: `213` seconds; readiness and `/v1/models` passed.
- Structured result: `{"status":"approved","findings":[]}`; reasoning parsed separately.
- Latency: `4.041933448` seconds; `125` completion tokens; measured decode
  rate `30.925793709406964` tokens/second.
- Measured available-memory drop: `26989322240` bytes; remaining available
  memory `95837954048` bytes.
- Clean stop restored available memory to `121841950720` bytes.

## Planner Runtime

- Startup: `131` seconds; readiness and `/v1/models` passed.
- Strict plan JSON passed with one plan step, one acceptance criterion, and no tool call.
- A `256` token trial ended `finish_reason=length`; configured planner budget
  `1500` avoids that measured lower bound. `512` token trial completed in
  `6.963814218` seconds with `271` tokens.
- Measured decode rate: `38.91545516816371` tokens/second.
- Measured available-memory drop: `25925709824` bytes; remaining available
  memory `95916240896` bytes.
- Clean stop restored available memory to `122724655104` bytes.

## Resident Profile

- Executor + reviewer first passed with `45066366976` bytes available.
- Initial second-process trial failed before load because vLLM defaulted to
  `gpu_memory_utilization=0.92`; calibrated per-role values fixed the guard.
- First low-KV trial proved reviewer needs `0.66 GiB` for 8192 tokens; final
  reviewer and planner reservations are `750000000` bytes.
- Executor + planner + reviewer passed concurrently with all required context
  limits and `25814450176` bytes initially available.
- Final benchmark after integration: `25148334080` bytes available, exceeding
  required `20000000000` by `5148334080` bytes.
- `scripts/start-judge.sh` while resident active: exit `73`, exact output
  `resident role executor is running`.
- Current systemd resident target: executor, planner, and reviewer all active;
  final `/proc/meminfo` `MemAvailable` was `22406086656` bytes.
- Executor vLLM reported `17829` KV tokens at `16384` context; planner reported
  `59392` at `8192`; reviewer reported `8649` at `8192`.

## Gateway

- User systemd service active on `127.0.0.1:9000`.
- `/healthz`, `/readyz`, `/v1/models`, non-streaming, and streaming passed.
- Real gateway tool call ID `chatcmpl-tool-9f4743372a9de247` and JSON arguments
  survived planner/executor round trip.
- Real gateway tool-call latency: `11.151994731` seconds.
- Session `integration-tool` remained in SQLite after service restart.
- Measured gateway `/healthz` overhead: `0.000731` seconds.
- Bearer rejection, malformed tool call, timeout, HTTP 500, replay blocking,
  no-progress blocking, planner/reviewer/judge routing, rollback, redaction,
  compression, integrity, capacity, and completion gates have automated tests.

## Build And Tests

- `uv run ruff format --check .`: passed.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 18 source files.
- `uv run pytest -q`: `17 passed`, one third-party TestClient deprecation warning.
- `docker compose config -q`: passed.
- `docker compose build gateway`: passed; image
  `sha256:2a1f97eb4c54c6b5644621a3ace80ac15b9259410dcbb06cf5702b869fc3742b`.
- Targeted post-change tests: `11 passed`; Ruff and mypy passed after strict
  judge and context-tuner additions.
- Final `scripts/verify-models.sh executor reviewer planner`: all verified.
- Final incomplete-file scan under model root: zero files.

## Development Branch Validation

- `uv run pytest -q`: exit `0`; `68 passed`, one third-party TestClient warning.
- `uv run ruff check gateway/src tests`: exit `0`.
- `uv run mypy`: exit `0`; `23` source files.
- `scripts/run-mvp-benchmark.sh`: exit `0`; `10/10` synthetic fixture tasks
  passed. Input/output token metrics are explicitly unknown (`null`).
- `scripts/mine-improvements.sh`, `scripts/evaluate-improvement.sh`,
  `scripts/build-training-dataset.sh`, and `scripts/export-agentic-traces.sh`:
  exit `0`.
- `systemd-analyze --user verify systemd/*`: exit `0`.
- Read-only user-service check on `2026-07-11`: gateway `/healthz` returned
  `200` on configured tailnet address `100.125.239.72:9000`; loopback is not
  configured for this gateway. `/readyz` returned `503` because profile state
  was `failed` after judge startup hit the 16 GiB headroom gate (`exit 70`).
  Rollback completed without intervention: executor, reviewer, and planner
  returned ready; gateway `/readyz` returned `200`; available memory was
  `23037333504` bytes.
- Real gateway read-only request, session `runtime-readonly-1783700774`:
  HTTP `200`, response `READY`, usage `356` prompt / `2` completion / `358`
  total tokens.
- Real tool continuation, session `runtime-tool-1783700822`: first HTTP `200`
  response preserved tool ID `chatcmpl-tool-a8fafd00dce4b44d` for
  `read_file("/tmp/dgx-moa-validation.txt")`, usage `678` prompt / `35`
  completion / `713` total. A normalized synthetic tool observation continued
  in the same session with HTTP `200`, no additional tool call, and
  `{"output":"validation fixture"}`; usage `629` prompt / `7` completion /
  `636` total tokens.
- `scripts/validate-opencode-loop.sh` against recovered resident services:
  exit `0`; session `opencode-loop-1783701252`; authenticated discovery,
  tool-result continuation, and streaming passed.
- Consolidated `scripts/smoke-test.sh`: exit `0`; session
  `opencode-loop-1783728287`; tool continuation and streaming passed. The
  streaming check captures output before matching `[DONE]`, avoiding a
  `pipefail` false failure from `grep -q` closing its input early.
- Final read-only resident check: `/readyz` returned `200` with executor,
  planner, and reviewer ready; `MemAvailable` was `23184121856` bytes.

## Tailscale

- Attempted `tailscale serve --bg http://127.0.0.1:9000`.
- Blocker: `Serve is not enabled on your tailnet.`
- Enable URL: `https://login.tailscale.com/f/serve?node=ngaf9Ptc8f11CNTRL`.
- Funnel was never enabled or used.
