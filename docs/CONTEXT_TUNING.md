# Context Tuning

`scripts/tune-context.sh resident` and `scripts/tune-context.sh judge` perform
three restart/readiness checks, five sequential requests, structured-output and
near-limit probes, memory measurement, KV-cache log parsing, and OOM inspection.
Results append to `data/benchmarks/context-tuning.json`.

The selector uses `0.65 * executor + 0.20 * planner + 0.15 * reviewer`, while
requiring 20 GiB available memory for resident and 16 GiB for judge. It records
the next larger rejected candidate and its reason. Context values never exceed
the model config's native limit.

Current resident evidence:

| Role | Context | KV cache | KV tokens | Available memory |
|---|---:|---:|---:|---:|
| Executor | 16,384 | 500,000,000 bytes | 17,829 | 69,172,068,352 bytes during readiness |
| Planner | 8,192 | 750,000,000 bytes | 59,392 | 22,406,086,656 bytes final profile |
| Reviewer | 8,192 | 750,000,000 bytes | 8,649 | 22,406,086,656 bytes final profile |

These are the current stable baseline, not guessed maxima. Larger candidates
require larger KV reservations and a fresh profile-level three-restart trial.
