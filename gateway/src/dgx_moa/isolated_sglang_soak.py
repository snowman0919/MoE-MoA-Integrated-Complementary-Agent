#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dgx_moa import isolated_sglang_validation as RUNTIME

EXECUTOR_MODEL = "dgx-moa-executor-candidate"
SPECIALIST_MODEL = "dgx-moa-specialist-candidate"
STOP_REQUESTED = False
STOP_SIGNAL: int | None = None


def positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def request_one(
    endpoint: str,
    model: str,
    role: str,
    sequence: int,
    client: int,
    prefix: str,
    timeout: float,
    backend: RUNTIME.ValidationBackend,
) -> dict[str, Any]:
    marker = f"SOAK_{role.upper()}_{sequence}_{client}_{uuid.uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": f"{prefix}\nReply exactly: {marker}",
            }
        ],
        "temperature": 0,
        "max_tokens": 32,
    }
    if role == "specialist":
        payload.update(
            separate_reasoning=True,
            chat_template_kwargs={"enable_thinking": False},
        )
    try:
        response, latency = backend.post_json(
            f"{endpoint}/v1/chat/completions",
            payload,
            timeout,
        )
        content = str(RUNTIME.message(response).get("content") or "").strip()
        if content != marker:
            raise RuntimeError("marker_mismatch")
        return {
            "role": role,
            "client": client,
            "status": "passed",
            "latency_seconds": round(latency, 3),
            **RUNTIME.token_usage(response.get("usage")),
        }
    except Exception as error:
        failure = str(error)
        if not failure.startswith(("http_status_", "transport_")):
            failure = "request_failed"
        return {
            "role": role,
            "client": client,
            "status": "failed",
            "error_type": type(error).__name__,
            "failure": failure,
        }


def run_cycle(
    executor_endpoint: str,
    specialist_endpoint: str,
    clients_per_role: int,
    sequence: int,
    prefix: str,
    timeout: float,
    *,
    backend: RUNTIME.ValidationBackend | None = None,
) -> dict[str, Any]:
    backend = backend or RUNTIME.validation_backend()
    specs = [
        (executor_endpoint, EXECUTOR_MODEL, "executor", client)
        for client in range(clients_per_role)
    ] + [
        (specialist_endpoint, SPECIALIST_MODEL, "specialist", client)
        for client in range(clients_per_role)
    ]
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        futures = [
            pool.submit(
                request_one,
                endpoint,
                model,
                role,
                sequence,
                client,
                prefix,
                timeout,
                backend,
            )
            for endpoint, model, role, client in specs
        ]
        requests = [future.result() for future in futures]
    return {
        "type": "cycle",
        "sequence": sequence,
        "captured_at": datetime.now(UTC).isoformat(),
        "cycle_seconds": round(time.monotonic() - started, 3),
        "requests": requests,
        "runtime": backend.runtime_snapshot(),
    }


def append_event(path: Path, event: dict[str, Any], *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if create else os.O_APPEND)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}") from error
        if not isinstance(event, dict):
            raise ValueError(f"invalid event at line {line_number}")
        events.append(event)
    if not events or events[0].get("type") != "header":
        raise ValueError("missing soak header")
    return events


def container_failed(runtime: Any) -> bool:
    if not isinstance(runtime, dict):
        return True
    containers = runtime.get("containers")
    if not isinstance(containers, dict):
        return True
    for role in ("executor", "specialist"):
        state = containers.get(role)
        if (
            not isinstance(state, dict)
            or not state.get("available")
            or state.get("status") != "running"
            or state.get("oom_killed")
        ):
            return True
    return False


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * probability)))
    return round(ordered[index], 3)


def summarize(events: list[dict[str, Any]], elapsed_seconds: float | None = None) -> dict[str, Any]:
    header = events[0]
    target_value = header.get("duration_target_seconds")
    if (
        isinstance(target_value, bool)
        or not isinstance(target_value, int | float)
        or target_value <= 0
    ):
        raise ValueError("invalid duration target")
    cycles = [event for event in events if event.get("type") == "cycle"]
    requests = [
        request
        for cycle in cycles
        for request in cycle.get("requests", [])
        if isinstance(request, dict)
    ]
    failures = [request for request in requests if request.get("status") != "passed"]
    latencies = [
        float(request["latency_seconds"])
        for request in requests
        if isinstance(request.get("latency_seconds"), int | float)
    ]
    cached_tokens = [
        int(request["cached_tokens"])
        for request in requests
        if isinstance(request.get("cached_tokens"), int)
    ]
    cache_by_role = {
        role: {
            "requests_reported": len(values),
            "positive_requests": sum(value > 0 for value in values),
            "cached_tokens_total": sum(values),
        }
        for role in ("executor", "specialist")
        if (
            values := [
                int(request["cached_tokens"])
                for request in requests
                if request.get("role") == role and isinstance(request.get("cached_tokens"), int)
            ]
        )
    }
    memory_samples = [
        cycle.get("runtime", {}).get("memory", {})
        for cycle in cycles
        if isinstance(cycle.get("runtime"), dict)
    ]
    available = [
        int(sample["memavailable_kib"])
        for sample in memory_samples
        if isinstance(sample.get("memavailable_kib"), int)
    ]
    swap_used = [
        int(sample["swaptotal_kib"]) - int(sample["swapfree_kib"])
        for sample in memory_samples
        if isinstance(sample.get("swaptotal_kib"), int)
        and isinstance(sample.get("swapfree_kib"), int)
    ]
    observed = (
        float(elapsed_seconds)
        if elapsed_seconds is not None
        else max((float(cycle.get("elapsed_seconds", 0)) for cycle in cycles), default=0)
    )
    container_memory: dict[str, int | None] = {}
    for role in ("executor", "specialist"):
        samples = [
            cycle.get("runtime", {})
            .get("containers", {})
            .get(role, {})
            .get("memory", {})
            .get("memory_current_bytes")
            for cycle in cycles
        ]
        measured = [int(value) for value in samples if isinstance(value, int)]
        container_memory[role] = max(measured) if measured else None
    target = float(target_value)
    footers = [event for event in events if event.get("type") == "footer"]
    completed = any(event.get("finished_at") for event in footers)
    interrupted = any(event.get("interrupted") for event in footers)
    runtime_failed = any(container_failed(cycle.get("runtime")) for cycle in cycles)
    memory_headroom_passed = bool(available) and min(available) >= (
        RUNTIME.MINIMUM_AVAILABLE_MEMORY_KIB
    )
    passed = (
        completed
        and observed >= target
        and bool(cycles)
        and bool(requests)
        and not failures
        and not interrupted
        and not runtime_failed
        and memory_headroom_passed
    )
    return {
        "schema_version": "isolated-sglang-soak-summary-v1",
        "passed": passed,
        "duration_target_seconds": target,
        "duration_observed_seconds": round(observed, 3),
        "cycles": len(cycles),
        "requests": len(requests),
        "request_failures": len(failures),
        "p50_latency_seconds": (round(statistics.median(latencies), 3) if latencies else None),
        "p95_latency_seconds": percentile(latencies, 0.95),
        "cached_tokens_total": sum(cached_tokens),
        "cache_reuse_observed": any(value > 0 for value in cached_tokens),
        "cache_by_role": cache_by_role,
        "maximum_container_memory_bytes": container_memory,
        "minimum_memavailable_kib": min(available) if available else None,
        "memory_headroom_passed": memory_headroom_passed,
        "maximum_swap_used_kib": max(swap_used) if swap_used else None,
        "runtime_failure_or_oom": runtime_failed,
        "completed": completed,
        "interrupted": interrupted,
        "providers": header.get("providers"),
    }


