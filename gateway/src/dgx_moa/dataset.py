from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .security import redact


def split_for(task_id: str) -> str:
    return ("train", "validation", "test")[
        int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % 3
    ]


def build(trace_dir: Path, output: Path, manifest: Path) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(trace_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            trace = json.loads(line)
            if (
                trace.get("final_status") != "completed"
                or trace.get("review_outcome", {}).get("status") != "approved"
            ):
                continue
            task_id = str(trace.get("task_id") or trace["session_id"])
            example = redact(
                {
                    "schema_version": "training-example-v1",
                    "type": "executor_sft",
                    "quality_tier": "Silver",
                    "split": split_for(task_id),
                    "task_id": task_id,
                    "prompt": {
                        "objective": trace["objective"],
                        "verified_state": trace["verified_state"],
                        "recent_observation": trace["tool_observation"],
                    },
                    "chosen": {"action": trace["assistant_tool_call"] or "complete validated task"},
                }
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
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.trace_dir, arguments.output, arguments.manifest), indent=2))


if __name__ == "__main__":
    main()
