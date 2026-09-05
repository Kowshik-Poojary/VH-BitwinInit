"""Best-effort automatic quick-fixes for LeakGuard findings.

Only handles the common, safe case: a single-line ``x = acquire(...)``
assignment with at least one statement after it in the same block, which
gets rewritten as ``with acquire(...) as x:`` with the following statements
nested underneath. Anything riskier (multi-line acquire, attribute/subscript
targets, acquire as the last statement in its block) is left for a manual
fix rather than guessed at.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from leakguard.models import Finding


@dataclass
class FixSuggestion:
    start_line: int
    end_line: int
    new_lines: list[str]
    preview: str


def _find_assign(
    tree: ast.Module, lineno: int, var_name: str
) -> tuple[list[ast.stmt], int, ast.Assign] | None:
    found: tuple[list[ast.stmt], int, ast.Assign] | None = None

    class _Visitor(ast.NodeVisitor):
        def generic_visit(self, node: ast.AST) -> None:
            nonlocal found
            for field_name in ("body", "orelse", "finalbody"):
                body = getattr(node, field_name, None)
                if not isinstance(body, list):
                    continue
                for index, stmt in enumerate(body):
                    if (
                        isinstance(stmt, ast.Assign)
                        and stmt.lineno == lineno
                        and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and stmt.targets[0].id == var_name
                    ):
                        found = (body, index, stmt)
            super().generic_visit(node)

    _Visitor().visit(tree)
    return found


def build_with_fix(source: str, finding: Finding) -> FixSuggestion | None:
    var_name = finding.details.get("variable")
    if not var_name:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    located = _find_assign(tree, finding.location.line, var_name)
    if located is None:
        return None
    body, index, assign = located

    if assign.lineno != assign.end_lineno:
        return None  # multi-line acquire — too risky to reformat blindly

    following = body[index + 1 :]
    if not following:
        return None  # nothing after the acquire in this block to nest

    lines = source.splitlines(keepends=True)
    line_idx = assign.lineno - 1
    original_line = lines[line_idx]
    indent = original_line[: len(original_line) - len(original_line.lstrip())]

    value_text = original_line[assign.value.col_offset : assign.value.end_col_offset]
    trailing = original_line[assign.value.end_col_offset :]  # trailing comment/newline
    new_first_line = f"{indent}with {value_text} as {var_name}:{trailing}"

    end_line = following[-1].end_lineno or assign.end_lineno

    new_lines = list(lines)
    new_lines[line_idx] = new_first_line
    for i in range(assign.end_lineno, end_line):
        if lines[i].strip() == "":
            continue
        new_lines[i] = "    " + lines[i]

    preview_before = "".join(lines[line_idx:end_line])
    preview_after = "".join(new_lines[line_idx:end_line])

    return FixSuggestion(
        start_line=assign.lineno,
        end_line=end_line,
        new_lines=new_lines,
        preview=f"  --- before ---\n{_indent_block(preview_before)}  --- after ---\n{_indent_block(preview_after)}",
    )


def _indent_block(text: str) -> str:
    return "".join(f"  {line}" if line.strip() else line for line in text.splitlines(keepends=True))
