from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .improvement import compare

STATUSES = {"candidate", "testing", "canary", "approved", "rejected", "retired"}
REQUIRED = {
    "adapter_id",
    "status",
    "base_model_repository",
    "base_model_revision",
    "dataset_revision",
    "dataset_hash",
    "training_backend",
    "training_config_hash",
    "created_at",
    "benchmark",
}


def register(metadata_path: Path, root: Path) -> Path:
    metadata: dict[str, Any] = json.loads(metadata_path.read_text())
    if REQUIRED - metadata.keys() or metadata.get("status") not in STATUSES:
        raise ValueError("invalid adapter metadata")
    if metadata["status"] == "approved":
        raise ValueError("adapter promotion requires explicit human approval")
    adapter_id = str(metadata["adapter_id"])
    role = adapter_id.split("-", 1)[0]
    destination = root / role / f"{adapter_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return destination


def evaluate(metadata_path: Path, baseline: Path, candidate: Path, output: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("status") not in {"candidate", "testing", "canary"}:
        raise ValueError("adapter is not eligible for evaluation")
    result = compare(baseline, candidate, output)
    result["adapter_id"] = metadata["adapter_id"]
    result["automatic_promotion"] = False
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--root", type=Path, default=Path.home() / "models/adapters")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.baseline or arguments.candidate or arguments.output:
        if not all((arguments.baseline, arguments.candidate, arguments.output)):
            raise SystemExit("--baseline, --candidate, and --output are required together")
        print(
            json.dumps(
                evaluate(
                    arguments.metadata, arguments.baseline, arguments.candidate, arguments.output
                ),
                indent=2,
            )
        )
    else:
        print(register(arguments.metadata, arguments.root))


if __name__ == "__main__":
    main()
