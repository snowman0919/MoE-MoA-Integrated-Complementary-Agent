# Unload Mechanism and 64K Memory Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select and physically validate a memory-returning executor unload
mechanism and 65,536-token configuration, redesign the undeployed resident
profile, and make an evidence-backed Rust decision without touching production.

**Architecture:** Reuse the ignored Task 10 exact-process harness patterns for a
one-variable-at-a-time physical study. Keep full service stop as fallback; add
tracked runtime flags only when a measured winner needs them. Then make the
resident target executor-only while optional roles remain lifecycle-loadable.

**Tech Stack:** Python 3.13 project environment, installed Python 3.11/vLLM
0.22.1 runtime, FastAPI, httpx, Pydantic, stdlib subprocess/asyncio/SQLite,
systemd user transient units, pytest, Ruff, MyPy.

**Starting dev commit:** `0108902547581c1d8c6fe33cfdfd4ea249e38d8d`
**Production reference:** `c2a9af0d6b5db8dd940842c56a7236ac867061ff`
**Design:**
`docs/superpowers/specs/2026-07-19-memory-unload-64k-design.md`

## Global Constraints

- Work only in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` on
  `dev`; `/home/kotori9/dgx-moa-agent` remains read-only `main`.
- Never start, stop, restart, signal, edit, deploy, or name a production unit or
  process. The only service-manager mutation allowed by this plan is one exact
  transient `dgx-moa-dev-phase3-*.service` trial created by the ignored harness.
- Keep gateway/executor context 65,536 and `max_num_seqs=1`; do not hide a
  capacity failure by lowering context.
- Bind only fresh loopback ports `19300`-`19309`; production `9000`,
  `8101`-`8104`, and `8110` must remain untouched and are checked read-only.
- Use fresh `/tmp/dgx-moa-phase3-*` roots, allowlisted environment variables,
  exact PID/PGID/session/start-tick/cwd/argv ownership, bounded waits, and
  fail-closed teardown.
- Store no prompt, model output, tool content, Authorization header, API key,
  model weight, or secret in results, logs copied as evidence, traces, or Git.
- MemAvailable is system-wide and noisy. GPU bytes remain null when unavailable;
  do not infer a GPU percentage.
- Do not add dependencies, a mechanism plugin/interface, arbitrary extra-args
  environment variable, Rust scaffold, dashboard, or second supervisor.
- Checked-in lifecycle mode stays `disabled`; no production topology is
  activated or deployed.
- Use TDD for every non-trivial harness or tracked behavior. Review and commit
  each tracked task before continuing.

---

### Task 1: Build the Ignored Phase-Three Experiment Core

**Files:**
- Create ignored: `.superpowers/sdd/phase3-runtime/experiment.py`
- Create ignored: `.superpowers/sdd/phase3-runtime/test_experiment.py`
- Reuse read-only: `.superpowers/sdd/task10-runtime/harness.py`

**Interfaces:**
- Consumes: Task 10 `ExactProcessDriver`, `OwnedProcess`, `proc_identity`,
  `runtime_processes`, `memory_snapshot`, `gpu_snapshot`, `write_json_atomic`,
  and `seed_isolated_caches`.
- Produces: `Candidate`, `CANDIDATES`, `executor_argv`, `target_prompt`,
  `content_free_result`, `mechanism_eligible`, and `ExperimentDriver` for Tasks
  2 and 3.

- [ ] **Step 1: Write failing candidate, token-target, selection, and redaction tests**

```python
from experiment import (
    CANDIDATES,
    content_free_result,
    executor_argv,
    mechanism_eligible,
    target_prompt,
)


def test_candidate_matrix_changes_one_declared_dimension() -> None:
    assert tuple(CANDIDATES) == (
        "baseline",
        "fp8",
        "prefix_off",
        "eager",
        "chunked_8k",
        "cpu_offload_4g",
        "kv_offload_1g",
    )
    assert "--max-model-len" in executor_argv(19301, CANDIDATES["baseline"])
    assert executor_argv(19301, CANDIDATES["fp8"])[-5:] == [
        "--kv-cache-dtype",
        "fp8",
        "--calculate-kv-scales",
        "--kv-cache-memory-bytes",
        "900000000",
    ]


