# Memory Optimization

Updated: 2026-07-19

## Decision

Use exact full process stop/start for executor unload. It is both the selected
mechanism and the mandatory fallback. Sleep level 1, sleep level 2, and live
prefix/KV reset were physically exercised but did not satisfy the combined
memory-return, stability, and quality contract.

Keep the existing 65,536-token executor configuration. The one-variable study
selected `baseline`: `--max-model-len 65536`, `--max-num-seqs 1`,
`--kv-cache-memory-bytes 1700000000`, `--gpu-memory-utilization 0.5`, and
MARLIN. No new runtime flag is justified.

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

## 65,536-token candidate study

The authoritative result is
`/tmp/dgx-moa-phase3-7vfm7bzv/candidates-confirmed.json`, SHA-256
`10f233b47acfb52e54ee41532963d68e38831e7337818d4335b57f3bc2eaad03`.
It reports `passed=true`, no failures, and selection `baseline`. It links the
retained earlier generations; the content-free long-response diagnostic is
`/tmp/dgx-moa-phase3-dktd_9pv/long-diagnostic.json`, SHA-256
`e165f0d227cfe2713a8bee901567eee23fe3931c2cfd960ca5a209ddf9cc0340`.

| Candidate | One changed dimension | Ready / near-64K latency | Warm owned PSS / MemAvailable | Outcome |
| --- | --- | ---: | ---: | --- |
| baseline | none | `934.930s` / `17.775s` | `4545508352` / `66737324032` bytes | selected; complete contract passed |
| FP8 | FP8 KV, dynamic scales requested, `900000000` KV bytes | `1038.116s` / `19.864s` | `4537163776` / `66412109824` bytes | no material PSS improvement; dynamic scales disabled for the installed hybrid path and no capacity retry needed |
| prefix off | disable prefix caching | n/a | n/a | exact no-op: installed baseline already logged prefix caching disabled |
| eager | disable compile/CUDA graphs | `912.472s` / `20.047s` | `3859753984` / `66124435456` bytes | full contract passed, but rejected by matched safety rule |
| chunked 8K | batched-token ceiling `8192` | `949.070s` / `17.174s` | `4590109696` / `64325787648` bytes | no material PSS improvement |
| CPU offload 4G | `--cpu-offload-gb 4` | `953.048s` / `18.143s` | `5341807616` / `66104176640` bytes | PSS worsened |
| KV offload 1G | native KV offload size `1` | startup failed | n/a | hybrid block/hash divisibility incompatibility; exact teardown passed |

Every physical row kept context `65536` and `max_num_seqs=1`. All successful
screening rows reported `63786` backend prompt tokens, not merely a local
tokenizer estimate. Baseline and eager both passed five exact short cases, the
1,100-number long response, three native tool calls, restricted Python code,
strict reviewer JSON, stable owned memory, and teardown PSS/RSS zero. Their
long responses contained 1,100 finite numeric items and finished with `stop`;
baseline used 4,393 completion tokens in `113.904s`, eager 4,394 in `203.297s`.

Eager reduced owned PSS by `685754368` bytes, but its matched warm
MemAvailable was `612888576` bytes below baseline. That exceeds the
`268435456`-byte noise band, so the deterministic safety rule rejected eager
and retained baseline. `gpu_memory_utilization` was not swept because explicit
KV bytes were fixed and unified-memory GPU used/free byte telemetry remained
unavailable; no GPU percentage is inferred.

The baseline prefix probes both passed at 1,565 prompt tokens with
`0.492s`/`0.507s` latency. Prefix caching was already disabled, cached-token
telemetry was null, retained PSS delta was only `2105344` bytes, and reset
returned HTTP 200 in `0.023s`; this supplies no reason to add a disable flag.

### Retained corrections

The first full matrix exposed one ambiguous short fixture, then the long
fixture's token budget. A content-free diagnostic proved the repeated-number
request hit `1400` completion tokens, only 700 numeric items, and
`finish_reason=length`. Raising the cap alone still did not self-terminate.
The final fixture uses the ascending integers 1 through 1100 and an `END` stop,
with a 5,000-token cap. An interrupted eager load was exactly torn down. A
later attempt exhausted `/tmp`: baseline's raw log records nvcc failing to write
a generated C file, and the next eager preparation failed while copying the
seed cache. Its partial result was retained, result/log/manifest evidence was
preserved, and only exact regenerable experiment `cache/` directories were
removed. After the confirmed run, the current harness gained a 10-GiB disk
preflight gate for later studies; the confirmed artifact did not exercise it.

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
- The installed runtime logged prefix caching disabled by default, so
  `prefix_off` is a no-op/unsupported comparison rather than an optimization
  claim.
- FP8's original full-contract failure used the invalid repeated-number fixture;
  it was not rerun after diagnostics because its PSS improvement was only
  `8344576` bytes, far below the fixed noise band, and therefore could not win.
- No production threshold, topology, or service setting changed from this
  evidence. Deployment still requires reviewed source/config changes and a
  later human-controlled migration.
- C/D deliberately retain no failed model text or incomplete cycle details, so
  the exact bad text cannot be independently re-inspected. Shutdown logs include
  one vLLM `resource_tracker` semaphore-cleanup warning, but final exact checks
  found no surviving process, port, PSS, or RSS. Model equality is metadata-only.
