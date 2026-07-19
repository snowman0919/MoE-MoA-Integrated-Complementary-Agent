# Phase 4 Client Matrix and PR Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Physically pass every approved Generic API, native tool-loop,
OpenCode, Hermes, cold-load/retry, idle-unload/reload, streaming-integrity,
production-mutation, and review gate before pushing `dev` and opening a draft
`dev`-to-`main` pull request.

**Architecture:** Reuse the ignored Phase 3 exact-process driver for one isolated
warm executor and authenticated gateway, then reuse the ignored Task 10 lifecycle
harness for cold and idle transitions. A single small ignored Phase 4 harness
drives real installed clients, validates physical file effects, and emits only
content-free JSON. The complete serial validation session is the bounded soak;
its actual duration is reported without claiming a 24-hour run.

**Tech Stack:** Python 3.13 project environment, installed Python 3.11/vLLM
0.22.1 runtime, FastAPI, httpx, OpenAI Python SDK, OpenCode 1.17.18, Hermes
0.18.2, stdlib subprocess/asyncio/HTTP relay, pytest, Ruff, MyPy, GitHub CLI.

**Starting dev commit:** `a4fb572e03b3019adf82601535445536880dd33f`
**Production reference:** `c2a9af0d6b5db8dd940842c56a7236ac867061ff`

## Global Constraints

- Work only in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` on
  `dev`; `/home/kotori9/dgx-moa-agent` remains read-only `main`.
- Do not merge, deploy, restart production, change systemd/security topology,
  bind a production listener, or edit the production worktree.
- Bind the isolated gateway/executor only to loopback ports `19300`/`19301`;
  the reused Task 10 lifecycle harness may also bind its validation-only
  optional-role stub to loopback `19302`. A temporary exactly owned relay may
  bind the approved tailnet address only
  while Hermes is under test; it must forward exclusively to `127.0.0.1:19300`
  and be torn down by exact PID identity.
- Preserve the executor baseline: context `65536`, one sequence,
  `1700000000` KV bytes, `gpu_memory_utilization=0.5`, and MARLIN.
- Use fresh `/tmp/dgx-moa-phase4-*` roots, allowlisted environment variables,
  exact PID/PGID/session/start-tick/cwd/argv ownership, bounded waits, and
  fail-closed teardown.
- Never serialize prompts, model output, tool arguments/results, authorization
  headers, API keys, model weights, or secrets. Evidence contains only counts,
  statuses, timing, hashes, booleans, versions, and filesystem-effect metadata.
- Reuse existing ownership/lifecycle code. Do not add a framework, dependency,
  generic plugin abstraction, second supervisor, or production feature.
- Use TDD for the new ignored harness. Commit tracked plans/evidence separately
  from ignored physical artifacts.
- The PR gate is fail-closed: any required count shortfall, malformed SSE event,
  duplicate/missing `[DONE]`, production mutation, or Critical/Important review
  finding blocks push and PR creation.

---

### Task 1: Build the Minimal Ignored Phase 4 Harness

**Files:**
- Create ignored: `.superpowers/sdd/phase4-runtime/harness.py`
- Create ignored: `.superpowers/sdd/phase4-runtime/test_harness.py`
- Reuse read-only: `.superpowers/sdd/phase3-runtime/experiment.py`
- Reuse read-only: `.superpowers/sdd/task10-runtime/harness.py`

- [ ] **Step 1: Write failing contract tests**

Test exact required counts, content-free result validation, SSE `[DONE]`
cardinality, disposable-worktree effect checks, and fail-closed gate evaluation.

```python
REQUIRED = {
    "generic_nonstream": 5,
    "generic_stream": 10,
    "generic_long": 3,
    "native_tool_calls": 5,
    "native_continuations": 3,
    "native_multistep": 1,
    "opencode_read": 2,
    "opencode_small_edit": 2,
    "opencode_multifile": 1,
    "opencode_bounded_engineering": 1,
    "hermes_normal": 2,
    "hermes_stream": 1,
    "hermes_tool": 1,
    "hermes_multistep": 1,
}


def test_required_gate_is_fail_closed() -> None:
    result = passing_summary()
    assert evaluate_gate(result) == []
    result["counts"]["generic_stream"] = 9
    assert evaluate_gate(result) == ["generic_stream: 9 < 10"]