def test_target_prompt_hits_safe_token_window() -> None:
    prompt, tokens = target_prompt(lambda value: value.count("x ") + 100)
    assert 63_000 <= tokens <= 64_500
    assert "NEEDLE-PHASE3-7291" in prompt


def test_live_mechanism_must_match_full_stop_and_pass_quality() -> None:
    assert mechanism_eligible(1000, 901, faster=True, stable=True, quality=True)
    assert not mechanism_eligible(1000, 899, faster=True, stable=True, quality=True)
    assert not mechanism_eligible(1000, 1000, faster=False, stable=True, quality=True)


def test_result_never_serializes_content() -> None:
    result = content_free_result(
        status=200,
        prompt_tokens=63_500,
        completion_tokens=4,
        finish_reason="stop",
    )
    serialized = str(result)
    for sentinel in ("SENTINEL_PROMPT", "SENTINEL_OUTPUT", "Authorization", "tool_args"):
        assert sentinel not in serialized
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest .superpowers/sdd/phase3-runtime/test_experiment.py -q
```

Expected: import failure because `experiment.py` does not exist.

- [ ] **Step 3: Implement the fixed candidate model and argument builder**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Candidate:
    name: str
    extra_args: tuple[str, ...] = ()


CANDIDATES = {
    "baseline": Candidate("baseline"),
    "fp8": Candidate(
        "fp8",
        ("--kv-cache-dtype", "fp8", "--calculate-kv-scales",
         "--kv-cache-memory-bytes", "900000000"),
    ),
    "prefix_off": Candidate("prefix_off", ("--no-enable-prefix-caching",)),
    "eager": Candidate("eager", ("--enforce-eager",)),
    "chunked_8k": Candidate(
        "chunked_8k",
        ("--enable-chunked-prefill", "--max-num-batched-tokens", "8192"),
    ),
    "cpu_offload_4g": Candidate("cpu_offload_4g", ("--cpu-offload-gb", "4")),
    "kv_offload_1g": Candidate(
        "kv_offload_1g",
        ("--kv-offloading-size", "1", "--kv-offloading-backend", "native"),
    ),
}


def executor_argv(port: int, candidate: Candidate) -> list[str]:
    baseline = [
        "/home/kotori9/.pyenv/versions/3.11.14/bin/python",
        "/home/kotori9/.pyenv/versions/3.11.14/bin/vllm",
        "serve", "/home/kotori9/models/dgx-moa/executor",
        "--host", "127.0.0.1", "--port", str(port),
        "--served-model-name", "dgx-moa-executor",
        "--max-model-len", "65536", "--max-num-seqs", "1",
        "--kv-cache-memory-bytes", "1700000000",
        "--gpu-memory-utilization", "0.5", "--moe-backend", "MARLIN",
        "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder",
    ]
    if candidate.name == "fp8":
        index = baseline.index("--kv-cache-memory-bytes")
        del baseline[index:index + 2]
    return baseline + list(candidate.extra_args)
```

Keep the FP8 assertion above as the executable guard against duplicate KV-byte
arguments. Do not introduce a generic free-form CLI option.

- [ ] **Step 4: Implement deterministic prompt sizing and result-only evidence**

```python
def target_prompt(count_tokens: Callable[[str], int]) -> tuple[str, int]:
    low, high = 1, 80_000
    best = ""
    best_tokens = 0
    while low <= high:
        middle = (low + high) // 2
        value = (
            "Remember NEEDLE-PHASE3-7291. " + "x " * middle
            + "Reply with only NEEDLE-PHASE3-7291."
        )
        tokens = count_tokens(value)
        if tokens < 63_000:
            low = middle + 1
        elif tokens > 64_500:
            high = middle - 1
        else:
            best, best_tokens = value, tokens
            break
    if not best:
        raise RuntimeError("unable to target 63k-64.5k prompt tokens")
    return best, best_tokens


def content_free_result(
    *, status: int, prompt_tokens: int | None,
    completion_tokens: int | None, finish_reason: str | None,
) -> dict[str, object]:
    return {
        "status": status,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason,
    }


def mechanism_eligible(
    full_delta: int, live_delta: int, *, faster: bool,
    stable: bool, quality: bool,
) -> bool:
    return (
        full_delta > 0
        and live_delta >= full_delta * 0.90
        and faster and stable and quality
    )
```

