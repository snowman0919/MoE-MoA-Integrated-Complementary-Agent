#!/usr/bin/env python3
"""Summarize content-free request latency from a live SQLite database read-only."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed"]
    latencies = [row["completed_at"] - row["accepted_at"] for row in completed]
    ttft = [row["first_byte_at"] - row["accepted_at"] for row in completed if row["first_byte_at"]]
    tokens = [row["total_tokens"] for row in completed if row["total_tokens"] is not None]
    return {
        "requests": len(rows),
        "completed": len(completed),
        "completion_rate": len(completed) / len(rows) if rows else None,
        "request_completion_seconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "request_ttft_seconds": {
            "p50": percentile(ttft, 0.50),
            "p95": percentile(ttft, 0.95),
            "p99": percentile(ttft, 0.99),
        },
        "tokens_per_completed_request_mean": fmean(tokens) if tokens else None,
    }


def summarize(database_path: Path, since: datetime) -> dict[str, Any]:
    database = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in database.execute(
            "SELECT request_id, session_id, model_alias, accepted_at, first_byte_at, completed_at, "
            "status, total_tokens FROM request_usage WHERE accepted_at >= ? "
            "ORDER BY accepted_at",
            (since.timestamp(),),
        )
    ]
    event_times: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    event_session_requests: dict[str, str] = {}
    for row in database.execute(
        "SELECT session_id, event_type, payload, created_at FROM events "
        "WHERE event_type IN ('executor_scheduled', 'executor_started', "
        "'executor_local_http_400_fallback') AND created_at >= ? ORDER BY created_at",
        (since.isoformat(),),
    ):
        if row["event_type"] == "executor_scheduled":
            request_id = json.loads(row["payload"]).get("request_id")
            if isinstance(request_id, str):
                event_session_requests[row["session_id"]] = request_id
            continue
        request_id = event_session_requests.get(row["session_id"])
        if request_id is None:
            continue
        event_times[request_id][row["event_type"]].append(
            datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).timestamp()
        )
    database.close()

    grouped: dict[str, list[dict[str, Any]]] = {
        "all": rows,
        "local_only": [],
        "local_then_remote_fallback": [],
        "route_unproven": [],
    }
    for row in rows:
        end = row["completed_at"] or row["accepted_at"]
        events = event_times[row["request_id"]]
        local = any(row["accepted_at"] <= value <= end for value in events["executor_started"])
        fallback = any(
            row["accepted_at"] <= value <= end
            for value in events["executor_local_http_400_fallback"]
        )
        grouped[
            "local_then_remote_fallback"
            if fallback
            else "local_only"
            if local
            else "route_unproven"
        ].append(row)

    accepted = [row["accepted_at"] for row in rows]
    return {
        "schema_version": "request-path-baseline-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "database": str(database_path.resolve()),
            "mode": "sqlite_read_only",
            "since": since.isoformat(),
            "last_accepted_at": (
                datetime.fromtimestamp(max(accepted), UTC).isoformat() if accepted else None
            ),
        },
        "model_alias_counts": dict(sorted(Counter(row["model_alias"] for row in rows).items())),
        "groups": {name: metrics(group) for name, group in grouped.items()},
        "verified_completion_seconds": None,
        "external_cost_usd": None,
        "limitations": [
            "No objective verifier or hidden validation is linked to these operational rows.",
            "Request completion is not verified completion and cannot satisfy the release "
            "latency gate.",
            "Container image identity is not recorded in this production database epoch.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--since", type=datetime.fromisoformat, required=True)
    arguments = parser.parse_args()
    since = arguments.since
    if since.tzinfo is None:
        raise SystemExit("--since must include a UTC offset")
    result = summarize(arguments.database, since)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
