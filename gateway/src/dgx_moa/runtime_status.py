from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from .lifecycle import read_automation_status, read_latest_decisions
from .usage import UsageStore

SERVICES = ("gateway", "executor", "planner", "reviewer", "reasoner", "judge")


def command(*args: str) -> str:
    return subprocess.run(args, text=True, capture_output=True, check=False).stdout.strip()


def memory_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable unavailable")


def minimum_memory(path: Path) -> int | None:
    if not path.exists():
        return None
    values = [
        int(line.split()[1]) for line in path.read_text().splitlines() if len(line.split()) >= 2
    ]
    return min(values) if values else None


def state_counts(path: Path) -> dict[str, int]:
    counts = {"request": 0, "completed": 0, "failed": 0, "blocked": 0}
    if not path.exists():
        return counts
    with sqlite3.connect(path) as database:
        counts["request"] = database.execute(
            "SELECT count(*) FROM events WHERE event_type = 'request_received'"
        ).fetchone()[0]
        rows = database.execute("SELECT payload FROM sessions").fetchall()
    for (payload,) in rows:
        state = json.loads(payload)
        status = state.get("final_status") or state.get("phase")
        if status in counts:
            counts[status] += 1
    return counts


def event_count(path: Path, event_type: str) -> int:
    if not path.exists():
        return 0
    with sqlite3.connect(path) as database:
        return int(
            database.execute(
                "SELECT count(*) FROM events WHERE event_type = ?", (event_type,)
            ).fetchone()[0]
        )


def service_status(role: str) -> dict[str, Any]:
    unit = f"dgx-moa-{role}.service"
    values = dict(
        line.split("=", 1)
        for line in command(
            "systemctl",
            "--user",
            "show",
            unit,
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "NRestarts",
            "-p",
            "ExecMainStatus",
        ).splitlines()
        if "=" in line
    )
    return {
        "active_state": values.get("ActiveState", "unknown"),
        "sub_state": values.get("SubState", "unknown"),
        "restart_count": int(values.get("NRestarts", 0)),
        "last_exit_status": int(values.get("ExecMainStatus", 0)),
    }


def usage_status(
    path: Path,
    *,
    lifecycle_mode: str = "disabled",
    managed_roles: tuple[str, ...] = (),
) -> dict[str, Any]:
    store = UsageStore(path)
    requests = store.recent_requests()
    statistics = store.report()
    role_statistics = {
        role: role_report
        for role, role_report in store.all_role_statistics().items()
        if role_report["request_count"]
    }
    lifecycle_samples = store.recent_lifecycle_samples()
    decisions = (
        {
            role: decision
            for role, decision in read_latest_decisions(path).items()
            if role in managed_roles and decision.mode == lifecycle_mode
        }
        if lifecycle_mode != "disabled"
        else {}
    )
    automation = read_automation_status(path)
    role_states = {
        role: record.model_state for record in requests for role in record.roles_required
    }
    last_request = (
        requests[-1].model_dump(mode="json", exclude={"session_id"}) if requests else None
    )
    return {
        "last_request": last_request,
        "active_request_count": store.active_request_count(),
        "request_statistics": {
            key: value
            for key, value in statistics.items()
            if key not in {"load_duration_seconds", "unload_duration_seconds"}
        },
        "role_statistics": role_statistics,
        "role_states": role_states,
        "adaptive_idle_timeout_seconds": (
            decisions["executor"].threshold_seconds if "executor" in decisions else None
        ),
        "idle_decisions": {
            role: decision.model_dump(mode="json") for role, decision in decisions.items()
        },
        "automation": automation.model_dump(mode="json"),
        "cold_starts": statistics["cold_starts"],
        "loading_failures": sum(
            record.retryable_failure_class == "model_loading" for record in requests
        ),
        "lifecycle": {
            "load_duration_seconds": statistics["load_duration_seconds"],
            "unload_duration_seconds": statistics["unload_duration_seconds"],
            "samples": [sample.model_dump(mode="json") for sample in lifecycle_samples],
        },
    }


def report(
    state_db: Path,
    project: Path,
    *,
    lifecycle_mode: str = "disabled",
    managed_roles: tuple[str, ...] = (),
) -> dict[str, Any]:
    journal = command(
        "journalctl",
        "--user",
        "-u",
        "dgx-moa-gateway.service",
        "--since",
        "24 hours ago",
        "--no-pager",
        "-o",
        "cat",
    )
    model_journal = "\n".join(
        command(
            "journalctl",
            "--user",
            "-u",
            f"dgx-moa-{role}.service",
            "--since",
            "24 hours ago",
            "--no-pager",
            "-o",
            "cat",
        )
        for role in ("executor", "planner", "reviewer", "reasoner", "judge")
    )
    states = state_counts(state_db)
    services = {role: service_status(role) for role in SERVICES}
    return {
        "schema_version": "runtime-status-v1",
        "runtime_commit": command("git", "-C", str(project), "rev-parse", "HEAD") or "unknown",
        "services": services,
        "unexpected_process_exits": sum(
            status["last_exit_status"] != 0 for status in services.values()
        ),
        "gateway_5xx_count_24h": len(re.findall(r'HTTP/1\.1" 5\d\d', journal)),
        "model_backend_failures_24h": len(
            re.findall(r"EngineCore failed to start|model backend", model_journal, re.I)
        ),
        "sqlite_state_errors": event_count(state_db, "state_persistence_failed"),
        "trace_archive_errors": event_count(state_db, "observability_degraded"),
        "observability_degradation_count": event_count(state_db, "observability_degraded"),
        "profile_transaction_failures": sum(
            '"status":"rollback"' in line
            for line in (project / "data/run/profile-audit.jsonl").read_text().splitlines()
        )
        if (project / "data/run/profile-audit.jsonl").exists()
        else 0,
        "minimum_observed_mem_available_bytes": minimum_memory(project / "data/run/soak-mem.log"),
        "current_mem_available_bytes": memory_available(),
        "request_count": states["request"],
        "completed_session_count": states["completed"],
        "failed_session_count": states["failed"],
        "blocked_session_count": states["blocked"],
        "usage": usage_status(
            state_db,
            lifecycle_mode=lifecycle_mode,
            managed_roles=managed_roles,
        ),
        "historical_window": "24h journald; memory since soak log start when available",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--state-db", type=Path, default=Path("data/state/gateway.db"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = report(args.state_db, args.project)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(
        f"commit={result['runtime_commit']} mem_available={result['current_mem_available_bytes']}"
    )
    for role, status in result["services"].items():
        print(
            f"{role}={status['active_state']}/{status['sub_state']} "
            f"restarts={status['restart_count']} exit={status['last_exit_status']}"
        )
    print(
        f"requests={result['request_count']} completed={result['completed_session_count']} "
        f"failed={result['failed_session_count']} blocked={result['blocked_session_count']} "
        f"gateway_5xx_24h={result['gateway_5xx_count_24h']} "
        f"observability_degraded={result['observability_degradation_count']}"
    )
    usage = result["usage"]
    print(
        f"usage_requests={usage['request_statistics']['request_count']} "
        f"active={usage['active_request_count']} cold_starts={usage['cold_starts']} "
        f"loading_failures={usage['loading_failures']} "
        f"idle_timeout={usage['adaptive_idle_timeout_seconds']} "
        f"automation_disabled={usage['automation']['automation_disabled']} "
        f"lifecycle_failures={usage['automation']['failure_count']}"
    )


if __name__ == "__main__":
    main()
