#!/usr/bin/env python3
"""Prepare and seal the blinded 200-attempt confirmatory panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from dgx_moa import (
    breadth_noninferiority,
    breadth_quality,
    frontier_noninferiority,
    quality_matrix,
)

PROJECT = Path(__file__).resolve().parents[3]
SCORER_PATH = PROJECT / "gateway/src/dgx_moa/blind_quality.py"
PROTOCOL_PATH = PROJECT / "docs/QUALITY_EVALUATION.md"

REPEATS = 10
CODING_SEED = 56_052_026
BREADTH_SEED = 56_052_027
QUALITY_MARGIN = -5.0
SPEED_MARGIN = 1.5
OPAQUE_LABELS = ("variant-a", "variant-b", "variant-c", "variant-d")


@dataclass(frozen=True)
class PanelConfig:
    name: str
    bootstrap_seed: int
    runner: Any
    tasks: tuple[quality_matrix.Task, ...]
    task_by_slug: Mapping[str, quality_matrix.Task]
    runner_path: Path
    analyzer_path: Path


def configure_panel(panel: str) -> PanelConfig:
    if panel == "coding":
        return PanelConfig(
            panel,
            CODING_SEED,
            quality_matrix,
            quality_matrix.TASKS,
            MappingProxyType(quality_matrix.TASK_BY_SLUG),
            Path(quality_matrix.__file__),
            Path(frontier_noninferiority.__file__),
        )
    if panel == "breadth":
        return PanelConfig(
            panel,
            BREADTH_SEED,
            quality_matrix,
            breadth_quality.TASKS,
            MappingProxyType({task.slug: task for task in breadth_quality.TASKS}),
            Path(breadth_quality.__file__),
            Path(breadth_noninferiority.__file__),
        )
    raise ValueError(f"unknown panel: {panel}")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=True, timeout=30)
    return result.stdout.strip()


def repository_revision() -> str:
    if command_output(["git", "-C", str(PROJECT), "status", "--porcelain"]):
        raise RuntimeError("candidate repository must be clean before sealing")
    return command_output(["git", "-C", str(PROJECT), "rev-parse", "HEAD"])


def client_metadata(config: PanelConfig) -> dict[str, dict[str, str]]:
    codex = config.runner.CODEX_BINARY
    opencode = config.runner.OPENCODE_BINARY
    hermes_root = config.runner.HERMES_ROOT
    hermes_python = hermes_root / "venv/bin/python"
    hermes_revision = command_output(["git", "-C", str(hermes_root), "rev-parse", "HEAD"])
    if command_output(["git", "-C", str(hermes_root), "status", "--porcelain"]):
        raise RuntimeError("installed Hermes source must be clean before sealing")
    return {
        "baseline": {
            "version": command_output([str(codex), "--version"]),
            "binary_sha256": file_sha256(codex),
        },
        "codex": {
            "version": command_output([str(codex), "--version"]),
            "binary_sha256": file_sha256(codex),
        },
        "opencode": {
            "version": command_output([str(opencode), "--version"]),
            "binary_sha256": file_sha256(opencode),
        },
        "hermes": {
            "version": command_output(
                [
                    str(hermes_python),
                    "-c",
                    "import importlib.metadata as m; print(m.version('hermes-agent'))",
                ]
            ),
            "binary_sha256": file_sha256(hermes_python),
            "source_revision": hermes_revision,
        },
    }


def provider_fingerprints(config: PanelConfig) -> dict[str, str]:
    models = file_sha256(PROJECT / "config/models.yaml")
    frontier = file_sha256(PROJECT / "config/codex-frontier.yaml")
    hermes = file_sha256(Path("/home/kotori9/.hermes/config.yaml"))
    catalog = canonical_sha256(config.runner.codex_model_catalog())
    return {
        "baseline": canonical_sha256({"model": "gpt-5.6-sol", "reasoning": "high"}),
        "codex": canonical_sha256({"models": models, "frontier": frontier, "catalog": catalog}),
        "opencode": canonical_sha256(
            {"models": models, "frontier": frontier, "model": "dgx-moa-agent"}
        ),
        "hermes": canonical_sha256({"models": models, "frontier": frontier, "hermes": hermes}),
    }


def container_image_digest(config: PanelConfig) -> str:
    image = config.runner.DOCKER_IMAGE
    return command_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"])


def attempt_plan(
    protocol_id: str, config: PanelConfig | None = None
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    config = config or configure_panel("coding")
    harnesses = tuple(config.runner.HARNESSES)
    if len(harnesses) != len(OPAQUE_LABELS):
        raise RuntimeError("opaque label count does not match harness count")
    labels = list(OPAQUE_LABELS)
    random.Random(config.bootstrap_seed).shuffle(labels)
    routing = dict(zip(labels, harnesses, strict=True))
    attempts = [
        {
            "repeat": repeat,
            "task": task.slug,
            "variant": label,
        }
        for repeat in range(1, REPEATS + 1)
        for task in config.tasks
        for label in labels
    ]
    random.Random(config.bootstrap_seed + 1).shuffle(attempts)
    for index, attempt in enumerate(attempts, 1):
        attempt["attempt_id"] = f"{protocol_id}-a{index:03d}"
        attempt["order"] = index
    return attempts, routing


def exclusive_json(path: Path, value: Any, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def create_seal(args: argparse.Namespace) -> dict[str, Any]:
    config = configure_panel(getattr(args, "panel", "coding"))
    revision = repository_revision()
    attempts, routing = attempt_plan(args.protocol_id, config)
    clients = client_metadata(config)
    providers = provider_fingerprints(config)
    image_digest = container_image_digest(config)
    seal_dir = args.output_root / args.protocol_id
    seal_path = seal_dir / "confirmation-seal.json"
    routing_path = seal_dir / "confirmation-routing.json"
    if seal_path.exists() or routing_path.exists():
        raise FileExistsError(f"protocol already sealed: {args.protocol_id}")

    manifests: list[dict[str, Any]] = []
    for attempt in attempts:
        harness = routing[attempt["variant"]]
        task = config.task_by_slug[attempt["task"]]
        runner_args = Namespace(
            run_id=attempt["attempt_id"],
            workspace_root=args.workspace_root,
            output_root=args.output_root,
            gateway=args.gateway,
        )
        manifest = config.runner.prepare_one(runner_args, harness, task)
        manifests.append(
            {
                **attempt,
                "fixture_commit": manifest["initial_commit"],
                "tests_sha256": manifest["tests_sha256"],
            }
        )

    private = {
        "protocol_id": args.protocol_id,
        "panel": getattr(args, "panel", "coding"),
        "variant_routes": {
            label: {
                "harness": harness,
                "client": clients[harness],
                "provider_fingerprint": providers[harness],
            }
            for label, harness in routing.items()
        },
    }
    exclusive_json(routing_path, private, mode=0o600)
    seal = {
        "protocol_id": args.protocol_id,
        "protocol_version": "frontier-confirmation-v1",
        "panel": getattr(args, "panel", "coding"),
        "analysis_commit": revision,
        "repeats": REPEATS,
        "attempts_total": len(manifests),
        "bootstrap_seed": config.bootstrap_seed,
        "bootstrap_samples": 10_000,
        "quality_noninferiority_margin": QUALITY_MARGIN,
        "speed_noninferiority_margin": SPEED_MARGIN,
        "runner_sha256": file_sha256(config.runner_path),
        "analyzer_sha256": file_sha256(config.analyzer_path),
        "scorer_sha256": file_sha256(SCORER_PATH),
        "protocol_sha256": file_sha256(PROTOCOL_PATH),
        "container_image": config.runner.DOCKER_IMAGE,
        "container_image_digest": image_digest,
        "prompt_sha256": {
            task.slug: hashlib.sha256(config.runner.prompt(task).encode()).hexdigest()
            for task in config.tasks
        },
        "routing_sha256": canonical_sha256(private),
        "attempt_order_sha256": canonical_sha256(manifests),
        "attempts": manifests,
    }
    exclusive_json(seal_path, seal)
    return seal


def verify_seal(args: argparse.Namespace) -> dict[str, Any]:
    config = configure_panel(getattr(args, "panel", "coding"))
    seal_dir = args.output_root / args.protocol_id
    routing_path = seal_dir / "confirmation-routing.json"
    seal = json.loads((seal_dir / "confirmation-seal.json").read_text())
    private = json.loads(routing_path.read_text())
    expected_attempts, expected_routes = attempt_plan(args.protocol_id, config)
    clients = client_metadata(config)
    providers = provider_fingerprints(config)
    checks = {
        "analysis_commit": repository_revision() == seal["analysis_commit"],
        "panel": seal.get("panel") == getattr(args, "panel", "coding"),
        "runner_sha256": file_sha256(config.runner_path) == seal["runner_sha256"],
        "analyzer_sha256": file_sha256(config.analyzer_path) == seal["analyzer_sha256"],
        "scorer_sha256": file_sha256(SCORER_PATH) == seal["scorer_sha256"],
        "protocol_sha256": file_sha256(PROTOCOL_PATH) == seal["protocol_sha256"],
        "routing_sha256": canonical_sha256(private) == seal["routing_sha256"],
        "attempt_order_sha256": canonical_sha256(seal["attempts"]) == seal["attempt_order_sha256"],
        "container_image_digest": container_image_digest(config)
        == seal["container_image_digest"],
        "routing_permissions": routing_path.stat().st_mode & 0o777 == 0o600,
        "attempt_count": len(seal["attempts"])
        == REPEATS * len(config.tasks) * len(OPAQUE_LABELS),
    }
    sealed_order = [
        {key: row[key] for key in ("attempt_id", "order", "repeat", "task", "variant")}
        for row in seal["attempts"]
    ]
    checks["deterministic_order"] = sealed_order == expected_attempts
    for label, harness in expected_routes.items():
        route = private["variant_routes"].get(label, {})
        checks[f"route:{label}"] = route.get("harness") == harness
        checks[f"client:{label}"] = route.get("client") == clients[harness]
        checks[f"provider:{label}"] = route.get("provider_fingerprint") == providers[harness]
    for row in seal["attempts"]:
        harness = expected_routes[row["variant"]]
        evidence = args.output_root / row["attempt_id"] / harness / row["task"]
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        workspace = Path(manifest.get("workspace", "/missing"))
        tests_path = workspace / "tests/test_task.py"
        fixture_ok = (
            manifest.get("run_id") == row["attempt_id"]
            and manifest.get("harness") == harness
            and manifest.get("task") == row["task"]
            and manifest.get("initial_commit") == row["fixture_commit"]
            and manifest.get("tests_sha256") == row["tests_sha256"]
            and tests_path.is_file()
            and file_sha256(tests_path) == row["tests_sha256"]
        )
        if fixture_ok:
            fixture_ok = (
                command_output(["git", "-C", str(workspace), "rev-parse", "HEAD"])
                == row["fixture_commit"]
            )
        checks[f"fixture:{row['attempt_id']}"] = fixture_ok
    for task in config.tasks:
        checks[f"prompt_sha256:{task.slug}"] = (
            hashlib.sha256(config.runner.prompt(task).encode()).hexdigest()
            == seal["prompt_sha256"][task.slug]
        )
    result = {
        "protocol_id": args.protocol_id,
        "valid": all(checks.values()),
        "checks": checks,
    }
    if not result["valid"]:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--panel", choices=("coding", "breadth"), default="coding")
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "code")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/dgx-moa-client-quality"))
    parser.add_argument("--gateway", default="http://127.0.0.1:9000")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = create_seal(args) if args.action == "create" else verify_seal(args)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
