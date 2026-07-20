from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .config import load_settings
from .lifecycle import LifecycleStore


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_disable_lifecycle(config_path: Path) -> None:
    path = config_path.resolve(strict=True)
    raw: Any = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    gateway = raw.setdefault("gateway", {})
    if not isinstance(gateway, dict):
        raise ValueError("gateway configuration must be a mapping")
    gateway["lifecycle_mode"] = "disabled"
    gateway["lifecycle_unit_map"] = {}

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as output:
            yaml.safe_dump(raw, output, sort_keys=False)
            output.flush()
            os.fsync(output.fileno())
        validated = load_settings(temporary)
        if validated.lifecycle_mode != "disabled" or validated.lifecycle_unit_map:
            raise ValueError("environment overrides prevent disabled lifecycle rollback")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def rollback(config_path: Path) -> None:
    atomic_disable_lifecycle(config_path)
    settings = load_settings(config_path)
    store = LifecycleStore(settings.state_db, settings.models)
    store.reset_automation()


def main() -> None:
    parser = argparse.ArgumentParser(prog="dgx-moa-lifecycle")
    subcommands = parser.add_subparsers(dest="command", required=True)
    rollback_parser = subcommands.add_parser("rollback")
    rollback_parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "rollback":
        rollback(arguments.config)
        print(json.dumps({"lifecycle_mode": "disabled", "circuit_reset": True}))


if __name__ == "__main__":
    main()
