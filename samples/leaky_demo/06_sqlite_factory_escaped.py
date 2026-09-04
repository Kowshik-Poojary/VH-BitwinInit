"""Case 6 (SAFE / ESCAPED): sqlite3.connect() returned from factory to caller."""

import sqlite3


def connection_factory(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    return conn
