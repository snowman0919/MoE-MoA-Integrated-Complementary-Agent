#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dgx_moa.providers import parse_json_content
from dgx_moa.schemas import PlannerPlan, ReviewResult

EXECUTOR_CONTAINER = "dgx-moa-exp-sglang-executor"
SPECIALIST_CONTAINER = "dgx-moa-exp-sglang-specialist"
SAFE_HOSTS = {"127.0.0.1", "::1", "localhost"}


def local_endpoint(value: str) -> str:
    endpoint = value.rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in SAFE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("candidate endpoints must be loopback-only")
    return endpoint


def get_json(url: str, timeout: float) -> tuple[dict[str, Any], float]:
    return _json_request(Request(url), timeout)


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _json_request(request, timeout)


def _json_request(request: Request, timeout: float) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"http_status_{error.code}") from None
    except (URLError, TimeoutError):
        raise RuntimeError("transport_failure") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("invalid_json_response") from None
    if not isinstance(result, dict):
        raise RuntimeError("invalid_json_response")
    return result, time.monotonic() - started


def stream_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    done = False
    visible = ""
    chunks = 0
    usage: dict[str, Any] = {}
    try:
        with urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    done = True
                    continue
                event = json.loads(data)
                chunks += 1
                choices = event.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    visible += str(delta.get("content") or "")
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
    except HTTPError as error:
        raise RuntimeError(f"http_status_{error.code}") from None
    except (URLError, TimeoutError):
        raise RuntimeError("transport_failure") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("invalid_sse_response") from None
    marker = "STREAM_OK" in visible
    if not done or not marker:
        raise RuntimeError("incomplete_sse_response")
    return {
        "latency_seconds": round(time.monotonic() - started, 3),
        "chunks": chunks,
        "done": done,
        "marker": marker,
        **token_usage(usage),
    }


def token_usage(usage: Any) -> dict[str, int]:
    source = usage if isinstance(usage, dict) else {}
    details = source.get("prompt_tokens_details")
    cached = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
    return {
        "prompt_tokens": int(source.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(source.get("completion_tokens", 0) or 0),
        "total_tokens": int(source.get("total_tokens", 0) or 0),
        "cached_tokens": int(cached or 0),
    }


def completion(
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
    **extra: Any,
) -> tuple[dict[str, Any], float]:
    return post_json(
        f"{endpoint}/v1/chat/completions",
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
            **extra,
        },
        timeout,
    )


def message(response: dict[str, Any]) -> dict[str, Any]:
    try:
        result = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("missing_assistant_message") from None
    if not isinstance(result, dict):
        raise RuntimeError("missing_assistant_message")
    return result


def readiness(endpoint: str, model: str, marker: str, timeout: float) -> dict[str, Any]:
    response, latency = completion(
        endpoint,
        model,
        [{"role": "user", "content": f"Reply exactly: {marker}"}],
        timeout,
        max_tokens=32,
    )
    content = str(message(response).get("content") or "").strip()
    if content != marker:
        raise RuntimeError("readiness_marker_mismatch")
    return {
        "latency_seconds": round(latency, 3),
        "finish_reason": response["choices"][0].get("finish_reason"),
        "output_characters": len(content),
        **token_usage(response.get("usage")),
    }