def test_sse_requires_one_done_and_no_malformed_events() -> None:
    assert sse_integrity(["data: {}", "data: [DONE]"]) == (0, 1)
    assert sse_integrity(["data: {", "data: [DONE]", "data: [DONE]"]) == (1, 2)
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest .superpowers/sdd/phase4-runtime/test_harness.py -q
```

Expected: import failure because `harness.py` does not exist.

- [ ] **Step 3: Implement only the tested contract helpers**

Implement `REQUIRED`, `sse_integrity`, `content_free`, `physical_effects`, and
`evaluate_gate`. Reject unknown result keys that could contain request/response
content.

- [ ] **Step 4: Reuse exact process ownership and lifecycle entry points**

Import `ExperimentDriver`, `executor_argv`, and the Task 10 module by path. Patch
the Task 10 expected development commit to the actual clean `HEAD`; do not copy
its ownership or teardown implementation.

```python
task10.EXPECTED_DEV = git_head(DEV_REPO)
driver = ExperimentDriver(root, executor_argv(19301, baseline), 19301, env)
```

- [ ] **Step 5: Run GREEN and static checks**

```bash
uv run pytest .superpowers/sdd/phase4-runtime/test_harness.py -q
uv run ruff check .superpowers/sdd/phase4-runtime
uv run mypy .superpowers/sdd/phase4-runtime/harness.py
```

---

### Task 2: Run the Warm Physical Client Matrix

**Files:**
- Modify ignored: `.superpowers/sdd/phase4-runtime/harness.py`
- Produce ignored: `/tmp/dgx-moa-phase4-*/client-matrix.json`

- [ ] **Step 1: Take immutable preflight snapshots**

Record dev/prod commit and clean state, target ports, production unit states,
runtime process inventory, installed client versions, model revision/metadata
hash, and allowed bind addresses. Abort before startup if any invariant differs.

- [ ] **Step 2: Start the isolated executor and gateway**

Seed isolated caches from approved local data, start the executor with the
preserved baseline on `127.0.0.1:19301`, wait for readiness, start the gateway
on `127.0.0.1:19300`, and confirm `/health` plus `/v1/models` through
authentication. Revalidate exact ownership before every signal.

- [ ] **Step 3: Execute Generic API cases**

Run five non-stream requests using curl/httpx/official OpenAI client coverage,
ten independently parsed streams, three responses over 1,000 completion tokens,
and at least one request with `max_tokens >= 4096`. Exercise invalid model,
invalid request, invalid authentication, bounded backend timeout, and client
cancellation. For every stream assert first event precedes completion,
`malformed == 0`, and exactly one `[DONE]`.

- [ ] **Step 4: Execute native tool-loop cases**

Run five forced tool calls, three continuation turns returning tool results, and
one external multi-step loop with at least two sequential physical tool actions.
Record tool names/counts and continuation success only; retain no arguments,
results, prompts, or assistant content.

- [ ] **Step 5: Execute OpenCode cases with physical effects**

Use `--dir`, `--model`, `--pure`, `--auto`, and JSON output against a disposable
directory. Run two read cases, two small edits, one multi-file edit, and one
bounded engineering task. Verify the resulting paths and SHA-256 changes from
the filesystem, not from model claims.

- [ ] **Step 6: Execute Hermes cases with physical effects**

Use a disposable `HERMES_HOME`, an explicit custom provider config, file tools,
and the exactly owned temporary relay only if Hermes cannot address loopback in
the selected configuration. Run two normal cases, one streamed case, one tool
case, and one multi-step case; verify API-call counts and filesystem hashes.

- [ ] **Step 7: Recheck near-64K context and write content-free evidence**

Reuse the Phase 3 deterministic target-prompt helper to submit one 63,000–64,500
token templated request without lowering context. Write atomic JSON containing
only contract fields, counts, statuses, token counts, timing, hashes, booleans,
versions, and artifact paths.

- [ ] **Step 8: Tear down all owned warm processes**

Stop relay, gateway, and executor only after exact identity revalidation. Assert
ports `19300`/`19301` and the temporary relay address are unbound and no owned
runtime process remains.

---

### Task 3: Run Cold, Idle, Reload, and Bounded Soak Gates

**Files:**
- Modify ignored: `.superpowers/sdd/phase4-runtime/harness.py`
- Produce ignored: `/tmp/dgx-moa-phase4-*/lifecycle.json`
- Produce ignored: `/tmp/dgx-moa-phase4-*/summary.json`

- [ ] **Step 1: Invoke the existing Task 10 lifecycle harness**

Run it through a wrapper that sets the actual clean development commit and a
fresh Phase 4 root. Require prompt cold `503`, exactly one load, visible progress,
ready retry, active-request and stream guards, idle unload, memory return, next
cold `503`, exactly one reload, and successful retry.

- [ ] **Step 2: Treat the whole serial session as the bounded soak**

The soak begins before warm startup and ends after lifecycle teardown. Confirm
that it included chat, streaming, tools, OpenCode, Hermes, idle, unload, and
reload, then record its real wall-clock duration. Do not label it a 24-hour soak.

- [ ] **Step 3: Prove production mutation count remains zero**

Compare pre/post production Git commit/status, production unit states, target
ports, runtime process inventory, and immutable file metadata. Require
`production_mutation_count == 0`; any difference blocks the gate.

- [ ] **Step 4: Evaluate the complete fail-closed gate**

Require every matrix count at or above its target, cold and idle assertions all
true, `stream_malformed == 0`, `stream_duplicate_done == 0`,
`production_mutation_count == 0`, and no leaked process/listener.

---

### Task 4: Publish Measured Evidence

**Files:**
- Modify: `docs/VALIDATION.md`
- Modify: `docs/STATE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/SECURITY_REVIEW.md`

- [ ] **Step 1: Record the exact measured matrix and soak result**

Add the artifact root, hashes, actual duration, client versions, case totals,
long-response/token bounds, SSE integrity counts, lifecycle transitions, and
production pre/post equality. Explicitly distinguish ignored raw evidence from
tracked summarized evidence.

- [ ] **Step 2: Document the PR gate and deployment boundary**

State that the result authorizes a draft integration PR only. It does not merge,
deploy, enable lifecycle mode, change production topology, or make the resident
target active.

- [ ] **Step 3: Scan tracked changes for forbidden content**

```bash
git diff --check
rg -n "Authorization:|Bearer |api[_-]?key|SENTINEL_PROMPT|SENTINEL_OUTPUT" docs
git status --short
```

- [ ] **Step 4: Commit the evidence**

```bash
git add docs/VALIDATION.md docs/STATE.md docs/OPERATIONS.md docs/SECURITY_REVIEW.md
git commit -m "docs(validation): record phase four client gate"
```

---

### Task 5: Run Final Verification and Independent Review

- [ ] **Step 1: Run repository gates from the committed tree**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
bash scripts/validate-systemd.sh
bash -n scripts/*.sh
git diff --check origin/main...HEAD
```

