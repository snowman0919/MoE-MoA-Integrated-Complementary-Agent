from pathlib import Path

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


def test_gateway_lifespan_keeps_wal_sidecars_resident(settings: Settings) -> None:
    app = create_app(settings)
    wal = Path(f"{settings.state_db}-wal")
    shm = Path(f"{settings.state_db}-shm")

    with TestClient(app):
        assert wal.is_file()
        assert shm.is_file()
        for _ in range(100):
            with connect_sqlite(settings.state_db, secure=True) as database:
                database.execute("SELECT 1").fetchone()
            assert wal.is_file()
            assert shm.is_file()
