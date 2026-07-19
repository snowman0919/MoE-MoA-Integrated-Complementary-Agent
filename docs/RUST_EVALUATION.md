# Rust Gateway Evaluation

Updated: 2026-07-19

## Decision

Keep the gateway in Python. Do not create a Rust crate or prototype in Phase 3.
The isolated five-minute measurement passed all three predeclared rejection
thresholds with substantial margin, and the focused lifecycle/API/restart
recovery suite found no remaining Python-attributable correctness gap.

| Gate | Reject Rust when | Measured | Result |
| --- | ---: | ---: | --- |
| gateway process-group PSS | at most `268435456` bytes (256 MiB) | peak `48741376` bytes (46.48 MiB) | reject Rust |
| five-minute idle CPU | at most `1%` of one core | `0.24998221036527596%` | reject Rust |
| loopback `/healthz` p99 | at most `50ms` | `2.1657010074704885ms` | reject Rust |
| focused correctness/recovery | no Python-attributable gap | `360 passed`, one upstream deprecation warning | reject Rust |

All required conditions passed, so the plan's fail-closed branch for a separate
approved Rust prototype specification was not entered.

## Authoritative measurement

The content-free result is
`/tmp/dgx-moa-phase3-gateway-nzacnu_v/gateway-probe.json`, SHA-256
`4513ca3f6980f7fcfb81d7f7a360851325fcd7f90cddcb475f2612c17f2f6d62`.
It has schema `phase3-gateway-idle-v1`, `passed=true`, no failures, and 600
samples at 500 ms intervals over `300.02134908083826` seconds.

- Startup readiness took `0.20371862896718085` seconds.
- HTTP latency p50/p95/p99/max was
  `1.5531240496784449` / `1.894660061225295` /
  `2.1657010074704885` / `2.8134610038250685` ms.
- Schedule-drift p50/p95/p99/max was
  `0.16089505515992641` / `0.685602892190218` /
  `0.7837000302970409` / `1.084138872101903` ms.
- Process-group PSS was `48708608` bytes initially and `48741376` bytes at
  both final and peak. RSS was `56107008` bytes initially and `56139776` bytes
  at both final and peak.
- Idle CPU was derived from Linux `utime+stime` clock-tick deltas,
  `SC_CLK_TCK`, and monotonic elapsed time; it measured
  `0.24998221036527596%` of one core.

The selected executor's measured warm owned PSS was `4545508352` bytes. The
gateway peak was about 1.07% of that value and roughly 4.19 GiB smaller. The
gateway is therefore not a material memory target relative to model residency.

## Isolation and teardown

The probe launched only the development `.venv/bin/dgx-moa` on loopback port
19300 with authentication, administration, Frontier, and lifecycle control
disabled. State, run, cache, home, temporary, configuration, and log paths were
isolated below the result root. It made only `/healthz` requests and retained
status/latency, schedule, CPU, and memory numbers; it did not retain request or
response bodies, headers, authorization values, model text, or tool content.

PID, PGID, and session were all `2478575`; start ticks, cwd, and observed argv
were recorded and revalidated before signaling. Termination took
`0.2674391020555049` seconds. Post-stop owned process count, PSS, and RSS were
all zero, port 19300 was unbound, and the scoped runtime-process count was zero.
The start and final checks found production clean and unchanged at
`c2a9af0d6b5db8dd940842c56a7236ac867061ff`; production processes, units,
ports, files, and deployment were not mutated.

The first executable smoke root,
`/tmp/dgx-moa-phase3-gateway-r8uzjlp_`, is retained as non-authoritative failed
evidence. It exposed a probe-only directory-order bug before a child process
started and still left port 19300 unbound. After the correction, the passing
three-second smoke is `/tmp/dgx-moa-phase3-gateway-rf8b296y/gateway-probe.json`,
SHA-256 `4cdcf0f40e124818236d52175c9dd29a9e47880017a697d796752a260405d1da`.
Neither smoke replaces the five-minute result.

## Correctness and recovery

After the physical probe, this exact focused command passed:

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py -q
```

It reported `360 passed` and the existing third-party Starlette TestClient
deprecation warning. The suite covers lifecycle recovery and reconciliation,
API behavior, and runtime-status handling; it does not establish production
deployment readiness.

## Candidate Rust boundary

If later evidence crosses a threshold, a separately approved prototype could
isolate the bounded transport/control responsibilities: authenticated OpenAI
HTTP parsing, SSE relay with exact terminal framing, lightweight routing,
process-status polling, and lifecycle-unit calls. SQLite session semantics,
agent state transitions, tool continuation, review policy, and trace contracts
should remain outside a first transport prototype unless a new design and
correctness matrix explicitly justify moving them.

## Limitations

- `/healthz` is a loopback event-loop/HTTP proxy, not a model request or a
  client-concurrency benchmark.
- The 2 Hz probe itself contributes to the measured CPU, so the value is a
  conservative idle proxy for this workload, not a zero-request baseline.
- Linux process-group `smaps_rollup` PSS/RSS and clock ticks are host
  measurements; they do not isolate every shared-page or kernel cost.
- Authentication and lifecycle were intentionally disabled to avoid secrets and
  external mutation. The result measures the resident gateway core, not every
  production feature combination.
- This is one five-minute development sample. It supports the bounded Rust
  decision threshold but is not long-duration production performance evidence.
