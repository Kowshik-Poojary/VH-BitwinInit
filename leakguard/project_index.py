"""Static project index for future interprocedural ownership analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FunctionSummary:
    filename: str
    name: str
    line: int
    calls: tuple[str, ...]
    acquired_variables: tuple[str, ...]
    returned_variables: tuple[str, ...]


@dataclass(frozen=True)
class ProjectIndex:
    functions: tuple[FunctionSummary, ...]

    def by_name(self, name: str) -> tuple[FunctionSummary, ...]:
        return tuple(function for function in self.functions if function.name == name)


class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.acquired: list[str] = []
        self.returned: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
        ):
            name = node.value.func
            if isinstance(name, ast.Name) and name.id == "open":
                self.acquired.append(node.targets[0].id)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if isinstance(node.value, ast.Name):
            self.returned.append(node.value.id)
        self.generic_visit(node)


def build_project_index(paths: tuple[Path, ...]) -> ProjectIndex:
    summaries: list[FunctionSummary] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in ast.walk(tree):
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitor = _FunctionVisitor()
                for statement in function.body:
                    visitor.visit(statement)
                summaries.append(
                    FunctionSummary(
                        filename=str(path),
                        name=function.name,
                        line=function.lineno,
                        calls=tuple(visitor.calls),
                        acquired_variables=tuple(visitor.acquired),
                        returned_variables=tuple(visitor.returned),
                    )
                )
    return ProjectIndex(tuple(summaries))