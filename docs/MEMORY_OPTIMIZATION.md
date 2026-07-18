# Memory Optimization

Updated: 2026-07-19

## Decision

Use exact full process stop/start for executor unload. It is both the selected
mechanism and the mandatory fallback. Sleep level 1, sleep level 2, and live
prefix/KV reset were physically exercised but did not satisfy the combined
memory-return, stability, and quality contract.

This is isolated development evidence, not a deployment. Checked-in lifecycle
mode remains `disabled`; production was not started, stopped, restarted,
modified, or deployed.

## Evidence boundary

The authoritative resumed result is
`/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms-resumed.json`, SHA-256
`625b25afbadbb1e8ef42f95e836df627ec22e37c87e07301102eaaa6194b6af9`.
It links the preserved first complete attempt
`/tmp/dgx-moa-phase3-9l7a3ayp/mechanisms.json`, SHA-256
`6a5ce3ba6055f265f93e6f7a06752bbd883002bcbabf65512ab109db3e440994`.
The first tokenizer-only failure is retained at
`/tmp/dgx-moa-phase3-52ffwbov`.

The result JSON stores no prompt, model output, tool content, Authorization
header, API key, or tool arguments. It retains status, usage, finish reason,
tool name/argument-key metadata, timing, memory, process identity, and model
metadata fingerprint only. GPU telemetry was available but used/free byte
fields were null on the unified-memory GB10, so no GPU percentage is inferred.

## Physical mechanism matrix

| Row | Native operation | Result | Memory returned | Timing | Quality and reason |
| --- | --- | --- | ---: | --- | --- |
| A | exact transient user-unit stop/start | selected, 2/2 cycles | `55048712192`-byte median MemAvailable delta | ready `946.36s` cold / `272.08s` warm; stop `1.15s` / `1.12s` | short and forced native tool passed; backend prompt usage `63786` twice; near-limit latency `17.79s` / `17.57s` |
| B | sleep level 1, two sleep/wake cycles | rejected | `25938081792`-byte median, only `47.12%` of A | sleep median `11.93s`; wake median `23.12s` | short, native tool, and `63786`-token check passed, but returned less than the required 90% and owned PSS was not stable |
| C | sleep level 2 | rejected on first post-wake quality check | no accepted delta row | ready `941.28s`; sleep and wake routes returned HTTP 200 | pre-sleep short/tool passed; the first post-wake exact short check failed, so the trial stopped before near-limit or a second cycle |
| D | dev-only live `POST /reset_prefix_cache` with the existing `1700000000`-byte auto-dtype constraint | rejected on first post-reset quality check | no accepted delta row | ready `952.86s`; reset returned HTTP 200 | two pre-reset identical-prefix probes passed (`0.70s`, `0.50s`), then the first post-reset exact short check failed; no near-limit claim is made |

For C and D, raw `supported=false` means the complete selectable contract did
not finish. It does not mean the native HTTP route was missing: the retained
access logs record successful sleep/wake or reset calls before the quality
failure. Model text is deliberately not retained, so the failure is reported
only as an exact-output mismatch.

## Full-stop evidence

Both A cycles used the same allowlisted name
`dgx-moa-dev-phase3-f4f0410a.service`, recreated only after `--collect`
reported it absent. Before each stop, the runner revalidated exact unit ID,
working directory, MainPID, start ticks, cwd, argv, PGID, SID, and cgroup. The
two MemAvailable deltas were `55227699200` and `54869725184` bytes. Ready owned
PSS was `4392537088` and `4105054208` bytes; unified-memory host reclamation is
therefore represented primarily by MemAvailable, not process PSS or unavailable
GPU-byte counters.

The resumed JSON preserves the two A identities: PID/PGID/SID `1551989` with
start tick `129736543`, then `1576082` with start tick `129834027`. The generic
foreground-driver manifests/events are empty for A because systemd, not that
driver, owned the processes. Teardown is instead corroborated by the recorded
identity revalidation, shutdown logs, stop timings, successful exact-name reuse,
settled owned PSS/RSS zero, and final port/runtime fingerprint.

The final fingerprint found ports `19300`, `19301`, `9000`, `8101`-`8104`, and
`8110` unbound, no DGX MoA/vLLM runtime process, clean dev at `ec91a09`, clean
production `main` at `c2a9af0`, and unchanged model metadata SHA-256
`8077dc0ac131f7ae208132823c06b58d3410eba670ff511e3e42b9daf790c077`.

## Selection rule

A live mechanism had to return at least 90% of A's matched MemAvailable delta,
remain stable across two cycles, wake faster than restart, and pass short,
native-tool, and near-limit quality. The 90% threshold was
`49543840972.8` bytes. B returned `25938081792` bytes and failed stability;
C and D failed quality before producing selectable rows. Consequently speed
alone cannot select a live mechanism, and A remains the fail-closed choice.

## Limitations and next study

- MemAvailable is system-wide and noisy. Matched cycles and exact-owned PSS/RSS
  reduce ambiguity but cannot turn it into a device-only measurement.
- A and B each have only two samples; their medians are deterministic selection
  inputs, not statistically robust performance distributions.
- The installed runtime logged prefix caching disabled by default, so the later
  `prefix_off` 64K candidate is a no-op/unsupported comparison rather than an
  optimization claim.
- The mechanism study proves one physical near-limit request shape, not the full
  five-short/long/tool/code/reviewer candidate contract. The FP8, explicit KV,
  graph/eager, chunked-prefill, CPU-offload, and KV-offload matrix remains the
  next phase-three task.
- No production threshold, topology, or service setting changed from this
  evidence. Deployment still requires reviewed source/config changes and a
  later human-controlled migration.
- C/D deliberately retain no failed model text or incomplete cycle details, so
  the exact bad text cannot be independently re-inspected. Shutdown logs include
  one vLLM `resource_tracker` semaphore-cleanup warning, but final exact checks
  found no surviving process, port, PSS, or RSS. Model equality is metadata-only.
