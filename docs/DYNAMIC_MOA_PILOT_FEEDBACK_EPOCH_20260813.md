# Dynamic MoA Pilot Feedback Epoch — 2026-08-13

## Release

- Parent context epoch SHA-256: `75ab6b8e1458a4e0a480ba0769fb084693c8b2c2c852a717fdf048a630aebc82`
- Runtime code release: `fd658a1e81c3cacd869f2ced4b04a3ca2c076cc3`
- Rollback predecessor: `90e8387429e39279f304c0738f82669689dac03e`
- Status: `PILOT_ACTIVE`; the Pilot objective is implemented and physically
  qualified. Post-Pilot beta/stable research gates remain deferred.

## Feedback-driven corrections

Four one-off production canaries exposed high-impact defects. The fixes were
made at their shared boundaries: raw ASGI disconnect delivery and owner-task
cancellation, terminal-loop usage accounting, public-content validation for
Flash overflow, and explicit final-iteration budget termination. No new
dependency or service was added. Live observation was disabled after its local
credential was exposed during operator inspection; the credential is absent
from Git and must be rotated externally before that optional channel is enabled.

Role Context A/B v5 is authoritative at
`data/diagnostics/role-context-ab/20260813-v5/result.json`, SHA-256
`76c31d57c7706d4c555be929e15b7a62b71e27ff0f08379841e15d90b6b6e062`.
Direct evidence changed Planner corrections 0→2, Reviewer critical recall
false→true, missed criteria 4→0, and completion/verified completion
false→true. Frontier criterion acceptance is 2→2, closing the v4 regression.

## Final physical request

Authenticated session `prod-critical-final-20260813` reached the fixed gateway
at `0.0.0.0:9000` and returned HTTP 200 with exact
`CRITICAL_FINAL_OK` (SHA-256
`74018f7facf46adf0883bf713ff916872c76a28afdccfc0ee0baa8e554c23a5f`).
The durable log records static graph compilation followed by runtime projections
for Reasoner, Planner, Frontier A, Executor, Reviewer, and Judge. Frontier A
used Codex OAuth `primary`, `gpt-5.6-sol`, configured `xhigh`, architecture
mode, 15,759 prompt tokens, 297 completion tokens, and 14,808.631 ms. Reviewer
approved once and Judge `kimi-k3` approved once. No provider provenance was
returned to the client.

The same release physically proved non-stream disconnect propagation:
`prod-disconnect-v2-20260813` ended `cancelled` with active leases at zero.
DeepSeek V4 Flash overflow returned a non-empty public answer through the
cross-key scheduler while the owner request stayed on local Mistral. Chat,
Responses streaming, native tool call, same-session tool continuation, and
per-key Dashboard/request isolation passed. The post-heavy recovery request
returned HTTP 200 and the gateway retained restart count zero.

## Runtime and rollback

Only the authenticated gateway listens on wildcard TCP `0.0.0.0:9000`.
Candidate A remains vLLM on `127.0.0.1:19301`, exact snapshot
`b1a9048590131d38491bd23a7c9f6ed0962f0358`, 131,072 model context, one
sequence, 3.4 GB KV cache, GPU utilization 0.5, native NVFP4 B12x, and bounded
12/16/4 GiB system-memory cgroup limits. Reasoner remains the agreed Qwythos
service at `100.90.167.128`; no local `dgx-moa-reasoner.service` exists.

Rollback was rehearsed by draining the fixed unit, checking out
`90e838742`, restarting, and running an authenticated canary. Redeployment to
the runtime release repeated the drain/restart and returned the identical
18-byte content SHA-256
`cf3ca67e6c27a068bcdbed24f78220b8441d5a22d5dc7ba8c018b9f1058ebef0`.
Both stages were active with restart count zero. Candidate A was not restarted.

The final source gate passed Ruff, format, strict mypy over 50 source files,
and pytest `1091 passed`. Worktree and retained-runtime ownership is frozen in
`docs/PILOT_WORKTREE_INVENTORY_20260813.md`.
