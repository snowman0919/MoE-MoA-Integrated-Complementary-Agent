import os
import sqlite3
from pathlib import Path

import pytest
from dgx_moa.api import create_app
from dgx_moa.config import Settings
from dgx_moa.database import connect_sqlite
from fastapi.testclient import TestClient


def test_secure_sqlite_connection_policy(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.db"

    with connect_sqlite(path, rows=True, secure=True) as database:
        database.execute("CREATE TABLE sample (value TEXT)")
        database.execute("INSERT INTO sample VALUES ('ok')")
        row = database.execute("SELECT value FROM sample").fetchone()
        assert row["value"] == "ok"
        assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    assert path.stat().st_mode & 0o777 == 0o600


def test_sqlite_context_closes_connection_and_sidecars(tmp_path: Path) -> None:
    path = tmp_path / "state.db"

    with connect_sqlite(path, secure=True) as database:
        database.execute("CREATE TABLE sample (value TEXT)")
        assert Path(f"{path}-wal").is_file()
        assert Path(f"{path}-shm").is_file()

    assert not Path(f"{path}-wal").exists()
    assert not Path(f"{path}-shm").exists()
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        database.execute("SELECT 1")


def test_gateway_startup_leaves_no_database_descriptors(settings: Settings) -> None:
    database = str(settings.state_db)

    with TestClient(create_app(settings)):
        descriptors = []
        for descriptor in Path("/proc/self/fd").iterdir():
            try:
                descriptors.append(os.readlink(descriptor))
            except FileNotFoundError:
                continue

    assert not [
        descriptor
        for descriptor in descriptors
        if descriptor == database or descriptor.startswith(f"{database}-")
    ]