The physical tokenizer adapter imports `AutoTokenizer` lazily under the installed
vLLM Python and counts the full chat template with `add_generation_prompt=True`.

- [ ] **Step 5: Reuse exact ownership without copying it**

```python
import sys

TASK10_RUNTIME = Path(__file__).parents[1] / "task10-runtime"
sys.path.insert(0, str(TASK10_RUNTIME))
import harness as task10  # noqa: E402


class ExperimentDriver(task10.ExactProcessDriver):
    def __init__(self, root: Path, argv: list[str], port: int, extra_env: dict[str, str]):
        self.phase3_argv = argv
        self.phase3_port = port
        self.phase3_env = extra_env
        super().__init__(root)

    def _argv(self, role: str) -> list[str]:
        if role != "executor":
            raise ValueError("phase3 manages only executor")
        return self.phase3_argv

    def _port(self, role: str) -> int:
        if role != "executor":
            raise ValueError("phase3 manages only executor")
        return self.phase3_port

    def _env(self) -> dict[str, str]:
        return {**super()._env(), **self.phase3_env}
```

Add `/proc/meminfo` Cached, SReclaimable, and Shmem to the phase-three snapshot;
do not modify the Task 10 runner.

- [ ] **Step 6: Verify the ignored core and clean tracked state**

```bash
uv run pytest .superpowers/sdd/phase3-runtime/test_experiment.py -q
uv run ruff format --check .superpowers/sdd/phase3-runtime
uv run ruff check .superpowers/sdd/phase3-runtime
uv run python -m py_compile .superpowers/sdd/phase3-runtime/experiment.py
uv run python .superpowers/sdd/phase3-runtime/experiment.py --dry-run
git status --short
```

Expected: tests/lint/compile/dry-run pass; Git remains clean because the runner
is intentionally ignored. There is no commit for this ignored-only task.

---

### Task 2: Measure Full Stop, Sleep Levels, and Live KV Reset

**Files:**
- Modify ignored: `.superpowers/sdd/phase3-runtime/experiment.py`
- Modify ignored: `.superpowers/sdd/phase3-runtime/test_experiment.py`
- Create: `docs/MEMORY_OPTIMIZATION.md`
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: Task 1 `ExperimentDriver`, baseline argv, memory snapshots, and
  content-free results.
- Produces: `mechanisms.json` with physical A-D rows and a selected mechanism.

- [ ] **Step 1: Write failing exact transient-unit authorization tests**

```python
import pytest
from experiment import validate_transient_unit


def test_only_phase3_dev_transient_unit_is_allowed() -> None:
    assert validate_transient_unit("dgx-moa-dev-phase3-a1b2c3d4.service")
    for unit in (
        "dgx-moa-executor.service",
        "dgx-moa-dev-executor.service",
        "dgx-moa-dev-phase3-a1b2c3d4.target",
        "../dgx-moa-dev-phase3-a1b2c3d4.service",
    ):
        with pytest.raises(ValueError):
            validate_transient_unit(unit)
```

Add a fake-command test asserting that the controller issues only
`systemd-run --user`, `systemctl --user show`, and `systemctl --user stop` for
that exact unit and never invokes production scripts, `journalctl`, or a glob.

- [ ] **Step 2: Run RED**

```bash
uv run pytest .superpowers/sdd/phase3-runtime/test_experiment.py -q
```

- [ ] **Step 3: Implement the narrow transient-unit controller**

```python
import re
import subprocess

DEV_UNIT = re.compile(r"^dgx-moa-dev-phase3-[a-f0-9]{8}\.service$")


def validate_transient_unit(unit: str) -> bool:
    if not DEV_UNIT.fullmatch(unit):
        raise ValueError("invalid phase3 transient unit")
    return True


def start_transient(unit: str, root: Path, argv: list[str], env: dict[str, str]) -> None:
    validate_transient_unit(unit)
    command = [
        "systemd-run", "--user", f"--unit={unit}", "--collect",
        "--property=Type=simple", "--property=KillMode=control-group",
        "--property=TimeoutStopSec=180",
        f"--property=WorkingDirectory={root}",
        f"--property=StandardOutput=append:{root / 'logs/systemd-executor.log'}",
        f"--property=StandardError=append:{root / 'logs/systemd-executor.log'}",
    ]
    for key, value in sorted(env.items()):
        command.append(f"--setenv={key}={value}")
    subprocess.run([*command, "--", *argv], check=True)


def stop_transient(unit: str) -> None:
    validate_transient_unit(unit)
    subprocess.run(["systemctl", "--user", "stop", unit], check=True)
```

