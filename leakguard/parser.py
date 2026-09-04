"""Convert Python source into normalized resource-operation facts."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .rules import DEFAULT_RULES, ResourceRule


@dataclass(frozen=True)
class ResourceOperation:
    kind: str
    line: int
    variable: str
    resource_type: str = "File"
    cleanup: str = "close"


@dataclass(frozen=True)
class ScopeFacts:
    name: str
    operations: tuple[ResourceOperation, ...]
    line: int | None = None


class _ScopeVisitor(ast.NodeVisitor):
    def __init__(self, rules: tuple[ResourceRule, ...]) -> None:
        self.operations: list[ResourceOperation] = []
        self.rules = rules

    def visit_Assign(self, node: ast.Assign) -> None:
        variable = self._assigned_name(node.targets)
        rule = self._matching_rule(node.value)
        if variable and rule:
            self.operations.append(ResourceOperation(
                "acquire", node.lineno, variable, rule.resource_type, rule.cleanup
            ))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        variable = node.target.id if isinstance(node.target, ast.Name) else None
        rule = self._matching_rule(node.value) if node.value else None
        if variable and rule:
            self.operations.append(ResourceOperation(
                "acquire", node.lineno, variable, rule.resource_type, rule.cleanup
            ))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            variable = self._optional_name(item.optional_vars)
            rule = self._matching_rule(item.context_expr)
            if variable and rule and rule.managed:
                self.operations.append(ResourceOperation(
                    "managed", node.lineno, variable, rule.resource_type, rule.cleanup
                ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and any(rule.cleanup == node.func.attr for rule in self.rules)
            and isinstance(node.func.value, ast.Name)
        ):
            self.operations.append(
                ResourceOperation("close", node.lineno, node.func.value.id)
            )
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if isinstance(node.value, ast.Name):
            self.operations.append(ResourceOperation("return", node.lineno, node.value.id))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    @staticmethod
    def _assigned_name(targets: list[ast.expr]) -> str | None:
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            return targets[0].id
        return None

    @staticmethod
    def _optional_name(target: ast.expr | None) -> str | None:
        return target.id if isinstance(target, ast.Name) else None

    def _matching_rule(self, node: ast.expr | None) -> ResourceRule | None:
        if not isinstance(node, ast.Call):
            return None
        name = self._call_name(node.func)
        return next((rule for rule in self.rules if rule.call == name), None)

    @staticmethod
    def _call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = _ScopeVisitor._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""


def parse_source(
    source: str,
    filename: str = "<string>",
    rules: tuple[ResourceRule, ...] = DEFAULT_RULES,
) -> tuple[ScopeFacts, ...]:
    """Parse source and return normalized facts for module and functions."""
    tree = ast.parse(source, filename=filename)
    scopes: list[ScopeFacts] = []

    module_visitor = _ScopeVisitor(rules)
    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_visitor.visit(statement)
    if module_visitor.operations:
        scopes.append(ScopeFacts("<module>", tuple(module_visitor.operations)))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visitor = _ScopeVisitor(rules)
            for statement in node.body:
                visitor.visit(statement)
            if visitor.operations:
                scopes.append(
                    ScopeFacts(node.name, tuple(visitor.operations), node.lineno)
                )

    return tuple(scopes)


def parse_file(
    path: str | Path,
    rules: tuple[ResourceRule, ...] = DEFAULT_RULES,
) -> tuple[ScopeFacts, ...]:
    """Read and parse a Python file."""
    file_path = Path(path)
    return parse_source(file_path.read_text(encoding="utf-8"), str(file_path), rules)
