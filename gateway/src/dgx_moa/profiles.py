from __future__ import annotations

import json
import sqlite3
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from typing import Literal, cast

from .state import now

Profile = Literal["resident", "judge", "stopped"]


class ProfileManager:
    def __init__(self, run_dir: str | Path, project_root: str | Path = "."):
        self.run_dir = Path(run_dir)
        self.project_root = Path(project_root).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.run_dir / "profile.json"

    def current(self) -> dict[str, str]:
        if not self.state_file.exists():
            return {"active_profile": "stopped", "status": "stopped", "updated_at": now()}
        state = cast(dict[str, str], json.loads(self.state_file.read_text()))
        state.setdefault(
            "status", "ready" if state.get("active_profile") != "stopped" else "stopped"
        )
        return state

    def _write(self, state: dict[str, str]) -> dict[str, str]:
        state["updated_at"] = now()
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(self.state_file)
        return state

    def record(self, profile: Profile) -> dict[str, str]:
        return self._write(
            {"active_profile": profile, "status": "stopped" if profile == "stopped" else "ready"}
        )

    def transition(self, target: Literal["resident", "judge"]) -> dict[str, str]:
        current = self.current()["active_profile"]
        return self._write(
            {
                "active_profile": current,
                "status": "transitioning",
                "from": current,
                "to": target,
            }
        )

    def failed(self, target: str, error: str) -> dict[str, str]:
        state = self.current()
        state.update({"status": "degraded", "to": target, "error": error[:500]})
        return self._write(state)

    @staticmethod
    def checkpoint(database_path: str | Path) -> None:
        with sqlite3.connect(database_path) as database:
            database.execute("PRAGMA wal_checkpoint(FULL)")

    def switch(self, profile: Literal["resident", "judge", "restore"]) -> dict[str, str]:
        current = self.current()["active_profile"]
        if current == profile or (profile == "restore" and current == "resident"):
            return self.current()
        command = self.project_root / "scripts" / "switch-profile.sh"
        subprocess.run([str(command), profile], cwd=self.project_root, check=True)
        return self.current()


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "command", choices=("status", "transition", "ready", "failed", "checkpoint")
    )
    parser.add_argument("value", nargs="?")
    parser.add_argument("--run-dir", default="data/run")
    parser.add_argument("--state-db", default="data/state/gateway.db")
    arguments = parser.parse_args()
    manager = ProfileManager(arguments.run_dir)
    if arguments.command == "status":
        result = manager.current()
    elif arguments.command == "transition":
        result = manager.transition(cast(Literal["resident", "judge"], arguments.value))
    elif arguments.command == "ready":
        result = manager.record(cast(Profile, arguments.value))
    elif arguments.command == "failed":
        result = manager.failed(arguments.value or "unknown", "profile startup failed")
    else:
        manager.checkpoint(arguments.state_db)
        result = manager.current()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
