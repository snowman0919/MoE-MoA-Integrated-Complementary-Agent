#!/usr/bin/env python3
"""Reproducible coding tasks for installed client harnesses."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
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
DOCKER_IMAGE = "dgx-moa-quality-harness:py311-git-v1"
CODEX_BINARY = Path(
    "/home/kotori9/.codex/packages/standalone/releases/0.145.0-aarch64-unknown-linux-musl/bin/codex"
)
OPENCODE_BINARY = Path("/home/kotori9/.opencode/bin/opencode")
OPENCODE_NODE_MODULES = Path("/home/kotori9/.config/opencode/node_modules")
OPENCODE_PACKAGE_JSON = Path("/home/kotori9/.config/opencode/package.json")
OPENCODE_PACKAGE_LOCK = Path("/home/kotori9/.config/opencode/package-lock.json")
OPENCODE_RIPGREP = Path(shutil.which("rg") or "/usr/bin/rg")
OPENCODE_OUTPUT_LIMIT = 4_096
OPENCODE_ISOLATION_ENV = {
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_SHARE": "1",
    "OPENCODE_DISABLE_TERMINAL_TITLE": "1",
    "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "1",
}
HERMES_ROOT = Path("/home/kotori9/.hermes/hermes-agent")
HERMES_PYTHON_ROOT = Path("/home/kotori9/.pyenv/versions/3.11.14")
FIXED_PLAN_PROVIDERS = {
    "codex",
    "default",
    "frontier",
    "local",
    "opencode_go",
    "primary",
    "remote",
    "secondary",
}
BAD_TERMINALS = (
    "stream disconnected before completion",
    "reconnecting 5/5",
    "api call failed",
    "remote executor fallback unavailable",
    '"type":"turn.failed"',
    '"type":"response.failed"',
    "다음 도구 작업을 준비합니다.",
    "다음 작업에 필요한 증거를 확인합니다.",
    "필요한 증거를 한 번에 확인합니다.",
    "Planner 역할이 구조와 구현 순서를 설계합니다.",
)


def codex_model_catalog() -> dict[str, Any]:
    return {
        "models": [
            {
                "slug": "dgx-moa-orchestrated",
                "display_name": "DGX MoA Orchestrated",
                "description": "Dynamic MoA coding runtime",
                "base_instructions": (
                    "You are Codex, a coding agent. Inspect only what is needed, then implement "
                    "with apply_patch, run bounded tests, review the diff, and persist until the "
                    "task is verified. Never stop after only reading or planning. Raw apply_patch "
                    "input starts with *** Begin Patch and ends with *** End Patch; do not wrap it "
                    "in a Markdown fence."
                ),
                "default_reasoning_level": "high",
                "supported_reasoning_levels": [
                    {"effort": "high", "description": "Full Dynamic MoA orchestration"}
                ],
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1,
                "default_reasoning_summary": "none",
                "default_verbosity": "low",
                "include_skills_usage_instructions": True,
                "support_verbosity": True,
                "apply_patch_tool_type": "freeform",
                "truncation_policy": {"mode": "tokens", "limit": 10_000},
                "supports_parallel_tool_calls": True,
                "supports_image_detail_original": True,
                "context_window": 65_536,
                "max_context_window": 65_536,
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
                "input_modalities": ["text", "image"],
                "supports_search_tool": False,
                "use_responses_lite": False,
            }
        ]
    }


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

            `secret` must be a non-empty exact `bytes` instance (not `bytearray`).
            `tolerance_seconds` and `max_body_bytes` must be positive integers.
            Reject invalid constructor arguments with `TypeError` or `ValueError`.

            `verify(body, timestamp, nonce, signature)` signs the exact bytes
            `timestamp + b"." + nonce + b"." + body` with HMAC-SHA256. The supplied
            signature format is `v1=<lowercase hex>`. `timestamp` must be a
            non-empty ASCII decimal digit string without a sign or decimal point.

            Reject malformed input, oversized bodies, timestamps outside tolerance,
            invalid signatures, and replayed valid nonces. Nonces match
            the entire `[A-Za-z0-9_-]{8,128}` pattern; a trailing newline is invalid.
            Invalid signatures must not consume a nonce.
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
HIDDEN_CHECKS = {
    "rate-limiter": block(
        """
        from rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(2, 2.5, clock=lambda: 99)
        assert limiter.allow("a", 1.0)
        assert limiter.remaining("a", 1.0) == 1
        assert limiter.remaining("a", 1.0) == 1
        assert limiter.allow("a", 3.5)
        assert limiter.remaining("a", 3.5) == 1
        for key in (None, "", 1):
            try:
                limiter.remaining(key, 4)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError("invalid key accepted")
        for args in ((1, True), (1, float("nan")), (True, 1)):
            try:
                SlidingWindowLimiter(*args)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError("invalid constructor input accepted")
        print("hidden checks passed")
        """
    ),
    "atomic-store": block(
        """
        import math
        import tempfile
        from pathlib import Path
        from atomic_store import AtomicJSONStore

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = AtomicJSONStore(path)
            assert store.update(0, {"nested": {"ok": True}}) == 1
            before = path.read_bytes()
            for version, changes in ((True, {"x": 1}), (1, []), (1, {"x": math.nan})):
                try:
                    store.update(version, changes)
                except (TypeError, ValueError):
                    pass
                else:
                    raise AssertionError("invalid update accepted")
                assert path.read_bytes() == before
            assert [item for item in path.parent.iterdir() if item != path] == []
        print("hidden checks passed")
        """
    ),
    "dag-runner": block(
        """
        import time
        from dag_runner import execution_layers, run_dag

        assert execution_layers({}) == []
        result = run_dag(
            {"z": set(), "a": set(), "done": {"z", "a"}},
            {
                "z": lambda: (time.sleep(0.01), "z")[1],
                "a": lambda: (time.sleep(0.03), "a")[1],
                "done": lambda: "done",
            },
            max_workers=2,
        )
        assert list(result) == ["a", "z", "done"]
        for dependencies, functions, workers in (
            ({"a": "bad"}, {"a": lambda: 1}, 1),
            ({"a": set()}, {"a": lambda: 1, "b": lambda: 2}, 1),
            ({"a": set()}, {"a": lambda: 1}, True),
        ):
            try:
                run_dag(dependencies, functions, max_workers=workers)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError("invalid DAG input accepted")
        print("hidden checks passed")
        """
    ),
    "webhook-verifier": block(
        """
        import hashlib
        import hmac
        from webhook import WebhookVerifier

        secret = b"hidden-secret"
        verifier = WebhookVerifier(secret, tolerance_seconds=300, clock=lambda: 1000)
        body, timestamp, nonce = b"x", "700", "boundary_nonce"
        raw = timestamp.encode() + b"." + nonce.encode() + b"." + body
        signature = "v1=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
        assert verifier.verify(body, timestamp, nonce, signature)
        dashed_nonce = "valid-nonce_1"
        dashed_raw = b"1000." + dashed_nonce.encode() + b".x"
        dashed = "v1=" + hmac.new(secret, dashed_raw, hashlib.sha256).hexdigest()
        assert verifier.verify(b"x", "1000", dashed_nonce, dashed)
        newline_nonce = "valid_nonce\\n"
        newline_raw = b"1000." + newline_nonce.encode() + b".x"
        newline_signature = (
            "v1=" + hmac.new(secret, newline_raw, hashlib.sha256).hexdigest()
        )
        assert not verifier.verify(
            b"x", "1000", newline_nonce, newline_signature
        )
        upper_nonce = "uppercase_nonce"
        upper_raw = b"1000." + upper_nonce.encode() + b".x"
        upper = "v1=" + hmac.new(secret, upper_raw, hashlib.sha256).hexdigest().upper()
        assert not verifier.verify(b"x", "1000", upper_nonce, upper)
        for index, bad_timestamp in enumerate(
            ("1000.0", "+1000", "nan", "", "1000\\n")
        ):
            bad_nonce = f"bad_timestamp_{index}"
            bad_raw = (
                bad_timestamp.encode() + b"." + bad_nonce.encode() + b".x"
            )
            bad_signature = (
                "v1=" + hmac.new(secret, bad_raw, hashlib.sha256).hexdigest()
            )
            assert not verifier.verify(
                b"x", bad_timestamp, bad_nonce, bad_signature
            )
        for args in (
            (secret, -1, 10),
            (secret, True, 10),
            (secret, 1.0, 10),
            (secret, 1, 0),
            (secret, 1, True),
            ("secret", 1, 10),
            (b"", 1, 10),
            (bytearray(b"secret"), 1, 10),
        ):
            try:
                WebhookVerifier(args[0], tolerance_seconds=args[1], max_body_bytes=args[2])
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError("invalid verifier configuration accepted")
        print("hidden checks passed")
        """
    ),
    "log-report": block(
        """
        import json
        from log_report import summarize

        source = [
            "",
            json.dumps({
                "level": "INFO",
                "event": "ok",
                "outer": [{"myTokenSuffix": "secret"}, {"AUTHORIZATION_value": "private"}],
            }),
        ]
        report = summarize(source, sample_limit=0)
        assert report["samples"] == []
        assert report["levels"] == {"INFO": 1}
        redacted = summarize(source, sample_limit=1)
        encoded = json.dumps(redacted)
        assert "secret" not in encoded and "private" not in encoded
        for lines, marker in (
            (["", '{"level":1,"event":"x"}'], "line 2"),
            (['{"level":"INFO","event":null}'], "line 1"),
        ):
            try:
                summarize(lines)
            except ValueError as error:
                assert marker in str(error)
            else:
                raise AssertionError("invalid record accepted")
        try:
            summarize([], sample_limit=True)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("boolean sample limit accepted")
        print("hidden checks passed")
        """
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_name(run_id: str, harness: str, task: Task) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", run_id.lower()).strip("-") or "run"
    safe_run = (
        normalized
        if len(normalized) <= 24
        else f"{normalized[:24]}-{hashlib.sha256(normalized.encode()).hexdigest()[:8]}"
    )
    return f"moa-qm-{safe_run}-{harness}-{task.slug}"


def quality_session_id(run_id: str, harness: str, task: Task) -> str:
    return f"quality-{run_id}-{harness}-{task.slug}"


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
        TEST_COMMAND,
        cwd=workspace,
        env=filtered_env({"PYTHONDONTWRITEBYTECODE": "1"}),
        text=True,
        capture_output=True,
        check=False,
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
        session = quality_session_id(args.run_id, "opencode", task)
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
                    "models": {
                        "dgx-moa-agent": {
                            "name": "DGX MoA Agent",
                            "limit": {"context": 65_536, "output": OPENCODE_OUTPUT_LIMIT},
                        }
                    },
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
        "`python -m unittest discover -s tests -v`를 실제 실행하고, 실패하면 수정 후 "
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
        if command[:2] == ["docker", "run"] and "--name" in command:
            name_index = command.index("--name") + 1
            if name_index < len(command):
                subprocess.run(
                    ["docker", "container", "rm", "--force", command[name_index]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
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


def docker_command(
    workspace: Path,
    state: Path,
    inner: list[str],
    *,
    environment_names: tuple[str, ...] = (),
    extra_environment: tuple[str, ...] = (),
    network: str = "host",
    read_only_mounts: tuple[tuple[Path, str], ...] = (),
    workspace_mode: str = "rw",
    container_name: str | None = None,
) -> list[str]:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--network",
        network,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "512",
        "--memory",
        "2g",
        "--cpus",
        "4",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--tmpfs",
        "/run:rw,nosuid,nodev,size=16m",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--workdir",
        str(workspace),
        "--volume",
        f"{workspace}:{workspace}:{workspace_mode}",
        "--volume",
        f"{state}:/state:rw",
        "--env",
        "HOME=/state",
        "--env",
        "USER=quality",
        "--env",
        "LOGNAME=quality",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "PATH=/tools:/usr/local/bin:/usr/bin:/bin",
    ]
    if container_name is not None:
        command[2:2] = ["--name", container_name]
    for name in environment_names:
        command.extend(("--env", name))
    for value in extra_environment:
        command.extend(("--env", value))
    for source, target in read_only_mounts:
        command.extend(("--volume", f"{source}:{target}:ro"))
    return [
        *command,
        "--entrypoint",
        "/bin/sh",
        DOCKER_IMAGE,
        "-c",
        'umask 077; exec "$@"',
        "sh",
        *inner,
    ]


def opencode_runtime_mounts(state: Path) -> tuple[tuple[Path, str], ...]:
    missing = [
        path
        for path in (
            OPENCODE_NODE_MODULES,
            OPENCODE_PACKAGE_JSON,
            OPENCODE_PACKAGE_LOCK,
            OPENCODE_RIPGREP,
        )
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(f"OpenCode runtime cache missing: {missing[0]}")
    config = state / ".config/opencode"
    config.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OPENCODE_PACKAGE_JSON, config / "package.json")
    shutil.copy2(OPENCODE_PACKAGE_LOCK, config / "package-lock.json")
    (state / ".cache/opencode/bin").mkdir(parents=True, exist_ok=True)
    return (
        (OPENCODE_NODE_MODULES, "/state/.config/opencode/node_modules"),
        (OPENCODE_RIPGREP, "/state/.cache/opencode/bin/rg"),
    )


def prepare_hermes_profile(
    home: Path,
    gateway: str,
    workspace: Path | None = None,
    workspace_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.yaml"
    shutil.copy2("/home/kotori9/.hermes/config.yaml", config_path)
    lines = config_path.read_text().splitlines()
    in_provider = False
    base_url_replaced = False
    key_replaced = False
    extra_headers_index: int | None = None
    session_replaced = False
    task_replaced = False
    for index, line in enumerate(lines):
        if re.match(r"^\s*-\s+name:\s*dgx-moa-agent\s*$", line):
            in_provider = True
            continue
        if in_provider and re.match(r"^\s*-\s+name:", line):
            break
        if in_provider and re.match(r"^\s+base_url:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}base_url: {gateway.rstrip('/')}/v1"
            base_url_replaced = True
        elif in_provider and re.match(r"^\s+(?:api_key|key_env):", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}key_env: DGX_MOA_API_KEY"
            key_replaced = True
        elif in_provider and re.match(r"^\s+extra_headers:", line):
            extra_headers_index = index
        elif in_provider and session_id is not None and re.match(r"^\s+X-Session-ID:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}X-Session-ID: {session_id}"
            session_replaced = True
        elif in_provider and task_id is not None and re.match(r"^\s+X-Task-ID:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}X-Task-ID: {task_id}"
            task_replaced = True
        elif in_provider and workspace is not None and re.match(r"^\s+X-Workspace-Path:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}X-Workspace-Path: {workspace}"
        elif in_provider and workspace_id is not None and re.match(r"^\s+X-Workspace-ID:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}X-Workspace-ID: {workspace_id}"
    if not base_url_replaced or not key_replaced:
        raise RuntimeError("Hermes dgx-moa-agent provider is incomplete")
    if (session_id is not None or task_id is not None) and extra_headers_index is None:
        raise RuntimeError("Hermes dgx-moa-agent provider lacks extra_headers")
    headers = []
    if session_id is not None and not session_replaced:
        headers.append(f"      X-Session-ID: {session_id}")
    if task_id is not None and not task_replaced:
        headers.append(f"      X-Task-ID: {task_id}")
    if headers:
        assert extra_headers_index is not None
        lines[extra_headers_index + 1 : extra_headers_index + 1] = headers
    config_path.write_text("\n".join(lines) + "\n")
    config_path.chmod(0o600)


def hermes_usage_succeeded(path: Path) -> bool:
    try:
        usage = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return usage.get("completed") is True and usage.get("failed") is False


def codex_moa_command(args: argparse.Namespace, workspace: Path, task: Task) -> list[str]:
    provider = "dgx_moa_quality"
    base_url = args.gateway.rstrip("/") + "/v1"
    session = quality_session_id(args.run_id, "codex", task)
    headers = (
        "{ "
        f'"X-Session-ID" = {json.dumps(session)}, '
        f'"X-Trace-Origin" = "validation", '
        f'"X-Task-ID" = {json.dumps(f"{args.run_id}-{task.slug}")}'
        " }"
    )
    return [
        "/tools/codex",
        "exec",
        "--ephemeral",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--strict-config",
        "--ignore-user-config",
        "-c",
        'model="dgx-moa-orchestrated"',
        "-c",
        "model_context_window=65536",
        "-c",
        'model_catalog_json="/state/model-catalog.json"',
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'model_verbosity="low"',
        "-c",
        f"model_provider={json.dumps(provider)}",
        "-c",
        f"model_providers.{provider}.name={json.dumps('DGX MoA quality')}",
        "-c",
        f"model_providers.{provider}.base_url={json.dumps(base_url)}",
        "-c",
        f"model_providers.{provider}.env_key={json.dumps('DGX_MOA_API_KEY')}",
        "-c",
        f"model_providers.{provider}.wire_api={json.dumps('responses')}",
        "-c",
        f"model_providers.{provider}.http_headers={headers}",
        "-C",
        str(workspace),
        prompt(task),
    ]


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


def cuda_memory_used() -> int | None:
    try:
        runtime = ctypes.CDLL("libcudart.so")
        free = ctypes.c_size_t()
        total = ctypes.c_size_t()
        if runtime.cudaMemGetInfo(ctypes.byref(free), ctypes.byref(total)) != 0:
            return None
        if total.value < free.value:
            return None
        return total.value - free.value
    except (OSError, ValueError):
        return None


def resource_snapshot() -> dict[str, Any]:
    memory: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, raw = line.split(":", 1)
            value = raw.strip().split()[0]
            memory[name] = int(value) * 1024
    except (OSError, ValueError, IndexError):
        memory = {}
    gpu_memory: int | None = None
    gpu_memory_source: str | None = None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        values = [
            int(value.strip()) for value in result.stdout.splitlines() if value.strip().isdigit()
        ]
        if result.returncode == 0 and values:
            gpu_memory = sum(values) * 1024 * 1024
            gpu_memory_source = "nvidia-smi"
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    if gpu_memory is None:
        gpu_memory = cuda_memory_used()
        if gpu_memory is not None:
            gpu_memory_source = "cudaMemGetInfo"
    return {
        "host_memory_used_bytes": (
            memory["MemTotal"] - memory["MemAvailable"]
            if {"MemTotal", "MemAvailable"} <= memory.keys()
            else None
        ),
        "swap_used_bytes": (
            memory["SwapTotal"] - memory["SwapFree"]
            if {"SwapTotal", "SwapFree"} <= memory.keys()
            else None
        ),
        "gpu_memory_used_bytes": gpu_memory,
        "gpu_memory_source": gpu_memory_source,
    }


def invocation_telemetry(
    database: Path | None,
    started_at: float,
    ended_at: float,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    incomplete: dict[str, Any] = {
        "complete": False,
        "reason": "state_db_not_configured" if database is None else "state_db_unavailable",
        "provider_pinned": False,
        "provider_switches": 0,
        "remote_cost_complete": False,
        "remote_cost_usd": None,
        "missing_token_rows": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cached_tokens": None,
        "retryable_failures": None,
        "provider_errors": 0,
        "invocations": [],
        "routing_events": {},
    }
    if database is None or not database.is_file():
        return incomplete
    try:
        with sqlite3.connect(database) as connection:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(model_invocation_usage)")
            }
            required = {
                "request_id",
                "role",
                "provider",
                "model",
                "status",
                "fallback_reason",
                "latency_ms",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "invoked_at",
            }
            if not required <= columns:
                return incomplete | {"reason": "invocation_schema_incomplete"}
            cost_column = "invocation.cost_usd" if "cost_usd" in columns else "NULL"
            cache_column = "invocation.cached_tokens" if "cached_tokens" in columns else "NULL"
            invocation_column = (
                "invocation.invocation_id" if "invocation_id" in columns else "NULL"
            )
            request_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(request_usage)")
            }
            can_join_requests = {"request_id", "accepted_at"} <= request_columns
            if session_id is not None and "session_id" in request_columns:
                invocation_join = (
                    " JOIN request_usage AS request"
                    " ON request.request_id = invocation.request_id"
                )
                invocation_where = "request.session_id = ?"
                invocation_parameters: tuple[object, ...] = (session_id,)
            elif can_join_requests:
                invocation_join = (
                    " JOIN request_usage AS request"
                    " ON request.request_id = invocation.request_id"
                )
                invocation_where = (
                    "(CASE WHEN typeof(request.accepted_at) IN ('integer', 'real') "
                    "THEN request.accepted_at "
                    "ELSE CAST(strftime('%s', request.accepted_at) AS REAL) END) "
                    "BETWEEN ? AND ?"
                )
                invocation_parameters = (started_at, ended_at)
            else:
                invocation_join = ""
                invocation_where = "invocation.invoked_at >= ? AND invocation.invoked_at <= ?"
                invocation_parameters = (started_at, ended_at)
            rows = connection.execute(
                "SELECT invocation.request_id, invocation.role, invocation.provider, "
                "invocation.model, invocation.status, invocation.fallback_reason, "
                "invocation.latency_ms, invocation.prompt_tokens, "
                "invocation.completion_tokens, invocation.total_tokens, "
                f"{cache_column}, {cost_column}, {invocation_column} "
                f"FROM model_invocation_usage AS invocation{invocation_join} "
                f"WHERE {invocation_where} ORDER BY invocation.invoked_at",
                invocation_parameters,
            ).fetchall()
            allowed_events = (
                "specialist_provider_selected",
                "specialist_provider_completed",
                "specialist_provider_failed",
                "specialist_warmup_started",
                "specialist_warmup_completed",
                "specialist_warmup_failed",
                "specialist_unused_warmup",
                "executor_provider_switch_prevented",
            )
            placeholders = ",".join("?" for _ in allowed_events)
            event_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(events)")
            }
            if session_id is not None and "session_id" in event_columns:
                event_where = "session_id = ?"
                event_parameters: tuple[object, ...] = (session_id,)
            else:
                event_where = "CAST(strftime('%s', created_at) AS REAL) BETWEEN ? AND ?"
                event_parameters = (started_at, ended_at)
            routing_events = dict(
                connection.execute(
                    "SELECT event_type, COUNT(*) FROM events "
                    f"WHERE event_type IN ({placeholders}) AND {event_where} "
                    "GROUP BY event_type ORDER BY event_type",
                    (*allowed_events, *event_parameters),
                ).fetchall()
            )
            accepted_epoch = (
                "CASE WHEN typeof(accepted_at) IN ('integer', 'real') THEN accepted_at "
                "ELSE CAST(strftime('%s', accepted_at) AS REAL) END"
            )
            retry_where = (
                "session_id = ?"
                if session_id is not None and "session_id" in request_columns
                else f"({accepted_epoch}) BETWEEN ? AND ?"
            )
            retry_parameters: tuple[object, ...] = (
                (session_id,)
                if session_id is not None and "session_id" in request_columns
                else (started_at, ended_at)
            )
            retryable_failures = (
                connection.execute(
                    "SELECT COUNT(*) FROM request_usage "
                    f"WHERE retryable_failure_class IS NOT NULL AND {retry_where}",
                    retry_parameters,
                ).fetchone()[0]
                if {"accepted_at", "retryable_failure_class"} <= request_columns
                else None
            )
    except (OSError, sqlite3.Error, ValueError):
        return incomplete | {"reason": "telemetry_query_failed"}
    groups: dict[tuple[str, str, str, str, str | None], list[float]] = {}
    providers_by_call: dict[tuple[str, ...], set[tuple[str, str]]] = {}
    for row in rows:
        request_id, role, provider, model, status, fallback_reason, latency_ms, *_ = row
        groups.setdefault(
            (str(role), str(provider), str(model), str(status), fallback_reason), []
        ).append(float(latency_ms))
        invocation_id = row[12]
        call = (
            ("invocation", str(invocation_id))
            if invocation_id is not None
            else ("request-role", str(request_id), str(role))
        )
        providers_by_call.setdefault(call, set()).add((str(provider), str(model)))
    switches = sum(len(providers) > 1 for providers in providers_by_call.values())
    remote_rows = [row for row in rows if str(row[2]) != "local" and row[4] == "completed"]
    paid_rows = [row for row in remote_rows if str(row[2]) not in FIXED_PLAN_PROVIDERS]
    remote_cost_complete = all(
        str(row[2]).startswith("openrouter:") and row[11] is not None for row in paid_rows
    )
    remote_cost = (
        round(sum(float(row[11]) for row in paid_rows), 9) if remote_cost_complete else None
    )
    successful_rows = [row for row in rows if row[4] in {"completed", "success"}]
    provider_errors = len(rows) - len(successful_rows)
    token_complete = bool(successful_rows) and all(
        all(value is not None for value in row[7:10]) for row in successful_rows
    )
    cache_complete = (
        "cached_tokens" in columns
        and bool(successful_rows)
        and all(row[10] is not None for row in successful_rows)
    )
    invocations = [
        {
            "role": role,
            "provider": provider,
            "model": model,
            "status": status,
            "fallback_reason": fallback_reason,
            "calls": len(latencies),
            "average_latency_ms": round(sum(latencies) / len(latencies), 3),
            "maximum_latency_ms": round(max(latencies), 3),
        }
        for (role, provider, model, status, fallback_reason), latencies in sorted(groups.items())
    ]
    return {
        "complete": (
            bool(rows)
            and remote_cost_complete
            and switches == 0
            and provider_errors == 0
            and token_complete
            and cache_complete
            and retryable_failures is not None
        ),
        "reason": (
            None
            if rows
            and remote_cost_complete
            and switches == 0
            and provider_errors == 0
            and token_complete
            and cache_complete
            and retryable_failures is not None
            else "no_invocations"
            if not rows
            else "remote_cost_missing"
            if not remote_cost_complete
            else "provider_switch_detected"
            if switches
            else "provider_error"
            if provider_errors
            else "token_usage_missing"
            if not token_complete
            else "cache_usage_missing"
            if not cache_complete
            else "retry_telemetry_missing"
        ),
        "provider_pinned": bool(rows) and switches == 0,
        "provider_switches": switches,
        "remote_cost_complete": remote_cost_complete,
        "remote_cost_usd": remote_cost,
        "missing_token_rows": sum(row[9] is None for row in successful_rows),
        "prompt_tokens": (sum(int(row[7]) for row in successful_rows) if token_complete else None),
        "completion_tokens": (
            sum(int(row[8]) for row in successful_rows) if token_complete else None
        ),
        "total_tokens": (sum(int(row[9]) for row in successful_rows) if token_complete else None),
        "cached_tokens": (sum(int(row[10]) for row in successful_rows) if cache_complete else None),
        "retryable_failures": retryable_failures,
        "provider_errors": provider_errors,
        "invocations": invocations,
        "routing_events": routing_events,
    }


def run_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    if not (evidence / "manifest.json").exists():
        raise RuntimeError(f"prepare first: {harness}/{task.slug}")
    resources_before = resource_snapshot()
    started_at = time.time()
    started = time.monotonic()
    session_id = (
        quality_session_id(args.run_id, harness, task)
        if harness in {"opencode", "codex", "hermes"}
        else None
    )
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
                **OPENCODE_ISOLATION_ENV,
            }
        )
        inner = [
            "/tools/opencode",
            "run",
            "--format",
            "json",
            "--pure",
            "--auto",
            "--title",
            f"quality-{task.slug}",
            "--dir",
            str(workspace),
            "--model",
            "dgx-moa/dgx-moa-agent",
            prompt(task),
        ]
        command = (
            docker_command(
                workspace,
                state,
                inner,
                container_name=workspace.name,
                environment_names=("DGX_MOA_API_KEY",),
                extra_environment=tuple(
                    f"{name}={value}" for name, value in OPENCODE_ISOLATION_ENV.items()
                ),
                read_only_mounts=(
                    (OPENCODE_BINARY, "/tools/opencode"),
                    *opencode_runtime_mounts(state),
                ),
            )
            if args.runtime == "docker"
            else inner
        )
        run = run_process(command, cwd=workspace, environment=environment, timeout=args.timeout)
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    elif harness == "codex":
        if args.runtime == "docker":
            key = os.getenv("DGX_MOA_OPENCODE_KEY")
            if not key:
                raise RuntimeError("DGX_MOA_OPENCODE_KEY is required")
            state = args.output_root / args.run_id / "profiles" / f"codex-{task.slug}"
            state.mkdir(parents=True, exist_ok=True)
            (state / "model-catalog.json").write_text(
                json.dumps(codex_model_catalog(), separators=(",", ":"))
            )
            command = docker_command(
                workspace,
                state,
                codex_moa_command(args, workspace, task),
                container_name=workspace.name,
                environment_names=("DGX_MOA_API_KEY",),
                extra_environment=("CODEX_HOME=/state",),
                read_only_mounts=(
                    (CODEX_BINARY, "/tools/codex"),
                    (OPENCODE_RIPGREP, "/tools/rg"),
                ),
            )
            run = run_process(
                command,
                cwd=workspace,
                environment=filtered_env({"DGX_MOA_API_KEY": key}),
                timeout=args.timeout,
            )
            return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
        else:
            return_code, stdout, stderr = run_codex_admin(args, workspace, task)
            return_code = 0 if return_code == 200 else return_code
    elif harness == "baseline":
        inner = [
            "/tools/codex" if args.runtime == "docker" else str(CODEX_BINARY),
            "exec",
            "--ephemeral",
            "--json",
            *(
                ["--dangerously-bypass-approvals-and-sandbox"]
                if args.runtime == "docker"
                else ["--sandbox", "workspace-write"]
            ),
            "-C",
            str(workspace),
            "-m",
            "gpt-5.6-sol",
            prompt(task),
        ]
        if args.runtime == "docker":
            state = args.output_root / args.run_id / "profiles" / f"baseline-{task.slug}"
            command = docker_command(
                workspace,
                state,
                inner,
                container_name=workspace.name,
                extra_environment=("CODEX_HOME=/state",),
                read_only_mounts=(
                    (CODEX_BINARY, "/tools/codex"),
                    (OPENCODE_RIPGREP, "/tools/rg"),
                    (Path.home() / ".codex/auth.json", "/state/auth.json"),
                ),
            )
        else:
            command = inner
        run = run_process(
            command,
            cwd=workspace,
            environment=filtered_env(),
            timeout=args.timeout,
        )
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    else:
        key = os.getenv("DGX_MOA_OPENCODE_KEY")
        if not key:
            raise RuntimeError("DGX_MOA_OPENCODE_KEY is required")
        hermes_home = args.output_root / args.run_id / "profiles" / f"hermes-{task.slug}"
        prepare_hermes_profile(
            hermes_home,
            args.gateway,
            workspace,
            f"quality-{args.run_id}",
            session_id,
            f"{args.run_id}-{task.slug}",
        )
        usage_path = (
            Path("/state/usage.json") if args.runtime == "docker" else evidence / "usage.json"
        )
        inner = [
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
        command = (
            docker_command(
                workspace,
                hermes_home,
                inner,
                container_name=workspace.name,
                environment_names=("DGX_MOA_API_KEY",),
                extra_environment=("HERMES_HOME=/state",),
                read_only_mounts=(
                    (HERMES_ROOT, str(HERMES_ROOT)),
                    (HERMES_PYTHON_ROOT, str(HERMES_PYTHON_ROOT)),
                ),
            )
            if args.runtime == "docker"
            else inner
        )
        run = run_process(
            command,
            cwd=workspace,
            environment=filtered_env(
                {
                    "DGX_MOA_API_KEY": key,
                    "HERMES_HOME": str(hermes_home),
                }
            ),
            timeout=args.timeout,
        )
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
        if return_code == 0 and not hermes_usage_succeeded(hermes_home / "usage.json"):
            return_code = 1
    duration = round(time.monotonic() - started, 3)
    ended_at = time.time()
    telemetry = invocation_telemetry(
        getattr(args, "state_db", None),
        started_at,
        ended_at,
        session_id=session_id,
    )
    resources_after = resource_snapshot()
    (evidence / "stdout.log").write_text(stdout)
    (evidence / "stderr.log").write_text(stderr)
    result = {
        "harness": harness,
        "task": task.slug,
        "return_code": return_code,
        "started_at_epoch": started_at,
        "ended_at_epoch": ended_at,
        "duration_seconds": duration,
        "runtime": args.runtime,
        "container_image": DOCKER_IMAGE if args.runtime == "docker" else None,
        "telemetry": telemetry,
        "resources": {"before": resources_before, "after": resources_after},
    }
    (evidence / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def log_text(evidence: Path) -> str:
    values = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".log", ".txt"}:
            values.append(path.read_text(errors="replace"))
    return "\n".join(values)


def successful_hermes_test_result(role: str, tool_name: str | None, content: str) -> bool:
    if role != "tool":
        return False
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return False
    if tool_name == "terminal":
        return payload.get("exit_code") == 0 and any(
            marker in str(payload.get("output", "")) for marker in ("Ran ", "OK")
        )
    if tool_name != "execute_code" or payload.get("status") != "success":
        return False
    try:
        execution = json.loads(payload.get("output", ""))
    except (TypeError, ValueError):
        return False
    tests = execution.get("unittest") or execution.get("tests") or {}
    if not isinstance(tests, dict):
        return False
    return (tests.get("success") is True or tests.get("exit_code") == 0) and any(
        marker in str(tests.get("output", "")) for marker in ("Ran ", "OK")
    )


def hermes_test_evidence(args: argparse.Namespace, task: Task, evidence: Path) -> bool:
    profile = args.output_root / args.run_id / "profiles" / f"hermes-{task.slug}"
    usage_path = profile / "usage.json"
    state_path = profile / "state.db"
    if not usage_path.is_file() or not state_path.is_file():
        return False
    try:
        usage = json.loads(usage_path.read_text())
        connection = sqlite3.connect(state_path)
        raw_session_id = usage.get("session_id")
        if isinstance(raw_session_id, str) and raw_session_id:
            session_id = raw_session_id
        else:
            session_ids = connection.execute(
                "SELECT DISTINCT session_id FROM messages WHERE session_id IS NOT NULL"
            ).fetchall()
            if len(session_ids) != 1:
                return False
            session_id = str(session_ids[0][0])
        rows = connection.execute(
            """
            SELECT role, tool_name, content, tool_calls
            FROM messages
            WHERE session_id = ?
              AND (tool_name IN ('terminal', 'execute_code') OR tool_calls LIKE '%unittest%')
            ORDER BY id
            """,
            (session_id,),
        ).fetchall()
    except (KeyError, OSError, sqlite3.Error, ValueError):
        return False
    finally:
        if "connection" in locals():
            connection.close()
    calls = sum("unittest" in str(row[3] or "") for row in rows)
    successful_results = sum(
        successful_hermes_test_result(row[0], row[1], str(row[2] or "")) for row in rows
    )
    (evidence / "hermes-tool-evidence.json").write_text(
        json.dumps(
            {
                "session_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
                "unittest_tool_calls": calls,
                "successful_unittest_results": successful_results,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return calls > 0 and successful_results > 0


def score_one(
    args: argparse.Namespace,
    harness: str,
    task: Task,
    hidden_checks: dict[str, str] = HIDDEN_CHECKS,
) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    manifest = json.loads((evidence / "manifest.json").read_text())
    run = json.loads((evidence / "run.json").read_text())
    validator_state = evidence / "validator-state"
    public_inner = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    public_command = (
        docker_command(
            workspace,
            validator_state,
            public_inner,
            container_name=f"{workspace.name}-public",
            extra_environment=("PYTHONDONTWRITEBYTECODE=1",),
            network="none",
            workspace_mode="ro",
        )
        if args.runtime == "docker"
        else list(TEST_COMMAND)
    )
    validation = run_process(
        public_command,
        cwd=workspace,
        environment=filtered_env(),
        timeout=120,
    )
    hidden_command = (
        docker_command(
            workspace,
            validator_state,
            ["python", "-c", hidden_checks[task.slug]],
            container_name=f"{workspace.name}-hidden",
            extra_environment=("PYTHONDONTWRITEBYTECODE=1",),
            network="none",
            workspace_mode="ro",
        )
        if args.runtime == "docker"
        else [sys.executable, "-c", hidden_checks[task.slug]]
    )
    hidden = run_process(
        hidden_command,
        cwd=workspace,
        environment=filtered_env(),
        timeout=120,
    )
    (evidence / "validation.stdout.log").write_text(validation.stdout)
    (evidence / "validation.stderr.log").write_text(validation.stderr)
    (evidence / "hidden-validation.stdout.log").write_text(hidden.stdout)
    (evidence / "hidden-validation.stderr.log").write_text(hidden.stderr)
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
    tool_evidence = (
        hermes_test_evidence(args, task, evidence) if harness == "hermes" else "unittest" in raw_log
    )
    no_bad_terminal = not any(marker.lower() in raw_log.lower() for marker in BAD_TERMINALS)
    checks = {
        "harness_exit": run["return_code"] == 0,
        "validation_exit": validation.returncode == 0,
        "hidden_validation_exit": hidden.returncode == 0,
        "tests_unchanged": tests_unchanged,
        "source_changed_only": changed == [task.source_name],
        "terminal": terminal_ok,
        "tool_evidence": tool_evidence,
        "korean_final": korean_final,
        "no_bad_terminal": no_bad_terminal,
        "docker_isolation": run.get("runtime") == "docker",
    }
    score = {
        **run,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "changed_paths": changed,
        "validation_exit": validation.returncode,
        "hidden_validation_exit": hidden.returncode,
    }
    (evidence / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True) + "\n")
    return score


def summary(args: argparse.Namespace, tasks: tuple[Task, ...] = TASKS) -> dict[str, Any]:
    rows = []
    for harness in HARNESSES:
        for task in tasks:
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
        harness: (
            counts[harness]["passed"] >= baseline_passed
            if counts["baseline"]["total"] == len(tasks) and counts[harness]["total"] == len(tasks)
            else None
        )
        for harness in ("opencode", "codex", "hermes")
    }
    result = {
        "run_id": args.run_id,
        "counts": counts,
        "usability_not_below_baseline": usability_not_below_baseline,
        "complete": (
            baseline_passed == len(tasks)
            and all(counts[harness]["passed"] == len(tasks) for harness in HARNESSES[1:])
        ),
        "rows": rows,
    }
    output = args.output_root / args.run_id / "summary.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def parse_args(task_by_slug: dict[str, Task] = TASK_BY_SLUG) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "score", "summary"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--harness", choices=HARNESSES)
    parser.add_argument("--task", choices=tuple(task_by_slug))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    parser.add_argument("--state-db", type=Path)
    parser.add_argument("--timeout", type=int, default=1_800)
    parser.add_argument("--runtime", choices=("host", "docker"), default="docker")
    return parser.parse_args()


def selected(
    args: argparse.Namespace,
    tasks: tuple[Task, ...] = TASKS,
    task_by_slug: dict[str, Task] = TASK_BY_SLUG,
) -> list[tuple[str, Task]]:
    harnesses = (args.harness,) if args.harness else HARNESSES
    selected_tasks = (task_by_slug[args.task],) if args.task else tasks
    return [(harness, task) for harness in harnesses for task in selected_tasks]


def main(
    tasks: tuple[Task, ...] = TASKS,
    hidden_checks: dict[str, str] = HIDDEN_CHECKS,
) -> int:
    task_by_slug = {task.slug: task for task in tasks}
    args = parse_args(task_by_slug)
    args.output_root.mkdir(parents=True, exist_ok=True)
    if args.action == "prepare":
        for harness, task in selected(args, tasks, task_by_slug):
            print(json.dumps(prepare_one(args, harness, task), sort_keys=True), flush=True)
    elif args.action == "run":
        if not args.harness or not args.task:
            raise SystemExit("run requires --harness and --task")
        print(json.dumps(run_one(args, args.harness, task_by_slug[args.task]), sort_keys=True))
    elif args.action == "score":
        for harness, task in selected(args, tasks, task_by_slug):
            print(
                json.dumps(score_one(args, harness, task, hidden_checks), sort_keys=True),
                flush=True,
            )
    else:
        print(json.dumps(summary(args, tasks), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
