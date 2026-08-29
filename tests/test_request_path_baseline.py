from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def test_request_path_baseline_separates_local_and_fallback(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts/summarize-request-path-baseline.py"
    spec = importlib.util.spec_from_file_location("request_path_baseline", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database_path = tmp_path / "gateway.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "CREATE TABLE request_usage (request_id TEXT, session_id TEXT, model_alias TEXT, "
            "accepted_at REAL, first_byte_at REAL, completed_at REAL, status TEXT, "
            "total_tokens INTEGER)"
        )
        database.execute(
            "CREATE TABLE events (session_id TEXT, event_type TEXT, payload TEXT, created_at TEXT)"
        )
        database.executemany(
            "INSERT INTO request_usage VALUES (?, 'client', 'dgx-moa', ?, ?, ?, 'completed', ?)",
            [("local", 10, 11, 12, 20), ("fallback", 20, 22, 24, 40)],
        )
        database.executemany(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            [
                (
                    "local-events",
                    "executor_scheduled",
                    '{"request_id":"local"}',
                    "1970-01-01T00:00:10.1+00:00",
                ),
                ("local-events", "executor_started", "{}", "1970-01-01T00:00:10.5+00:00"),
                (
                    "fallback-events",
                    "executor_scheduled",
                    '{"request_id":"fallback"}',
                    "1970-01-01T00:00:20.1+00:00",
                ),
                (
                    "fallback-events",
                    "executor_started",
                    "{}",
                    "1970-01-01T00:00:20.5+00:00",
                ),
                (
                    "fallback-events",
                    "executor_local_http_400_fallback",
                    "{}",
                    "1970-01-01T00:00:21+00:00",
                ),
            ],
        )

    result = module.summarize(database_path, datetime.fromtimestamp(0, UTC))

    assert result["groups"]["local_only"]["request_completion_seconds"]["p50"] == 2
    assert result["groups"]["local_then_remote_fallback"]["requests"] == 1
    assert result["verified_completion_seconds"] is None
    assert "session_id" not in json.dumps(result)
