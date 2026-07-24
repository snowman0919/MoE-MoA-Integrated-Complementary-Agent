#!/usr/bin/env python3
"""Run reproducible coding tasks through installed client harnesses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARNESSES = ("baseline", "opencode", "codex", "hermes")
CORE_ENV = ("HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
TEST_COMMAND = (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
BAD_TERMINALS = (
    "stream disconnected before completion",
    "reconnecting 5/5",
    '"type":"turn.failed"',
    '"type":"response.failed"',
    "다음 도구 작업을 준비합니다.",
    "Planner 역할이 구조와 구현 순서를 설계합니다.",
)


@dataclass(frozen=True)
class Task:
    slug: str
    source_name: str
    readme: str
    starter: str
    tests: str


def block(value: str) -> str:
    return textwrap.dedent(value).lstrip()


TASKS = (
    Task(
        "rate-limiter",
        "rate_limiter.py",
        block(
            """
            # Sliding-window rate limiter

            Implement `SlidingWindowLimiter(limit, window_seconds, clock=...)`.

            - `allow(key, now=None)` records an allowed request and returns bool.
            - `remaining(key, now=None)` reports capacity without consuming it.
            - Keys are independent. Empty/non-string keys are invalid.
            - `limit` is a positive int; `window_seconds` is positive.
            - Events exactly at `now - window_seconds` are expired.
            - Concurrent calls for one key must never admit more than `limit`.
            - Use only Python's standard library.
            """
        ),
        block(
            """
            import time


            class SlidingWindowLimiter:
                def __init__(self, limit, window_seconds, clock=time.monotonic):
                    raise NotImplementedError

                def allow(self, key, now=None):
                    raise NotImplementedError

                def remaining(self, key, now=None):
                    raise NotImplementedError
            """
        ),
        block(
            """
            import threading
            import unittest

            from rate_limiter import SlidingWindowLimiter


            class RateLimiterTests(unittest.TestCase):
                def test_validation(self):
                    for limit in (0, -1, True):
                        with self.assertRaises((TypeError, ValueError)):
                            SlidingWindowLimiter(limit, 1)
                    with self.assertRaises((TypeError, ValueError)):
                        SlidingWindowLimiter(1, 0)

                def test_window_and_remaining(self):
                    limiter = SlidingWindowLimiter(2, 10, clock=lambda: 0)
                    self.assertEqual(limiter.remaining("a", 0), 2)
                    self.assertTrue(limiter.allow("a", 0))
                    self.assertTrue(limiter.allow("a", 1))
                    self.assertFalse(limiter.allow("a", 9))
                    self.assertEqual(limiter.remaining("a", 9), 0)
                    self.assertTrue(limiter.allow("a", 10))
                    self.assertEqual(limiter.remaining("a", 10), 0)

                def test_keys_are_independent(self):
                    limiter = SlidingWindowLimiter(1, 5)
                    self.assertTrue(limiter.allow("a", 1))
                    self.assertTrue(limiter.allow("b", 1))
                    self.assertFalse(limiter.allow("a", 1))
                    with self.assertRaises((TypeError, ValueError)):
                        limiter.allow("")

                def test_concurrent_admission_is_bounded(self):
                    limiter = SlidingWindowLimiter(7, 5)
                    barrier = threading.Barrier(40)
                    results = []
                    lock = threading.Lock()

                    def worker():
                        barrier.wait()
                        result = limiter.allow("shared", 1)
                        with lock:
                            results.append(result)

                    threads = [threading.Thread(target=worker) for _ in range(40)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                    self.assertEqual(sum(results), 7)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "atomic-store",
        "atomic_store.py",
        block(
            """
            # Atomic versioned JSON store

            Implement `AtomicJSONStore(path)` and `VersionConflict`.

            - `read()` returns `(version, data)`; a missing file is `(0, {})`.
            - `update(expected_version, changes)` atomically merges a mapping and
              returns the next version.
            - Stale versions raise `VersionConflict` without changing the file.
            - Invalid/non-JSON values fail without changing the file.
            - Corrupt existing JSON raises `ValueError` and is never overwritten.
            - Writes use a same-directory temporary file, fsync, and `os.replace`.
            - Calls are thread-safe within the process. Standard library only.
            """
        ),
        block(
            """
            class VersionConflict(RuntimeError):
                pass


            class AtomicJSONStore:
                def __init__(self, path):
                    raise NotImplementedError

                def read(self):
                    raise NotImplementedError

                def update(self, expected_version, changes):
                    raise NotImplementedError
            """
        ),
        block(
            """
            import json
            import tempfile
            import threading
            import unittest
            from pathlib import Path

            from atomic_store import AtomicJSONStore, VersionConflict


            class AtomicStoreTests(unittest.TestCase):
                def setUp(self):
                    self.temp = tempfile.TemporaryDirectory()
                    self.path = Path(self.temp.name) / "state.json"
                    self.store = AtomicJSONStore(self.path)

                def tearDown(self):
                    self.temp.cleanup()

                def test_missing_and_round_trip(self):
                    self.assertEqual(self.store.read(), (0, {}))
                    self.assertEqual(self.store.update(0, {"a": 1}), 1)
                    self.assertEqual(self.store.read(), (1, {"a": 1}))
                    self.assertEqual(self.store.update(1, {"b": [2]}), 2)
                    self.assertEqual(self.store.read(), (2, {"a": 1, "b": [2]}))

                def test_stale_and_invalid_updates_preserve_bytes(self):
                    self.store.update(0, {"a": 1})
                    before = self.path.read_bytes()
                    with self.assertRaises(VersionConflict):
                        self.store.update(0, {"a": 2})
                    with self.assertRaises((TypeError, ValueError)):
                        self.store.update(1, {"bad": object()})
                    self.assertEqual(self.path.read_bytes(), before)

                def test_corruption_fails_closed(self):
                    self.path.write_text("{broken")
                    with self.assertRaises(ValueError):
                        self.store.read()
                    with self.assertRaises(ValueError):
                        self.store.update(0, {"a": 1})
                    self.assertEqual(self.path.read_text(), "{broken")

                def test_compare_and_swap_is_thread_safe(self):
                    barrier = threading.Barrier(20)
                    results = []
                    lock = threading.Lock()

                    def worker(index):
                        barrier.wait()
                        try:
                            result = self.store.update(0, {str(index): index})
                        except VersionConflict:
                            result = None
                        with lock:
                            results.append(result)

                    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                    self.assertEqual(results.count(1), 1)
                    self.assertEqual(self.store.read()[0], 1)
                    leftovers = [p for p in self.path.parent.iterdir() if p != self.path]
                    self.assertEqual(leftovers, [])


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "dag-runner",
        "dag_runner.py",
        block(
            """
            # Deterministic concurrent DAG runner

            Implement `execution_layers(dependencies)` and
            `run_dag(dependencies, functions, max_workers=4)`.

            - Every dependency and function name must be declared as a node.
            - Return deterministic lexicographically sorted execution layers.
            - Cycles raise `CycleError` containing the unresolved node names.
            - Nodes in one layer execute concurrently; later layers wait.
            - A failure prevents dependent/later layers from starting and is re-raised.
            - The returned result mapping follows deterministic layer/name order.
            - Validate inputs and use only the standard library.
            """
        ),
        block(
            """
            class CycleError(ValueError):
                pass


            def execution_layers(dependencies):
                raise NotImplementedError


            def run_dag(dependencies, functions, max_workers=4):
                raise NotImplementedError
            """
        ),
        block(
            """
            import threading
            import time
            import unittest

            from dag_runner import CycleError, execution_layers, run_dag


            class DagRunnerTests(unittest.TestCase):
                def test_deterministic_layers(self):
                    deps = {
                        "build": {"lint", "test"},
                        "test": {"fetch"},
                        "lint": set(),
                        "fetch": set(),
                    }
                    self.assertEqual(
                        execution_layers(deps),
                        [("fetch", "lint"), ("test",), ("build",)],
                    )

                def test_unknown_dependency_and_cycle(self):
                    with self.assertRaises(ValueError):
                        execution_layers({"a": {"missing"}})
                    with self.assertRaises(CycleError) as caught:
                        execution_layers({"a": {"b"}, "b": {"a"}})
                    self.assertIn("a", str(caught.exception))
                    self.assertIn("b", str(caught.exception))

                def test_same_layer_runs_concurrently(self):
                    started = threading.Barrier(2)

                    def slow(name):
                        started.wait(timeout=1)
                        time.sleep(0.12)
                        return name

                    before = time.monotonic()
                    result = run_dag(
                        {"a": set(), "b": set(), "c": {"a", "b"}},
                        {"a": lambda: slow("a"), "b": lambda: slow("b"), "c": lambda: "c"},
                        max_workers=2,
                    )
                    elapsed = time.monotonic() - before
                    self.assertLess(elapsed, 0.23)
                    self.assertEqual(list(result), ["a", "b", "c"])

                def test_failure_stops_later_layers(self):
                    called = []

                    def fail():
                        raise RuntimeError("boom")

                    with self.assertRaisesRegex(RuntimeError, "boom"):
                        run_dag(
                            {"a": set(), "b": {"a"}},
                            {"a": fail, "b": lambda: called.append("b")},
                        )
                    self.assertEqual(called, [])

                def test_function_set_must_match_nodes(self):
                    with self.assertRaises(ValueError):
                        run_dag({"a": set()}, {})
                    with self.assertRaises((TypeError, ValueError)):
                        run_dag({"a": set()}, {"a": lambda: 1}, max_workers=0)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "webhook-verifier",
        "webhook.py",
        block(
            """
            # Replay-safe webhook verifier

            Implement `WebhookVerifier(secret, tolerance_seconds=300, clock=time.time,
            max_body_bytes=1_000_000)`.

            `verify(body, timestamp, nonce, signature)` signs the exact bytes
            `timestamp + b"." + nonce + b"." + body` with HMAC-SHA256. The supplied
            signature format is `v1=<lowercase hex>`.

            Reject malformed input, oversized bodies, timestamps outside tolerance,
            invalid signatures, and replayed valid nonces. Nonces match
            `[A-Za-z0-9_-]{8,128}`. Invalid signatures must not consume a nonce.
            Concurrent verification of one valid nonce permits exactly one success.
            Use constant-time comparison and only the standard library.
            """
        ),
        block(
            """
            class WebhookVerifier:
                def __init__(
                    self,
                    secret,
                    tolerance_seconds=300,
                    clock=None,
                    max_body_bytes=1_000_000,
                ):
                    raise NotImplementedError

                def verify(self, body, timestamp, nonce, signature):
                    raise NotImplementedError
            """
        ),
        block(
            """
            import hashlib
            import hmac
            import threading
            import unittest

            from webhook import WebhookVerifier


            def signature(secret, body, timestamp, nonce):
                message = timestamp.encode() + b"." + nonce.encode() + b"." + body
                return "v1=" + hmac.new(secret, message, hashlib.sha256).hexdigest()


            class WebhookTests(unittest.TestCase):
                def setUp(self):
                    self.secret = b"test-secret"
                    self.verifier = WebhookVerifier(
                        self.secret, clock=lambda: 1000, max_body_bytes=20
                    )

                def test_valid_then_replay(self):
                    sig = signature(self.secret, b"hello", "1000", "nonce_123")
                    self.assertTrue(self.verifier.verify(b"hello", "1000", "nonce_123", sig))
                    self.assertFalse(self.verifier.verify(b"hello", "1000", "nonce_123", sig))

                def test_invalid_does_not_consume_nonce(self):
                    self.assertFalse(
                        self.verifier.verify(
                            b"x", "1000", "nonce_456", "v1=" + "0" * 64
                        )
                    )
                    sig = signature(self.secret, b"x", "1000", "nonce_456")
                    self.assertTrue(self.verifier.verify(b"x", "1000", "nonce_456", sig))

                def test_bounds_and_validation(self):
                    sig = signature(self.secret, b"x", "699", "nonce_789")
                    self.assertFalse(self.verifier.verify(b"x", "699", "nonce_789", sig))
                    self.assertFalse(self.verifier.verify(b"x" * 21, "1000", "nonce_789", sig))
                    for nonce in ("short", "../unsafe", "x" * 129):
                        self.assertFalse(self.verifier.verify(b"x", "1000", nonce, sig))
                    self.assertFalse(self.verifier.verify("not-bytes", "1000", "nonce_789", sig))

                def test_concurrent_replay_gate(self):
                    verifier = WebhookVerifier(self.secret, clock=lambda: 1000)
                    sig = signature(self.secret, b"x", "1000", "concurrent_nonce")
                    barrier = threading.Barrier(30)
                    results = []
                    lock = threading.Lock()

                    def worker():
                        barrier.wait()
                        result = verifier.verify(b"x", "1000", "concurrent_nonce", sig)
                        with lock:
                            results.append(result)

                    threads = [threading.Thread(target=worker) for _ in range(30)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                    self.assertEqual(sum(results), 1)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "log-report",
        "log_report.py",
        block(
            """
            # Safe JSONL log report

            Implement `summarize(lines, sample_limit=3)` plus
            `python -m log_report PATH`.

            - Ignore blank lines; malformed/non-object JSON raises
              `ValueError("line N: ...")`.
            - Each object requires string `level` and `event`.
            - Return deterministic counts by level/event and up to `sample_limit`
              sanitized records in input order.
            - Recursively replace values whose case-insensitive key contains
              api_key, token, cookie, authorization, prompt, or reasoning with
              `[REDACTED]`; do not mutate caller objects.
            - CLI prints sorted JSON and exits 0. Input errors print one concise
              stderr line and exit 2. Standard library only.
            """
        ),
        block(
            """
            def summarize(lines, sample_limit=3):
                raise NotImplementedError


            def main(argv=None):
                raise NotImplementedError


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        block(
            """
            import json
            import subprocess
            import sys
            import tempfile
            import unittest
            from pathlib import Path

            from log_report import summarize


            class LogReportTests(unittest.TestCase):
                def test_counts_samples_and_recursive_redaction(self):
                    source = [
                        json.dumps(
                            {
                                "level": "INFO",
                                "event": "start",
                                "token": "secret",
                                "nested": {"CookieValue": "x"},
                            }
                        ),
                        "",
                        json.dumps(
                            {
                                "level": "ERROR",
                                "event": "failed",
                                "message": "bad",
                                "items": [{"api_key": "y"}],
                            }
                        ),
                        json.dumps({"level": "INFO", "event": "start", "prompt_raw": "private"}),
                    ]
                    report = summarize(source, sample_limit=2)
                    self.assertEqual(report["levels"], {"ERROR": 1, "INFO": 2})
                    self.assertEqual(report["events"], {"failed": 1, "start": 2})
                    self.assertEqual(len(report["samples"]), 2)
                    encoded = json.dumps(report)
                    self.assertNotIn("secret", encoded)
                    self.assertNotIn('"x"', encoded)
                    self.assertNotIn('"y"', encoded)
                    self.assertIn("[REDACTED]", encoded)

                def test_input_not_mutated_and_validation(self):
                    record = {"level": "INFO", "event": "x", "token": "keep"}
                    summarize([json.dumps(record)])
                    self.assertEqual(record["token"], "keep")
                    with self.assertRaisesRegex(ValueError, "line 1"):
                        summarize(["{bad"])
                    with self.assertRaisesRegex(ValueError, "line 1"):
                        summarize(["[]"])
                    with self.assertRaises((TypeError, ValueError)):
                        summarize([], sample_limit=-1)

                def test_cli_success_and_failure(self):
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / "events.jsonl"
                        path.write_text('{"level":"INFO","event":"ok"}\\n')
                        good = subprocess.run(
                            [sys.executable, "-m", "log_report", str(path)],
                            text=True,
                            capture_output=True,
                        )
                        self.assertEqual(good.returncode, 0)
                        self.assertEqual(json.loads(good.stdout)["events"], {"ok": 1})
                        path.write_text("{bad\\n")
                        bad = subprocess.run(
                            [sys.executable, "-m", "log_report", str(path)],
                            text=True,
                            capture_output=True,
                        )
                        self.assertEqual(bad.returncode, 2)
                        self.assertIn("line 1", bad.stderr)
                        self.assertNotIn("Traceback", bad.stderr)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
)
TASK_BY_SLUG = {task.slug: task for task in TASKS}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_name(run_id: str, harness: str, task: Task) -> str:
    safe_run = re.sub(r"[^a-z0-9-]", "-", run_id.lower())[:24]
    return f"moa-qm-{safe_run}-{harness}-{task.slug}"


def paths(args: argparse.Namespace, harness: str, task: Task) -> tuple[Path, Path]:
    workspace = args.workspace_root / workspace_name(args.run_id, harness, task)
    evidence = args.output_root / args.run_id / harness / task.slug
    return workspace, evidence


def git(workspace: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *arguments],
        text=True,
        capture_output=True,
        check=check,
    )


def prepare_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    if workspace.exists() or evidence.exists():
        raise RuntimeError(f"fixture already exists: {workspace}")
    workspace.mkdir(parents=True)
    evidence.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text(
        "Stay inside this repository. Do not modify AGENTS.md, README.md, or tests/. "
        "Use only Python's standard library. Inspect, implement, and run the full test command.\n"
    )
    (workspace / "README.md").write_text(task.readme)
    (workspace / task.source_name).write_text(task.starter)
    tests = workspace / "tests"
    tests.mkdir()
    (tests / "test_task.py").write_text(task.tests)
    git(workspace, "init", "-q", "-b", "main")
    git(workspace, "add", ".")
    git(
        workspace,
        "-c",
        "user.name=quality-matrix",
        "-c",
        "user.email=quality@example.invalid",
        "commit",
        "-qm",
        "starter",
    )
    starter_test = subprocess.run(
        TEST_COMMAND, cwd=workspace, text=True, capture_output=True, check=False
    )
    if starter_test.returncode == 0:
        raise RuntimeError(f"starter unexpectedly passes: {task.slug}")
    manifest = {
        "run_id": args.run_id,
        "harness": harness,
        "task": task.slug,
        "workspace": str(workspace),
        "source_name": task.source_name,
        "initial_commit": git(workspace, "rev-parse", "HEAD").stdout.strip(),
        "tests_sha256": sha256(tests / "test_task.py"),
        "starter_test_exit": starter_test.returncode,
    }
    (evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if harness == "opencode":
        exclude = workspace / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\nopencode.json\n")
        session = f"quality-{args.run_id}-opencode-{task.slug}"
        config = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "dgx-moa": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "DGX MoA",
                    "options": {
                        "baseURL": args.gateway.rstrip("/") + "/v1",
                        "apiKey": "{env:DGX_MOA_API_KEY}",
                        "headers": {
                            "X-Session-ID": session,
                            "X-Runtime-Channel": "main",
                            "X-Trace-Origin": "validation",
                            "X-Task-ID": f"{args.run_id}-{task.slug}",
                            "X-Workspace-Path": str(workspace),
                            "X-Workspace-ID": f"quality-{args.run_id}",
                            "X-Repository-Branch": "main",
                            "X-Repository-Commit": manifest["initial_commit"],
                            "X-Dirty-State": "clean",
                        },
                    },
                    "models": {"dgx-moa-agent": {"name": "DGX MoA Agent"}},
                }
            },
            "model": "dgx-moa/dgx-moa-agent",
            "permission": {
                "*": "deny",
                "bash": "allow",
                "edit": "allow",
                "glob": "allow",
                "grep": "allow",
                "read": "allow",
                "write": "allow",
            },
        }
        (workspace / "opencode.json").write_text(json.dumps(config, indent=2) + "\n")
    return manifest


def prompt(task: Task) -> str:
    return (
        "이 저장소의 신규 실사용급 작업을 완료하라. AGENTS.md, README.md, tests/를 확인하고 "
        f"{task.source_name}만 구현하라. 테스트나 요구사항 파일은 수정하지 마라. "
        f"`{sys.executable} -m unittest discover -s tests -v`를 실제 실행하고, 실패하면 수정 후 "
        "재실행하라. 도구 실행 없이 완료를 선언하지 말고 진행 문장만 남긴 채 종료하지 마라. "
        "최종 응답은 한국어 6줄 이내로 변경 파일, 테스트 명령/결과, 남은 위험을 적어라."
    )


def filtered_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = {name: os.environ[name] for name in CORE_ENV if name in os.environ}
    environment.update(extra or {})
    return environment


def run_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = (
            error.stdout.decode(errors="replace")
            if isinstance(error.stdout, bytes)
            else error.stdout
        )
        stderr = (
            error.stderr.decode(errors="replace")
            if isinstance(error.stderr, bytes)
            else error.stderr
        )
        return subprocess.CompletedProcess(
            command, 124, stdout or "", (stderr or "") + "\ntimeout\n"
        )


def run_codex_admin(args: argparse.Namespace, workspace: Path, task: Task) -> tuple[int, str, str]:
    token = os.getenv("DGX_MOA_OPERATOR_KEY")
    if not token:
        raise RuntimeError("DGX_MOA_OPERATOR_KEY is required for Codex admin")
    body = json.dumps(
        {"prompt": prompt(task), "mode": "agent", "workspace": workspace.name}
    ).encode()
    request = urllib.request.Request(
        args.gateway.rstrip("/") + "/v1/admin/codex",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            return response.status, response.read().decode(errors="replace"), ""
    except urllib.error.HTTPError as error:
        return error.code, "", error.read().decode(errors="replace")
    except (TimeoutError, urllib.error.URLError) as error:
        return 124, "", type(error).__name__


def run_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    if not (evidence / "manifest.json").exists():
        raise RuntimeError(f"prepare first: {harness}/{task.slug}")
    started_at = time.time()
    started = time.monotonic()
    if harness == "opencode":
        key = os.getenv("DGX_MOA_OPENCODE_KEY")
        if not key:
            raise RuntimeError("DGX_MOA_OPENCODE_KEY is required")
        state = evidence / "opencode-state"
        state.mkdir(exist_ok=True)
        environment = filtered_env(
            {
                "DGX_MOA_API_KEY": key,
                "HOME": str(state),
                "XDG_CACHE_HOME": str(state / "cache"),
                "XDG_CONFIG_HOME": str(state / "config"),
                "XDG_DATA_HOME": str(state / "data"),
                "XDG_STATE_HOME": str(state / "state"),
            }
        )
        command = [
            "/home/kotori9/.opencode/bin/opencode",
            "run",
            "--format",
            "json",
            "--pure",
            "--auto",
            "--dir",
            str(workspace),
            "--model",
            "dgx-moa/dgx-moa-agent",
            prompt(task),
        ]
        run = run_process(command, cwd=workspace, environment=environment, timeout=args.timeout)
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    elif harness == "codex":
        return_code, stdout, stderr = run_codex_admin(args, workspace, task)
        return_code = 0 if return_code == 200 else return_code
    elif harness == "baseline":
        command = [
            "/home/kotori9/.local/bin/codex",
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "workspace-write",
            "-C",
            str(workspace),
            "-m",
            "gpt-5.6-sol",
            prompt(task),
        ]
        run = run_process(
            command,
            cwd=workspace,
            environment=filtered_env(),
            timeout=args.timeout,
        )
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    else:
        hermes_home = args.output_root / args.run_id / "profiles" / f"hermes-{task.slug}"
        hermes_home.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/home/kotori9/.hermes/config.yaml", hermes_home / "config.yaml")
        shutil.copy2("/home/kotori9/.hermes/.env", hermes_home / ".env")
        (hermes_home / "config.yaml").chmod(0o600)
        (hermes_home / ".env").chmod(0o600)
        usage_path = evidence / "usage.json"
        command = [
            "/home/kotori9/.hermes/hermes-agent/venv/bin/python",
            "-m",
            "hermes_cli.main",
            "-z",
            prompt(task),
            "--usage-file",
            str(usage_path),
            "--provider",
            "custom:dgx-moa-agent",
            "--model",
            "dgx-moa-orchestrated",
            "--pass-session-id",
        ]
        run = run_process(
            command,
            cwd=workspace,
            environment=filtered_env({"HERMES_HOME": str(hermes_home)}),
            timeout=args.timeout,
        )
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    duration = round(time.monotonic() - started, 3)
    (evidence / "stdout.log").write_text(stdout)
    (evidence / "stderr.log").write_text(stderr)
    result = {
        "harness": harness,
        "task": task.slug,
        "return_code": return_code,
        "started_at_epoch": started_at,
        "ended_at_epoch": time.time(),
        "duration_seconds": duration,
    }
    (evidence / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def log_text(evidence: Path) -> str:
    values = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".log", ".txt"}:
            values.append(path.read_text(errors="replace"))
    return "\n".join(values)


def score_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    manifest = json.loads((evidence / "manifest.json").read_text())
    run = json.loads((evidence / "run.json").read_text())
    validation = subprocess.run(
        TEST_COMMAND, cwd=workspace, text=True, capture_output=True, check=False
    )
    (evidence / "validation.stdout.log").write_text(validation.stdout)
    (evidence / "validation.stderr.log").write_text(validation.stderr)
    tests_unchanged = sha256(workspace / "tests/test_task.py") == manifest["tests_sha256"]
    changed = [
        line
        for line in git(workspace, "diff", "--name-only", "HEAD").stdout.splitlines()
        if line and line != "opencode.json"
    ]
    raw_log = log_text(evidence)
    stdout = (evidence / "stdout.log").read_text(errors="replace")
    terminal = {
        "opencode": '"reason":"stop"',
        "codex": '"type":"turn.completed"',
        "baseline": '"type":"turn.completed"',
        "hermes": "",
    }[harness]
    terminal_ok = bool(stdout.strip()) if not terminal else terminal in raw_log
    korean_final = bool(re.search(r"[가-힣]", stdout[-8_000:]))
    tool_evidence = "unittest" in raw_log
    no_bad_terminal = not any(marker.lower() in raw_log.lower() for marker in BAD_TERMINALS)
    checks = {
        "harness_exit": run["return_code"] == 0,
        "validation_exit": validation.returncode == 0,
        "tests_unchanged": tests_unchanged,
        "source_changed_only": changed == [task.source_name],
        "terminal": terminal_ok,
        "tool_evidence": tool_evidence,
        "korean_final": korean_final,
        "no_bad_terminal": no_bad_terminal,
    }
    score = {
        **run,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "changed_paths": changed,
        "validation_exit": validation.returncode,
    }
    (evidence / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True) + "\n")
    return score


def summary(args: argparse.Namespace) -> dict[str, Any]:
    rows = []
    for harness in HARNESSES:
        for task in TASKS:
            _, evidence = paths(args, harness, task)
            score_path = evidence / "score.json"
            if score_path.exists():
                rows.append(json.loads(score_path.read_text()))
    counts = {
        harness: {
            "passed": sum(row["harness"] == harness and row["status"] == "passed" for row in rows),
            "total": sum(row["harness"] == harness for row in rows),
        }
        for harness in HARNESSES
    }
    baseline_passed = counts["baseline"]["passed"]
    usability_not_below_baseline = {
        harness: counts[harness]["passed"] >= baseline_passed
        for harness in ("opencode", "codex", "hermes")
    }
    result = {
        "run_id": args.run_id,
        "counts": counts,
        "usability_not_below_baseline": usability_not_below_baseline,
        "complete": (
            baseline_passed == len(TASKS)
            and all(counts[harness]["passed"] == len(TASKS) for harness in HARNESSES[1:])
        ),
        "rows": rows,
    }
    output = args.output_root / args.run_id / "summary.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "score", "summary"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--harness", choices=HARNESSES)
    parser.add_argument("--task", choices=tuple(TASK_BY_SLUG))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    parser.add_argument("--timeout", type=int, default=1_800)
    return parser.parse_args()


def selected(args: argparse.Namespace) -> list[tuple[str, Task]]:
    harnesses = (args.harness,) if args.harness else HARNESSES
    tasks = (TASK_BY_SLUG[args.task],) if args.task else TASKS
    return [(harness, task) for harness in harnesses for task in tasks]


def main() -> int:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    if args.action == "prepare":
        for harness, task in selected(args):
            print(json.dumps(prepare_one(args, harness, task), sort_keys=True), flush=True)
    elif args.action == "run":
        if not args.harness or not args.task:
            raise SystemExit("run requires --harness and --task")
        print(json.dumps(run_one(args, args.harness, TASK_BY_SLUG[args.task]), sort_keys=True))
    elif args.action == "score":
        for harness, task in selected(args):
            print(json.dumps(score_one(args, harness, task), sort_keys=True), flush=True)
    else:
        print(json.dumps(summary(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
