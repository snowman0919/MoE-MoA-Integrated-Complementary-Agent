from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


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
