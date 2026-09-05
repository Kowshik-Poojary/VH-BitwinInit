"""Tests for loop leakage detection with upper limit of loops (threshold)."""

from pathlib import Path
import pytest
from leakguard.analyzer import analyze_project
from leakguard.cli import main


def test_loop_leak_closed_later_default(tmp_path: Path):
    source_file = tmp_path / "leak_closed_later.py"
    source_file.write_text(
        "import socket\n"
        "def poll_servers(addresses):\n"
        "    s = None\n"
        "    for host, port in addresses:\n"
        "        s = socket.socket()\n"
        "        s.connect((host, port))\n"
        "    if s:\n"
        "        s.close()\n"
    )
    findings = analyze_project(source_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R002"
    assert findings[0].resource_type == "socket"
    assert findings[0].message == "upper limit of x loops reached hence can be leaky while it may get closed later"
    assert findings[0].details.get("loop_limit_reached") is True
    assert findings[0].details.get("max_loops") == "x"


def test_loop_leak_custom_max_loops(tmp_path: Path):
    source_file = tmp_path / "leak_custom_limit.py"
    source_file.write_text(
        "import socket\n"
        "def run():\n"
        "    for x in range(10):\n"
        "        s = socket.socket()\n"
        "    s.close()\n"
    )
    findings = analyze_project(source_file, max_loops=5)
    assert len(findings) == 1
    assert findings[0].message == "upper limit of 5 loops reached hence can be leaky while it may get closed later"
    assert findings[0].details.get("loop_limit_reached") is True
    assert findings[0].details.get("max_loops") == "5"


def test_loop_leak_max_loops_10(tmp_path: Path):
    source_file = tmp_path / "leak_limit_10.py"
    source_file.write_text(
        "def run():\n"
        "    for i in range(20):\n"
        "        f = open('file.txt')\n"
        "    f.close()\n"
    )
    findings = analyze_project(source_file, max_loops=10)
    assert len(findings) == 1
    assert findings[0].message == "upper limit of 10 loops reached hence can be leaky while it may get closed later"
    assert findings[0].details.get("max_loops") == "10"


def test_loop_safe_closed_inside(tmp_path: Path):
    source_file = tmp_path / "safe_loop.py"
    source_file.write_text(
        "import socket\n"
        "def run():\n"
        "    for x in range(10):\n"
        "        s = socket.socket()\n"
        "        s.close()\n"
    )
    findings = analyze_project(source_file)
    assert len(findings) == 0


def test_loop_safe_with_context_manager(tmp_path: Path):
    source_file = tmp_path / "safe_with.py"
    source_file.write_text(
        "def run(items):\n"
        "    for item in items:\n"
        "        with open(item) as f:\n"
        "            data = f.read()\n"
    )
    findings = analyze_project(source_file)
    assert len(findings) == 0


def test_loop_while_true_leak(tmp_path: Path):
    source_file = tmp_path / "while_leak.py"
    source_file.write_text(
        "def run():\n"
        "    while True:\n"
        "        f = open('log.txt')\n"
    )
    findings = analyze_project(source_file)
    assert len(findings) == 1
    assert findings[0].message == "upper limit of x loops reached hence can be leaky while it may get closed later"


def test_loop_cli_scan_custom_limit(tmp_path: Path, capsys: pytest.CaptureFixture):
    source_file = tmp_path / "cli_test.py"
    source_file.write_text(
        "import socket\n"
        "def run():\n"
        "    for x in range(10):\n"
        "        s = socket.socket()\n"
        "    s.close()\n"
    )
    code = main(["scan", str(source_file), "--max-loops", "3"])
    out = capsys.readouterr().out
    assert code == 1  # blocked on error
    assert "upper limit of 3 loops reached hence can be leaky while it may get closed later" in out
