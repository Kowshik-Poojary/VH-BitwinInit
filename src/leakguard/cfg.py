"""Control-flow graph construction for LeakGuard."""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from leakguard.models import (
    AssignmentInfo,
    ContextManagerInfo,
    ControlFlowKind,
    FileAnalysis,
    FunctionInfo,
    OperationKind,
    ProjectAnalysis,
    ResourceOperation,
    ReturnInfo,
    SourceLocation,
)
from leakguard.parser import parse_python_source, read_python_source


class BlockKind(str, Enum):
    ENTRY = "ENTRY"
    PLAIN = "PLAIN"
    CONDITION = "CONDITION"
    LOOP_HEADER = "LOOP_HEADER"
    MERGE = "MERGE"
    EXIT = "EXIT"
    HANDLER = "HANDLER"
    FINALLY = "FINALLY"
    WITH_ENTER = "WITH_ENTER"


class CFGEventKind(str, Enum):
    ACQUIRE = "ACQUIRE"
    CLOSE = "CLOSE"
    ASSIGN = "ASSIGN"
    RETURN = "RETURN"
    RAISE = "RAISE"
    CONTEXT_MANAGER = "CONTEXT_MANAGER"
    CONTROL_FLOW = "CONTROL_FLOW"
    CALL_PASS = "CALL_PASS"


@dataclass
class CFGEvent:
    kind: CFGEventKind
    line: int
    column: int
    label: str
    resource_type: str | None = None
    target: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "line": self.line,
            "column": self.column,
            "label": self.label,
            "resource_type": self.resource_type,
            "target": self.target,
            "details": self.details,
        }


@dataclass
class CFGBlock:
    id: int
    kind: BlockKind
    events: list[CFGEvent] = field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "events": [e.to_dict() for e in self.events],
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass
class CFGEdge:
    source_id: int
    target_id: int
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label,
        }


@dataclass
class FunctionCFG:
    function: FunctionInfo
    blocks: list[CFGBlock]
    edges: list[CFGEdge]
    entry_id: int
    exit_ids: list[int]

    def get_block(self, block_id: int) -> CFGBlock | None:
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def successors(self, block_id: int) -> list[tuple[int, str | None]]:
        return [(e.target_id, e.label) for e in self.edges if e.source_id == block_id]

    def predecessors(self, block_id: int) -> list[tuple[int, str | None]]:
        return [(e.source_id, e.label) for e in self.edges if e.target_id == block_id]

    def paths_to_exit_from(self, start_id: int, max_depth: int = 100) -> list[list[int]]:
        """Enumerate paths from start block to any exit (for testing/analysis)."""
        exits = set(self.exit_ids)
        paths: list[list[int]] = []

        def dfs(current: int, path: list[int], visited: set[int]) -> None:
            if len(path) > max_depth:
                return
            if current in exits:
                paths.append(list(path))
                return
            succs = self.successors(current)
            if not succs:
                paths.append(list(path))
                return
            for target, _ in succs:
                if target in visited:
                    continue
                visited.add(target)
                path.append(target)
                dfs(target, path, visited)
                path.pop()
                visited.remove(target)

        dfs(start_id, [start_id], {start_id})
        return paths

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function.to_dict(),
            "blocks": [b.to_dict() for b in self.blocks],
            "edges": [e.to_dict() for e in self.edges],
            "entry_id": self.entry_id,
            "exit_ids": self.exit_ids,
        }


@dataclass
class FileCFG:
    path: str
    module_name: str
    functions: list[FunctionCFG] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "module_name": self.module_name,
            "functions": [f.to_dict() for f in self.functions],
        }


@dataclass
class CFGStatistics:
    files_processed: int = 0
    functions_processed: int = 0
    total_blocks: int = 0
    total_edges: int = 0
    build_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_processed": self.files_processed,
            "functions_processed": self.functions_processed,
            "total_blocks": self.total_blocks,
            "total_edges": self.total_edges,
            "build_time_ms": self.build_time_ms,
        }


@dataclass
class CFGProject:
    project_path: str
    files: list[FileCFG] = field(default_factory=list)
    statistics: CFGStatistics = field(default_factory=CFGStatistics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "files": [f.to_dict() for f in self.files],
            "statistics": self.statistics.to_dict(),
        }


