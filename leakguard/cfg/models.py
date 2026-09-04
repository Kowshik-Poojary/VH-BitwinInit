"""Models for function-level control-flow graphs."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class CFGNode:
    node_id: int
    ast_node: ast.AST | str
    successors: list[int] = field(default_factory=list)
    predecessors: list[int] = field(default_factory=list)


@dataclass
class CFG:
    function_name: str
    nodes: dict[int, CFGNode] = field(default_factory=dict)
    entry: int | None = None
    exit: int | None = None

    def add_edge(self, source_id: int, target_id: int) -> None:
        source = self.nodes[source_id]
        target = self.nodes[target_id]
        if target_id not in source.successors:
            source.successors.append(target_id)
        if source_id not in target.predecessors:
            target.predecessors.append(source_id)
