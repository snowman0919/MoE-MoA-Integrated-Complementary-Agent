#!/usr/bin/env python3
"""Physical validation for the isolated dual-SGLang candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
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
IMAGE = (
    "lmsysorg/sglang:dev-cu13@"
    "sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0"
)
EXECUTOR_REVISION = "15c399c8189eccc9c47d17dcf8adf3c16e8bb3f8"
SPECIALIST_REVISION = "a19cfe00be84568a6867111c9a68c9c44fdcffe6"
MINIMUM_AVAILABLE_MEMORY_KIB = 10 * 1024**2
SAFE_HOSTS = {"127.0.0.1", "::1", "localhost"}
SAFE_CHECK_FAILURES = frozenset(
    {
        "cache_marker_mismatch",
        "host_memory_headroom_below_minimum",
        "host_memory_unavailable",
        "incomplete_sse_response",
        "invalid_capacity_metric",
        "invalid_json_response",
        "invalid_model_catalog",
        "invalid_sse_response",
        "invalid_text_response",
        "missing_assistant_message",
        "model_catalog_mismatch",
        "radix_cache_reuse_not_observed",
        "readiness_marker_mismatch",
        "reasoning_split_failure",
        "runtime_contract_mismatch",
        "served_token_capacity_mismatch",
        "structured_output_failure",
        "tool_call_argument_failure",
        "tool_call_parser_failure",
        "transport_failure",
    }
)


@dataclass(frozen=True)
class ValidationBackend:
    post_json: Callable[[str, dict[str, Any], float], tuple[dict[str, Any], float]]
    get_json: Callable[[str, float], tuple[dict[str, Any], float]]
    stream_json: Callable[..., dict[str, Any]]
    get_text: Callable[[str, float], str]
    runtime_snapshot: Callable[[], dict[str, Any]]


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


def get_text(url: str, timeout: float) -> str:
    try:
        with urlopen(Request(url), timeout=timeout) as response:
            return bytes(response.read()).decode()
    except HTTPError as error:
        raise RuntimeError(f"http_status_{error.code}") from None
    except (URLError, TimeoutError):
        raise RuntimeError("transport_failure") from None
    except UnicodeDecodeError:
        raise RuntimeError("invalid_text_response") from None


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


def stream_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    expected: str = "STREAM_OK",
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
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
        with opener(request, timeout=timeout) as response:
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
    marker = visible.strip() == expected
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
    backend: ValidationBackend | None = None,
    **extra: Any,
) -> tuple[dict[str, Any], float]:
    return (backend or validation_backend()).post_json(
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


def readiness(
    endpoint: str,
    model: str,
    prompt: str,
    expected: str,
    timeout: float,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, Any]:
    response, latency = completion(
        endpoint,
        model,
        [{"role": "user", "content": prompt}],
        timeout,
        backend=backend,
        max_tokens=32,
    )
    content = str(message(response).get("content") or "").strip()
    if content != expected:
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
    *,
    backend: ValidationBackend | None = None,
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
        backend=backend,
        max_tokens=2048,
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


def reasoning(
    endpoint: str,
    model: str,
    timeout: float,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, Any]:
    response, latency = completion(
        endpoint,
        model,
        [{"role": "user", "content": "Calculate 17 * 19. End the visible answer with 323."}],
        timeout,
        backend=backend,
        max_tokens=512,
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
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": "Analyze privately in English and return only the requested JSON.",
        },
        {"role": "user", "content": prompt},
    ]
    analysis, analysis_latency = completion(
        endpoint,
        model,
        messages,
        timeout,
        backend=backend,
        max_tokens=768,
        separate_reasoning=True,
        chat_template_kwargs={"enable_thinking": True},
    )
    analysis_message = message(analysis)
    private_analysis = str(
        analysis_message.get("reasoning_content") or analysis_message.get("content") or ""
    )
    final_messages = [*messages]
    if private_analysis:
        final_messages.append(
            {"role": "assistant", "reasoning_content": private_analysis, "content": ""}
        )
    final_messages.append(
        {
            "role": "user",
            "content": (
                "Using the private English analysis above, return only one minimal valid "
                "JSON object matching the required schema. Do not repeat the analysis."
            ),
        }
    )
    response, final_latency = completion(
        endpoint,
        model,
        final_messages,
        timeout,
        backend=backend,
        max_tokens=1536,
        separate_reasoning=True,
        chat_template_kwargs={
            "enable_thinking": False,
            "truncate_history_thinking": False,
        },
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
    analysis_usage = token_usage(analysis.get("usage"))
    final_usage = token_usage(response.get("usage"))
    return {
        "latency_seconds": round(analysis_latency + final_latency, 3),
        "schema": schema.__name__,
        "reasoning_characters": len(str(result.get("reasoning_content") or "")),
        "analysis_completion_tokens": analysis_usage["completion_tokens"],
        "prompt_tokens": analysis_usage["prompt_tokens"] + final_usage["prompt_tokens"],
        "completion_tokens": (
            analysis_usage["completion_tokens"] + final_usage["completion_tokens"]
        ),
        "total_tokens": analysis_usage["total_tokens"] + final_usage["total_tokens"],
        "cached_tokens": analysis_usage["cached_tokens"] + final_usage["cached_tokens"],
    }


def cache_reuse(
    endpoint: str,
    model: str,
    timeout: float,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, Any]:
    nonce = uuid.uuid4().hex
    prefix = (f"Radix validation {nonce}. Keep this context unchanged. " * 384).strip()
    cached: list[int] = []
    latencies: list[float] = []
    for suffix in ("first", "second"):
        response, latency = completion(
            endpoint,
            model,
            [
                {
                    "role": "user",
                    "content": (
                        f"{prefix}\nRequest {suffix}: What is 2+2? "
                        "Reply with only the number."
                    ),
                }
            ],
            timeout,
            backend=backend,
            max_tokens=32,
        )
        if str(message(response).get("content") or "").strip() != "4":
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


def model_catalog(
    endpoint: str, timeout: float, *, backend: ValidationBackend | None = None
) -> list[str]:
    response, _ = (backend or validation_backend()).get_json(f"{endpoint}/v1/models", timeout)
    models = response.get("data")
    if not isinstance(models, list):
        raise RuntimeError("invalid_model_catalog")
    return sorted(str(item["id"]) for item in models if isinstance(item, dict) and item.get("id"))


def expected_catalog(
    endpoint: str,
    model: str,
    timeout: float,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, list[str]]:
    models = model_catalog(endpoint, timeout, backend=backend)
    if models != [model]:
        raise RuntimeError("model_catalog_mismatch")
    return {"models": models}


def served_token_capacity(
    endpoint: str,
    model: str,
    timeout: float,
    expected: int = 65_536,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, int]:
    metrics = (backend or validation_backend()).get_text(f"{endpoint}/metrics", timeout)
    prefix = "sglang:max_total_num_tokens{"
    values = []
    for line in metrics.splitlines():
        if line.startswith(prefix) and f'model_name="{model}"' in line:
            try:
                values.append(int(float(line.rsplit(" ", 1)[1])))
            except (IndexError, ValueError):
                raise RuntimeError("invalid_capacity_metric") from None
    if values != [expected]:
        raise RuntimeError("served_token_capacity_mismatch")
    return {"max_total_num_tokens": values[0]}


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


def validation_backend() -> ValidationBackend:
    return ValidationBackend(post_json, get_json, stream_json, get_text, runtime_snapshot)


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
        "--swa-full-tokens-ratio",
        "--max-mamba-cache-size",
        "--quantization",
        "--kv-cache-dtype",
        "--cuda-graph-backend-decode",
        "--cuda-graph-max-bs-decode",
        "--cuda-graph-backend-prefill",
        "--reasoning-parser",
        "--tool-call-parser",
    ):
        if option in args:
            selected[option.removeprefix("--")] = args[args.index(option) + 1]
    selected["radix-cache"] = "--disable-radix-cache" not in args
    selected["metrics"] = "--enable-metrics" in args
    selected["cache-report"] = "--enable-cache-report" in args
    selected["incremental-streaming"] = "--incremental-streaming-output" in args
    selected["overlap-schedule"] = "--disable-overlap-schedule" not in args
    bindings = item.get("HostConfig", {}).get("PortBindings") or {}
    ports = sorted(
        f"{binding.get('HostIp')}:{binding.get('HostPort')}->{container_port}"
        for container_port, items in bindings.items()
        for binding in items or []
    )
    return {
        "available": True,
        "status": item.get("State", {}).get("Status"),
        "oom_killed": bool(item.get("State", {}).get("OOMKilled")),
        "image": item.get("Config", {}).get("Image"),
        "image_id": item.get("Image"),
        "model_revision": revision,
        "ports": ports,
        "settings": selected,
        "memory": process_memory(int(item.get("State", {}).get("Pid", 0) or 0)),
    }


def process_memory(
    pid: int,
    proc_root: Path = Path("/proc"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> dict[str, int]:
    if pid < 1:
        return {}
    result: dict[str, int] = {}
    status = proc_root / str(pid) / "status"
    if status.is_file():
        for line in status.read_text().splitlines():
            key, _, status_value = line.partition(":")
            if key in {"VmRSS", "VmSwap"}:
                result[f"process_{key.lower()}_kib"] = int(status_value.split()[0])
    cgroup = proc_root / str(pid) / "cgroup"
    if not cgroup.is_file():
        return result
    unified = next(
        (
            line.split("::", 1)[1]
            for line in cgroup.read_text().splitlines()
            if line.startswith("0::")
        ),
        None,
    )
    if unified is None:
        return result
    directory = cgroup_root / unified.lstrip("/")
    for filename in ("memory.current", "memory.peak", "memory.swap.current"):
        memory_path = directory / filename
        if memory_path.is_file():
            result[filename.replace(".", "_") + "_bytes"] = int(
                memory_path.read_text().strip()
            )
    return result


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
        failure = str(error)
        return {
            "status": "failed",
            "error_type": type(error).__name__,
            "failure": failure
            if failure in SAFE_CHECK_FAILURES or failure.startswith("http_status_")
            else "check_failed",
        }


def runtime_contract(snapshot: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "executor": {
            "revision": EXECUTOR_REVISION,
            "port": "127.0.0.1:18101->18101/tcp",
            "settings": {
                "context-length": "65536",
                "mem-fraction-static": "0.45",
                "max-running-requests": "1",
                "max-total-tokens": "65536",
                "max-mamba-cache-size": "5",
                "quantization": "modelopt_fp4",
                "cuda-graph-backend-decode": "disabled",
                "cuda-graph-backend-prefill": "disabled",
                "tool-call-parser": "qwen3_coder",
                "radix-cache": True,
                "metrics": True,
                "cache-report": True,
                "incremental-streaming": True,
                "overlap-schedule": False,
            },
        },
        "specialist": {
            "revision": SPECIALIST_REVISION,
            "port": "127.0.0.1:18102->18102/tcp",
            "settings": {
                "context-length": "65536",
                "mem-fraction-static": "0.90",
                "max-running-requests": "1",
                "max-total-tokens": "65536",
                "swa-full-tokens-ratio": "0.06",
                "quantization": "modelopt_fp4",
                "cuda-graph-backend-decode": "full",
                "cuda-graph-max-bs-decode": "1",
                "cuda-graph-backend-prefill": "disabled",
                "reasoning-parser": "gemma4",
                "tool-call-parser": "gemma4",
                "radix-cache": True,
                "metrics": True,
                "cache-report": True,
                "incremental-streaming": True,
                "overlap-schedule": True,
            },
        },
    }
    containers = snapshot.get("containers") or {}
    for role, contract in expected.items():
        container = containers.get(role) or {}
        if (
            container.get("available") is not True
            or container.get("status") != "running"
            or container.get("oom_killed") is not False
            or container.get("image") != IMAGE
            or container.get("model_revision") != contract["revision"]
            or container.get("ports") != [contract["port"]]
            or container.get("settings") != contract["settings"]
        ):
            raise RuntimeError("runtime_contract_mismatch")
    memavailable_kib = (snapshot.get("memory") or {}).get("memavailable_kib")
    if isinstance(memavailable_kib, bool) or not isinstance(memavailable_kib, int):
        raise RuntimeError("host_memory_unavailable")
    if memavailable_kib < MINIMUM_AVAILABLE_MEMORY_KIB:
        raise RuntimeError("host_memory_headroom_below_minimum")
    return {
        "host_memory_available_gib": round(memavailable_kib / 1024**2, 3),
        "executor_cgroup_memory_current_bytes": (
            containers["executor"].get("memory") or {}
        ).get("memory_current_bytes"),
        "roles": sorted(expected),
    }


def run_validation(
    executor_endpoint: str,
    specialist_endpoint: str,
    timeout: float,
    *,
    backend: ValidationBackend | None = None,
) -> dict[str, Any]:
    backend = backend or validation_backend()
    started = datetime.now(UTC)
    before = backend.runtime_snapshot()
    executor_model = "dgx-moa-executor-candidate"
    specialist_model = "dgx-moa-specialist-candidate"
    checks = {
        "runtime_before_contract": checked(lambda: runtime_contract(before)),
    }
    inference_actions = {
        "executor_readiness": lambda: readiness(
                executor_endpoint,
                executor_model,
                "What is 2+2? Reply with only the number.",
                "4",
                timeout,
                backend=backend,
        ),
        "specialist_readiness": lambda: readiness(
                specialist_endpoint,
                specialist_model,
                "Reply exactly: SPECIALIST_READY",
                "SPECIALIST_READY",
                timeout,
                backend=backend,
        ),
        "executor_tool_parser": lambda: tool_call(
            executor_endpoint, executor_model, "executor", timeout, backend=backend
        ),
        "specialist_reasoning": lambda: reasoning(
            specialist_endpoint, specialist_model, timeout, backend=backend
        ),
        "planner_structured_output": lambda: structured(
                specialist_endpoint,
                specialist_model,
                PlannerPlan,
                (
                    "Plan a two-file API migration. Include ordered dependencies, validation, "
                    "rollback, risks, and acceptance evidence."
                ),
                timeout,
                backend=backend,
        ),
        "reviewer_structured_output": lambda: structured(
                specialist_endpoint,
                specialist_model,
                ReviewResult,
                (
                    "Review a concurrent cache change where a shared dictionary is mutated "
                    "without a lock. Return a concrete concurrency finding."
                ),
                timeout,
                backend=backend,
        ),
        "specialist_tool_parser": lambda: tool_call(
            specialist_endpoint, specialist_model, "specialist", timeout, backend=backend
        ),
        "executor_streaming": lambda: backend.stream_json(
                f"{executor_endpoint}/v1/chat/completions",
                {
                    "model": executor_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "What is 2+2? Reply with only the number.",
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 32,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
                timeout,
                "4",
        ),
        "specialist_streaming": lambda: backend.stream_json(
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
        ),
        "executor_radix_cache": lambda: cache_reuse(
            executor_endpoint, executor_model, timeout, backend=backend
        ),
    }
    if checks["runtime_before_contract"]["status"] == "passed":
        checks.update(
            {name: checked(action) for name, action in inference_actions.items()}
        )
    else:
        checks.update(
            {
                name: {"status": "skipped", "failure": "unsafe_runtime_contract"}
                for name in inference_actions
            }
        )
    catalogs = {
        "executor": checked(
            lambda: expected_catalog(
                executor_endpoint, executor_model, timeout, backend=backend
            )
        ),
        "specialist": checked(
            lambda: expected_catalog(
                specialist_endpoint, specialist_model, timeout, backend=backend
            )
        ),
    }
    capacities = {
        "executor": checked(
            lambda: served_token_capacity(
                executor_endpoint, executor_model, timeout, backend=backend
            )
        ),
        "specialist": checked(
            lambda: served_token_capacity(
                specialist_endpoint,
                specialist_model,
                timeout,
                65_536,
                backend=backend,
            )
        ),
    }
    after = backend.runtime_snapshot()
    checks["runtime_after_contract"] = checked(lambda: runtime_contract(after))
    passed = all(
        item["status"] == "passed"
        for item in (*checks.values(), *catalogs.values(), *capacities.values())
    )
    return {
        "schema_version": "isolated-sglang-runtime-v1",
        "captured_at": started.isoformat(),
        "duration_seconds": round((datetime.now(UTC) - started).total_seconds(), 3),
        "passed": passed,
        "providers": {
            "executor": {
                "provider": "sglang",
                "model": executor_model,
                "repository": "Cirrascale/Qwen3-Coder-Next-NVFP4",
                "revision": EXECUTOR_REVISION,
            },
            "planner_reviewer": {
                "provider": "sglang",
                "model": specialist_model,
                "repository": "nvidia/Gemma-4-26B-A4B-NVFP4",
                "revision": SPECIALIST_REVISION,
            },
        },
        "catalogs": catalogs,
        "capacities": capacities,
        "checks": checks,
        "runtime_before": before,
        "runtime_after": after,
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