- [ ] **Step 2: Re-run content-free and production-equality audits**

Rehash ignored JSON, validate it against the Phase 4 schema, compare production
pre/post snapshots, confirm production Git remains at its reference, and prove
all development listeners/processes are gone.

- [ ] **Step 3: Request an independent severity review**

Review the complete `origin/main...HEAD` diff plus Phase 4 evidence for
correctness, security, evidence integrity, and production safety. Require zero
Critical and zero Important findings. Fix and re-run gates for any such finding.

---

### Task 6: Push and Open the Draft Pull Request

- [ ] **Step 1: Confirm intentional publish scope**

Require clean `dev`, expected canonical origin, all commits intentional, no raw
evidence or secrets tracked, and all approved gate values still passing.

- [ ] **Step 2: Push `dev` without force**

```bash
git push origin dev
```

- [ ] **Step 3: Open one draft `dev`-to-`main` PR**

Use the connected GitHub integration when available, otherwise `gh`. Include a
concise change summary, exact validation commands/results, Phase 4 matrix totals,
actual bounded-soak duration, zero mutation/SSE/review findings, and explicit
“no merge or deploy performed” wording.

- [ ] **Step 4: Verify remote PR state**

Confirm base `main`, head `dev`, draft state, canonical repository, and check
status. Do not merge, mark ready, or deploy.

---

### Task 7: Continue the Approved Post-PR Reliability Phase

- [ ] **Step 1: Observe PR checks and review state**

Collect remote check results read-only. If a check fails, use systematic
debugging and fix only the validated cause on `dev`, then repeat the entire
relevant gate and update the draft PR.

- [ ] **Step 2: Extend isolated reliability evidence without production mutation**

If PR checks pass, continue with a longer explicitly timed isolated development
soak using the same Phase 4 matrix and exact teardown contract. Report its actual
duration and keep merge/deploy as separate human approval gates.