def request_stop(received_signal: int, _frame: Any) -> None:
    global STOP_REQUESTED, STOP_SIGNAL
    STOP_REQUESTED = True
    STOP_SIGNAL = received_signal


def run_soak(args: argparse.Namespace) -> int:
    global STOP_REQUESTED, STOP_SIGNAL
    STOP_REQUESTED = False
    STOP_SIGNAL = None
    if args.output.exists():
        raise SystemExit("refusing to overwrite existing soak evidence")
    executor_endpoint = RUNTIME.local_endpoint(args.executor_endpoint)
    specialist_endpoint = RUNTIME.local_endpoint(args.specialist_endpoint)
    admission = RUNTIME.run_validation(executor_endpoint, specialist_endpoint, args.timeout)
    header = {
        "type": "header",
        "schema_version": "isolated-sglang-soak-v1",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_target_seconds": args.duration_seconds,
        "interval_seconds": args.interval_seconds,
        "clients_per_role": args.clients_per_role,
        "providers": admission.get("providers"),
        "admission": admission,
    }
    append_event(args.output, header, create=True)
    if not admission.get("passed"):
        footer = {"type": "footer", "interrupted": False, "failure": "admission_failed"}
        append_event(args.output, footer)
        print(json.dumps(summarize([header, footer]), indent=2, sort_keys=True))
        return 1

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    started = time.monotonic()
    sequence = 0
    consecutive_failed_cycles = 0
    prefix = (
        f"Stable shared soak prefix {uuid.uuid4().hex}. Preserve this prefix for cache reuse. "
        * 256
    ).strip()
    events = [header]
    while not STOP_REQUESTED and time.monotonic() - started < args.duration_seconds:
        sequence += 1
        cycle = run_cycle(
            executor_endpoint,
            specialist_endpoint,
            args.clients_per_role,
            sequence,
            prefix,
            args.timeout,
        )
        cycle["elapsed_seconds"] = round(time.monotonic() - started, 3)
        append_event(args.output, cycle)
        events.append(cycle)
        cycle_failed = any(
            request.get("status") != "passed" for request in cycle["requests"]
        ) or container_failed(cycle["runtime"])
        consecutive_failed_cycles = consecutive_failed_cycles + 1 if cycle_failed else 0
        if consecutive_failed_cycles >= 3 or container_failed(cycle["runtime"]):
            break
        remaining = args.interval_seconds - (time.monotonic() - started) % args.interval_seconds
        time.sleep(min(remaining, max(0, args.duration_seconds - (time.monotonic() - started))))

    elapsed = time.monotonic() - started
    footer = {
        "type": "footer",
        "finished_at": datetime.now(UTC).isoformat(),
        "duration_observed_seconds": round(elapsed, 3),
        "interrupted": STOP_REQUESTED,
        **({"stop_signal": STOP_SIGNAL} if STOP_SIGNAL is not None else {}),
    }
    append_event(args.output, footer)
    events.append(footer)
    result = summarize(events, elapsed)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--summary", type=Path)
    run.add_argument("--duration-seconds", type=positive_float, default=36_000)
    run.add_argument("--interval-seconds", type=positive_float, default=1)
    run.add_argument("--clients-per-role", type=positive_int, default=2)
    run.add_argument("--timeout", type=positive_float, default=300)
    run.add_argument("--executor-endpoint", default="http://127.0.0.1:18101")
    run.add_argument("--specialist-endpoint", default="http://127.0.0.1:18102")

    report = subparsers.add_parser("summarize")
    report.add_argument("events", type=Path)
    report.add_argument("--write", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run_soak(args)
    result = summarize(load_events(args.events))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.write_text(rendered)
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