class _BlockFactory:
    def __init__(self) -> None:
        self.blocks: dict[int, CFGBlock] = {}
        self._next_id = 0

    def new_block(self, kind: BlockKind = BlockKind.PLAIN) -> CFGBlock:
        block = CFGBlock(id=self._next_id, kind=kind)
        self.blocks[self._next_id] = block
        self._next_id += 1
        return block

    def all_blocks(self) -> list[CFGBlock]:
        return list(self.blocks.values())


@dataclass
class _LoopTargets:
    break_target: CFGBlock
    continue_target: CFGBlock


class _FunctionCFGBuilder:
    """Build a CFG from a function AST node."""

    def __init__(
        self,
        func_node: ast.AST,
        factory: _BlockFactory,
        exit_block: CFGBlock,
    ) -> None:
        self.func_node = func_node
        self.factory = factory
        self.exit_block = exit_block
        self.edges: list[CFGEdge] = []
        self._finally_stack: list[CFGBlock] = []

    def build(self) -> tuple[CFGBlock, list[CFGBlock]]:
        entry = self.factory.new_block(BlockKind.ENTRY)
        body = getattr(self.func_node, "body", [])
        body_entry, body_exits = self._compile_stmts(body, loop_targets=None)
        self._connect(entry, body_entry, "entry")
        for block in body_exits:
            self._connect(block, self.exit_block, "fallthrough")
        return entry, body_exits

    def _compile_stmts(
        self,
        stmts: list[ast.stmt],
        loop_targets: _LoopTargets | None,
    ) -> tuple[CFGBlock, list[CFGBlock]]:
        if not stmts:
            empty = self.factory.new_block(BlockKind.PLAIN)
            return empty, [empty]

        entry = self.factory.new_block(BlockKind.PLAIN)
        current = entry
        fallthrough: list[CFGBlock] = [current]

        for stmt in stmts:
            fallthrough = self._compile_stmt(stmt, current, loop_targets, fallthrough)
            if not fallthrough:
                break
            current = fallthrough[0]
            if len(fallthrough) > 1:
                merge = self.factory.new_block(BlockKind.MERGE)
                for block in fallthrough:
                    self._connect(block, merge, "merge")
                fallthrough = [merge]
                current = merge

        return entry, fallthrough

    def _compile_stmt(
        self,
        stmt: ast.stmt,
        current: CFGBlock,
        loop_targets: _LoopTargets | None,
        incoming: list[CFGBlock],
    ) -> list[CFGBlock]:
        current = incoming[0]
        self._mark_stmt(current, stmt)

        if isinstance(stmt, ast.If):
            return self._compile_if(stmt, current, loop_targets)
        if isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)):
            return self._compile_loop(stmt, current, loop_targets)
        if isinstance(stmt, ast.Try):
            return self._compile_try(stmt, current, loop_targets)
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            return self._compile_with(stmt, current, loop_targets)
        if isinstance(stmt, ast.Return):
            target = self._finally_stack[-1] if self._finally_stack else self.exit_block
            self._connect(current, target, "return")
            return []
        if isinstance(stmt, ast.Raise):
            target = self._finally_stack[-1] if self._finally_stack else self.exit_block
            self._connect(current, target, "raise")
            return []
        if isinstance(stmt, ast.Break):
            if loop_targets is not None:
                self._connect(current, loop_targets.break_target, "break")
            else:
                self._connect(current, self.exit_block, "break")
            return []
        if isinstance(stmt, ast.Continue):
            if loop_targets is not None:
                self._connect(current, loop_targets.continue_target, "continue")
            else:
                self._connect(current, self.exit_block, "continue")
            return []
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return incoming
        return incoming

    def _compile_if(
        self,
        stmt: ast.If,
        current: CFGBlock,
        loop_targets: _LoopTargets | None,
    ) -> list[CFGBlock]:
        cond_block = self.factory.new_block(BlockKind.CONDITION)
        self._connect(current, cond_block, "fallthrough")
        self._mark_stmt(cond_block, stmt)

        true_entry, true_exits = self._compile_stmts(stmt.body, loop_targets)
        self._connect(cond_block, true_entry, "true")

        if stmt.orelse:
            false_entry, false_exits = self._compile_stmts(stmt.orelse, loop_targets)
            self._connect(cond_block, false_entry, "false")
            return true_exits + false_exits

        merge = self.factory.new_block(BlockKind.MERGE)
        self._connect(cond_block, merge, "false")
        for block in true_exits:
            self._connect(block, merge, "merge")
        return [merge]

    def _compile_loop(
        self,
        stmt: ast.stmt,
        current: CFGBlock,
        loop_targets: _LoopTargets | None,
    ) -> list[CFGBlock]:
        header = self.factory.new_block(BlockKind.LOOP_HEADER)
        self._connect(current, header, "fallthrough")
        self._mark_stmt(header, stmt)

        after = self.factory.new_block(BlockKind.MERGE)
        body = stmt.body if isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)) else []
        targets = _LoopTargets(break_target=after, continue_target=header)

        body_entry, body_exits = self._compile_stmts(body, targets)
        self._connect(header, body_entry, "true")
        self._connect(header, after, "false")
        for block in body_exits:
            self._connect(block, header, "loop")
        return [after]

    def _compile_try(
        self,
        stmt: ast.Try,
        current: CFGBlock,
        loop_targets: _LoopTargets | None,
    ) -> list[CFGBlock]:
        finally_header: CFGBlock | None = None
        if stmt.finalbody:
            finally_header = self.factory.new_block(BlockKind.FINALLY)
            self._mark_stmt(finally_header, stmt.finalbody[0])
            self._finally_stack.append(finally_header)

        try_entry, try_exits = self._compile_stmts(stmt.body, loop_targets)
        self._connect(current, try_entry, "try")

        merge = self.factory.new_block(BlockKind.MERGE)

        if stmt.handlers:
            for handler in stmt.handlers:
                handler_header = self.factory.new_block(BlockKind.HANDLER)
                self._mark_stmt(handler_header, handler)
                h_entry, h_exits = self._compile_stmts(handler.body, loop_targets)
                self._connect(current, handler_header, "except")
                self._connect(handler_header, h_entry, "handler")
                for block in h_exits:
                    self._connect(block, merge, "handler_exit")
            for block in try_exits:
                self._connect(block, merge, "try_exit")
        else:
            for block in try_exits:
                self._connect(block, merge, "try_exit")

        if stmt.orelse:
            else_entry, else_exits = self._compile_stmts(stmt.orelse, loop_targets)
            self._connect(merge, else_entry, "else")
            merge = self.factory.new_block(BlockKind.MERGE)
            for block in else_exits:
                self._connect(block, merge, "else_exit")

        if finally_header is not None:
            self._finally_stack.pop()
            f_entry, f_exits = self._compile_stmts(stmt.finalbody, loop_targets)
            self._connect(merge, finally_header, "to_finally")
            self._connect(finally_header, f_entry, "finally")
            return f_exits

        return [merge]

    def _compile_with(
        self,
        stmt: ast.With | ast.AsyncWith,
        current: CFGBlock,
        loop_targets: _LoopTargets | None,
    ) -> list[CFGBlock]:
        with_block = self.factory.new_block(BlockKind.WITH_ENTER)
        self._connect(current, with_block, "fallthrough")
        self._mark_stmt(with_block, stmt)

        body_entry, body_exits = self._compile_stmts(stmt.body, loop_targets)
        self._connect(with_block, body_entry, "with_body")
        after = self.factory.new_block(BlockKind.MERGE)
        for block in body_exits:
            self._connect(block, after, "with_exit")
        return [after]

    def _connect(self, source: CFGBlock, target: CFGBlock, label: str | None) -> None:
        self.edges.append(CFGEdge(source_id=source.id, target_id=target.id, label=label))

    def _mark_stmt(self, block: CFGBlock, stmt: ast.AST) -> None:
        line = getattr(stmt, "lineno", None)
        end_line = getattr(stmt, "end_lineno", None)
        if line is not None:
            if block.start_line is None or line < block.start_line:
                block.start_line = line
            if end_line is not None:
                if block.end_line is None or end_line > block.end_line:
                    block.end_line = end_line
            elif block.end_line is None or line > block.end_line:
                block.end_line = line


