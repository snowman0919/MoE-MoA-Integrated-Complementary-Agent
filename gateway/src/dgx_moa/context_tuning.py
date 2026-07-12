from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from itertools import product
from pathlib import Path
from typing import Any, cast

import httpx

from .config import load_settings
from .schemas import JudgeVerdict

CONTEXT_CANDIDATES = {
    "executor": [16384, 24576, 32768, 40960, 49152, 65536, 81920, 98304, 131072],
    "planner": [8192, 12288, 16384, 24576, 32768, 49152, 65536],
    "reviewer": [8192, 12288, 16384, 24576, 32768, 49152, 65536],
    "reasoner": [8192, 12288, 16384, 24576, 32768, 49152, 65536],
    "judge": [8192, 16384, 24576, 32768, 49152, 65536, 98304, 131072],
}
HEADROOM = {"resident": 5 * 1024**3, "judge": 16 * 1024**3}
PORTS = {"executor": 8101, "planner": 8102, "reviewer": 8103, "reasoner": 8104, "judge": 8110}


def weighted_context_score(contexts: dict[str, int]) -> float:
    return (
        0.60 * contexts["executor"]
        + 0.20 * contexts["planner"]
        + 0.15 * contexts["reviewer"]
        + 0.05 * contexts["reasoner"]
    )


def candidate_vectors(profile: str, native_limits: dict[str, int]) -> list[dict[str, int]]:
    if profile == "judge":
        return [
            {"judge": value}
            for value in CONTEXT_CANDIDATES["judge"]
            if value <= native_limits["judge"]
        ]
    if profile != "resident":
        raise ValueError("profile must be resident or judge")
    values = [
        [value for value in CONTEXT_CANDIDATES[role] if value <= native_limits[role]]
        for role in ("executor", "planner", "reviewer", "reasoner")
    ]
    candidates = [
        {"executor": executor, "planner": planner, "reviewer": reviewer, "reasoner": reasoner}
        for executor, planner, reviewer, reasoner in product(*values)
    ]
    return sorted(candidates, key=weighted_context_score)


def parse_vllm_capacity(log: str) -> dict[str, int | float | None]:
    tokens = re.findall(r"GPU KV cache size: ([\d,]+) tokens", log)
    concurrency = re.findall(r"Maximum concurrency .*?: ([\d.]+)x", log)
    return {
        "kv_cache_tokens": int(tokens[-1].replace(",", "")) if tokens else None,
        "maximum_concurrency": float(concurrency[-1]) if concurrency else None,
    }


def stable(result: dict[str, Any]) -> bool:
    profile = result["profile"]
    return all(
        (
            result.get("startup_attempts") == 3,
            result.get("readiness"),
            result.get("minimum_completion"),
            result.get("structured_output"),
            result.get("sequential_requests") == 5,
            result.get("near_limit"),
            result.get("service_restart"),
            result.get("responsive"),
            not result.get("oom"),
            result.get("mem_available_bytes", 0) >= HEADROOM[profile],
        )
    )


def select_best(results: list[dict[str, Any]], profile: str) -> dict[str, Any] | None:
    passed = [result for result in results if result.get("profile") == profile and stable(result)]
    if not passed:
        return None
    if profile == "judge":
        return max(passed, key=lambda result: result["contexts"]["judge"])
    return max(passed, key=lambda result: weighted_context_score(result["contexts"]))


def next_larger_rejection(
    selected: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any] | None:
    profile = selected["profile"]
    selected_score = (
        selected["contexts"]["judge"]
        if profile == "judge"
        else weighted_context_score(selected["contexts"])
    )
    larger = []
    for result in results:
        if result.get("profile") != profile or stable(result):
            continue
        score = (
            result["contexts"]["judge"]
            if profile == "judge"
            else weighted_context_score(result["contexts"])
        )
        if score > selected_score and result.get("failure_reason"):
            larger.append((score, result))
    return min(larger, key=lambda item: item[0])[1] if larger else None


def mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable missing")


def request_body(role: str, context: int, near_limit: bool = False) -> dict[str, Any]:
    content = "Reply with OK."
    if near_limit:
        content = "x " * max(1, context - 512) + "\nReply OK."
    body: dict[str, Any] = {
        "model": f"dgx-moa-{role}",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 16,
        "temperature": 0,
    }
    if role == "planner":
        body["messages"] = [{"role": "user", "content": "Return a one-step JSON plan."}]
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "plan",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"plan": {"type": "array", "items": {"type": "string"}}},
                    "required": ["plan"],
                    "additionalProperties": False,
                },
            },
        }
    elif role == "reviewer":
        body["messages"] = [{"role": "user", "content": "Return an approved JSON review."}]
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "review",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["approved", "rejected"]},
                        "findings": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["status", "findings"],
                    "additionalProperties": False,
                },
            },
        }
    elif role == "judge":
        body["messages"] = [
            {
                "role": "system",
                "content": (
                    "Read-only heavy judge. Return only the requested JSON. Never call tools."
                ),
            },
            {"role": "user", "content": content},
        ]
        body["max_tokens"] = 256
        body["reasoning_effort"] = "high"
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "judge_verdict",
                "strict": True,
                "schema": JudgeVerdict.model_json_schema(),
            },
        }
    return body


