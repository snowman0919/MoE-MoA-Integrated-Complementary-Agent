# Dynamic MoA concurrent runtime incident — 2026-08-08

## Scope

This record preserves observed facts from an unexpected concurrent runtime and
model-filesystem mutation during the development-only Mistral download gate. It
does not identify an actor or authorize recovery, service startup, deployment,
or deletion.

## Timeline (KST)

- `16:42:19`: the goal-controlled download started in process group `3336933`
  with revision `b1a9048590131d38491bd23a7c9f6ed0962f0358`, local directory
  `/home/kotori9/models/.mistral-small-4-119b-2603-nvfp4.partial.VSLjpC`, and
  `--max-workers 4`.
- `16:44:24`: the user systemd journal records an explicit stop of
  `dgx-moa-planner.service`; the SGLang process received `SIGTERM`, drained zero
  requests, and the unit finished stopping at `16:44:36`.
- `16:44:49`–`16:44:50`: the `dgx-moa` and `experimental` model parent
  directories received new mtimes. Three paths that the pre-cleanup inventory
  had retained and verified present were then absent.
- `16:45:09`: a second Hugging Face download started in process group
  `3339050`, using cache directory `/home/kotori9/models/.hf-cache`. This was not
  the goal-controlled command. Both download processes had Codex App Server PID
  `3055408` as their direct parent; this fact does not establish the initiating
  actor.
- After detecting the collision, both exact download process groups received
  `SIGTERM`. A `16:48:15` process snapshot found no remaining Hugging Face
  download, model deletion, or service-control process.
- `16:49:16`: the final read-only incident snapshot below was captured.
- `16:52:34`: while validation continued, `config/models.yaml` changed outside
  the goal-controlled edit stream to pin the Mistral Executor revision above,
  set its cache snapshot destination and Mistral parsers, and replace the
  Reasoner LAN address with a tailnet address.
- `16:53:17`: `gateway/src/dgx_moa/key_dashboard.py` changed outside the
  goal-controlled edit stream from the Qwen Executor label to
  `Mistral-Small-4`. A two-second stability recheck found no further mtime or
  diff change and no active editor/download/service-control process. These
  goal-aligned but concurrently authored changes were preserved as user-owned
  work and were not reverted.

## Filesystem snapshot

Unexpectedly absent retained paths:

- `/home/kotori9/models/dgx-moa/executor`
- `/home/kotori9/models/experimental/qwen3-coder-next-modelopt-nvfp4-15c399c8`
- `/home/kotori9/models/experimental/gemma-4-26b-a4b-nvfp4-a19cfe00`

Still-present retained paths and measured bytes:

| Path | Bytes |
| --- | ---: |
| `/home/kotori9/models/dgx-moa/planner` | `20767794920` |
| `/home/kotori9/models/dgx-moa/reviewer` | `19382990745` |
| `/home/kotori9/models/dgx-moa/reasoner` | `6188996125` |
| `/home/kotori9/models/specialist-unified-qwen36-27b-nvfp4` | `21941625842` |
| `/home/kotori9/models/specialist-unified-llama33-nemotron-super-49b-nvfp4` | `31090452036` |

Recoverable partial data was preserved without modification:

| Path | Bytes |
| --- | ---: |
| `/home/kotori9/models/.mistral-small-4-119b-2603-nvfp4.partial.VSLjpC` | `20492283799` |
| `/home/kotori9/models/.hf-cache` | `2834955254` |

Filesystem free space was `267652116480` bytes. The earlier authorized cleanup
removed only the three candidates listed in
`MODEL_INVENTORY_DYNAMIC_MOA_V2_20260808.md`; it did not target any of the three
unexpectedly absent retained paths.

## Runtime snapshot

- User units: gateway `active`; Executor, Planner, Reviewer, and Reasoner
  `inactive`.
- The authenticated gateway remained bound only to `100.125.239.72:9000`.
- Tailnet `/healthz`: HTTP `200`, `{"status":"ok","remote_judge":"available"}`.
- Tailnet `/readyz`: HTTP `503`; Executor, Planner, Reviewer, and Judge reported
  `stopped`. The response reported Reasoner `ready` while its user unit was
  inactive, so that field is retained as a state-reconciliation discrepancy,
  not readiness evidence.
- The stopped Planner mount/process was gone; no live process-backed copy of
  its deleted Gemma path was available.

## Safety disposition

No download was resumed, no partial was deleted, no model was restored, and no
service was started. Physical model validation and any production-path change
remain paused until the concurrent actor is no longer active and an operator
explicitly chooses recovery/re-download scope. The gateway remains unhealthy
for resident service because `/readyz` is `503`.

## Subsequent cache completion and isolated load failure

Later read-only evidence showed that the canonical Hugging Face/Xet cache
transfer continued from `16:49:21` through `17:00:55`, outside the terminated
goal-controlled process group. The initiating actor was not established. The
pinned snapshot then contained `23` manifest files totaling `70846528432`
bytes, with zero broken symlinks. `hf cache verify` checked `23/23` files at
revision `b1a9048590131d38491bd23a7c9f6ed0962f0358` and exited `0`.

At `17:04:30`, another concurrent process started local vLLM `0.22.1` on
`127.0.0.1:19301` with the pinned snapshot and the required first-load profile:
context `65536`, one sequence, `1700000000` KV bytes,
`gpu_memory_utilization=0.5`, MARLIN MoE, TRITON_MLA attention, and Mistral
tool/reasoning parsers. This process was not initiated by the goal-controlled
command stream. It never opened the port or returned readiness. At `17:22:07`,
its EngineCore was in uninterruptible `folio_wait_bit_common` sleep with 102
threads; observed GPU allocation reached `120052` MiB.

Kernel records from `17:28:26` onward show global out-of-memory handling,
`NV_ERR_NO_MEMORY`, and kills of unrelated desktop/system processes. The
gateway was killed three times between `17:27:25` and `17:27:57` and reached
its restart limit; the user systemd manager was also killed. At `17:28:42`, the
kernel killed EngineCore PID `3386567` and vLLM parent PID `3386426`. A new user
manager started gateway PID `3392930`, which reported ready at `17:28:44`.

After recovery, no canary listener or GPU compute process remained. The
authenticated tailnet `/healthz` returned HTTP `200`; `/readyz` remained HTTP
`503` with role services stopped. The loopback gateway socket was listening on
`127.0.0.1:9000`, while its on-demand service being inactive was normal socket
activation state.

A further read-only check found that another direct-session vLLM parent PID
`3395728` had started at `17:29:29`, again targeting the pinned snapshot and
port `19301`. Its EngineCore PID `3395983` held `68256` MiB of GPU memory but
had not opened the port. The process was parented by Codex App Server PID
`3055408`; this does not establish the initiating actor. Because the prior
global OOM made any same-profile retry unsafe, the exact process group
`3395728` alone received `SIGTERM`. GPU allocation was released, but the
parent retained a zombie EngineCore after ten seconds, so the same exact group
received `SIGKILL`. Both PIDs, the listener, and GPU compute allocation were
then absent. Available system memory measured `126931980288` bytes; swap use
remained `944574464` bytes.

The cache integrity gate therefore passed, but isolated load, readiness, and
memory-isolation gates failed. Chat, Responses, streaming, tools, long-context,
cache, cancellation, and restart rows were not run because readiness was never
reached. The same profile must not be retried, and this evidence authorizes no
backend substitution, deployment, or production mutation.
