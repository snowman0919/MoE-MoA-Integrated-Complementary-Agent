from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def ensure_lifecycle_samples_schema(database: sqlite3.Connection) -> None:
    database.execute(
        "CREATE TABLE IF NOT EXISTS lifecycle_samples ("
        "sample_id INTEGER PRIMARY KEY, role TEXT NOT NULL, kind TEXT NOT NULL, "
        "duration_seconds REAL NOT NULL, memory_before_bytes INTEGER, "
        "memory_after_bytes INTEGER)"
    )


@contextmanager
def connect_sqlite(
    path: str | Path,
    *,
    rows: bool = False,
    secure: bool = False,
) -> Iterator[sqlite3.Connection]:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if secure:
        descriptor = os.open(database_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(database_path, 0o600)
    connection = sqlite3.connect(database_path, timeout=30)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        if rows:
            connection.row_factory = sqlite3.Row
        with connection:
            yield connection
    finally:
        connection.close()
