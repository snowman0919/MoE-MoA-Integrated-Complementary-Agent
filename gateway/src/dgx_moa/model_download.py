from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import yaml
from huggingface_hub import snapshot_download


def classify_failure(error: Exception) -> str:
    message = str(error).lower()
    if (isinstance(error, OSError) and error.errno == errno.ENOSPC) or "no space" in message:
        return "capacity-blocked"
    if any(marker in message for marker in ("401", "unauthorized", "gated repo", "forbidden")):
        return "authentication-blocked"
    if any(marker in message for marker in ("404", "repository not found", "revision not found")):
        return "repository-unavailable"
    if any(marker in message for marker in ("timeout", "connection", "network")):
        return "network-failure"
    return "download-failed"


def verify_model(path: str | Path, require_quantization: bool = True) -> dict[str, Any]:
    model_path = Path(path)
    errors: list[str] = []
    config_path = model_path / "config.json"
    tokenizer_paths = [model_path / "tokenizer_config.json", model_path / "tokenizer.json"]
    if not config_path.is_file():
        errors.append("config.json missing")
        config: dict[str, Any] = {}
    else:
        config = json.loads(config_path.read_text())
    if not any(path.is_file() for path in tokenizer_paths):
        errors.append("tokenizer configuration missing")
    tokenizer_config = model_path / "tokenizer_config.json"
    tokenizer_data = json.loads(tokenizer_config.read_text()) if tokenizer_config.is_file() else {}
    if (
        not tokenizer_data.get("chat_template")
        and not (model_path / "chat_template.jinja").is_file()
    ):
        errors.append("chat template missing")
    if not config.get("architectures"):
        errors.append("architecture missing")
    if require_quantization and not config.get("quantization_config"):
        errors.append("quantization configuration missing")
    incomplete = list(model_path.rglob("*.incomplete"))
    if incomplete:
        errors.append(f"{len(incomplete)} incomplete files remain")
    index_path = model_path / "model.safetensors.index.json"
    shards: list[str] = []
    if index_path.is_file():
        index = json.loads(index_path.read_text())
        shards = sorted(set(index.get("weight_map", {}).values()))
        for shard in shards:
            shard_path = model_path / shard
            if not shard_path.is_file() or shard_path.stat().st_size == 0:
                errors.append(f"missing or empty shard: {shard}")
    elif not any(model_path.glob("*.safetensors")):
        errors.append("safetensors weights missing")
    revision_path = model_path / ".revision"
    if not revision_path.is_file():
        errors.append("model revision missing")
    return {
        "path": str(model_path),
        "status": "verified" if not errors else "invalid",
        "revision": revision_path.read_text().strip() if revision_path.is_file() else None,
        "architecture": config.get("architectures", []),
        "quantization": config.get("quantization_config", {}).get("quant_method"),
        "shard_count": len(shards) or len(list(model_path.glob("*.safetensors"))),
        "actual_bytes": sum(
            file.stat().st_size for file in model_path.rglob("*") if file.is_file()
        ),
        "errors": errors,
    }


def download_role(role: str, model: dict[str, Any], hf_home: Path) -> dict[str, Any]:
    destination = Path(model["destination"]).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    snapshot_download(
        repo_id=model["repository"],
        revision=model["revision"],
        local_dir=destination,
        cache_dir=hf_home / "hub",
        token=os.getenv("HF_TOKEN"),
    )
    (destination / ".revision").write_text(model["revision"] + "\n")
    result = verify_model(destination, require_quantization=bool(model.get("quantization")))
    result.update(
        {
            "role": role,
            "repository": model["repository"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "free_bytes": shutil.disk_usage(destination).free,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("download", "verify"))
    parser.add_argument("--config", type=Path, default=Path("config/models.yaml"))
    parser.add_argument("--role", action="append")
    arguments = parser.parse_args()
    raw = yaml.safe_load(arguments.config.read_text())
    roles = arguments.role or list(raw["models"])
    hf_home = Path(raw.get("hf_home", "~/models/.hf-cache")).expanduser()
    results = []
    for role in roles:
        model = raw["models"][role]
        if arguments.command == "download":
            try:
                results.append(download_role(role, model, hf_home))
            except Exception as error:
                results.append(
                    {
                        "role": role,
                        "repository": model["repository"],
                        "revision": model["revision"],
                        "status": classify_failure(error),
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        else:
            results.append(
                verify_model(
                    Path(model["destination"]).expanduser(), bool(model.get("quantization"))
                )
            )
    print(json.dumps(results, indent=2))
    if any(result["status"] != "verified" for result in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
