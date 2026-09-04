from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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
) -> ResourceState:
    started = False
    aliases = {target}
    passed_to_function = False

    for event in events:
        if event.kind == CFGEventKind.ACQUIRE and event.target == target:
            if not started:
                if (event.line, event.column) != (acquire_line, acquire_column):
                    continue
                started = True
                continue
            return ResourceState.OPEN

        if not started:
            continue

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
            return ResourceState.ESCAPED

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
            return ResourceState.CLOSED

    if passed_to_function:
        return ResourceState.UNKNOWN
    return ResourceState.OPEN


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

    for path in paths:
        events = _events_for_path(
            function_cfg,
            path,
        )

        state = _classify_path(
            events,
            target,
            acquire.line,
            acquire.column,
        )

        results.append(
            LifecycleResult(
                state=state,
                acquire_line=acquire.line,
                message=f"Resource {target} ends as {state.value}",
                path=path,
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
    if states == {ResourceState.CLOSED}:
        return ResourceState.CLOSED
    if ResourceState.ESCAPED in states:
        return ResourceState.ESCAPED
    return ResourceState.UNKNOWN


def resource_confidence(results: list[LifecycleResult]) -> str:
    if not results:
        return "LOW"

    states = {result.state for result in results}
    if ResourceState.UNKNOWN in states or ResourceState.ESCAPED in states:
        return "LOW"
    if ResourceState.OPEN in states and ResourceState.CLOSED in states:
        return "MEDIUM"
    return "HIGH"


def lifecycle_findings(
    project: ProjectAnalysis,
    cfg_project: CFGProject,
) -> list[Finding]:
    findings: list[Finding] = []
    rule_ids = {
        "file": "LKG-R001",
        "socket": "LKG-R002",
        "database": "LKG-R003",
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
                if state == ResourceState.CLOSED:
                    continue

                status = {
                    ResourceState.LEAKED: FindingStatus.DEFINITE_LEAK,
                    ResourceState.ESCAPED: FindingStatus.ESCAPED,
                    ResourceState.UNKNOWN: FindingStatus.UNKNOWN,
                }.get(state, FindingStatus.UNKNOWN)
                resource_type = acquire.resource_type or "resource"
                findings.append(
                    Finding(
                        rule_id=rule_ids.get(resource_type, "LKG-R000"),
                        severity=(
                            FindingSeverity.ERROR
                            if status == FindingStatus.DEFINITE_LEAK
                            else FindingSeverity.WARNING
                        ),
                        category=FindingCategory.RESOURCE_LEAK,
                        message=(
                            f"Resource {acquire.target} is not guaranteed "
                            "to be closed."
                        ),
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
