from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml
from huggingface_hub import HfApi, hf_hub_download


class FileMetadata(TypedDict):
    name: str
    size: int


def classify(repository: str) -> str:
    owner = repository.split("/", 1)[0]
    if owner in {"Qwen", "CohereLabs"}:
        return "official"
    if owner == "nvidia":
        return "vendor-provided"
    return "community-maintained"


def _json_file(repository: str, revision: str, filename: str) -> dict[str, Any]:
    try:
        path = hf_hub_download(repository, filename, revision=revision)
    except Exception:
        return {}
    return cast(dict[str, Any], json.loads(Path(path).read_text()))


def inspect_repository(repository: str, revision: str = "main") -> dict[str, Any]:
    info = HfApi().model_info(repository, revision=revision, files_metadata=True)
    pinned = info.sha or revision
    config = _json_file(repository, pinned, "config.json")
    tokenizer = _json_file(repository, pinned, "tokenizer_config.json")
    siblings = info.siblings or []
    files: list[FileMetadata] = [
        {"name": str(sibling.rfilename), "size": int(sibling.size or 0)} for sibling in siblings
    ]
    safetensors = [file for file in files if file["name"].endswith(".safetensors")]
    card_data = cast(dict[str, Any], info.card_data or {})
    safetensors_info = cast(dict[str, Any], info.safetensors or {})
    return {
        "repository": info.id,
        "owner": info.id.split("/", 1)[0],
        "exists": True,
        "revision": pinned,
        "license": card_data.get("license", "unknown"),
        "gated": bool(info.gated),
        "private": bool(info.private),
        "classification": classify(info.id),
        "architecture": config.get("architectures", []),
        "model_type": config.get("model_type"),
        "quantization": config.get("quantization_config", {}).get("quant_method"),
        "quantization_config": config.get("quantization_config", {}),
        "total_parameters": safetensors_info.get("total"),
        "active_parameters": None,
        "shard_count": len(safetensors),
        "download_size": sum(file["size"] for file in files),
        "chat_template": bool(tokenizer.get("chat_template"))
        or any(file["name"] == "chat_template.jinja" for file in files),
        "trust_remote_code": bool(config.get("auto_map")),
        "tool_call_parser": "runtime-test-required",
        "reasoning_parser": "runtime-test-required",
        "minimum_vllm_version": "runtime-test-required",
        "files": files,
    }


def inspect_many(repositories: list[str], output: Path | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for repository in repositories:
        try:
            results.append(inspect_repository(repository))
        except Exception as error:
            results.append(
                {
                    "repository": repository,
                    "exists": False,
                    "classification": classify(repository),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2))
    return results


def cached_bytes(repository: str, hf_home: Path) -> int:
    path = hf_home / "hub" / f"models--{repository.replace('/', '--')}"
    return (
        sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
        if path.exists()
        else 0
    )


def estimate(
    config_path: Path,
    minimum_free: int = 80_000_000_000,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    raw = yaml.safe_load(config_path.read_text())
    hf_home = Path(raw.get("hf_home", Path.home() / "models/.hf-cache")).expanduser()
    rows: list[dict[str, Any]] = []
    selected = roles or list(raw["models"])
    for role in selected:
        model = raw["models"][role]
        metadata = inspect_repository(model["repository"], model["revision"])
        total = metadata["download_size"]
        cached = min(total, cached_bytes(model["repository"], hf_home))
        destination = Path(model["destination"]).expanduser()
        existing = (
            sum(file.stat().st_size for file in destination.rglob("*") if file.is_file())
            if destination.exists()
            else 0
        )
        rows.append(
            {
                "role": role,
                "repository": model["repository"],
                "revision": metadata["revision"],
                "download_size": total,
                "existing_cached_size": cached,
                "new_required_bytes": max(0, total - min(total, existing)),
                "destination": str(destination),
                "classification": model["classification"],
            }
        )
    final = sum(row["new_required_bytes"] for row in rows)
    temporary = 0
    docker_allowance = 0
    safety_margin = 0
    required = final
    free = shutil.disk_usage(config_path).free
    result = {
        "rows": rows,
        "final_model_bytes": final,
        "temporary_bytes": temporary,
        "docker_allowance_bytes": docker_allowance,
        "safety_margin_bytes": safety_margin,
        "required_bytes": required,
        "free_bytes": free,
        "remaining_bytes": free - required,
        "minimum_free_bytes": minimum_free,
        "safe": free - required >= minimum_free,
    }
    return result


def print_estimate(result: dict[str, Any]) -> None:
    print(
        "role\trepository\trevision\tdownload size\texisting cached size\t"
        "new required bytes\tdestination\tclassification"
    )
    for row in result["rows"]:
        print("\t".join(str(row[key]) for key in row))
    for key in (
        "final_model_bytes",
        "temporary_bytes",
        "docker_allowance_bytes",
        "safety_margin_bytes",
        "required_bytes",
        "free_bytes",
        "remaining_bytes",
        "minimum_free_bytes",
        "safe",
    ):
        print(f"{key}={result[key]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("repositories", nargs="+")
    inspect_parser.add_argument("--output", type=Path)
    estimate_parser = subparsers.add_parser("estimate")
    estimate_parser.add_argument("--config", type=Path, default=Path("config/models.yaml"))
    estimate_parser.add_argument("--role", action="append")
    arguments = parser.parse_args()
    if arguments.command == "inspect":
        print(json.dumps(inspect_many(arguments.repositories, arguments.output), indent=2))
    else:
        result = estimate(arguments.config, roles=arguments.role)
        print_estimate(result)
        raise SystemExit(0 if result["safe"] else 2)


if __name__ == "__main__":
    main()
