from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from leakguard.cfg import (
    BlockKind,
    CFGEvent,
    CFGEventKind,
    CFGProject,
    FunctionCFG,
)
from leakguard.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    ProjectAnalysis,
    SourceLocation,
)


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
) -> list[list[int]]:
    return function_cfg.paths_to_exit_from(acquire_block_id)


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

    events.sort(key=lambda event: (event.line, event.column))

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
) -> list[LifecycleResult]:

    acquire = _get_acquire_event(
        function_cfg,
        acquire_block_id,
        target,
        acquire_line,
        acquire_column,
    )

    if acquire is None:
        return []

    paths = _get_paths_from_acquire(
        function_cfg,
        acquire_block_id,
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
        )

        results.append(
            LifecycleResult(
                state=state,
                acquire_line=acquire.line,
                message=f"Resource {target} ends as {state.value}",
                path=path,
                terminating_event=term_event,
                path_trace=path_trace,
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


def lifecycle_findings(
    project: ProjectAnalysis,
    cfg_project: CFGProject,
) -> list[Finding]:
    findings: list[Finding] = []
    rule_ids = {
        "file": "LKG-R001",
        "socket": "LKG-R002",
        "database": "LKG-R003",
        "tempfile": "LKG-R004",
    }

    for file_cfg in cfg_project.files:
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
                if leaking_result and leaking_result.terminating_event:
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
                        details={
                            "variable": acquire.target,
                            "confidence": resource_confidence(results),
                            "path_trace": path_trace,
                            "paths": [
                                {"state": result.state.value, "blocks": result.path}
                                for result in results
                            ],
                        },
                    )
                )

    return findings


def analyze_function(function_cfg: FunctionCFG) -> list[LifecycleResult]:
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
            )
        )

    return results