Before stop, `systemctl --user show` must return the expected unit name,
WorkingDirectory under the exact root, and MainPID whose `/proc` identity matches
the recorded argv. Use a unique exact unit for the restart cycle and verify it
is absent after `--collect` cleanup.

- [ ] **Step 4: Implement bounded sleep and reset cycles**

```python
def post_and_time(client: httpx.Client, path: str) -> float:
    started = time.monotonic()
    response = client.post(path)
    response.raise_for_status()
    return time.monotonic() - started


def sleep_cycle(client: httpx.Client, level: int) -> dict[str, object]:
    sleep_seconds = post_and_time(client, f"/sleep?level={level}&mode=abort")
    sleeping = client.get("/is_sleeping")
    sleeping.raise_for_status()
    if sleeping.json() != {"is_sleeping": True}:
        raise RuntimeError(f"sleep level {level} was not entered")
    wake_seconds = post_and_time(client, "/wake_up")
    return {"level": level, "sleep_seconds": sleep_seconds, "wake_seconds": wake_seconds}
```

Start sleep trials with `VLLM_SERVER_DEV_MODE=1` and `--enable-sleep-mode`.
Use `POST /reset_prefix_cache` only while no request is active. Poll `/health`
and `/v1/models` after wake, then run one short response, one forced native
tool call, and the backend-counted near-64K retrieval check. The full-stop row
runs the same checks after restart, and the reset row runs them after cache
clear. Repeat each live mechanism twice to detect retained growth; record level
2 as an explicit unsupported/rejected row if the engine cannot complete its
first bounded sleep/wake cycle.

- [ ] **Step 5: Run all pre-execution gates sequentially**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check
uv run pytest .superpowers/sdd/phase3-runtime/test_experiment.py -q
uv run python .superpowers/sdd/phase3-runtime/experiment.py --dry-run mechanisms
```

Expected repository baseline: 531 tests and trace audit 10/10. Dry-run must show
only ports `19301`/dev transient units and no production mutation.

- [ ] **Step 6: Execute the physical mechanism matrix**

```bash
/home/kotori9/.pyenv/versions/3.11.14/bin/python \
  .superpowers/sdd/phase3-runtime/experiment.py \
  --execute mechanisms --cache-seed /tmp/dgx-moa-task10-yhs6_hr8
```

Poll output at intervals shorter than 60 seconds. Stop only exact owned groups or
the exact validated transient dev unit. The command must exit nonzero on a leak,
bound scoped port, dirty repository, failed redaction scan, or incomplete A-D
row.

- [ ] **Step 7: Review raw evidence and publish mechanism results**

Require an independent read-only review of `mechanisms.json`, the complete
process/unit history, memory snapshots, short/tool checks, and final fingerprint.
Write `docs/MEMORY_OPTIMIZATION.md` with the A-D table, selected mechanism,
bytes/timings, rejected mechanisms, unified-memory limitations, and full-stop
fallback. Append every failed attempt to `docs/VALIDATION.md`.

- [ ] **Step 8: Verify and commit the mechanism study**

```bash
uv run pytest tests/test_goal_tooling.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
git diff --check
git add docs/MEMORY_OPTIMIZATION.md docs/VALIDATION.md
git commit -m "docs(memory): record unload mechanism study"
```

---

### Task 3: Run the One-Variable 64K Optimization Study

**Files:**
- Modify ignored: `.superpowers/sdd/phase3-runtime/experiment.py`
- Modify ignored: `.superpowers/sdd/phase3-runtime/test_experiment.py`
- Modify: `docs/MEMORY_OPTIMIZATION.md`
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: Task 1 candidate matrix and Task 2 physical/safety runner.
- Produces: `candidates.json`, a baseline comparison, and one evidence-selected
  executor configuration.

- [ ] **Step 1: Add failing physical-quality parser tests**

Test content-free validators with fixed fake responses:

```python
def test_near_limit_requires_usage_and_needle() -> None:
    result = validate_near_limit(
        status=200,
        prompt_tokens=63_750,
        output="NEEDLE-PHASE3-7291",
        finish_reason="stop",
    )
    assert result == {"passed": True, "prompt_tokens": 63_750, "finish_reason": "stop"}


