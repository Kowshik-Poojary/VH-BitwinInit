"""AST expression utilities for LeakGuard."""

from __future__ import annotations

import ast
from typing import Any


def expr_to_str(node: ast.expr | None) -> str:
    """Convert an AST expression node to a source-like string."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return _fallback_expr_str(node)


def _fallback_expr_str(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_fallback_expr_str(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        func = _fallback_expr_str(node.func)
        return f"{func}(...)"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Subscript):
        return f"{_fallback_expr_str(node.value)}[...]"
    if isinstance(node, ast.BinOp):
        return f"{_fallback_expr_str(node.left)} ... {_fallback_expr_str(node.right)}"
    if isinstance(node, ast.UnaryOp):
        return f"...{_fallback_expr_str(node.operand)}"
    if isinstance(node, ast.JoinedStr):
        return "f'...'"
    if isinstance(node, ast.List):
        return "[...]"
    if isinstance(node, ast.Tuple):
        return "(...)"
    if isinstance(node, ast.Dict):
        return "{...}"
    if isinstance(node, ast.Starred):
        return f"*{_fallback_expr_str(node.value)}"
    if isinstance(node, ast.Lambda):
        return "lambda ..."
    if isinstance(node, ast.IfExp):
        return f"{_fallback_expr_str(node.body)} if ... else ..."
    return type(node).__name__


def target_to_str(node: ast.expr) -> str:
    """Convert an assignment target to a string."""
    return expr_to_str(node)


def targets_to_strs(targets: list[ast.expr]) -> list[str]:
    return [target_to_str(t) for t in targets]


def get_call_info(node: ast.Call) -> dict[str, Any]:
    """Extract structured call information from a Call node."""
    func = node.func
    base: str | None = None
    attribute: str | None = None
    function_name: str | None = None
    qualified_name: str | None = None
    is_method_call = False

    if isinstance(func, ast.Name):
        function_name = func.id
        qualified_name = func.id
    elif isinstance(func, ast.Attribute):
        attribute = func.attr
        is_method_call = True
        base = expr_to_str(func.value)
        qualified_name = f"{base}.{attribute}"
    else:
        function_name = expr_to_str(func)
        qualified_name = function_name

    return {
        "base": base,
        "attribute": attribute,
        "function_name": function_name,
        "qualified_name": qualified_name,
        "is_method_call": is_method_call,
    }


def get_decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{expr_to_str(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return expr_to_str(node.func)
    return expr_to_str(node)


def get_base_names(bases: list[ast.expr]) -> list[str]:
    return [expr_to_str(b) for b in bases]
