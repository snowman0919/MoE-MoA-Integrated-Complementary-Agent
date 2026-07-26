from pathlib import Path

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
