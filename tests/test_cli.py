import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from leakguard.cli import main


class CliTests(unittest.TestCase):
    def test_leak_returns_failure_and_reports_details(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leak.py"
            path.write_text(
                "def test():\n    f = open('data.txt')\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([str(path)])

        self.assertEqual(result, 1)
        self.assertIn("Resource leak", output.getvalue())
        self.assertIn("Variable: f", output.getvalue())

    def test_safe_file_returns_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.py"
            path.write_text(
                "def test():\n"
                "    with open('data.txt') as f:\n"
                "        return f.read()\n",
                encoding="utf-8",
            )
            result = main([str(path)])

        self.assertEqual(result, 0)

    def test_scan_directory_reports_findings_from_multiple_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.py").write_text(
                "def safe():\n"
                "    with open('data.txt') as f:\n"
                "        return f.read()\n",
                encoding="utf-8",
            )
            (root / "nested").mkdir()
            (root / "nested" / "leak.py").write_text(
                "def leak():\n    f = open('data.txt')\n",
                encoding="utf-8",
            )
            (root / ".venv").mkdir()
            (root / ".venv" / "ignored.py").write_text(
                "f = open('ignored.txt')\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["scan", str(root)])

        report = output.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("Scanning 2 Python file(s)", report)
        self.assertIn("nested", report)
        self.assertIn("1 resource leak(s) found", report)
        self.assertNotIn("ignored.py", report)

    def test_scan_detects_early_return_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "branch.py"
            path.write_text(
                "def read(flag):\n"
                "    f = open('data.txt')\n"
                "    if flag:\n"
                "        return\n"
                "    f.close()\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([str(path)])

        self.assertEqual(result, 1)
        self.assertIn("at least one reachable path", output.getvalue())

    def test_scan_reports_reassigned_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reassigned.py"
            path.write_text(
                "def read():\n"
                "    f = open('first.txt')\n"
                "    f = open('second.txt')\n"
                "    f.close()\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([str(path)])

        report = output.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("Opened: ", report)
        self.assertIn(":2", report)
        self.assertIn("replaced before cleanup", report)

    def test_scan_handles_nested_functions_with_distinct_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.py"
            path.write_text(
                "def outer():\n"
                "    outer_file = open('outer.txt')\n"
                "    def inner():\n"
                "        inner_file = open('inner.txt')\n"
                "        return inner_file\n"
                "    return inner()\n",
                encoding="utf-8",
            )
            result = main([str(path)])

        self.assertEqual(result, 1)

    def test_scan_can_exclude_intentional_fixture_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "def read():\n"
                "    with open('data.txt') as f:\n"
                "        return f.read()\n",
                encoding="utf-8",
            )
            (root / "fixtures").mkdir()
            (root / "fixtures" / "intentional.py").write_text(
                "def leak():\n    f = open('data.txt')\n",
                encoding="utf-8",
            )

            result = main(["scan", str(root), "--exclude", "fixtures"])

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
