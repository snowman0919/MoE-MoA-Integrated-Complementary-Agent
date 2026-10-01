#!/usr/bin/env python3
"""Read-only, fail-closed Current-Executor P0 capability audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

EXECUTOR_BASE_IMAGE = (
    "python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a"
)
REQUIRED_P0_SERVICES = ("gateway", "executor", "reasoner", "harness")


def run(*command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def json_stream(value: str) -> list[Any]:
    decoder = json.JSONDecoder()
    documents = []
    cursor = 0
    while cursor < len(value):
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor == len(value):
            break
        document, cursor = decoder.raw_decode(value, cursor)
        documents.append(document)
    return documents


def artifact_digest(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    files = 0
    size = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_size = path.stat().st_size
        digest.update(file_size.to_bytes(8, "big"))
        with path.open("rb") as source:
            while chunk := source.read(8 * 1024 * 1024):
                digest.update(chunk)
        files += 1
        size += file_size
    return {"sha256": digest.hexdigest(), "files": files, "bytes": size}


def option_value(arguments: list[str], option: str) -> str | None:
    try:
        return arguments[arguments.index(option) + 1]
    except (IndexError, ValueError):
        return None


def select_reasoner_model(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((row for row in payload.get("models", []) if row.get("name") == name), None)


def digest_pinned(image: str) -> bool:
    return "@sha256:" in image or image.startswith("sha256:")


def executor_probe_command(image: str, executor_python: Path, python_root: Path) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--env",
        "HOME=/tmp",
        "--env",
        "XDG_CACHE_HOME=/tmp/cache",
        "--volume",
        f"{executor_python.parent.parent}:{executor_python.parent.parent}:ro",
        "--volume",
        f"{python_root}:{python_root}:ro",
        image,
        str(executor_python),
        "-c",
        "import json,sglang,torch; print(json.dumps({"
        "'sglang':sglang.__version__,'torch':torch.__version__,"
        "'cuda_available':torch.cuda.is_available(),"
        "'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},"
        "sort_keys=True))",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--compose", type=Path, default=Path("compose.yaml"))
    parser.add_argument("--gateway-image")
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--executor-python", type=Path)
    parser.add_argument("--executor-python-root", type=Path)
    parser.add_argument("--executor-base-image", default=EXECUTOR_BASE_IMAGE)
    parser.add_argument("--executor-pid", type=int)
    parser.add_argument("--executor-state-manifest", type=Path)
    parser.add_argument("--executor-provenance", type=Path)
    parser.add_argument("--executor-model-dir", type=Path)
    parser.add_argument("--executor-draft-dir", type=Path)
    parser.add_argument("--reasoner-url")
    parser.add_argument("--reasoner-model")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    dockerfile = (repository / "Dockerfile").read_text()
    compose_path = (
        arguments.compose if arguments.compose.is_absolute() else repository / arguments.compose
    )
    compose = yaml.safe_load(compose_path.read_text())
    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    build_images = [line.split()[1] for line in dockerfile.splitlines() if line.startswith("FROM ")]
    images = [
        service.get("image")
        for service in services.values()
        if isinstance(service, dict) and isinstance(service.get("image"), str)
    ]
    static_failures = []
    if not build_images or any(not digest_pinned(image) for image in build_images):
        static_failures.append("gateway_base_image_not_digest_pinned")
    if not images or any(not digest_pinned(image) for image in images):
        static_failures.append("compose_images_not_digest_pinned")
    for required in REQUIRED_P0_SERVICES:
        if required not in services:
            static_failures.append(f"compose_service_missing:{required}")
    clients = {name: shutil.which(name) for name in ("codex", "opencode", "hermes")}
    if any(path is None for path in clients.values()):
        static_failures.append("client_binary_missing")

    gateway_container: dict[str, Any] = {"verified": False, "reason": "not_run"}
    if arguments.gateway_image is not None:
        inspected = run(
            "docker", "image", "inspect", arguments.gateway_image, "--format", "{{.Id}}"
        )
        image_id = inspected.stdout.strip()
        gateway_container = {
            "verified": inspected.returncode == 0 and image_id.startswith("sha256:"),
            "reference": arguments.gateway_image,
            "image_id": image_id or None,
        }

    component: dict[str, Any] = {"verified": False, "reason": "not_run"}
    if arguments.production_root is not None:
        health = run("./scripts/healthcheck.sh", cwd=arguments.production_root)
        try:
            documents = json_stream(health.stdout) if health.returncode == 0 else []
            health_payload, models_payload, ready_payload = documents
            model_rows = models_payload.get("data", [])
            component = {
                "verified": (
                    health_payload.get("status") == "ok"
                    and ready_payload.get("status") == "ready"
                    and ready_payload.get("services", {}).get("executor") == "ready"
                    and {row.get("id") for row in model_rows} == {"dgx-moa", "dgx-moa-fast"}
                    and {row.get("context_length") for row in model_rows} == {262144}
                ),
                "health_status": health_payload.get("status"),
                "ready_status": ready_payload.get("status"),
                "executor_status": ready_payload.get("services", {}).get("executor"),
                "models": [
                    {"id": row.get("id"), "context_length": row.get("context_length")}
                    for row in model_rows
                ],
                "response_sha256": hashlib.sha256(health.stdout.encode()).hexdigest(),
            }
        except (AttributeError, TypeError, ValueError):
            component = {"verified": False, "reason": "invalid_healthcheck_output"}

    executor_container: dict[str, Any] = {"verified": False, "reason": "not_run"}
    if arguments.executor_python is not None or arguments.executor_python_root is not None:
        if arguments.executor_python is None or arguments.executor_python_root is None:
            parser.error("--executor-python and --executor-python-root must be provided together")
        probe = run(
            *executor_probe_command(
                arguments.executor_base_image,
                arguments.executor_python.absolute(),
                arguments.executor_python_root.absolute(),
            )
        )
        try:
            payload = json.loads(probe.stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload = {}
        executor_container = {
            "verified": (
                probe.returncode == 0
                and payload.get("cuda_available") is True
                and payload.get("device") == "NVIDIA GB10"
            ),
            "base_image": arguments.executor_base_image,
            "base_image_digest_pinned": "@sha256:" in arguments.executor_base_image,
            "runtime": payload,
            "response_sha256": hashlib.sha256(probe.stdout.encode()).hexdigest(),
            "return_code": probe.returncode,
        }

    identity_inputs = (
        arguments.executor_pid,
        arguments.executor_state_manifest,
        arguments.executor_provenance,
        arguments.executor_model_dir,
        arguments.executor_draft_dir,
    )
    executor_identity: dict[str, Any] = {"verified": False, "reason": "not_run"}
    if any(value is not None for value in identity_inputs):
        if any(value is None for value in identity_inputs):
            parser.error("all executor identity arguments must be provided together")
        assert arguments.executor_pid is not None
        assert arguments.executor_state_manifest is not None
        assert arguments.executor_provenance is not None
        assert arguments.executor_model_dir is not None
        assert arguments.executor_draft_dir is not None
        command = [
            value.decode()
            for value in Path(f"/proc/{arguments.executor_pid}/cmdline").read_bytes().split(b"\0")
            if value
        ]
        state = json.loads(arguments.executor_state_manifest.read_text())
        provenance = json.loads(arguments.executor_provenance.read_text())
        runtime = executor_container.get("runtime", {})
        target_artifact = artifact_digest(arguments.executor_model_dir)
        draft_artifact = artifact_digest(arguments.executor_draft_dir)
        checks = {
            "loopback": option_value(command, "--host") == "127.0.0.1",
            "model_path": option_value(command, "--model-path")
            == str(arguments.executor_model_dir.absolute()),
            "draft_path": option_value(command, "--speculative-draft-model-path")
            == str(arguments.executor_draft_dir.absolute()),
            "served_model": option_value(command, "--served-model-name") == "dgx-moa-executor",
            "context": option_value(command, "--context-length") == "262144",
            "one_request": option_value(command, "--max-running-requests") == "1",
            "memory_fraction": option_value(command, "--mem-fraction-static") == "0.35",
            "attention": option_value(command, "--attention-backend") == "flashinfer",
            "kv_cache": option_value(command, "--kv-cache-dtype") == "fp8_e4m3",
            "total_tokens": option_value(command, "--max-total-tokens") == "270000",
            "batch_one_graph": option_value(command, "--cuda-graph-max-bs") == "1",
            "quantization": option_value(command, "--quantization") == "modelopt_fp4",
            "dspark": option_value(command, "--speculative-algorithm") == "DSPARK",
            "draft_revision": option_value(command, "--speculative-draft-model-revision")
            == state.get("draft", {}).get("revision"),
            "source_revision": provenance.get("source_revision")
            == state.get("source", {}).get("revision"),
            "modelopt_revision": provenance.get("modelopt_revision")
            == state.get("modelopt_revision"),
            "sglang_revision": str(state.get("sglang_revision", ""))[:9]
            in str(runtime.get("sglang", "")),
            "target_artifact_nonempty": target_artifact["files"] > 0,
            "draft_artifact_nonempty": draft_artifact["files"] > 0,
        }
        executor_identity = {
            "verified": all(checks.values()),
            "checks": checks,
            "argv": command,
            "argv_sha256": hashlib.sha256(
                b"\0".join(value.encode() for value in command)
            ).hexdigest(),
            "state_manifest_sha256": hashlib.sha256(
                arguments.executor_state_manifest.read_bytes()
            ).hexdigest(),
            "provenance_sha256": hashlib.sha256(
                arguments.executor_provenance.read_bytes()
            ).hexdigest(),
            "target_artifact": target_artifact,
            "draft_artifact": draft_artifact,
            "source_repository": provenance.get("source_repository"),
            "source_revision": provenance.get("source_revision"),
            "modelopt_revision": provenance.get("modelopt_revision"),
            "sglang_revision": state.get("sglang_revision"),
            "draft_revision": state.get("draft", {}).get("revision"),
        }

    reasoner_identity: dict[str, Any] = {"verified": False, "reason": "not_run"}
    if arguments.reasoner_url is not None or arguments.reasoner_model is not None:
        if arguments.reasoner_url is None or arguments.reasoner_model is None:
            parser.error("--reasoner-url and --reasoner-model must be provided together")
        with urllib.request.urlopen(
            arguments.reasoner_url.rstrip("/") + "/api/tags", timeout=10
        ) as response:
            reasoner_payload = json.load(response)
        model = select_reasoner_model(reasoner_payload, arguments.reasoner_model) or {}
        digest = model.get("digest")
        host = urlsplit(arguments.reasoner_url).hostname
        reasoner_identity = {
            "verified": bool(
                model
                and isinstance(digest, str)
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
            ),
            "endpoint_loopback": host in {"127.0.0.1", "::1", "localhost"},
            "model": model.get("name"),
            "digest": digest,
            "bytes": model.get("size"),
            "details": model.get("details"),
        }

    if not executor_container.get("verified"):
        static_failures.append("executor_container_preflight_not_verified")
    if not gateway_container.get("verified"):
        static_failures.append("gateway_container_identity_not_verified")
    if not executor_identity.get("verified"):
        static_failures.append("executor_runtime_identity_not_verified")
    if not reasoner_identity.get("verified"):
        static_failures.append("reasoner_source_identity_not_verified")
    elif not reasoner_identity.get("endpoint_loopback"):
        static_failures.append("reasoner_endpoint_not_loopback")

    statuses = {
        "STATIC_VERIFIED": not static_failures,
        "REAL_API_COMPONENT_VERIFIED": bool(component.get("verified")),
        "HARNESS_E2E_VERIFIED": False,
        "FAULT_RECOVERY_VERIFIED": False,
        "SOAK_VERIFIED": False,
        "RELEASE_CERTIFIED": False,
    }
    result = {
        "schema_version": "current-executor-p0-audit-v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_commit": run("git", "rev-parse", "HEAD", cwd=repository).stdout.strip(),
        "static_failures": sorted(static_failures),
        "compose_services": sorted(services),
        "compose_path": str(compose_path),
        "gateway_build_images": build_images,
        "gateway_container_identity": gateway_container,
        "source_hashes": {
            "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "dockerfile_sha256": hashlib.sha256(
                (repository / "Dockerfile").read_bytes()
            ).hexdigest(),
            "compose_sha256": hashlib.sha256(compose_path.read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256(
                (repository / "config/models.yaml").read_bytes()
            ).hexdigest(),
            "harness_sha256": hashlib.sha256(
                (repository / "scripts/run-client-quality-matrix.py").read_bytes()
            ).hexdigest(),
        },
        "client_binaries": {name: path is not None for name, path in clients.items()},
        "real_api_component": component,
        "executor_container_preflight": executor_container,
        "executor_runtime_identity": executor_identity,
        "reasoner_source_identity": reasoner_identity,
        "statuses": statuses,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if statuses["RELEASE_CERTIFIED"] else 2)


if __name__ == "__main__":
    main()