def test_tool_validator_requires_native_json_arguments() -> None:
    result = validate_tool_call(
        {"id": "call_1", "type": "function",
         "function": {"name": "lookup_phase3", "arguments": '{"key":"alpha"}'}}
    )
    assert result == {"passed": True, "name": "lookup_phase3", "argument_keys": ["key"]}
```

Add failures for prompt tokens outside 63,000-64,500, absent needle, malformed
arguments, wrong tool name, `finish_reason=length`, non-finite numeric text, and
completion count at or below 1,000 for the long response.

- [ ] **Step 2: Run RED, then implement bounded validators**

```bash
uv run pytest .superpowers/sdd/phase3-runtime/test_experiment.py -q
```

Use `json.loads` for tool arguments, `math.isfinite` for parsed benchmark
numbers, and `ast.parse` for the code response. The only accepted code shape is
one `clamp(value, low, high)` function using arguments, comparisons, returns,
constants, and `if`; reject imports, attributes, comprehensions, calls, globals,
and all other nodes before compiling with empty builtins.

- [ ] **Step 3: Add exact quality fixtures without retaining content**

The runtime-only fixtures are:

```python
SHORT_CASES = (
    ("Reply only ORBIT-42.", "ORBIT-42"),
    ("Reply only with 37 plus 58.", "95"),
    ("cedar=19, birch=23. Reply only with birch.", "23"),
    ("Reply only lowercase: RELIABLE", "reliable"),
    ("Reply only with the third item: amber, cobalt, jade.", "jade"),
)
```

Use one 1,100-token numbered response request with `max_tokens=1400`; three
forced `lookup_phase3` tool calls for keys alpha/beta/gamma; the restricted
`clamp` code task; and one strict JSON schema requiring
`{"status":"approved","findings":[]}`. Persist only pass/fail, usage, timing,
finish reason, tool name/argument-key metadata, and SHA-256 of normalized output.

For both baseline and `prefix_off`, send two requests with the same synthetic
system prefix and different content-free suffixes. Record first/repeat prefill
latency, backend cache-hit evidence when exposed, settled MemAvailable/PSS,
reset success, and retained cost. Reject disabling prefix caching unless the
measured latency benefit is absent or the retained-memory cost conflicts with
recovery.

- [ ] **Step 4: Execute every required candidate**

```bash
/home/kotori9/.pyenv/versions/3.11.14/bin/python \
  .superpowers/sdd/phase3-runtime/experiment.py \
  --execute candidates --cache-seed /tmp/dgx-moa-task10-yhs6_hr8
```

For every candidate: start from a clean exact root, reach ready, record stage
memory, run short/tool/near-64K checks, record warm latency, stop, settle, and
fingerprint. Baseline and FP8 always run the full quality contract. Any other
candidate with improved memory also runs the full contract. FP8 receives one
1,000,000,000-byte retry only for proven insufficient KV capacity; every other
retry is forbidden and retained as failure.

- [ ] **Step 5: Select by deterministic evidence**

Reject any candidate with startup/request/quality/teardown failure, context
capacity below 65,536, owned-memory growth, or worse settled MemAvailable beyond
the matched noise band. Among remaining candidates select the lowest warm
owned-PSS configuration; break ties by near-64K latency, then cold-ready time.
If none improves safely, select the current baseline. Record why
`gpu_memory_utilization` was not swept and how dynamic FP8 scales were disabled
by the installed hybrid-model path.

- [ ] **Step 6: Independently review and commit the 64K evidence**

Update the memory and validation documents with all candidate rows, exact
settings, token usage, quality booleans, bytes, timings, rejected flags, and the
selection. Do not call a tokenizer-sized prompt a physical 64K pass unless the
backend-reported prompt usage is in range.

```bash
uv run pytest tests/test_goal_tooling.py -q
git diff --check
git add docs/MEMORY_OPTIMIZATION.md docs/VALIDATION.md
git commit -m "docs(memory): select measured 64k configuration"
```

---

### Task 4: Expose Only the Evidence-Selected Runtime Flags

**Files:**
- Modify only when required: `gateway/src/dgx_moa/serve.py`
- Modify only when required: `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 3 selected candidate.
- Produces: the smallest safe role-specific argv mapping needed to reproduce
  that candidate through the existing server launcher.

