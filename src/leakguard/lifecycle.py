from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from leakguard.cfg import (
    BlockKind,
    CFGEvent,
    CFGEventKind,
    CFGProject,
    FunctionCFG,
)
from leakguard.interproc import FunctionSummary, build_summaries
from leakguard.models import (
    FileAnalysis,
    Finding,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    ProjectAnalysis,
    SourceLocation,
)

CalleeResolver = Callable[[str], str | None]


class ResourceState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LEAKED = "LEAKED"
    ESCAPED = "ESCAPED"
    UNKNOWN = "UNKNOWN"


@dataclass
class LifecycleResult:
    state: ResourceState
    acquire_line: int
    message: str
    path: list[int]
    terminating_event: CFGEvent | None = None
    path_trace: list[dict[str, Any]] = field(default_factory=list)
    reached_loop_limit: bool = False
    loop_limit: int | str = "x"


def _get_acquire_event(
    function_cfg: FunctionCFG,
    block_id: int,
    target: str,
    line: int | None = None,
    column: int | None = None,
) -> CFGEvent | None:
    block = function_cfg.get_block(block_id)

    if block is None:
        return None

    for event in block.events:
        if (
            event.kind == CFGEventKind.ACQUIRE
            and event.target == target
            and (line is None or event.line == line)
            and (column is None or event.column == column)
        ):
            return event

    return None


def _get_paths_from_acquire(
    function_cfg: FunctionCFG,
    acquire_block_id: int,
    max_loops: int = 10,
) -> list[list[int]]:
    return function_cfg.paths_to_exit_from(acquire_block_id, max_loops=max_loops)


def _events_for_path(
    function_cfg: FunctionCFG,
    path: list[int],
) -> list[CFGEvent]:

    events: list[CFGEvent] = []
    terminal_seen = False

    for block_id in path:
        block = function_cfg.get_block(block_id)

        if block is None:
            continue

        if block.kind == BlockKind.FINALLY:
            terminal_seen = False
        if terminal_seen and block_id in function_cfg.exit_ids:
            continue

        block_events = sorted(
            block.events,
            key=lambda event: (event.line, event.column),
        )
        for index, event in enumerate(block_events):
            events.append(event)
            is_terminal = event.kind in (
                CFGEventKind.RETURN,
                CFGEventKind.RAISE,
            ) or (
                event.kind == CFGEventKind.CONTROL_FLOW
                and event.label in ("RETURN", "RAISE")
            )
            if is_terminal:
                terminal_seen = True
                break
    return events


def _path_has_close(
    events: list[CFGEvent],
    target: str,
) -> bool:
    aliases = {target}
    acquisition_assignments = {
        (event.target, event.line)
        for event in events
        if event.kind == CFGEventKind.ACQUIRE and event.target
    }

    for event in events:
        if event.kind == CFGEventKind.ASSIGN and event.target:
            if (event.target, event.line) in acquisition_assignments:
                continue
            value = event.details.get("value_expression")
            if value in aliases:
                aliases.add(event.target)
            elif event.target in aliases:
                aliases.remove(event.target)
            continue
        if (
            event.kind in (
                CFGEventKind.CLOSE,
                CFGEventKind.CONTEXT_MANAGER,
            )
            and event.target in aliases
        ):
            return True

    return False


