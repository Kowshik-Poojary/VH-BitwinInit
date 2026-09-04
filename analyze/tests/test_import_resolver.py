"""Tests for import resolution."""

from __future__ import annotations

import textwrap
from pathlib import Path

from leakguard.analyzer import analyze_file
from leakguard.import_resolver import ImportResolver


def test_resolve_import_alias(tmp_path):
    path = tmp_path / "alias.py"
    path.write_text(
        textwrap.dedent(
            """
            import sqlite3 as db

            def connect():
                conn = db.connect("x")
            """
        ),
        encoding="utf-8",
    )
    analysis, _ = analyze_file(path, tmp_path)
    assert analysis is not None
    resolver = ImportResolver(analysis)
    assert resolver.resolve_attribute_call("db", "connect") == "sqlite3.connect"


def test_resolve_from_import(tmp_path):
    path = tmp_path / "from_import.py"
    path.write_text(
        textwrap.dedent(
            """
            from sqlite3 import connect

            def connect_db():
                conn = connect("x")
            """
        ),
        encoding="utf-8",
    )
    analysis, _ = analyze_file(path, tmp_path)
    assert analysis is not None
    resolver = ImportResolver(analysis)
    assert resolver.resolve_name("connect") is None
    assert "connect" in resolver._from_import_map