This task is a measured branch, not a guess:

- `baseline`: no source change and no commit.
- `eager`: already supported by `DGX_MOA_EXECUTOR_ENFORCE_EAGER`; no source
  change and no commit.
- `fp8`: add validated `DGX_MOA_EXECUTOR_KV_CACHE_DTYPE=fp8` support; existing
  KV-byte environment support supplies 900,000,000 or 1,000,000,000.
- `prefix_off`: add boolean `DGX_MOA_EXECUTOR_ENABLE_PREFIX_CACHING=false` and
  emit `--no-enable-prefix-caching`.
- `chunked_8k`: add boolean chunked-prefill plus integer batched-token support.
- `cpu_offload_4g`: add finite nonnegative role CPU-offload support.
- `kv_offload_1g`: add finite nonnegative role KV-offload size with the fixed
  native backend.

- [ ] **Step 1: Write exactly one failing selected-branch test**

For example, only if FP8 wins:

```python
def test_executor_uses_selected_fp8_kv_dtype(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DGX_MOA_EXECUTOR_KV_CACHE_DTYPE", "fp8")
    monkeypatch.setattr("dgx_moa.serve.load_settings", lambda: settings)
    arguments = command("executor")
    assert arguments[arguments.index("--kv-cache-dtype") + 1] == "fp8"
```

Add one invalid-value test for the same selected input. Do not add tests or code
for losing candidates.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/test_serve.py -q
```

- [ ] **Step 3: Implement the selected safe mapping**

The FP8 branch, if selected, is exactly:

```python
if kv_dtype := os.getenv(f"DGX_MOA_{role.upper()}_KV_CACHE_DTYPE"):
    if kv_dtype not in {"auto", "fp8"}:
        raise ValueError("KV_CACHE_DTYPE must be auto or fp8")
    arguments += ["--kv-cache-dtype", kv_dtype]
```

For a boolean winner, use existing `role_bool_environment`; for a numeric winner,
parse to `int` or `float`, require finite/nonnegative and a role-specific name,
then append the one fixed flag. Never accept a raw argument string.

- [ ] **Step 4: Verify and commit only a real source change**

```bash
uv run pytest tests/test_serve.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
git diff --check
git add gateway/src/dgx_moa/serve.py tests/test_serve.py
git commit -m "feat(runtime): apply measured 64k settings"
```

When baseline/eager wins, verify `git diff -- gateway/src/dgx_moa/serve.py
tests/test_serve.py` is empty and proceed without inventing a commit.

---

### Task 5: Prove the Selection Three Times and Redesign the Resident Profile

**Files:**
- Modify: `systemd/dgx-moa-resident.target`
- Modify: `scripts/wait-profile.sh`
- Modify: `scripts/verify-profile-stopped.sh`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/context_tuning.py`
- Modify: `tests/test_systemd_units.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_context_tuning.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/MODEL_LIFECYCLE.md`
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: selected mechanism/configuration and optional Task 4 launcher support.
- Produces: three clean physical cycles and an undeployed executor-only resident
  target with optional roles remaining on demand.

- [ ] **Step 1: Run three clean selected-config physical cycles**

```bash
/home/kotori9/.pyenv/versions/3.11.14/bin/python \
  .superpowers/sdd/phase3-runtime/experiment.py \
  --execute selected --cycles 3 --cache-seed /tmp/dgx-moa-task10-yhs6_hr8
```

Each cycle requires ready, backend-reported 63K-64.5K prompt usage, expected
needle, three native tool calls, complete quality contract, selected unload,
zero owned PSS/RSS after final stop, scoped ports unbound, and no failures.
After the third cycle, launch an isolated gateway on port 19300 and make one
normal client request that confirms the advertised executor context is 65,536;
retain only status/usage/config metadata. Independent review must pass before
changing tracked topology.

