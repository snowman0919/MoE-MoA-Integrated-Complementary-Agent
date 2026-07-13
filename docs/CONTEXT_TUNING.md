# Context Tuning

`scripts/tune-context.sh resident` and `scripts/tune-context.sh judge` perform
three restart/readiness checks, five sequential requests, structured-output and
near-limit probes, memory measurement, KV-cache log parsing, and OOM inspection.
Results append to `data/benchmarks/context-tuning.json`.

The selector uses `0.60 * executor + 0.20 * planner + 0.15 * reviewer + 0.05
* reasoner`, while requiring 10 GiB available memory for resident and 16 GiB
for judge. It records the next larger rejected candidate and its reason.
Context values never exceed the model config's native limit.

Current resident evidence:

| Role | Context | KV cache | KV tokens | Available memory |
|---|---:|---:|---:|---:|
| Executor | 16,384 | 500,000,000 bytes | 17,829 | 69,172,068,352 bytes during readiness |
| Planner | 8,192 | 750,000,000 bytes | 59,392 | 22,406,086,656 bytes final profile |
| Reviewer | 8,192 | 750,000,000 bytes | 8,649 | 22,406,086,656 bytes final profile |

These are the current stable baseline, not guessed maxima. Larger candidates
require larger KV reservations and a fresh profile-level three-restart trial.

Resident executor trials on 2026-07-12 kept the stable limit at `16384`:

| Candidate | KV cache | Measured KV tokens | Result |
|---:|---:|---:|---|
| 24,576 | 750,000,000 bytes | 28,086 | rejected; reviewer/planner CUDA startup OOM |
| 20,480 | 600,000,000 bytes | 21,978 | rejected; two ready cycles, third reviewer startup OOM |
| 18,432 | 525,000,000 bytes | 19,428 | rejected; reviewer startup OOM |

The successful `20480` cycles reached a minimum final available-memory sample of
`21705404416` bytes, only `230567936` bytes above the 20 GiB gate. A planner
calibration at 200,000,000 KV bytes yielded 15,360 tokens for its unchanged 8,192
context, but did not prevent the earlier reviewer allocation failure. The restored
`16384` executor passed five sequential requests and a near-limit request in
`5.863` seconds; final resident available memory was `23362560000` bytes.

`DGX_MOA_<ROLE>_KV_CACHE_MEMORY_BYTES` overrides the role reservation for an
isolated calibration retry. It does not establish a new context limit or replace
the required readiness/headroom validation; the judge default remains
`4000000000` bytes until a lower value is measured.
