"""Service module with aliased imports."""

import sqlite3 as db


def connect_with_alias(path: str):
    conn = db.connect(path)
    conn.close()


def leaky_alias(path: str):
    conn = db.connect(path)