- [ ] **Step 2: Write failing executor-only resident tests**

```python
def test_resident_target_requires_only_gateway_and_executor() -> None:
    resident = (SYSTEMD / "dgx-moa-resident.target").read_text()
    assert "Requires=dgx-moa-gateway.service dgx-moa-executor.service" in resident
    requires = next(line for line in resident.splitlines() if line.startswith("Requires="))
    assert "planner" not in requires and "reviewer" not in requires and "reasoner" not in requires
```

Update `test_profile_aware_readiness` so the fake returns 200 only for executor
and resident `/readyz` still returns 200 with planner/reviewer/reasoner stopped.
Add script-text tests requiring resident wait port `(8101)` and stop verification
for services executor/planner/reviewer/reasoner plus ports 8101-8104.

For context tuning:

```python
def test_resident_candidates_keep_public_executor_at_64k() -> None:
    assert candidate_vectors("resident", {"executor": 262144}) == [{"executor": 65536}]
```

- [ ] **Step 3: Run RED**

```bash
uv run pytest tests/test_systemd_units.py tests/test_api.py \
  tests/test_context_tuning.py -q
```

- [ ] **Step 4: Make resident readiness and target executor-only**

Change the target to:

```ini
[Unit]
Description=DGX MoA resident profile
Requires=dgx-moa-gateway.service dgx-moa-executor.service
After=dgx-moa-gateway.service dgx-moa-executor.service dgx-moa-judge.target
Conflicts=dgx-moa-judge.target

[Install]
WantedBy=default.target
```

In `api.py`, use:

```python
roles = {
    "resident": ("executor",),
    "judge": ("judge",),
}.get(current, ())
```

Keep optional service `PartOf=dgx-moa-resident.target` so profile stop also
stops any optional role loaded on demand.

- [ ] **Step 5: Align scripts and the old tuning command**

Use these exact shell arrays:

```bash
# wait-profile.sh
resident) ports=(8101); minimum=5368709120 ;;

# verify-profile-stopped.sh
resident) services=(executor planner reviewer reasoner); ports=(8101 8102 8103 8104) ;;
```

In `context_tuning.py`, return only `{"executor": 65536}` for a resident native
limit at or above 65,536, use only role `executor` in resident `run_trial`, and
make the resident score equal to executor context. Judge behavior stays intact.

- [ ] **Step 6: Verify tracked behavior and units**

```bash
uv run pytest tests/test_systemd_units.py tests/test_api.py \
  tests/test_context_tuning.py -q
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
git diff --check
```

- [ ] **Step 7: Document migration and commit**

Document that this is an undeployed target change, lifecycle remains disabled,
optional cold roles return typed 503 when required, migration requires later
human-reviewed PR/deployment, and rollback restores the previous target file.

```bash
git add systemd/dgx-moa-resident.target scripts/wait-profile.sh \
  scripts/verify-profile-stopped.sh gateway/src/dgx_moa/api.py \
  gateway/src/dgx_moa/context_tuning.py tests/test_systemd_units.py \
  tests/test_api.py tests/test_context_tuning.py docs/ARCHITECTURE.md \
  docs/OPERATIONS.md docs/MODEL_LIFECYCLE.md docs/VALIDATION.md
git commit -m "feat(runtime): keep optional roles on demand"
```

---

### Task 6: Measure Python Residency and Decide Against or For Rust

**Files:**
- Create ignored: `.superpowers/sdd/phase3-runtime/gateway_probe.py`
- Create ignored: `.superpowers/sdd/phase3-runtime/test_gateway_probe.py`
- Create: `docs/RUST_EVALUATION.md`
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: existing `.venv/bin/dgx-moa`, Task 1 ownership/memory helpers, and
  current restart-recovery tests.
- Produces: five-minute content-free Python gateway measurements and a Rust
  decision.

- [ ] **Step 1: Write failing CPU/PSS/percentile probe tests**

```python
def test_cpu_delta_uses_clock_ticks() -> None:
    assert cpu_percent(start_ticks=100, end_ticks=150, elapsed=5.0, hz=100) == 10.0


def test_nearest_rank_p99() -> None:
    values = list(range(1, 101))
    assert percentile(values, 0.99) == 99
```