def _classify_path(
    events: list[CFGEvent],
    target: str,
    acquire_line: int,
    acquire_column: int,
    file_path: str = "",
    summaries: dict[str, FunctionSummary] | None = None,
    callee_resolver: CalleeResolver | None = None,
) -> tuple[ResourceState, CFGEvent | None, list[dict[str, Any]]]:
    started = False
    aliases = {target}
    passed_to_function = False
    path_trace: list[dict[str, Any]] = []
    terminating_event: CFGEvent | None = None

    for event in events:
        if event.kind == CFGEventKind.ACQUIRE and event.target == target:
            if not started:
                if (event.line, event.column) != (acquire_line, acquire_column):
                    continue
                started = True
                path_trace.append({
                    "file": file_path,
                    "line": event.line,
                    "column": event.column,
                    "event": f"ACQUIRE {target}",
                    "kind": event.kind.value,
                })
                continue
            terminating_event = event
            path_trace.append({
                "file": file_path,
                "line": event.line,
                "column": event.column,
                "event": f"REASSIGN {target}",
                "kind": event.kind.value,
            })
            return ResourceState.OPEN, terminating_event, path_trace

        if not started:
            continue

        path_trace.append({
            "file": file_path,
            "line": event.line,
            "column": event.column,
            "event": event.label,
            "kind": event.kind.value,
        })

        if (
            event.kind == CFGEventKind.CALL_PASS
            and any(argument in aliases for argument in event.details.get("arguments", []))
        ):
            # Try inter-procedural resolution: if the callee provably closes the argument, treat as CLOSED.
            if summaries is not None and callee_resolver is not None:
                callee_qname = callee_resolver(event.label)
                if callee_qname is not None:
                    smry = summaries.get(callee_qname)
                    if smry is not None and not smry.is_method:
                        args = event.details.get("arguments", [])
                        for i, arg in enumerate(args):
                            if arg in aliases and i in smry.closes_param_indices:
                                return ResourceState.CLOSED, event, path_trace
            passed_to_function = True
            continue

        if (
            event.kind == CFGEventKind.RETURN
            and event.target in aliases
        ):
            terminating_event = event
            return ResourceState.ESCAPED, terminating_event, path_trace

        if event.kind == CFGEventKind.ASSIGN and event.target:
            if event.line == acquire_line and event.target == target:
                continue
            value = event.details.get("value_expression")
            if value in aliases:
                aliases.add(event.target)
            elif event.target in aliases:
                aliases.remove(event.target)
            continue

        if (
            event.kind in (
                CFGEventKind.CLOSE,
                CFGEventKind.CONTEXT_MANAGER,
            )
            and event.target in aliases
        ):
            return ResourceState.CLOSED, event, path_trace

        if event.kind in (CFGEventKind.RETURN, CFGEventKind.RAISE) or (
            event.kind == CFGEventKind.CONTROL_FLOW and event.label in ("RETURN", "RAISE")
        ):
            terminating_event = event

    if not terminating_event and events:
        terminating_event = events[-1]

    if passed_to_function:
        return ResourceState.UNKNOWN, terminating_event, path_trace
    return ResourceState.OPEN, terminating_event, path_trace


def _find_acquire_blocks(
    function_cfg: FunctionCFG,
) -> list[tuple[int, CFGEvent]]:

    acquisitions: list[tuple[int, CFGEvent]] = []

    for block in function_cfg.blocks:
        for event in block.events:
            if event.kind == CFGEventKind.ACQUIRE:
                acquisitions.append((block.id, event))

    return acquisitions


def analyze_resource(
    function_cfg: FunctionCFG,
    acquire_block_id: int,
    target: str,
    acquire_line: int | None = None,
    acquire_column: int | None = None,
    summaries: dict[str, FunctionSummary] | None = None,
    callee_resolver: CalleeResolver | None = None,
    max_loops: int | str = "x",
) -> list[LifecycleResult]:
    if isinstance(max_loops, int):
        loop_limit_num = max_loops
        display_limit = str(max_loops)
    elif str(max_loops).isdigit():
        loop_limit_num = int(max_loops)
        display_limit = str(max_loops)
    else:
        loop_limit_num = 10
        display_limit = str(max_loops)

    acquire = _get_acquire_event(
        function_cfg,
        acquire_block_id,
        target,
        acquire_line,
        acquire_column,
    )

    if acquire is None:
        return []

    acquire_block = function_cfg.get_block(acquire_block_id)
    is_in_loop = bool(acquire_block and acquire_block.in_loop) or bool(acquire.details.get("in_loop"))
    loop_headers = {b.id for b in function_cfg.blocks if b.kind == BlockKind.LOOP_HEADER}

    paths = _get_paths_from_acquire(
        function_cfg,
        acquire_block_id,
        max_loops=loop_limit_num,
    )

    results: list[LifecycleResult] = []
    file_path = (
        function_cfg.function.location.file
        if function_cfg.function and function_cfg.function.location
        else ""
    )

    for path in paths:
        events = _events_for_path(
            function_cfg,
            path,
        )

        state, term_event, path_trace = _classify_path(
            events,
            target,
            acquire.line,
            acquire.column,
            file_path=file_path,
            summaries=summaries,
            callee_resolver=callee_resolver,
        )

        reached_loop_limit = False
        if is_in_loop or loop_headers:
            loop_header_count = max((path.count(h_id) for h_id in loop_headers), default=0)
            if loop_header_count >= loop_limit_num:
                reached_loop_limit = True
            elif is_in_loop and (
                (term_event and "REASSIGN" in getattr(term_event, "label", ""))
                or any("REASSIGN" in str(step.get("event", "")) for step in path_trace)
                or loop_header_count > 1
                or (loop_header_count >= 1 and state in (ResourceState.OPEN, ResourceState.LEAKED))
            ):
                reached_loop_limit = True

        results.append(
            LifecycleResult(
                state=state,
                acquire_line=acquire.line,
                message=f"Resource {target} ends as {state.value}",
                path=path,
                terminating_event=term_event,
                path_trace=path_trace,
                reached_loop_limit=reached_loop_limit,
                loop_limit=display_limit,
            )
        )

    return results