def tool_call(
    endpoint: str,
    model: str,
    parser_role: str,
    timeout: float,
) -> dict[str, Any]:
    function_name = "inspect_file" if parser_role == "executor" else "report_risk"
    field = "path" if parser_role == "executor" else "risk"
    value = "README.md" if parser_role == "executor" else "race"
    response, latency = completion(
        endpoint,
        model,
        [
            {
                "role": "user",
                "content": f"Call {function_name} exactly once with {field}={value}.",
            }
        ],
        timeout,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": "Candidate parser validation.",
                    "parameters": {
                        "type": "object",
                        "properties": {field: {"type": "string"}},
                        "required": [field],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": function_name}},
        parallel_tool_calls=False,
    )
    calls = message(response).get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != function_name:
        raise RuntimeError("tool_call_parser_failure")
    try:
        arguments = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise RuntimeError("tool_call_argument_failure") from None
    if arguments != {field: value}:
        raise RuntimeError("tool_call_argument_failure")
    return {
        "latency_seconds": round(latency, 3),
        "tool_name": function_name,
        "finish_reason": response["choices"][0].get("finish_reason"),
        **token_usage(response.get("usage")),
    }


def reasoning(endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    response, latency = completion(
        endpoint,
        model,
        [{"role": "user", "content": "Calculate 17 * 19. End the visible answer with 323."}],
        timeout,
        max_tokens=256,
        separate_reasoning=True,
        chat_template_kwargs={"enable_thinking": True},
    )
    result = message(response)
    visible = str(result.get("content") or "")
    hidden = str(result.get("reasoning_content") or "")
    if "323" not in visible or not hidden.strip():
        raise RuntimeError("reasoning_split_failure")
    return {
        "latency_seconds": round(latency, 3),
        "visible_characters": len(visible),
        "reasoning_characters": len(hidden),
        **token_usage(response.get("usage")),
    }


def structured(
    endpoint: str,
    model: str,
    schema: type[PlannerPlan] | type[ReviewResult],
    prompt: str,
    timeout: float,
) -> dict[str, Any]:
    response, latency = completion(
        endpoint,
        model,
        [
            {
                "role": "system",
                "content": "Analyze privately in English and return only the requested JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        timeout,
        max_tokens=2048,
        separate_reasoning=True,
        chat_template_kwargs={"enable_thinking": True},
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        },
    )
    try:
        schema.model_validate(parse_json_content(response))
    except (TypeError, ValueError):
        raise RuntimeError("structured_output_failure") from None
    result = message(response)
    return {
        "latency_seconds": round(latency, 3),
        "schema": schema.__name__,
        "reasoning_characters": len(str(result.get("reasoning_content") or "")),
        **token_usage(response.get("usage")),
    }


def cache_reuse(endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    nonce = uuid.uuid4().hex
    prefix = (f"Radix validation {nonce}. Keep this context unchanged. " * 384).strip()
    cached: list[int] = []
    latencies: list[float] = []
    for suffix, marker in (("first", "CACHE_ONE"), ("second", "CACHE_TWO")):
        response, latency = completion(
            endpoint,
            model,
            [{"role": "user", "content": f"{prefix}\nRequest {suffix}: reply exactly {marker}"}],
            timeout,
            max_tokens=32,
        )
        if str(message(response).get("content") or "").strip() != marker:
            raise RuntimeError("cache_marker_mismatch")
        cached.append(token_usage(response.get("usage"))["cached_tokens"])
        latencies.append(latency)
    if cached[1] <= cached[0] + 100:
        raise RuntimeError("radix_cache_reuse_not_observed")
    return {
        "first_latency_seconds": round(latencies[0], 3),
        "second_latency_seconds": round(latencies[1], 3),
        "first_cached_tokens": cached[0],
        "second_cached_tokens": cached[1],
    }


def model_catalog(endpoint: str, timeout: float) -> list[str]:
    response, _ = get_json(f"{endpoint}/v1/models", timeout)
    models = response.get("data")
    if not isinstance(models, list):
        raise RuntimeError("invalid_model_catalog")
    return sorted(str(item["id"]) for item in models if isinstance(item, dict) and item.get("id"))


def runtime_snapshot() -> dict[str, Any]:
    containers: dict[str, Any] = {}
    for role, name in (
        ("executor", EXECUTOR_CONTAINER),
        ("specialist", SPECIALIST_CONTAINER),
    ):
        containers[role] = container_snapshot(name)
    gpu = _command_json(
        [
            "nvidia-smi",
            "--query-gpu=uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            memory[f"{key.lower()}_kib"] = int(value.split()[0])
    return {"containers": containers, "gpu": gpu, "memory": memory}


def container_snapshot(name: str) -> dict[str, Any]:
    inspected = _command_json(["docker", "container", "inspect", name])
    if not isinstance(inspected, list) or not inspected:
        return {"available": False}
    item = inspected[0]
    source = next(
        (
            mount.get("Source")
            for mount in item.get("Mounts", [])
            if mount.get("Destination") == "/model"
        ),
        None,
    )
    revision = None
    if source:
        metadata = Path(source) / ".cache/huggingface/download/config.json.metadata"
        if metadata.is_file():
            revision = metadata.read_text().splitlines()[0]
    args = item.get("Args") or []
    selected: dict[str, str | bool] = {}
    for option in (
        "--context-length",
        "--mem-fraction-static",
        "--max-running-requests",
        "--max-total-tokens",
        "--max-mamba-cache-size",
        "--quantization",
        "--kv-cache-dtype",
        "--reasoning-parser",
        "--tool-call-parser",
    ):
        if option in args:
            selected[option.removeprefix("--")] = args[args.index(option) + 1]
    selected["radix-cache"] = "--disable-radix-cache" not in args
    return {
        "available": True,
        "status": item.get("State", {}).get("Status"),
        "oom_killed": bool(item.get("State", {}).get("OOMKilled")),
        "image": item.get("Config", {}).get("Image"),
        "image_id": item.get("Image"),
        "model_revision": revision,
        "settings": selected,
    }


def _command_json(command: list[str]) -> Any:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        return []
    if command[0] == "docker":
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def checked(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return {"status": "passed", **action()}
    except Exception as error:  # evidence must retain every independent failure
        return {
            "status": "failed",
            "error_type": type(error).__name__,
            "failure": str(error)
            if str(error).startswith(("http_status_", "transport_"))
            else "check_failed",
        }


def run_validation(
    executor_endpoint: str,
    specialist_endpoint: str,
    timeout: float,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    before = runtime_snapshot()
    executor_model = "dgx-moa-executor-candidate"
    specialist_model = "dgx-moa-specialist-candidate"
    checks = {
        "executor_readiness": checked(
            lambda: readiness(executor_endpoint, executor_model, "EXECUTOR_READY", timeout)
        ),
        "specialist_readiness": checked(
            lambda: readiness(specialist_endpoint, specialist_model, "SPECIALIST_READY", timeout)
        ),
        "executor_tool_parser": checked(
            lambda: tool_call(executor_endpoint, executor_model, "executor", timeout)
        ),
        "specialist_reasoning": checked(
            lambda: reasoning(specialist_endpoint, specialist_model, timeout)
        ),
        "planner_structured_output": checked(
            lambda: structured(
                specialist_endpoint,
                specialist_model,
                PlannerPlan,
                (
                    "Plan a two-file API migration. Include ordered dependencies, validation, "
                    "rollback, risks, and acceptance evidence."
                ),
                timeout,
            )
        ),
        "reviewer_structured_output": checked(
            lambda: structured(
                specialist_endpoint,
                specialist_model,
                ReviewResult,
                (
                    "Review a concurrent cache change where a shared dictionary is mutated "
                    "without a lock. Return a concrete concurrency finding."
                ),
                timeout,
            )
        ),
        "specialist_tool_parser": checked(
            lambda: tool_call(specialist_endpoint, specialist_model, "specialist", timeout)
        ),
        "executor_streaming": checked(
            lambda: stream_json(
                f"{executor_endpoint}/v1/chat/completions",
                {
                    "model": executor_model,
                    "messages": [{"role": "user", "content": "Reply exactly: STREAM_OK"}],
                    "temperature": 0,
                    "max_tokens": 32,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
                timeout,
            )
        ),
        "specialist_streaming": checked(
            lambda: stream_json(
                f"{specialist_endpoint}/v1/chat/completions",
                {
                    "model": specialist_model,
                    "messages": [{"role": "user", "content": "Reply exactly: STREAM_OK"}],
                    "temperature": 0,
                    "max_tokens": 128,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "separate_reasoning": True,
                    "chat_template_kwargs": {"enable_thinking": True},
                },
                timeout,
            )
        ),
        "executor_radix_cache": checked(
            lambda: cache_reuse(executor_endpoint, executor_model, timeout)
        ),
    }
    catalogs = {
        "executor": checked(lambda: {"models": model_catalog(executor_endpoint, timeout)}),
        "specialist": checked(lambda: {"models": model_catalog(specialist_endpoint, timeout)}),
    }
    passed = all(item["status"] == "passed" for item in (*checks.values(), *catalogs.values()))
    return {
        "schema_version": "isolated-sglang-runtime-v1",
        "captured_at": started.isoformat(),
        "duration_seconds": round((datetime.now(UTC) - started).total_seconds(), 3),
        "passed": passed,
        "providers": {
            "executor": {"provider": "sglang", "model": executor_model},
            "planner_reviewer": {"provider": "sglang", "model": specialist_model},
        },
        "catalogs": catalogs,
        "checks": checks,
        "runtime_before": before,
        "runtime_after": runtime_snapshot(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--executor-endpoint",
        type=local_endpoint,
        default="http://127.0.0.1:18101",
    )
    parser.add_argument(
        "--specialist-endpoint",
        type=local_endpoint,
        default="http://127.0.0.1:18102",
    )
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_validation(args.executor_endpoint, args.specialist_endpoint, args.timeout)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
