"""Build a small control-flow graph for a Python function."""

from __future__ import annotations

import ast

from .models import CFG, CFGNode


class CFGBuilder:
    """Build CFGs for statements, branches, loops, and basic cleanup flow."""

    def __init__(self) -> None:
        self._next_id = 0
        self._cfg: CFG | None = None

    def build(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> CFG:
        """Build a graph whose entry and exit belong to one function."""
        self._next_id = 0
        cfg = CFG(function_name=function.name)
        self._cfg = cfg
        entry = self._new_node("ENTRY")
        exit_node = self._new_node("EXIT")
        cfg.entry = entry
        cfg.exit = exit_node

        body_entry = self._build_block(function.body, exit_node)
        cfg.add_edge(entry, body_entry)
        return cfg

    def _build_block(
        self,
        statements: list[ast.stmt],
        continuation: int,
        return_target: int | None = None,
    ) -> int:
        assert self._cfg is not None
        current = continuation
        for statement in reversed(statements):
            statement_id = self._new_node(statement)
            if isinstance(statement, ast.Return):
                target = return_target or self._cfg.exit
                assert target is not None
                self._cfg.add_edge(statement_id, target)
            elif isinstance(statement, ast.If):
                body_entry = self._build_block(
                    statement.body, current, return_target
                )
                if statement.orelse:
                    else_entry = self._build_block(
                        statement.orelse, current, return_target
                    )
                else:
                    else_entry = current
                self._cfg.add_edge(statement_id, body_entry)
                self._cfg.add_edge(statement_id, else_entry)
            elif isinstance(statement, (ast.For, ast.While)):
                body_entry = self._build_block(
                    statement.body, statement_id, return_target
                )
                self._cfg.add_edge(statement_id, body_entry)
                self._cfg.add_edge(statement_id, current)
                if statement.orelse:
                    else_entry = self._build_block(
                        statement.orelse, current, return_target
                    )
                    self._cfg.add_edge(statement_id, else_entry)
            elif isinstance(statement, ast.With):
                body_entry = self._build_block(
                    statement.body, current, return_target
                )
                self._cfg.add_edge(statement_id, body_entry)
            elif isinstance(statement, ast.Try):
                finally_entry = current
                if statement.finalbody:
                    finally_entry = self._build_block(
                        statement.finalbody, current, return_target
                    )
                exception_return_target = (
                    finally_entry if statement.finalbody else return_target
                )
                if exception_return_target is None:
                    exception_return_target = self._cfg.exit
                try_entry = self._build_block(
                    statement.body, finally_entry, exception_return_target
                )
                self._cfg.add_edge(statement_id, try_entry)
                if statement.handlers:
                    for handler in statement.handlers:
                        handler_entry = self._build_block(
                            handler.body, finally_entry, exception_return_target
                        )
                        self._cfg.add_edge(statement_id, handler_entry)
                if statement.orelse:
                    else_entry = self._build_block(
                        statement.orelse, finally_entry, exception_return_target
                    )
                    self._cfg.add_edge(statement_id, else_entry)
            else:
                self._cfg.add_edge(statement_id, current)
            current = statement_id
        return current

    def _new_node(self, ast_node: ast.AST | str) -> int:
        assert self._cfg is not None
        node_id = self._next_id
        self._next_id += 1
        self._cfg.nodes[node_id] = CFGNode(node_id=node_id, ast_node=ast_node)
        return node_id
