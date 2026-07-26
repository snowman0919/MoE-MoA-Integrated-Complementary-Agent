#!/usr/bin/env python3
"""Package and score opaque quality artifacts without retaining raw judge output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
SEAL_TOOL = runpy.run_path(str(PROJECT / "scripts/seal-frontier-confirmation.py"))
RUNNER = SEAL_TOOL["RUNNER"]
PRIMARY_MODEL = "gpt-5.6-sol"
SECONDARY_MODEL = "anthropic/claude-opus-5"
SECONDARY_PROVIDER = "amazon-bedrock"
CATEGORY_LIMITS = {
    "contract_completeness": 30,
    "correctness_edge_cases": 25,
    "security_data_integrity": 20,
    "maintainability_diff_discipline": 15,
    "validation_evidence_discipline": 10,
}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|authorization|cookie|password|token)\s*[:=]\s*\S+"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def score_schema() -> dict[str, Any]:
    properties = {
        name: {"type": "number", "minimum": 0, "maximum": limit}
        for name, limit in CATEGORY_LIMITS.items()
    }
    properties.update(
        {
            "total": {"type": "number", "minimum": 0, "maximum": 100},
            "findings": {"type": "array", "items": {"type": "string"}},
        }
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [*CATEGORY_LIMITS, "total", "findings"],
    }


def openrouter_schema(value: Any) -> Any:
    unsupported = {"exclusiveMaximum", "exclusiveMinimum", "maximum", "minimum", "multipleOf"}
    if isinstance(value, dict):
        return {
            key: openrouter_schema(item) for key, item in value.items() if key not in unsupported
        }
    if isinstance(value, list):
        return [openrouter_schema(item) for item in value]
    return value


def validate_score(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {*CATEGORY_LIMITS, "total", "findings"}:
        raise ValueError("judge result has an invalid shape")
    total = 0.0
    result: dict[str, Any] = {}
    for name, limit in CATEGORY_LIMITS.items():
        score = value[name]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"{name} must be numeric")
        score = float(score)
        if not 0 <= score <= limit:
            raise ValueError(f"{name} is out of range")
        result[name] = score
        total += score
    claimed = value["total"]
    if isinstance(claimed, bool) or not isinstance(claimed, (int, float)):
        raise ValueError("total must be numeric")
    if abs(float(claimed) - total) > 0.001:
        raise ValueError("total does not equal the component sum")
    findings = value["findings"]
    if (
        not isinstance(findings, list)
        or len(findings) > 10
        or any(not isinstance(item, str) or len(item) > 500 for item in findings)
    ):
        raise ValueError("findings are invalid")
    result["total"] = total
    result["findings"] = findings
    return result


def assert_sanitized(value: Any) -> None:
    encoded = json.dumps(value, sort_keys=True)
    if any(pattern.search(encoded) for pattern in SECRET_PATTERNS):
        raise ValueError("blind artifact contains a credential-like value")


def load_protocol(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    root = args.output_root / args.protocol_id
    seal = json.loads((root / "confirmation-seal.json").read_text())
    routing = json.loads((root / "confirmation-routing.json").read_text())
    return seal, routing


def artifact_payload(
    attempt: dict[str, Any],
    task: Any,
    starter: str,
    candidate: str,
    checks: dict[str, Any],
) -> dict[str, Any]:
    if not checks or any(not isinstance(value, bool) for value in checks.values()):
        raise ValueError(f"invalid functional checks: {attempt['attempt_id']}")
    package = {
        "schema_version": "blind-quality-artifact-v1",
        "attempt_id": attempt["attempt_id"],
        "repeat": attempt["repeat"],
        "task": task.slug,
        "variant": attempt["variant"],
        "contract": task.readme,
        "starter_source": starter,
        "candidate_source": candidate,
        "functional_checks": dict(sorted(checks.items())),
    }
    assert_sanitized(package)
    return package


def hard_gate_pass(harness: str, score: dict[str, Any]) -> bool:
    if score.get("status") != "passed":
        return False
    if harness == "baseline":
        return True
    telemetry = score.get("telemetry", {})
    resources = score.get("resources", {})
    required_numbers = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "retryable_failures",
        "remote_cost_usd",
    )
    resource_values = [
        resources.get(phase, {}).get(metric)
        for phase in ("before", "after")
        for metric in (
            "gpu_memory_used_bytes",
            "host_memory_used_bytes",
            "swap_used_bytes",
        )
    ]
    return (
        telemetry.get("complete") is True
        and telemetry.get("provider_pinned") is True
        and telemetry.get("provider_switches") == 0
        and telemetry.get("provider_errors") == 0
        and telemetry.get("remote_cost_complete") is True
        and all(
            isinstance(telemetry.get(name), (int, float))
            and not isinstance(telemetry.get(name), bool)
            for name in required_numbers
        )
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in resource_values
        )
    )


def package_all(args: argparse.Namespace) -> dict[str, Any]:
    SEAL_TOOL["verify_seal"](args)
    seal, routing = load_protocol(args)
    blind_root = args.output_root / args.protocol_id / "blind"
    index_path = blind_root / "index.json"
    if index_path.exists():
        raise FileExistsError(f"blind package index already exists: {index_path}")
    rows = []
    for attempt in seal["attempts"]:
        route = routing["variant_routes"][attempt["variant"]]
        harness = route["harness"]
        task = RUNNER["TASK_BY_SLUG"][attempt["task"]]
        evidence = args.output_root / attempt["attempt_id"] / harness / task.slug
        manifest = json.loads((evidence / "manifest.json").read_text())
        score = json.loads((evidence / "score.json").read_text())
        if not hard_gate_pass(harness, score):
            rows.append(
                {
                    "attempt_id": attempt["attempt_id"],
                    "artifact": None,
                    "functional_pass": False,
                }
            )
            continue
        workspace = Path(manifest["workspace"])
        starter = RUNNER["git"](
            workspace,
            "show",
            f"{manifest['initial_commit']}:{task.source_name}",
        ).stdout
        package = artifact_payload(
            attempt,
            task,
            starter,
            (workspace / task.source_name).read_text(),
            score["checks"],
        )
        artifact_path = blind_root / f"{attempt['attempt_id']}.json"
        SEAL_TOOL["exclusive_json"](artifact_path, package)
        rows.append(
            {
                "attempt_id": attempt["attempt_id"],
                "artifact": artifact_path.name,
                "artifact_sha256": SEAL_TOOL["file_sha256"](artifact_path),
                "functional_pass": True,
            }
        )
    index = {
        "protocol_id": args.protocol_id,
        "artifacts": rows,
        "passing": sum(row["functional_pass"] for row in rows),
        "total": len(rows),
    }
    SEAL_TOOL["exclusive_json"](index_path, index)
    return index


def load_judges(root: Path, judge: str) -> dict[str, dict[str, Any]]:
    directory = root / "judges" / judge
    if not directory.is_dir():
        return {}
    return {path.stem: json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))}


def initial_secondary_ids(
    seal: dict[str, Any],
    routing: dict[str, Any],
    primary: dict[str, dict[str, Any]],
) -> set[str]:
    baseline = next(
        label
        for label, route in routing["variant_routes"].items()
        if route["harness"] == "baseline"
    )
    rows = {
        (row["repeat"], row["task"], row["variant"]): row["attempt_id"]
        for row in seal["attempts"]
        if row["attempt_id"] in primary
    }
    selected: set[str] = set()
    for task in RUNNER["TASKS"]:
        for label in routing["variant_routes"]:
            candidates = [
                rows[(repeat, task.slug, label)]
                for repeat in range(1, SEAL_TOOL["REPEATS"] + 1)
                if (repeat, task.slug, label) in rows
            ]
            candidates.sort(
                key=lambda attempt_id: hashlib.sha256(
                    f"{SEAL_TOOL['BOOTSTRAP_SEED']}:{attempt_id}".encode()
                ).hexdigest()
            )
            selected.update(candidates[:2])
    for repeat in range(1, SEAL_TOOL["REPEATS"] + 1):
        for task in RUNNER["TASKS"]:
            baseline_id = rows.get((repeat, task.slug, baseline))
            if baseline_id is None:
                continue
            baseline_score = primary[baseline_id]["score"]["total"]
            for label in routing["variant_routes"]:
                candidate_id = rows.get((repeat, task.slug, label))
                if (
                    label != baseline
                    and candidate_id is not None
                    and abs(primary[candidate_id]["score"]["total"] - baseline_score) > 10
                ):
                    selected.update((baseline_id, candidate_id))
    return selected


def secondary_plan(args: argparse.Namespace) -> dict[str, Any]:
    seal, routing = load_protocol(args)
    root = args.output_root / args.protocol_id
    primary = load_judges(root, "primary")
    secondary = load_judges(root, "secondary")
    initial = initial_secondary_ids(seal, routing, primary)
    scored = initial & secondary.keys()
    agreement = (
        sum(
            abs(primary[attempt_id]["score"]["total"] - secondary[attempt_id]["score"]["total"])
            <= 10
            for attempt_id in scored
        )
        / len(scored)
        if scored
        else None
    )
    passing = {
        row["attempt_id"]
        for row in json.loads((root / "blind/index.json").read_text())["artifacts"]
        if row["functional_pass"]
    }
    required = (
        passing
        if agreement is not None and len(scored) == len(initial) and agreement < 0.8
        else initial
    )
    return {
        "protocol_id": args.protocol_id,
        "initial_count": len(initial),
        "required_count": len(required),
        "completed_count": len(required & secondary.keys()),
        "agreement_rate": agreement,
        "missing_attempt_ids": sorted(required - secondary.keys()),
    }


def assemble(args: argparse.Namespace) -> dict[str, Any]:
    plan = secondary_plan(args)
    if plan["missing_attempt_ids"]:
        raise RuntimeError(f"required secondary scores missing: {len(plan['missing_attempt_ids'])}")
    seal, routing = load_protocol(args)
    root = args.output_root / args.protocol_id
    primary = load_judges(root, "primary")
    secondary = load_judges(root, "secondary")
    rows = []
    for attempt in sorted(seal["attempts"], key=lambda row: row["order"]):
        harness = routing["variant_routes"][attempt["variant"]]["harness"]
        evidence = args.output_root / attempt["attempt_id"] / harness / attempt["task"]
        score = json.loads((evidence / "score.json").read_text())
        passed = hard_gate_pass(harness, score)
        if passed and attempt["attempt_id"] not in primary:
            raise RuntimeError(f"primary score missing: {attempt['attempt_id']}")
        quality = None
        if passed:
            quality = primary[attempt["attempt_id"]]["score"]["total"]
            if attempt["attempt_id"] in secondary:
                quality = (quality + secondary[attempt["attempt_id"]]["score"]["total"]) / 2
        telemetry = score.get("telemetry", {})
        cost = 0.0 if harness == "baseline" else telemetry.get("remote_cost_usd")
        rows.append(
            {
                "repeat": f"r{attempt['repeat']}",
                "task": attempt["task"],
                "variant": harness,
                "passed": passed,
                "telemetry_complete": True
                if harness == "baseline"
                else telemetry.get("complete") is True,
                "quality_score": quality,
                "duration_seconds": score["duration_seconds"],
                "variable_cost_usd": cost,
            }
        )
    output = root / "attempts.jsonl"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {"protocol_id": args.protocol_id, "attempts": len(rows), "output": str(output)}


def judge_prompt(package: dict[str, Any]) -> str:
    rubric = (
        "Score this opaque implementation only against its contract. Return the requested JSON. "
        "Do not use tools or infer the client/provider. Allocate: contract completeness 30, "
        "correctness and edge cases 25, security and data integrity 20, maintainability and diff "
        "discipline 15, validation and evidence discipline 10. Findings must be concise, "
        "redacted, and contain no hidden reasoning. EVIDENCE_JSON="
    )
    return rubric + json.dumps(package, sort_keys=True, separators=(",", ":"))


def primary_score(package: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    codex = RUNNER["CODEX_BINARY"]
    with tempfile.TemporaryDirectory(prefix="moa-blind-judge-") as directory:
        root = Path(directory)
        schema_path = root / "schema.json"
        result_path = root / "result.json"
        schema_path.write_text(json.dumps(score_schema(), sort_keys=True))
        command = [
            str(codex),
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--strict-config",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--config",
            'model_reasoning_effort="high"',
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(result_path),
            "--model",
            PRIMARY_MODEL,
            "--cd",
            str(root),
            judge_prompt(package),
        ]
        completed = subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=timeout
        )
        if completed.returncode != 0 or not result_path.exists():
            raise RuntimeError(f"primary judge failed with exit {completed.returncode}")
        return validate_score(json.loads(result_path.read_text()))


def secondary_score(
    package: dict[str, Any], *, key: str, timeout: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    body = {
        "model": SECONDARY_MODEL,
        "temperature": 0,
        "max_tokens": 4_096,
        "reasoning": {"effort": "high", "exclude": True},
        "provider": {"only": [SECONDARY_PROVIDER], "allow_fallbacks": False},
        "messages": [{"role": "user", "content": judge_prompt(package)}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "blind_quality_score",
                "strict": True,
                "schema": openrouter_schema(score_schema()),
            },
        },
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("provider") != "Amazon Bedrock":
        raise RuntimeError("secondary judge provider pin was not honored")
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    accounting = {
        "provider": payload.get("provider"),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "cost_usd": usage.get("cost"),
    }
    return validate_score(json.loads(content)), accounting


def judge_one(args: argparse.Namespace) -> dict[str, Any]:
    blind_root = args.output_root / args.protocol_id / "blind"
    package = json.loads((blind_root / f"{args.attempt_id}.json").read_text())
    assert_sanitized(package)
    started = time.monotonic()
    if args.judge == "primary":
        score = primary_score(package, timeout=args.timeout)
        accounting = {"input_tokens": None, "output_tokens": None, "cost_usd": 0.0}
        model = PRIMARY_MODEL
    else:
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key and args.openrouter_key_file:
            key = args.openrouter_key_file.read_text().strip()
        if not key:
            raise RuntimeError("OpenRouter key is required for the secondary judge")
        score, accounting = secondary_score(package, key=key, timeout=args.timeout)
        model = SECONDARY_MODEL
    result = {
        "schema_version": "blind-quality-score-v1",
        "protocol_id": args.protocol_id,
        "attempt_id": args.attempt_id,
        "judge": args.judge,
        "model": model,
        "duration_seconds": round(time.monotonic() - started, 3),
        "score": score,
        "accounting": accounting,
    }
    output = args.output_root / args.protocol_id / "judges" / args.judge / f"{args.attempt_id}.json"
    SEAL_TOOL["exclusive_json"](output, result, mode=0o600)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("package", "judge", "secondary-plan", "assemble"))
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--attempt-id")
    parser.add_argument("--judge", choices=("primary", "secondary"))
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    parser.add_argument("--openrouter-key-file", type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.action == "judge" and (not args.attempt_id or not args.judge):
        parser.error("judge requires --attempt-id and --judge")
    return args


def main() -> int:
    args = parse_args()
    result = (
        package_all(args)
        if args.action == "package"
        else judge_one(args)
        if args.action == "judge"
        else secondary_plan(args)
        if args.action == "secondary-plan"
        else assemble(args)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
