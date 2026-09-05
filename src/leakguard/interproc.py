"""Inter-procedural function summaries for parameter-close analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from leakguard.cfg import CFGEventKind, CFGProject, FunctionCFG


@dataclass
class FunctionSummary:
    qualified_name: str
    is_method: bool = False
    # 0-based indices of parameters that are provably closed on ALL paths
    closes_param_indices: set[int] = field(default_factory=set)


def _path_closes_param(
    function_cfg: FunctionCFG,
    path: list[int],
    param_name: str,
) -> bool:
    """Return True if param_name (or any alias) is closed somewhere on this path."""
    aliases: set[str] = {param_name}

    for block_id in path:
        block = function_cfg.get_block(block_id)
        if block is None:
            continue
        events = sorted(block.events, key=lambda e: (e.line, e.column))
        for event in events:
            if event.kind == CFGEventKind.ASSIGN and event.target:
                value = event.details.get("value_expression")
                if value in aliases:
                    aliases.add(event.target)
                elif event.target in aliases:
                    aliases.discard(event.target)
                continue
            if (
                event.kind in (CFGEventKind.CLOSE, CFGEventKind.CONTEXT_MANAGER)
                and event.target in aliases
            ):
                return True
    return False


def _summarize_function(function_cfg: FunctionCFG) -> FunctionSummary:
    func = function_cfg.function
    summary = FunctionSummary(
        qualified_name=func.qualified_name,
        is_method=func.is_method,
    )
    params = func.parameters
    if not params:
        return summary

    paths = function_cfg.paths_to_exit_from(function_cfg.entry_id)
    if not paths:
        return summary

    for idx, param_name in enumerate(params):
        if all(_path_closes_param(function_cfg, path, param_name) for path in paths):
            summary.closes_param_indices.add(idx)

    return summary


def build_summaries(cfg_project: CFGProject) -> dict[str, FunctionSummary]:
    """Build inter-procedural summaries for every function in the project."""
    summaries: dict[str, FunctionSummary] = {}
    for file_cfg in cfg_project.files:
        for function_cfg in file_cfg.functions:
            s = _summarize_function(function_cfg)
            summaries[s.qualified_name] = s
    return summaries
