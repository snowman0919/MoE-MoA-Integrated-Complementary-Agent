from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .security import redact

DATASET_TYPES = {
    "executor_sft",
    "executor_recovery_sft",
    "executor_preference_pairs",
    "planner_sft",
    "reviewer_preference_pairs",
    "failure_classification",
}
DEFAULT_TIERS = {"Gold", "Silver", "Bronze"}


def split_for(task_id: str) -> str:
    return ("train", "validation", "test")[
        int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % 3
    ]


def quality_tier(trace: dict[str, Any]) -> str:
    if trace.get("human_correction"):
        return "Gold"
    if (
        trace.get("final_status") == "completed"
        and trace.get("review_outcome", {}).get("status") == "approved"
    ):
        return "Silver"
    if trace.get("final_status") == "completed":
        return "Bronze"
    if trace.get("failure_classification"):
        return "Negative"
    return "Unknown"


def bounded(value: Any, maximum_characters: int) -> Any:
    if isinstance(value, str):
        return value[:maximum_characters]
    if isinstance(value, list):
        return [bounded(item, maximum_characters) for item in value]
    if isinstance(value, dict):
        return {key: bounded(item, maximum_characters) for key, item in value.items()}
    return value


def build(
    trace_dir: Path,
    output: Path,
    manifest: Path,
    dataset_type: str = "executor_sft",
    tiers: set[str] | None = None,
    maximum_characters: int = 16_384,
) -> dict[str, Any]:
    if dataset_type not in DATASET_TYPES:
        raise ValueError("unsupported dataset type")
    if maximum_characters < 1:
        raise ValueError("maximum characters must be positive")
    allowed_tiers = tiers or DEFAULT_TIERS
    examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(trace_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            trace = json.loads(line)
            tier = quality_tier(trace)
            if tier not in allowed_tiers:
                continue
            task_id = str(trace.get("task_id") or trace["session_id"])
            example = bounded(
                redact(
                    {
                        "schema_version": "training-example-v1",
                        "type": dataset_type,
                        "quality_tier": tier,
                        "split": split_for(task_id),
                        "task_id": task_id,
                        "prompt": {
                            "objective": trace["objective"],
                            "verified_state": trace["verified_state"],
                            "recent_observation": trace["tool_observation"],
                        },
                        "chosen": {
                            "action": trace["assistant_tool_call"] or "complete validated task"
                        },
                    }
                ),
                maximum_characters,
            )
            fingerprint = json.dumps(example, sort_keys=True)
            if fingerprint not in seen:
                seen.add(fingerprint)
                examples.append(example)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(item, sort_keys=True) for item in examples) + "\n")
    content_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    report = {
        "schema_version": "dataset-manifest-v1",
        "count": len(examples),
        "sha256": content_hash,
        "dataset_type": dataset_type,
        "quality_tiers": {
            tier: sum(item["quality_tier"] == tier for item in examples)
            for tier in sorted(allowed_tiers)
        },
        "splits": {
            split: sum(item["split"] == split for item in examples)
            for split in ("train", "validation", "test")
        },
        "maximum_characters": maximum_characters,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dataset-type", choices=sorted(DATASET_TYPES), default="executor_sft")
    parser.add_argument("--tiers", default=",".join(sorted(DEFAULT_TIERS)))
    parser.add_argument("--maximum-characters", type=int, default=16_384)
    arguments = parser.parse_args()
    print(
        json.dumps(
            build(
                arguments.trace_dir,
                arguments.output,
                arguments.manifest,
                arguments.dataset_type,
                set(arguments.tiers.split(",")),
                arguments.maximum_characters,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
