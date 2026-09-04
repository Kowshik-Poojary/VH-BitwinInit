"""Tests for LeakGuard AST/project analysis foundation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from leakguard.analyzer import analyze_file, analyze_project, analyze_project_structure
from leakguard.models import (
    AnalysisErrorType,
    ControlFlowKind,
    OperationKind,
)
from leakguard.scanner import discover_python_files


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _analyze_source(tmp_path: Path, name: str, content: str):
    path = _write(tmp_path, name, content)
    analysis, errors = analyze_file(path, tmp_path)
    assert not errors, errors
    assert analysis is not None
    return analysis


class TestSimpleOpenClose:
    def test_open_close(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "simple.py",
            """
            def load():
                f = open("x")
                f.close()
            """,
        )
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        closes = [o for o in fa.resource_operations if o.kind == OperationKind.CLOSE]
        assert len(acquires) == 1
        assert acquires[0].resource_type == "file"
        assert acquires[0].target == "f"
        assert len(closes) == 1
        assert closes[0].target == "f"
        assert closes[0].method == "close"


class TestObviousLeak:
    def test_acquire_without_close(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "leak.py",
            """
            def load():
                f = open("x")
            """,
        )
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        closes = [o for o in fa.resource_operations if o.kind == OperationKind.CLOSE]
        assert len(acquires) == 1
        assert len(closes) == 0


class TestEarlyReturn:
    def test_early_return_records_control_flow(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "early_return.py",
            """
            def load(condition):
                f = open("x")
                if condition:
                    return
                f.close()
            """,
        )
        kinds = [cf.kind for cf in fa.control_flow]
        assert ControlFlowKind.IF in kinds
        assert ControlFlowKind.RETURN in kinds
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        closes = [o for o in fa.resource_operations if o.kind == OperationKind.CLOSE]
        assert len(acquires) == 1
        assert len(closes) == 1


class TestTryFinally:
    def test_try_finally(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "try_finally.py",
            """
            def load():
                f = open("x")
                try:
                    work(f)
                finally:
                    f.close()
            """,
        )
        kinds = [cf.kind for cf in fa.control_flow]
        assert ControlFlowKind.TRY in kinds
        assert ControlFlowKind.FINALLY in kinds
        closes = [o for o in fa.resource_operations if o.kind == OperationKind.CLOSE]
        assert len(closes) == 1


class TestWithStatement:
    def test_with_context_manager(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "with_stmt.py",
            """
            def load():
                with open("x") as f:
                    work(f)
            """,
        )
        assert len(fa.context_managers) == 1
        cm = fa.context_managers[0]
        assert cm.target == "f"
        assert cm.resource_type == "file"
        assert cm.registry_key == "open"
        assert not cm.is_async


class TestAlias:
    def test_alias_assignment(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "alias.py",
            """
            def load():
                f = open("x")
                g = f
                g.close()
            """,
        )
        assigns = fa.assignments
        assert any(a.targets == ["f"] for a in assigns)
        assert any(a.targets == ["g"] and a.value_expression == "f" for a in assigns)
        closes = [o for o in fa.resource_operations if o.kind == OperationKind.CLOSE]
        assert any(c.target == "g" for c in closes)


class TestReturnEscape:
    def test_return_resource(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "return_escape.py",
            """
            def load():
                f = open("x")
                return f
            """,
        )
        assert len(fa.returns) == 1
        assert fa.returns[0].value_expression == "f"
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        assert len(acquires) == 1


class TestSqlite:
    def test_sqlite_connect(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "sqlite.py",
            """
            import sqlite3

            def connect_db():
                conn = sqlite3.connect("db")
                conn.close()
            """,
        )
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        assert len(acquires) == 1
        assert acquires[0].resource_type == "database"
        assert acquires[0].registry_key == "sqlite3.connect"


class TestSocket:
    def test_socket(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "socket.py",
            """
            import socket

            def make_socket():
                sock = socket.socket()
                sock.close()
            """,
        )
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        assert len(acquires) == 1
        assert acquires[0].resource_type == "socket"


class TestNestedFolders:
    def test_nested_project(self, tmp_path):
        _write(tmp_path, "app/a.py", "def a(): f = open('x')")
        _write(tmp_path, "services/b.py", "def b(): f = open('y')")
        _write(tmp_path, "__pycache__/cached.py", "def c(): pass")

        project = analyze_project_structure(tmp_path)
        assert project.statistics.files_discovered == 2
        assert project.statistics.files_analyzed == 2
        modules = {fa.module_name for fa in project.file_analyses}
        assert "app.a" in modules or "app" in modules
        assert "services.b" in modules or "services" in modules


class TestSyntaxError:
    def test_syntax_error_does_not_stop_scan(self, tmp_path):
        _write(tmp_path, "good.py", "def ok(): pass")
        _write(tmp_path, "bad.py", "def broken(:\n    pass")

        project = analyze_project_structure(tmp_path)
        assert project.statistics.files_discovered == 2
        assert project.statistics.files_analyzed == 1
        assert project.statistics.parse_errors == 1
        assert any(e.error_type == AnalysisErrorType.PARSE_ERROR for e in project.errors)


class TestImportAlias:
    def test_import_alias(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "alias_import.py",
            """
            import sqlite3 as db

            def connect_db():
                conn = db.connect("x")
                conn.close()
            """,
        )
        imports = fa.imports
        assert any(i.module == "sqlite3" and i.alias == "db" for i in imports)
        calls = fa.calls
        assert any(c.base == "db" and c.attribute == "connect" for c in calls)


class TestFromImport:
    def test_from_import(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "from_import.py",
            """
            from sqlite3 import connect

            def connect_db():
                conn = connect("x")
                conn.close()
            """,
        )
        imports = fa.imports
        assert any(
            i.is_from_import and i.imported_name == "connect" and i.module == "sqlite3"
            for i in imports
        )
        calls = fa.calls
        assert any(c.function_name == "connect" for c in calls)


class TestReassignment:
    def test_reassignment(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "reassign.py",
            """
            def load():
                f = open("a")
                f = open("b")
                f.close()
            """,
        )
        acquires = [o for o in fa.resource_operations if o.kind == OperationKind.ACQUIRE]
        assert len(acquires) == 2
        assigns = [a for a in fa.assignments if "open" in a.value_expression]
        assert len(assigns) == 2


class TestFunctionCallPass:
    def test_resource_passed_to_function(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "pass.py",
            """
            def load():
                f = open("x")
                process(f)
            """,
        )
        passes = fa.function_call_passes
        assert any(p.callee_name == "process" and "f" in p.argument_expressions for p in passes)


class TestClassMethods:
    def test_class_method_context(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "class_method.py",
            """
            import sqlite3

            class Database:
                def connect(self):
                    self.conn = sqlite3.connect("db")

                def disconnect(self):
                    self.conn.close()
            """,
        )
        classes = fa.classes
        assert len(classes) == 1
        assert classes[0].name == "Database"
        methods = fa.functions
        assert any(m.name == "connect" and m.is_method for m in methods)


class TestLargeFile:
    def test_large_synthetic_file(self, tmp_path):
        lines = ["def big():"]
        lines.append("    f = open('x')")
        lines.extend(f"    x_{i} = {i}" for i in range(5000))
        lines.append("    f.close()")
        content = "\n".join(lines)
        path = _write(tmp_path, "large.py", content)

        analysis, errors = analyze_file(path, tmp_path)
        assert not errors
        assert analysis is not None
        assert len(analysis.assignments) >= 5000


class TestMaxFileSize:
    def test_size_limit_produces_error(self, tmp_path):
        content = "def ok(): pass\n" * 100
        path = _write(tmp_path, "big.py", content)
        analysis, errors = analyze_file(path, tmp_path, max_file_size=10)
        assert analysis is None
        assert len(errors) == 1
        assert errors[0].error_type == AnalysisErrorType.SIZE_LIMIT


class TestScannerExclusions:
    def test_default_exclusions(self, tmp_path):
        _write(tmp_path, "main.py", "pass")
        _write(tmp_path, ".venv/lib.py", "pass")
        _write(tmp_path, "__pycache__/cache.py", "pass")

        files = discover_python_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "main.py"


class TestPublicAPI:
    def test_analyze_project_returns_findings_for_errors(self, tmp_path):
        _write(tmp_path, "bad.py", "def x(:")
        findings = analyze_project(tmp_path)
        assert len(findings) == 1
        assert findings[0].status.value == "ERROR"


class TestUnreadableFile:
    def test_unreadable_invalid_encoding(self, tmp_path):
        # File with explicit utf-8 cookie declaration but invalid non-utf8 bytes
        bad_file = tmp_path / "bad_encoding.py"
        bad_file.write_bytes(b"# -*- coding: utf-8 -*-\n\xff\xfe\xfd\n")
        good_file = _write(tmp_path, "good.py", "def ok(): pass")

        project = analyze_project_structure(tmp_path)
        assert project.statistics.files_discovered == 2
        assert project.statistics.files_analyzed == 1
        assert project.statistics.read_errors == 1
        assert any(e.error_type == AnalysisErrorType.READ_ERROR for e in project.errors)


class TestAsyncWith:
    def test_async_with(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "async_with.py",
            """
            async def load():
                async with open("x") as f:
                    await work(f)
            """,
        )
        assert len(fa.context_managers) == 1
        assert fa.context_managers[0].is_async


class TestControlFlowBreakContinue:
    def test_break_continue(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "break_continue.py",
            """
            def load(items):
                for item in items:
                    if item == 0:
                        break
                    if item < 0:
                        continue
            """,
        )
        kinds = [cf.kind for cf in fa.control_flow]
        assert ControlFlowKind.FOR in kinds
        assert ControlFlowKind.BREAK in kinds
        assert ControlFlowKind.CONTINUE in kinds


class TestRaise:
    def test_raise_recorded(self, tmp_path):
        fa = _analyze_source(
            tmp_path,
            "raise.py",
            """
            def load():
                f = open("x")
                raise ValueError("fail")
            """,
        )
        assert len(fa.raises) == 1
        kinds = [cf.kind for cf in fa.control_flow]
        assert ControlFlowKind.RAISE in kinds