def _function_matches(node: ast.AST, func_info: FunctionInfo) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return node.name == func_info.name and node.lineno == func_info.location.line


def _find_function_node(
    tree: ast.Module, func_info: FunctionInfo
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if _function_matches(node, func_info):
            return node
    return None


def _in_function_scope(
    item_line: int,
    func_info: FunctionInfo,
    nested_lines: set[int],
) -> bool:
    if item_line in nested_lines:
        return False
    start = func_info.location.line
    end = func_info.location.end_line or start
    return start <= item_line <= end


def _collect_nested_function_lines(func_node: ast.AST) -> set[int]:
    nested: set[int] = set()
    for node in ast.walk(func_node):
        if node is func_node:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", start)
            if start is not None:
                nested.add(start)
                if end is not None:
                    for line in range(start, end + 1):
                        nested.add(line)
    return nested


def _annotate_function_cfg(
    cfg: FunctionCFG,
    file_analysis: FileAnalysis,
    func_info: FunctionInfo,
    nested_lines: set[int],
) -> None:
    """Attach FileAnalysis events to CFG blocks by line number."""

    def block_for_line(line: int) -> CFGBlock | None:
        best: CFGBlock | None = None
        for block in cfg.blocks:
            if block.start_line is None:
                continue
            start = block.start_line
            end = block.end_line or start
            if start <= line <= end:
                if best is None or (best.start_line or 0) <= (block.start_line or 0):
                    best = block
        return best

    def add_event(line: int, column: int, event: CFGEvent) -> None:
        block = block_for_line(line)
        if block is None and cfg.blocks:
            block = cfg.blocks[0]
        if block is not None:
            block.events.append(event)

    qname = func_info.qualified_name

    for op in file_analysis.resource_operations:
        if op.context and op.context.qualified_name() != qname:
            continue
        if not _in_function_scope(op.location.line, func_info, nested_lines):
            continue
        kind = CFGEventKind.ACQUIRE if op.kind == OperationKind.ACQUIRE else CFGEventKind.CLOSE
        add_event(
            op.location.line,
            op.location.column,
            CFGEvent(
                kind=kind,
                line=op.location.line,
                column=op.location.column,
                label=op.expression,
                resource_type=op.resource_type,
                target=op.target,
                details={"registry_key": op.registry_key, "method": op.method},
            ),
        )

    for assign in file_analysis.assignments:
        if assign.context and assign.context.qualified_name() != qname:
            continue
        if not _in_function_scope(assign.location.line, func_info, nested_lines):
            continue
        add_event(
            assign.location.line,
            assign.location.column,
            CFGEvent(
                kind=CFGEventKind.ASSIGN,
                line=assign.location.line,
                column=assign.location.column,
                label=f"{', '.join(assign.targets)} = {assign.value_expression}",
                target=assign.targets[0] if assign.targets else None,
                details={"value_expression": assign.value_expression},
            ),
        )

    for ret in file_analysis.returns:
        if ret.context and ret.context.qualified_name() != qname:
            continue
        if not _in_function_scope(ret.location.line, func_info, nested_lines):
            continue
        add_event(
            ret.location.line,
            ret.location.column,
            CFGEvent(
                kind=CFGEventKind.RETURN,
                line=ret.location.line,
                column=ret.location.column,
                label=f"return {ret.value_expression}" if ret.value_expression else "return",
                target=ret.value_expression,
            ),
        )

    for cm in file_analysis.context_managers:
        if cm.context and cm.context.qualified_name() != qname:
            continue
        if not _in_function_scope(cm.location.line, func_info, nested_lines):
            continue
        add_event(
            cm.location.line,
            cm.location.column,
            CFGEvent(
                kind=CFGEventKind.CONTEXT_MANAGER,
                line=cm.location.line,
                column=cm.location.column,
                label=cm.expression,
                resource_type=cm.resource_type,
                target=cm.target,
                details={"registry_key": cm.registry_key},
            ),
        )

    for call_pass in file_analysis.function_call_passes:
        if call_pass.caller and call_pass.caller.qualified_name() != qname:
            continue
        if not _in_function_scope(call_pass.location.line, func_info, nested_lines):
            continue
        add_event(
            call_pass.location.line,
            call_pass.location.column,
            CFGEvent(
                kind=CFGEventKind.CALL_PASS,
                line=call_pass.location.line,
                column=call_pass.location.column,
                label=call_pass.callee_expression,
                details={"arguments": call_pass.argument_expressions},
            ),
        )

    for cf in file_analysis.control_flow:
        if cf.context and cf.context.qualified_name() != qname:
            continue
        if not _in_function_scope(cf.location.line, func_info, nested_lines):
            continue
        add_event(
            cf.location.line,
            cf.location.column,
            CFGEvent(
                kind=CFGEventKind.CONTROL_FLOW,
                line=cf.location.line,
                column=cf.location.column,
                label=cf.kind.value,
                details={"condition": cf.condition, "target": cf.target},
            ),
        )


def build_function_cfg(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    func_info: FunctionInfo,
    file_analysis: FileAnalysis,
) -> FunctionCFG:
    """Build and annotate CFG for a single function."""
    factory = _BlockFactory()
    exit_block = factory.new_block(BlockKind.EXIT)

    builder = _FunctionCFGBuilder(func_node, factory, exit_block)
    entry, _ = builder.build()

    cfg = FunctionCFG(
        function=func_info,
        blocks=factory.all_blocks(),
        edges=builder.edges,
        entry_id=entry.id,
        exit_ids=[exit_block.id],
    )

    nested_lines = _collect_nested_function_lines(func_node)
    _annotate_function_cfg(cfg, file_analysis, func_info, nested_lines)
    return cfg


def build_file_cfg(file_analysis: FileAnalysis) -> FileCFG | None:
    """Build CFGs for all functions in a file."""
    path = Path(file_analysis.path)
    source, read_error = read_python_source(path)
    if read_error is not None or source is None:
        return None

    tree, parse_error = parse_python_source(source, filename=str(path))
    if parse_error is not None or tree is None:
        return None

    file_cfg = FileCFG(path=file_analysis.path, module_name=file_analysis.module_name)

    for func_info in file_analysis.functions:
        func_node = _find_function_node(tree, func_info)
        if func_node is None:
            continue
        file_cfg.functions.append(
            build_function_cfg(func_node, func_info, file_analysis)
        )

    del tree
    del source
    return file_cfg


def build_cfg(project: ProjectAnalysis) -> CFGProject:
    """Build control-flow graphs for an analyzed project."""
    start = time.perf_counter()
    cfg_project = CFGProject(project_path=project.project_path)
    stats = CFGStatistics()

    for file_analysis in project.file_analyses:
        file_cfg = build_file_cfg(file_analysis)
        if file_cfg is None:
            continue
        stats.files_processed += 1
        stats.functions_processed += len(file_cfg.functions)
        for func_cfg in file_cfg.functions:
            stats.total_blocks += len(func_cfg.blocks)
            stats.total_edges += len(func_cfg.edges)
        cfg_project.files.append(file_cfg)

    stats.build_time_ms = (time.perf_counter() - start) * 1000
    cfg_project.statistics = stats
    return cfg_project


def find_function_cfg(cfg_project: CFGProject, qualified_name: str) -> FunctionCFG | None:
    for file_cfg in cfg_project.files:
        for func_cfg in file_cfg.functions:
            if func_cfg.function.qualified_name == qualified_name:
                return func_cfg
    return None


def path_has_acquire_without_close(path_blocks: list[int], func_cfg: FunctionCFG) -> bool:
    """Check if a CFG path acquires a resource but never closes it (heuristic)."""
    acquired: set[str] = set()
    closed: set[str] = set()

    for block_id in path_blocks:
        block = func_cfg.get_block(block_id)
        if block is None:
            continue
        for event in block.events:
            if event.kind == CFGEventKind.ACQUIRE and event.target:
                acquired.add(event.target)
            elif event.kind == CFGEventKind.CLOSE and event.target:
                closed.add(event.target)
            elif event.kind == CFGEventKind.CONTEXT_MANAGER and event.target:
                acquired.discard(event.target)

    return bool(acquired - closed)
