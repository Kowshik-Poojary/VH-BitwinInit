"""Unit tests validating the 10 seeded demo cases in samples/leaky_demo/."""

from pathlib import Path
import pytest
from leakguard.analyzer import analyze_project


@pytest.fixture
def samples_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "samples" / "leaky_demo"


def test_01_open_no_close(samples_dir: Path):
    path = samples_dir / "01_open_no_close.py"
    findings = analyze_project(path)
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R001"
    assert findings[0].resource_type == "file"
    assert findings[0].details["confidence"] == "HIGH"
    assert "no close() found" in findings[0].message


def test_02_open_early_return(samples_dir: Path):
    path = samples_dir / "02_open_early_return.py"
    findings = analyze_project(path)
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R001"
    assert findings[0].resource_type == "file"
    assert findings[0].details["confidence"] == "MEDIUM"
    assert "return path" in findings[0].message


def test_03_open_try_except_leak(samples_dir: Path):
    path = samples_dir / "03_open_try_except_leak.py"
    findings = analyze_project(path)
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R001"
    assert findings[0].resource_type == "file"
    assert "no close() found" in findings[0].message


def test_04_open_try_finally_safe(samples_dir: Path):
    path = samples_dir / "04_open_try_finally_safe.py"
    findings = analyze_project(path)
    assert len(findings) == 0, f"Expected 0 findings for try-finally, got: {findings}"


def test_05_open_with_safe(samples_dir: Path):
    path = samples_dir / "05_open_with_safe.py"
    findings = analyze_project(path)
    assert len(findings) == 0, f"Expected 0 findings for 'with', got: {findings}"


def test_06_sqlite_factory_escaped(samples_dir: Path):
    path = samples_dir / "06_sqlite_factory_escaped.py"
    findings = analyze_project(path)
    assert len(findings) == 0, f"Expected 0 findings for returned factory resource, got: {findings}"


def test_07_socket_shutdown_close_safe(samples_dir: Path):
    path = samples_dir / "07_socket_shutdown_close_safe.py"
    findings = analyze_project(path)
    assert len(findings) == 0, f"Expected 0 findings for shutdown+close socket, got: {findings}"


def test_08_socket_loop_reassign_leak(samples_dir: Path):
    path = samples_dir / "08_socket_loop_reassign_leak.py"
    findings = analyze_project(path)
    assert len(findings) >= 1
    assert any(f.rule_id == "LKG-R002" and f.resource_type == "socket" for f in findings)


def test_09_tempfile_no_close(samples_dir: Path):
    path = samples_dir / "09_tempfile_no_close.py"
    findings = analyze_project(path)
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R004"
    assert findings[0].resource_type == "tempfile"


def test_10_trick_cases(samples_dir: Path):
    path = samples_dir / "10_trick_cases.py"
    findings = analyze_project(path)
    # The variable named open_file must NOT be flagged.
    # The aliased import `conn = db.connect(...)` MUST be flagged.
    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R003"
    assert findings[0].resource_type == "database"
    assert findings[0].details["variable"] == "conn"


# --- Inter-procedural (cross-file) seeded cases ---

@pytest.fixture
def inter_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "samples" / "leaky_demo" / "inter"


def test_inter_cross_file_helper_no_findings(inter_dir: Path):
    """
    inter/main.py opens a file and passes it to close_file() defined in inter/closer.py.
    The inter-procedural analysis must recognize that close_file() closes its first parameter,
    and emit zero findings for the entire inter/ folder.
    """
    findings = analyze_project(inter_dir)
    assert findings == [], (
        f"Expected 0 findings for cross-file helper close pattern, got: {findings}"
    )


def test_inter_whole_leaky_demo_count(samples_dir: Path):
    """
    Scanning the full leaky_demo folder (including the inter/ subfolder) must not
    produce spurious findings from the safely-closed inter/ case.
    The inter/ folder contributes 0 findings; the rest contribute the expected count.
    """
    findings = analyze_project(samples_dir)
    inter_findings = [
        f for f in findings
        if "inter" in f.location.file.replace("\\", "/")
    ]
    assert inter_findings == [], (
        f"Inter-procedural sample should have 0 findings, got: {inter_findings}"
    )