Add validation that elapsed/HZ are positive, samples are finite/nonnegative,
and output contains no headers or response bodies.

- [ ] **Step 2: Run RED, implement stdlib probe, and run unit tests**

```bash
uv run pytest .superpowers/sdd/phase3-runtime/test_gateway_probe.py -q
```

Read `/proc/<pid>/stat` utime+stime, `os.sysconf("SC_CLK_TCK")`, and
`smaps_rollup`; sample `/healthz` every 500 ms on loopback and retain only
schedule drift and response latency numbers. Use nearest-rank percentiles and
`time.monotonic`.

- [ ] **Step 3: Run an isolated five-minute gateway baseline**

```bash
uv run python .superpowers/sdd/phase3-runtime/gateway_probe.py \
  --execute --duration-seconds 300 --port 19300
```

The probe launches `.venv/bin/dgx-moa` with auth disabled, lifecycle disabled,
current config, isolated state/run/trace directories, and no model calls. It
must own and terminate the exact process and leave port 19300 unbound.

- [ ] **Step 4: Run correctness/recovery evidence**

```bash
uv run pytest tests/test_lifecycle.py tests/test_api.py tests/test_runtime_status.py -q
```

- [ ] **Step 5: Write and commit the Rust decision**

Record PSS/RSS, five-minute idle CPU, loopback event-loop/HTTP p50/p95/p99 proxy,
startup time, recovery-test result, comparison with executor model memory, and
candidate Rust responsibilities. If PSS is at most 256 MiB, CPU at most 1%, p99
at most 50 ms, and no Python-attributable correctness gap remains, reject Rust
and create no crate. If any threshold fails, stop Phase 3 and create a separate
approved Rust prototype spec; do not improvise Rust inside this plan.

```bash
git add docs/RUST_EVALUATION.md docs/VALIDATION.md
git commit -m "docs(runtime): record measured Rust decision"
```

---

### Task 7: Publish the Phase-Three Decision and Run Final Gates

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/STATE.md`
- Modify: `docs/VALIDATION.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/MODEL_LIFECYCLE.md`
- Modify: `docs/MEMORY_OPTIMIZATION.md`
- Modify: `docs/RUST_EVALUATION.md`

**Interfaces:**
- Consumes: all independently reviewed Phase 3 physical and tracked evidence.
- Produces: one internally consistent current-state record and clean Phase 3
  handoff to the phase-four client matrix/soak.

- [ ] **Step 1: Update only evidence-backed claims**

Record exact selected mechanism/config, every rejected mechanism and reason,
near-64K backend token count, three-cycle result, original three-role/warm
executor/cold bytes, load/wake/unload timings, Python measurements, undeployed
resident topology, migration, rollback, and limitations. Preserve every failed
root and distinguish metadata fingerprints from content hashes.

Do not edit `docs/TRACE_SCHEMA.md` unless the tracked trace schema actually
changed; state explicitly in the final review that Phase 3 made no schema change.

- [ ] **Step 2: Run the eight final gates sequentially**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check
```

Expected: all exit zero; trace corpus remains 10/10 unless later tracked tests
intentionally add complete sanitized v2 records.

- [ ] **Step 3: Perform the completion audit and independent review**

Compare the final diff and documents against every Phase 3 design acceptance
item and raw result row. Verify production repo commit/status, scoped ports,
runtime processes, model metadata fingerprint, and tracked file scope. Any
uncertain row remains incomplete rather than inferred.

- [ ] **Step 4: Commit Phase 3 documentation**

```bash
git add README.md AGENTS.md docs/STATE.md docs/VALIDATION.md \
  docs/OPERATIONS.md docs/ARCHITECTURE.md docs/DECISIONS.md \
  docs/MODEL_LIFECYCLE.md docs/MEMORY_OPTIMIZATION.md docs/RUST_EVALUATION.md
git commit -m "docs: publish memory and resident profile decisions"
```

- [ ] **Step 5: Re-run final verification after the commit**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check
git status --short
```

Expected: every gate exits zero and the worktree is clean. Do not push or open
the PR yet; those remain after Phase 4 client counts and soak.
