"""Conservative, verified fixes for simple file leaks."""

from __future__ import annotations

import ast
from pathlib import Path

from .detector import Finding


def fix_finding(finding: Finding) -> bool:
    """Wrap one simple function-local open in a context manager."""
    path = Path(finding.filename)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    target: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == finding.scope
            and node.lineno <= finding.opened_line <= node.end_lineno
        ):
            target = node
            break
    if target is None:
        return False
    if any(isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With))
           for node in ast.walk(target)):
        return False

    lines = source.splitlines(keepends=True)
    index = finding.opened_line - 1
    original = lines[index]
    stripped = original.lstrip()
    prefix = original[: len(original) - len(stripped)]
    marker = f"{finding.variable} = open("
    if not stripped.startswith(marker):
        return False

    expression = stripped.rstrip().split("=", 1)[1].strip()
    lines[index] = f"{prefix}with {expression} as {finding.variable}:\n"
    body_start = index + 1
    body_end = target.end_lineno
    for line_number in range(body_start, body_end):
        if lines[line_number].strip():
            lines[line_number] = f"    {lines[line_number]}"
    path.write_text("".join(lines), encoding="utf-8")
    return True
