# State

Updated: 2026-07-13T12:52:29+09:00

## Branch and deployment

- `main` is the reviewed production target and stable recursive control plane.
- `dev` is the integration branch; recursive experiments must use isolated
  `auto/<layer>/<proposal-id>` worktrees created from `dev`.
- The production runtime worktree is `/home/kotori9/dgx-moa-agent` on `main`.
  Development stays in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent`
  on `dev`.
- Promotion remains `dev` -> reviewed PR -> `main` fast-forward pull -> controlled
  gateway restart. Runtime services never execute from the development worktree.

## Runtime

- Gateway: authenticated direct tailnet TCP at `100.125.239.72:9000`.
- Model endpoints: loopback-only executor `8101`, planner `8102`, reviewer `8103`.
- Resident target and profile are ready; executor, planner, and reviewer are active.
- Context limits are executor, planner, and reviewer `65536`.
- KV reservations, model selection, unit topology, and memory gates are unchanged.
- A configurable 10-second prestart memory-settle delay prevents reloads from
  racing unified-memory reclamation. The final resident restoration passed.
- Local OpenCode `1.17.18` is active in tmux session `dgx-opencode`, working in
  the `dev` repository with provider `dgx-moa/dgx-moa-agent`.

## Validation baseline

- Automated suite: `96 passed`; Ruff format/check, MyPy, shell syntax, and
  systemd unit verification pass.
- Fixed synthetic benchmark: `10/10`, success rate `1.0`, routes `3/6/1`
  fast/standard/escalation, tool calls per success `1.2`.
- Required real OpenCode staging: 10 sessions covering read `3`, small edit `3`,
  multi-file `2`, failure recovery `1`, bounded engineering `1`.
- Required-session outcomes: 6 completed and 4 explicitly failed on bounded
  timeout/validation. One earlier calibration failure is retained.
- Staging trajectories: 11/11 complete; review/blocked validation trajectories:
  2/2 complete; applicable mandatory trace completeness is `100%`.
- Updated reviewer boundary passed a full in-process API run against the real
  planner, executor, and reviewer: HTTP 200, structured rejection, phase
  `correction`, completion blocked.

## Stability evidence

- Bounded soak: `26867` seconds (`7h 27m 47s`), 5370 memory samples.
- Minimum observed `MemAvailable`: `20783300608` bytes; maximum
  `123198304256` bytes. Resident startup uses the operator-approved 5 GiB
  (`5368709120` bytes) gate as of 2026-07-13. The 64K resident profile runs
  executor, reviewer, and planner; VibeThinker remains optional and stopped.
- Soak exercised real OpenCode requests, idle intervals, gateway and resident
  restarts, tool continuation, review, explicit block, and trace archival.
- SQLite state errors: 0. Trace archive errors/degradations: 0.
- This is not a 24-hour stability result; 24-hour observation remains pending.

## Heavy Judge and Frontier

- Heavy Judge remains validated with its unchanged model, `4000000000`-byte KV
  reservation, 8192 context, structured accept verdict, and resident restoration.
  It was not rerun because Judge code/configuration did not change.
- Frontier Codex is enabled through separate OAuth profiles (`primary` and
  `secondary`). Each can be invoked independently with
  `scripts/codex-profile.sh test <profile>` or the existing
  `dgx-moa-codex-frontier@<profile>.service` template; its read-only sandbox
  and systemd hardening remain unchanged. Both stored OAuth refresh tokens
  were rejected on 2026-07-13, so each profile needs interactive re-login
  before it can run work.

## Known limitations

- Multi-file and bounded-engineering staging tasks exceeded the 180-second
  harness bound; their failed traces are retained for later analysis.
- The 7.5-hour soak includes classified startup rollback incidents before the
  memory-settle fix; the final resident state is healthy with no active loop.
- Promotion still requires human review of PR #2 and a later main deployment.
