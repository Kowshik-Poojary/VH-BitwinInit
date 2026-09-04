"""Case 10: Trick cases distinguishing AST structure from naive pattern matching."""

import sqlite3 as db


def false_alarm_variable_name() -> str:
    # Looks like a leak to naive text/regex scanners, but is just a string variable
    open_file = "not_a_handle.txt"
    return open_file


def aliased_import_leak(db_file: str) -> None:
    # Invisible to naive tools that only search for 'sqlite3.connect', but detected by AST + ImportResolver
    conn = db.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    # Missing conn.close()!