def aggregate_resource_results(
    results: list[LifecycleResult],
) -> ResourceState:
    if not results:
        return ResourceState.UNKNOWN

    states = {result.state for result in results}
    if ResourceState.OPEN in states or ResourceState.LEAKED in states:
        return ResourceState.LEAKED
    if states.issubset({ResourceState.CLOSED, ResourceState.ESCAPED}):
        if ResourceState.CLOSED in states and ResourceState.ESCAPED not in states:
            return ResourceState.CLOSED
        if ResourceState.ESCAPED in states and ResourceState.CLOSED not in states:
            return ResourceState.ESCAPED
        return ResourceState.CLOSED
    return ResourceState.UNKNOWN


def resource_confidence(results: list[LifecycleResult]) -> str:
    if not results:
        return "LOW"

    leaks = {ResourceState.OPEN, ResourceState.LEAKED}
    leak_count = sum(1 for r in results if r.state in leaks)
    safe_count = sum(1 for r in results if r.state in (ResourceState.CLOSED, ResourceState.ESCAPED))
    unknown_count = sum(1 for r in results if r.state == ResourceState.UNKNOWN)

    if leak_count > 0 and safe_count == 0 and unknown_count == 0:
        return "HIGH"
    if leak_count > 0 and (safe_count > 0 or unknown_count > 0):
        return "MEDIUM"
    return "LOW"


