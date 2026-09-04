from pathlib import Path

from leakguard.analyzer import analyze_project_structure
from leakguard.analyzer import analyze_project
from leakguard.cfg import build_cfg
from leakguard.lifecycle import (
    ResourceState,
    analyze_function,
    aggregate_resource_results,
    resource_confidence,
)


def test_simple_close(tmp_path: Path):
    source = """
def test():
    f = open("a.txt")
    f.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]

    results = analyze_function(function_cfg)

    assert len(results) >= 1
    assert all(
        result.state == ResourceState.CLOSED
        for result in results
    )
    

def test_simple_leak(tmp_path: Path):
    source = """
def test():
    f = open("a.txt")
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]

    results = analyze_function(function_cfg)

    assert len(results) >= 1
    assert any(
        result.state == ResourceState.OPEN
        for result in results
    )
    
def test_return_without_close_is_a_leak(tmp_path: Path):
    source = """
def example():
    f = open("a.txt")
    return
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]

    results = analyze_function(function_cfg)

    assert len(results) >= 1
    assert any(
        result.state == ResourceState.OPEN
        for result in results
    )


def test_conditional_close_reports_both_paths(tmp_path: Path):
    source = """
def example(condition):
    f = open("a.txt")
    if condition:
        return
    f.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    states = {result.state for result in results}

    assert ResourceState.OPEN in states
    assert ResourceState.CLOSED in states
    assert aggregate_resource_results(results) == ResourceState.LEAKED
    assert resource_confidence(results) == "MEDIUM"


def test_analyze_function_checks_every_resource(tmp_path: Path):
    source = """
def example():
    safe = open("safe.txt")
    safe.close()
    leaked = open("leaked.txt")
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 2
    assert {result.state for result in results} == {
        ResourceState.CLOSED,
        ResourceState.OPEN,
    }


def test_context_manager_closes_resource(tmp_path: Path):
    source = """
def example():
    with open("a.txt") as file:
        return file.read()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 1
    assert results[0].state == ResourceState.CLOSED


def test_finally_closes_resource(tmp_path: Path):
    source = """
def example():
    file = open("a.txt")
    try:
        work(file)
    finally:
        file.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) >= 1
    assert all(result.state == ResourceState.CLOSED for result in results)


def test_alias_close_is_safe(tmp_path: Path):
    source = """
def example():
    file = open("a.txt")
    alias = file
    alias.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 1
    assert results[0].state == ResourceState.CLOSED


def test_reassignment_keeps_resource_identities_separate(tmp_path: Path):
    source = """
def example():
    file = open("first.txt")
    file = open("second.txt")
    file.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 2
    assert [result.state for result in results] == [
        ResourceState.OPEN,
        ResourceState.CLOSED,
    ]


def test_returned_resource_is_escaped(tmp_path: Path):
    source = """
def example():
    file = open("a.txt")
    return file
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 1
    assert results[0].state == ResourceState.ESCAPED


def test_passed_resource_is_unknown(tmp_path: Path):
    source = """
def example():
    file = open("a.txt")
    process(file)
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) == 1
    assert results[0].state == ResourceState.UNKNOWN


def test_project_analysis_returns_leak_finding(tmp_path: Path):
    source = """
def safe():
    file = open("safe.txt")
    file.close()

def leaky():
    file = open("leaked.txt")
"""
    (tmp_path / "sample.py").write_text(source)

    findings = analyze_project(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "LKG-R001"
    assert findings[0].status.value == "DEFINITE_LEAK"
    assert findings[0].resource_type == "file"


def test_raise_before_close_is_a_leak(tmp_path: Path):
    source = """
def example():
    file = open("a.txt")
    raise ValueError("failure")
    file.close()
"""

    file = tmp_path / "sample.py"
    file.write_text(source)

    project = analyze_project_structure(tmp_path)
    cfg_project = build_cfg(project)

    function_cfg = cfg_project.files[0].functions[0]
    results = analyze_function(function_cfg)

    assert len(results) >= 1
    assert any(result.state == ResourceState.OPEN for result in results)