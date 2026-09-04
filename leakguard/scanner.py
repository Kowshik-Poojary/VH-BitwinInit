"""Discover Python files and aggregate LeakGuard findings."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .detector import Finding, detect, detect_function
from .parser import parse_source
from .rules import DEFAULT_RULES, ResourceRule


SKIPPED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", ".tox"}


@dataclass(frozen=True)
class ScanError:
    filename: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    files: tuple[Path, ...]
    findings: tuple[Finding, ...]
    errors: tuple[ScanError, ...]


def discover_python_files(
    path: Path,
    excluded_directories: frozenset[str] = frozenset(),
) -> tuple[Path, ...]:
    """Return sorted Python files under a file or directory path."""
    if path.is_file():
        return (path,) if path.suffix == ".py" else ()

    files = (
        candidate
        for candidate in path.rglob("*.py")
        if not any(
            part in SKIPPED_DIRECTORIES or part in excluded_directories
            for part in candidate.parts
        )
    )
    return tuple(sorted(files))


def scan_path(
    path: str | Path,
    rules: tuple[ResourceRule, ...] = DEFAULT_RULES,
    excluded_directories: frozenset[str] = frozenset(),
) -> ScanResult:
    """Analyze one Python file or every Python file below a directory."""
    root = Path(path)
    files = discover_python_files(root, excluded_directories)
    findings: list[Finding] = []
    errors: list[ScanError] = []

    for file_path in files:
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
            scopes = parse_source(source, str(file_path), rules)
            function_scopes = {
                scope.line: scope
                for scope in scopes
                if scope.name != "<module>" and scope.line is not None
            }
            functions = (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            for function in functions:
                scope = function_scopes.get(function.lineno)
                if scope is not None:
                    findings.extend(
                        detect_function(function, scope, str(file_path))
                    )

            module_scope = next(
                (scope for scope in scopes if scope.name == "<module>"),
                None,
            )
            if module_scope is not None:
                findings.extend(detect((module_scope,), str(file_path)))
        except (OSError, SyntaxError) as error:
            errors.append(ScanError(str(file_path), str(error)))

    return ScanResult(tuple(files), tuple(findings), tuple(errors))
