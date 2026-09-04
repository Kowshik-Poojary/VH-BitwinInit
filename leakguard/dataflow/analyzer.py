"""Worklist-based path-sensitive resource analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from ..cfg.models import CFG
from ..parser import ResourceOperation
from .state import AnalysisState, ResourceState


@dataclass(frozen=True)
class DataflowResult:
    in_states: dict[int, AnalysisState] = field(default_factory=dict)
    out_states: dict[int, AnalysisState] = field(default_factory=dict)
    leaked_variables: tuple[str, ...] = ()


class DataflowAnalyzer:
    """Propagate resource states through a function control-flow graph."""

    def analyze(
        self,
        cfg: CFG,
        operations: tuple[ResourceOperation, ...],
    ) -> DataflowResult:
        if cfg.entry is None or cfg.exit is None:
            return DataflowResult()

        operations_by_line: dict[int, list[ResourceOperation]] = {}
        for operation in operations:
            operations_by_line.setdefault(operation.line, []).append(operation)

        in_states: dict[int, AnalysisState] = {cfg.entry: AnalysisState()}
        out_states: dict[int, AnalysisState] = {}
        worklist = [cfg.entry]

        while worklist:
            node_id = worklist.pop()
            state = in_states[node_id]
            out_state = self._transfer(
                cfg.nodes[node_id].ast_node,
                state,
                operations_by_line,
            )
            if out_states.get(node_id) == out_state:
                continue
            out_states[node_id] = out_state

            for successor in cfg.nodes[node_id].successors:
                incoming = in_states.get(successor)
                merged = (
                    out_state.copy()
                    if incoming is None
                    else incoming.merge(out_state)
                )
                if incoming != merged:
                    in_states[successor] = merged
                    worklist.append(successor)

        exit_state = in_states.get(cfg.exit, AnalysisState())
        leaked = tuple(
            variable
            for variable, state in sorted(exit_state.resources.items())
            if state == ResourceState.OPEN
        )
        return DataflowResult(in_states, out_states, leaked)

    @staticmethod
    def _transfer(
        ast_node: ast.AST | str,
        state: AnalysisState,
        operations_by_line: dict[int, list[ResourceOperation]],
    ) -> AnalysisState:
        new_state = state.copy()
        if isinstance(ast_node, str):
            return new_state

        for operation in operations_by_line.get(ast_node.lineno, []):
            if operation.kind == "acquire":
                new_state.resources[operation.variable] = ResourceState.OPEN
            elif operation.kind in {"close", "managed"}:
                new_state.resources[operation.variable] = ResourceState.CLOSED
            elif operation.kind == "return":
                new_state.resources[operation.variable] = ResourceState.ESCAPED
        return new_state
