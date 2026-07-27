import sqlite3
from pathlib import Path

import pytest
from dgx_moa.database import connect_sqlite


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