def complete(role: str, body: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"http://127.0.0.1:{PORTS[role]}/v1/chat/completions", json=body, timeout=900
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def probe_role(role: str, context: int) -> dict[str, Any]:
    started = time.monotonic()
    minimum = complete(role, request_body(role, context))
    structured = True
    if role in {"planner", "reviewer", "judge"}:
        content = minimum["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if role == "judge":
            JudgeVerdict.model_validate(parsed)
            structured = not minimum["choices"][0]["message"].get("tool_calls")
    for _ in range(4):
        complete(role, request_body(role, context))
    complete(role, request_body(role, context, near_limit=True))
    return {
        "minimum_completion": True,
        "structured_output": structured,
        "sequential_requests": 5,
        "near_limit": True,
        "latency_seconds": round(time.monotonic() - started, 3),
    }


def journal(unit: str, since: int) -> str:
    return subprocess.run(
        ["journalctl", "--user", "-u", unit, "--since", f"@{since}", "--no-pager"],
        check=False,
        text=True,
        capture_output=True,
    ).stdout


def run_trial(profile: str) -> dict[str, Any]:
    settings = load_settings()
    roles = ("executor", "planner", "reviewer", "reasoner") if profile == "resident" else ("judge",)
    contexts = {
        role: max(
            model.context_length,
            int(os.getenv(f"DGX_MOA_{role.upper()}_MAX_MODEL_LEN", model.context_length)),
        )
        for role, model in settings.models.items()
        if role in roles
    }
    started = int(time.time())
    available_samples = []
    for _ in range(3):
        subprocess.run(["systemctl", "--user", "restart", f"dgx-moa-{profile}.target"], check=True)
        subprocess.run(["scripts/wait-profile.sh", profile, "3600"], check=True)
        available_samples.append(mem_available())
    result: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profile": profile,
        "contexts": contexts,
        "startup_attempts": 3,
        "readiness": True,
        "service_restart": True,
        "responsive": True,
        "mem_available_bytes": min(available_samples),
        "model_revisions": {role: settings.models[role].revision for role in roles},
        "vllm_version": subprocess.run(
            [os.path.expanduser("~/.pyenv/shims/vllm"), "--version"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip(),
        "roles": {},
    }
    try:
        for role in roles:
            result["roles"][role] = probe_role(role, contexts[role])
        result.update(
            {
                "minimum_completion": True,
                "structured_output": True,
                "sequential_requests": 5,
                "near_limit": True,
            }
        )
    except Exception as error:
        result["failure_reason"] = f"{type(error).__name__}: {error}"
    logs = {role: journal(f"dgx-moa-{role}.service", started) for role in roles}
    result["kv_cache"] = {role: parse_vllm_capacity(log) for role, log in logs.items()}
    kernel = subprocess.run(
        ["journalctl", "-k", "--since", f"@{started}", "--no-pager"],
        check=False,
        text=True,
        capture_output=True,
    ).stdout.lower()
    result["oom"] = "out of memory: killed process" in kernel
    result["selected"] = stable(result)
    return result


def append_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {"results": []}
    data["results"].append(result)
    selected = select_best(data["results"], result["profile"])
    if selected:
        data.setdefault("selected", {})[result["profile"]] = selected["contexts"]
        rejected = next_larger_rejection(selected, data["results"])
        if rejected:
            data.setdefault("next_larger_rejection", {})[result["profile"]] = {
                "contexts": rejected["contexts"],
                "reason": rejected["failure_reason"],
            }
    path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    candidates = subparsers.add_parser("candidates")
    candidates.add_argument("profile", choices=("resident", "judge"))
    trial = subparsers.add_parser("trial")
    trial.add_argument("profile", choices=("resident", "judge"))
    trial.add_argument("--output", type=Path, default=Path("data/benchmarks/context-tuning.json"))
    arguments = parser.parse_args()
    if arguments.command == "candidates":
        settings = load_settings()
        limits = {role: model.context_length for role, model in settings.models.items()}
        print(json.dumps(candidate_vectors(arguments.profile, limits)))
        return
    result = run_trial(arguments.profile)
    append_result(arguments.output, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if stable(result) else 2)


if __name__ == "__main__":
    main()
