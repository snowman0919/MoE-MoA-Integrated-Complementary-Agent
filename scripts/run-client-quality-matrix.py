#!/usr/bin/env python3
"""Run reproducible coding tasks through installed client harnesses."""

from __future__ import annotations

import argparse
import functools
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

HARNESSES = ("baseline", "raw", "opencode", "codex", "hermes")
CORE_ENV = ("HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
TEST_COMMAND = (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
DOCKER_IMAGE = (
    "python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7"
)
CODEX_BINARY = Path(
    "/home/kotori9/.codex/packages/standalone/releases/0.146.0-aarch64-unknown-linux-musl/bin/codex"
)
OPENCODE_BINARY = Path("/home/kotori9/.opencode/bin/opencode")
RAW_CLIENT = Path(__file__).with_name("run-raw-openai-tool-loop.py")
OPENCODE_ISOLATION_ENV = {
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_SHARE": "1",
    "OPENCODE_DISABLE_TERMINAL_TITLE": "1",
}
HERMES_ROOT = Path("/home/kotori9/.hermes/hermes-agent")
HERMES_PYTHON_ROOT = Path("/home/kotori9/.pyenv/versions/3.11.14")
BAD_TERMINALS = (
    "stream disconnected before completion",
    "reconnecting 5/5",
    "api call failed",
    "remote executor fallback unavailable",
    '"type":"turn.failed"',
    '"type":"response.failed"',
    "다음 도구 작업을 준비합니다.",
    "Planner 역할이 구조와 구현 순서를 설계합니다.",
)
BAD_FINAL_OUTPUT = ("<tool_call>", "<function=", "다음 도구 작업을 준비합니다.")


@dataclass(frozen=True)
class Task:
    slug: str
    source_name: str
    readme: str
    starter: str
    tests: str


def block(value: str) -> str:
    return textwrap.dedent(value).lstrip()


def baseline_reasoning_effort() -> str:
    effort = os.getenv("DGX_MOA_BASELINE_REASONING_EFFORT", "high")
    if effort not in {"high", "xhigh"}:
        raise RuntimeError(f"invalid baseline reasoning effort: {effort}")
    return effort


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


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@functools.cache
def runtime_fingerprint(harness: str) -> dict[str, str]:
    if harness == "raw":
        return {
            "client": "python-stdlib-openai-compatible",
            "version": sys.version.split()[0],
            "script_sha256": sha256(RAW_CLIENT),
        }
    if harness in {"baseline", "codex"}:
        return {
            "client": "codex",
            "version": subprocess.run(
                [str(CODEX_BINARY), "--version"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
            "binary_sha256": sha256(CODEX_BINARY),
        }
    if harness == "opencode":
        return {
            "client": "opencode",
            "version": subprocess.run(
                [str(OPENCODE_BINARY), "--version"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
            "binary_sha256": sha256(OPENCODE_BINARY),
        }
    if harness == "hermes":
        return {
            "client": "hermes",
            "revision": git(HERMES_ROOT, "rev-parse", "HEAD").stdout.strip(),
            "config_sha256": sha256(Path("/home/kotori9/.hermes/config.yaml")),
        }
    raise ValueError(f"unknown harness: {harness}")


def workspace_name(run_id: str, harness: str, task: Task) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", run_id.lower()).strip("-") or "run"
    safe_run = (
        normalized
        if len(normalized) <= 24
        else f"{normalized[:24]}-{hashlib.sha256(normalized.encode()).hexdigest()[:8]}"
    )
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
        "gateway": args.gateway.rstrip("/"),
        "harness_sha256": sha256(Path(__file__)),
        "prompt_sha256": text_sha256(prompt(task)),
        "runtime_fingerprint": runtime_fingerprint(harness),
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
                            "X-Runtime-Channel": "dev",
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
                            "limit": {"context": 262_144, "output": 8_192},
                        },
                        "dgx-moa-fast": {
                            "name": "DGX MoA Fast",
                            "limit": {"context": 262_144, "output": 8_192},
                        },
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


def pin_hermes_gateway(path: Path, gateway: str, api_key: str) -> None:
    pattern = re.compile(r"(?ms)^  - name: dgx-moa-agent\n.*?(?=^  - name:|\Z)")
    matches = list(pattern.finditer(path.read_text()))
    if len(matches) != 1:
        raise RuntimeError("Hermes dgx-moa-agent provider is missing or duplicated")
    match = matches[0]
    block, url_count = re.subn(
        r"(?m)(^    base_url: )[^\n]+$",
        lambda value: value.group(1) + gateway.rstrip("/") + "/v1",
        match.group(),
    )
    block, key_count = re.subn(
        r"(?m)(^    api_key: )[^\n]+$",
        lambda value: value.group(1) + api_key,
        block,
    )
    if url_count != 1 or key_count != 1:
        raise RuntimeError("Hermes dgx-moa-agent URL or key is missing or duplicated")
    text = path.read_text()
    path.write_text(text[: match.start()] + block + text[match.end() :])


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
        if command[:2] == ["docker", "run"] and "--name" in command:
            container = command[command.index("--name") + 1]
            subprocess.run(
                ["docker", "rm", "-f", container],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
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
) -> list[str]:
    state = state.resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    container = "moa-qm-" + hashlib.sha256(f"{workspace}\0{state}".encode()).hexdigest()[:20]
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container,
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
    for name in environment_names:
        command.extend(("--env", name))
    for value in extra_environment:
        command.extend(("--env", value))
    for source, target in read_only_mounts:
        command.extend(("--volume", f"{source}:{target}:ro"))
    return [*command, DOCKER_IMAGE, *inner]


def codex_moa_command(args: argparse.Namespace, workspace: Path, task: Task) -> list[str]:
    provider = "dgx_moa_quality"
    base_url = args.gateway.rstrip("/") + "/v1"
    return [
        "/tools/codex",
        "exec",
        "--ephemeral",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--strict-config",
        "--ignore-user-config",
        "-c",
        'model="dgx-moa"',
        "-c",
        "model_context_window=131072",
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
        "-C",
        str(workspace),
        prompt(task),
    ]


def write_codex_model_catalog(gateway: str, key: str, path: Path) -> None:
    request = urllib.request.Request(
        gateway.rstrip("/") + "/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    models = payload.get("models")
    if not isinstance(models, list) or not any(
        isinstance(model, dict) and model.get("slug") == "dgx-moa" for model in models
    ):
        raise RuntimeError("gateway model catalog is missing dgx-moa")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps({"models": models}, indent=2) + "\n")
    path.chmod(0o600)


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


def validated_manifest(args: argparse.Namespace, task: Task, path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    expected = {
        "gateway": args.gateway.rstrip("/"),
        "harness_sha256": sha256(Path(__file__)),
        "prompt_sha256": text_sha256(prompt(task)),
        "runtime_fingerprint": runtime_fingerprint(str(manifest.get("harness"))),
    }
    mismatches = [name for name, value in expected.items() if manifest.get(name) != value]
    if mismatches:
        raise RuntimeError("fixture manifest mismatch: " + ", ".join(mismatches))
    return manifest


def run_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    workspace, evidence = paths(args, harness, task)
    manifest_path = evidence / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"prepare first: {harness}/{task.slug}")
    validated_manifest(args, task, manifest_path)
    started_at = time.time()
    started = time.monotonic()
    if harness == "raw":
        key = os.getenv("DGX_MOA_OPENCODE_KEY")
        if not key:
            raise RuntimeError("DGX_MOA_OPENCODE_KEY is required")
        state = evidence / "raw-state"
        command = docker_command(
            workspace,
            state,
            [
                "python",
                "/tools/raw-openai-tool-loop.py",
                "--gateway",
                args.gateway,
                "--workspace",
                str(workspace),
                "--session-id",
                f"quality-{args.run_id}-raw-{task.slug}",
                "--prompt",
                prompt(task),
            ],
            environment_names=("DGX_MOA_API_KEY",),
            read_only_mounts=((RAW_CLIENT, "/tools/raw-openai-tool-loop.py"),),
        )
        run = run_process(
            command,
            cwd=workspace,
            environment=filtered_env({"DGX_MOA_API_KEY": key}),
            timeout=args.timeout,
        )
        return_code, stdout, stderr = run.returncode, run.stdout, run.stderr
    elif harness == "opencode":
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
            os.getenv("DGX_MOA_OPENCODE_MODEL", "dgx-moa/dgx-moa-agent"),
            prompt(task),
        ]
        command = (
            docker_command(
                workspace,
                state,
                inner,
                environment_names=("DGX_MOA_API_KEY",),
                extra_environment=tuple(
                    f"{name}={value}" for name, value in OPENCODE_ISOLATION_ENV.items()
                ),
                read_only_mounts=((OPENCODE_BINARY, "/tools/opencode"),),
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
            write_codex_model_catalog(
                args.gateway,
                key,
                state / "model-catalog.json",
            )
            command = docker_command(
                workspace,
                state,
                codex_moa_command(args, workspace, task),
                environment_names=("DGX_MOA_API_KEY",),
                extra_environment=("CODEX_HOME=/state",),
                read_only_mounts=((CODEX_BINARY, "/tools/codex"),),
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
            "-c",
            f'model_reasoning_effort="{baseline_reasoning_effort()}"',
            prompt(task),
        ]
        if args.runtime == "docker":
            state = args.output_root / args.run_id / "profiles" / f"baseline-{task.slug}"
            command = docker_command(
                workspace,
                state,
                inner,
                extra_environment=("CODEX_HOME=/state",),
                read_only_mounts=(
                    (CODEX_BINARY, "/tools/codex"),
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
        hermes_home.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/home/kotori9/.hermes/config.yaml", hermes_home / "config.yaml")
        shutil.copy2("/home/kotori9/.hermes/.env", hermes_home / ".env")
        pin_hermes_gateway(hermes_home / "config.yaml", args.gateway, key)
        (hermes_home / "config.yaml").chmod(0o600)
        (hermes_home / ".env").chmod(0o600)
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
            "dgx-moa",
            "--pass-session-id",
        ]
        command = (
            docker_command(
                workspace,
                hermes_home,
                inner,
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
        "runtime": args.runtime,
        "container_image": DOCKER_IMAGE if args.runtime == "docker" else None,
    }
    (evidence / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def log_text(evidence: Path) -> str:
    values = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".log", ".txt"}:
            values.append(path.read_text(errors="replace"))
    return "\n".join(values)


def user_visible_output(harness: str, stdout: str) -> str:
    if harness == "hermes":
        return stdout.strip()
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if harness == "raw":
        values = [event.get("content") for event in events if event.get("event") == "final"]
    elif harness == "opencode":
        values = [
            event.get("part", {}).get("text")
            for event in events
            if event.get("type") == "text" and isinstance(event.get("part"), dict)
        ]
    else:
        values = [
            event.get("item", {}).get("text")
            for event in events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "agent_message"
        ]
    return next(
        (value.strip() for value in reversed(values) if isinstance(value, str) and value.strip()),
        "",
    )


def user_visible_checks(output: str, task: Task) -> dict[str, bool]:
    lines = [line for line in output.splitlines() if line.strip()]
    return {
        "user_visible_output": bool(output),
        "user_visible_six_lines": 0 < len(lines) <= 6,
        "user_visible_korean": bool(re.search(r"[가-힣]", output)),
        "user_visible_changed_file": task.source_name in output,
        "user_visible_test_command": "python -m unittest discover -s tests -v" in output,
        "user_visible_test_result": bool(re.search(r"\bOK\b|통과|passed|성공", output, re.I)),
        "user_visible_remaining_risk": bool(re.search(r"남은\s*(?:위험|리스크)", output)),
        "user_visible_clean": not any(
            marker.lower() in output.lower() for marker in BAD_FINAL_OUTPUT
        ),
    }


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
    unittest = execution.get("unittest") or execution.get("unit_tests", {})
    return (unittest.get("success") is True or unittest.get("exit_code") == 0) and any(
        marker in str(unittest.get("output", "")) for marker in ("Ran ", "OK")
    )


def hermes_test_evidence(args: argparse.Namespace, task: Task, evidence: Path) -> bool:
    profile = args.output_root / args.run_id / "profiles" / f"hermes-{task.slug}"
    usage_path = profile / "usage.json"
    state_path = profile / "state.db"
    if not usage_path.is_file() or not state_path.is_file():
        return False
    try:
        session_id = str(json.loads(usage_path.read_text())["session_id"])
        connection = sqlite3.connect(state_path)
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


def verdict_timing(
    run: dict[str, Any], scoring_started: float, scored_at: float, passed: bool
) -> dict[str, float | None]:
    started = float(run["started_at_epoch"])
    ended = float(run["ended_at_epoch"])
    if not started <= ended <= scoring_started <= scored_at:
        raise RuntimeError("invalid client-quality verdict timestamps")
    elapsed = round(scored_at - started, 3)
    return {
        "scoring_started_at_epoch": scoring_started,
        "scored_at_epoch": scored_at,
        "client_to_score_gap_seconds": round(scoring_started - ended, 3),
        "post_client_verification_seconds": round(scored_at - scoring_started, 3),
        "time_to_verdict_seconds": elapsed,
        "verified_completion_seconds": elapsed if passed else None,
    }


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def epoch_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verified = [
        float(row["verified_completion_seconds"])
        for row in rows
        if isinstance(row.get("verified_completion_seconds"), (int, float))
        and not isinstance(row["verified_completion_seconds"], bool)
    ]
    verdicts = [
        float(row["time_to_verdict_seconds"])
        for row in rows
        if isinstance(row.get("time_to_verdict_seconds"), (int, float))
        and not isinstance(row["time_to_verdict_seconds"], bool)
    ]
    starts = [float(row["started_at_epoch"]) for row in rows if "started_at_epoch" in row]
    ends = [float(row["scored_at_epoch"]) for row in rows if "scored_at_epoch" in row]
    wall_clock = max(ends) - min(starts) if starts and len(ends) == len(rows) else None
    failed_checks: dict[str, int] = {}
    for row in rows:
        for name, passed in row.get("checks", {}).items():
            if passed is False:
                failed_checks[name] = failed_checks.get(name, 0) + 1
    return {
        "attempts": len(rows),
        "verified_completions": len(verified),
        "verified_completion_seconds": {
            "p50": percentile(verified, 0.50),
            "p95": percentile(verified, 0.95),
            "p99": percentile(verified, 0.99),
        },
        "time_to_verdict_seconds": {
            "p50": percentile(verdicts, 0.50),
            "p95": percentile(verdicts, 0.95),
            "p99": percentile(verdicts, 0.99),
        },
        "wall_clock_seconds": round(wall_clock, 3) if wall_clock is not None else None,
        "successful_tasks_per_hour": (
            round(len(verified) * 3600 / wall_clock, 3) if wall_clock and verified else None
        ),
        "claimed_success_with_failed_contract": sum(
            row.get("status") != "passed"
            and row.get("checks", {}).get("user_visible_output") is True
            and row.get("checks", {}).get("user_visible_test_result") is True
            for row in rows
        ),
        "failed_checks": dict(sorted(failed_checks.items())),
    }


def score_one(args: argparse.Namespace, harness: str, task: Task) -> dict[str, Any]:
    scoring_started = time.time()
    workspace, evidence = paths(args, harness, task)
    manifest = validated_manifest(args, task, evidence / "manifest.json")
    run = json.loads((evidence / "run.json").read_text())
    validator_state = evidence / "validator-state"
    public_inner = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    public_command = (
        docker_command(
            workspace,
            validator_state,
            public_inner,
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
            ["python", "-c", HIDDEN_CHECKS[task.slug]],
            extra_environment=("PYTHONDONTWRITEBYTECODE=1",),
            network="none",
            workspace_mode="ro",
        )
        if args.runtime == "docker"
        else [sys.executable, "-c", HIDDEN_CHECKS[task.slug]]
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
        "raw": '"event": "final"',
        "opencode": '"reason":"stop"',
        "codex": '"type":"turn.completed"',
        "baseline": '"type":"turn.completed"',
        "hermes": "",
    }[harness]
    terminal_ok = bool(stdout.strip()) if not terminal else terminal in raw_log
    final_output = user_visible_output(harness, stdout)
    final_checks = user_visible_checks(final_output, task)
    (evidence / "user-visible-output.txt").write_text(final_output + ("\n" if final_output else ""))
    (evidence / "user-visible-output.json").write_text(
        json.dumps(
            {
                "sha256": text_sha256(final_output),
                "nonempty_lines": len([line for line in final_output.splitlines() if line.strip()]),
                "checks": final_checks,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
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
        **final_checks,
        "no_bad_terminal": no_bad_terminal,
        "docker_isolation": run.get("runtime") == "docker",
    }
    passed = all(checks.values())
    timing = verdict_timing(run, scoring_started, time.time(), passed)
    score = {
        **run,
        **timing,
        "status": "passed" if passed else "failed",
        "checks": checks,
        "changed_paths": changed,
        "validation_exit": validation.returncode,
        "hidden_validation_exit": hidden.returncode,
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
    matrix_complete = all(counts[harness]["total"] == len(TASKS) for harness in HARNESSES)
    usability_not_below_baseline = {
        harness: counts[harness]["passed"] >= baseline_passed if matrix_complete else None
        for harness in ("raw", "opencode", "codex", "hermes")
    }
    metrics = {
        "overall": epoch_metrics(rows),
        "by_harness": {
            harness: epoch_metrics([row for row in rows if row["harness"] == harness])
            for harness in HARNESSES
        },
    }
    result = {
        "run_id": args.run_id,
        "counts": counts,
        "matrix_complete": matrix_complete,
        "usability_not_below_baseline": usability_not_below_baseline,
        "metrics": metrics,
        "complete": (
            matrix_complete
            and baseline_passed == len(TASKS)
            and all(counts[harness]["passed"] == len(TASKS) for harness in HARNESSES[1:])
        ),
        "rows": rows,
    }
    output = args.output_root / args.run_id / "summary.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def schedule(args: argparse.Namespace) -> dict[str, Any]:
    entries = []
    for harness, task in sorted(
        selected(args),
        key=lambda item: text_sha256(f"{args.run_id}\0{item[0]}\0{item[1].slug}"),
    ):
        _, evidence = paths(args, harness, task)
        manifest_path = evidence / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"prepare first: {harness}/{task.slug}")
        entries.append(
            {
                "order": len(entries) + 1,
                "harness": harness,
                "task": task.slug,
                "manifest_sha256": sha256(manifest_path),
            }
        )
    result = {
        "protocol_version": "client-quality-v2",
        "run_id": args.run_id,
        "order_seed_sha256": text_sha256(args.run_id),
        "baseline": "gpt-5.6-sol",
        "functional_gate": "all_checks_pass",
        "entries": entries,
    }
    output = args.output_root / args.run_id / "schedule.json"
    if output.exists():
        existing = json.loads(output.read_text())
        if existing != result:
            raise RuntimeError("existing schedule does not match prepared manifests")
        return existing
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    output.chmod(0o444)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "schedule", "run", "score", "summary"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--harness", choices=HARNESSES)
    parser.add_argument("--task", choices=tuple(TASK_BY_SLUG))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    parser.add_argument("--timeout", type=int, default=1_800)
    parser.add_argument("--runtime", choices=("host", "docker"), default="docker")
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
    elif args.action == "schedule":
        print(json.dumps(schedule(args), sort_keys=True))
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