def _build_callee_resolver(
    file_analysis: FileAnalysis,
    summaries: dict[str, FunctionSummary],
) -> CalleeResolver:
    """Build a per-file resolver: callee expression string → qualified function name."""
    # Index all known qualified names by their bare (last-component) name.
    by_bare: dict[str, list[str]] = {}
    for qname in summaries:
        bare = qname.split(".")[-1]
        by_bare.setdefault(bare, []).append(qname)

    # Build an import alias map: local name → fully-qualified name.
    import_map: dict[str, str] = {}
    for imp in file_analysis.imports:
        if imp.is_from_import and imp.imported_name:
            local = imp.alias or imp.imported_name
            full = f"{imp.module}.{imp.imported_name}" if imp.module else imp.imported_name
            import_map[local] = full
        else:
            local = imp.alias or imp.module
            import_map[local] = imp.module

    def resolve(callee_expr: str) -> str | None:
        # Exact match (same-module call already has the qualified name).
        if callee_expr in summaries:
            return callee_expr
        # Via import alias (e.g. `from helpers import close_it` → helpers.close_it).
        resolved = import_map.get(callee_expr)
        if resolved and resolved in summaries:
            return resolved
        # Fallback: unique bare-name match in the project.
        candidates = by_bare.get(callee_expr, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    return resolve


def lifecycle_findings(
    project: ProjectAnalysis,
    cfg_project: CFGProject,
    max_loops: int | str = "x",
) -> list[Finding]:
    findings: list[Finding] = []
    rule_ids = {
        "file": "LKG-R001",
        "socket": "LKG-R002",
        "database": "LKG-R003",
        "tempfile": "LKG-R004",
    }

    if isinstance(max_loops, int):
        display_limit = str(max_loops)
    elif str(max_loops).isdigit():
        display_limit = str(max_loops)
    else:
        display_limit = str(max_loops)

    # Build inter-procedural summaries once for the entire project.
    summaries = build_summaries(cfg_project)

    # Build a lookup from file path → FileAnalysis for import resolution.
    file_analysis_by_path = {fa.path: fa for fa in project.file_analyses}

    for file_cfg in cfg_project.files:
        file_analysis = file_analysis_by_path.get(file_cfg.path)
        callee_resolver = (
            _build_callee_resolver(file_analysis, summaries)
            if file_analysis is not None
            else None
        )

        for function_cfg in file_cfg.functions:
            for block_id, acquire in _find_acquire_blocks(function_cfg):
                if acquire.target is None:
                    continue
                results = analyze_resource(
                    function_cfg,
                    block_id,
                    acquire.target,
                    acquire.line,
                    acquire.column,
                    summaries=summaries,
                    callee_resolver=callee_resolver,
                    max_loops=max_loops,
                )
                state = aggregate_resource_results(results)
                if state in (ResourceState.CLOSED, ResourceState.ESCAPED):
                    continue

                status = {
                    ResourceState.LEAKED: FindingStatus.DEFINITE_LEAK,
                    ResourceState.ESCAPED: FindingStatus.ESCAPED,
                    ResourceState.UNKNOWN: FindingStatus.UNKNOWN,
                }.get(state, FindingStatus.UNKNOWN)
                resource_type = acquire.resource_type or "resource"

                leaking_result = next(
                    (r for r in results if r.state in (ResourceState.OPEN, ResourceState.LEAKED)),
                    None,
                )
                loop_leak_result = next(
                    (r for r in results if r.reached_loop_limit and r.state in (ResourceState.OPEN, ResourceState.LEAKED)),
                    None,
                )

                if loop_leak_result is not None or (acquire.details.get("in_loop") and any(r.state in (ResourceState.OPEN, ResourceState.LEAKED) for r in results)):
                    msg = f"upper limit of {display_limit} loops reached hence can be leaky while it may get closed later"
                elif leaking_result and leaking_result.terminating_event:
                    term = leaking_result.terminating_event
                    if term.kind == CFGEventKind.RAISE or term.label == "RAISE":
                        msg = f"opened at line {acquire.line}, no close() found on exception path at line {term.line}"
                    elif term.kind == CFGEventKind.RETURN or term.label.startswith("return") or term.label == "RETURN":
                        msg = f"opened at line {acquire.line}, no close() found on return path at line {term.line}"
                    else:
                        msg = f"opened at line {acquire.line}, no close() found before exit at line {term.line}"
                else:
                    msg = f"opened at line {acquire.line}, no close() found before function exit"

                path_trace = leaking_result.path_trace if leaking_result else []

                details = {
                    "variable": acquire.target,
                    "confidence": resource_confidence(results),
                    "path_trace": path_trace,
                    "paths": [
                        {"state": result.state.value, "blocks": result.path}
                        for result in results
                    ],
                }
                if loop_leak_result is not None or acquire.details.get("in_loop"):
                    details["loop_limit_reached"] = True
                    details["max_loops"] = display_limit

                findings.append(
                    Finding(
                        rule_id=rule_ids.get(resource_type, "LKG-R000"),
                        severity=(
                            FindingSeverity.ERROR
                            if status == FindingStatus.DEFINITE_LEAK
                            else FindingSeverity.WARNING
                        ),
                        category=FindingCategory.RESOURCE_LEAK,
                        message=msg,
                        location=SourceLocation(
                            file=file_cfg.path,
                            line=acquire.line,
                            column=acquire.column,
                        ),
                        status=status,
                        resource_type=resource_type,
                        details=details,
                    )
                )

    return findings


def analyze_function(function_cfg: FunctionCFG, max_loops: int | str = "x") -> list[LifecycleResult]:
    results = []

    for block_id, acquire in _find_acquire_blocks(function_cfg):
        if acquire.target is None:
            continue

        results.extend(
            analyze_resource(
                function_cfg,
                block_id,
                acquire.target,
                acquire.line,
                acquire.column,
                max_loops=max_loops,
            )
        )

    return results
