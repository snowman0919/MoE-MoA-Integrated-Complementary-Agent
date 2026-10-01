#!/usr/bin/env python3
"""Apply or roll back rebuildable request-path indexes and latency telemetry."""

from __future__ import annotations

import argparse
from pathlib import Path

from dgx_moa.state import StateStore
from dgx_moa.usage import UsageStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "rollback"))
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    state = StateStore(arguments.database)
    usage = UsageStore(arguments.database)
    if arguments.action == "rollback":
        state.rollback_pending_indexes()
        usage.rollback_stage_latency()
    usage.close()
    print(f"{arguments.action}: {arguments.database}")


if __name__ == "__main__":
    main()
