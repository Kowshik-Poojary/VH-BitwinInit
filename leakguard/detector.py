"""Detect basic function-local resource leaks."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .cfg import CFGBuilder
from .dataflow import DataflowAnalyzer
from .parser import ScopeFacts
from .resources.detector import ResourceDetector


@dataclass(frozen=True)
class Finding:
    filename: str
    scope: str
    resource_type: str
    variable: str
    opened_line: int
    closed_line: int | None
    reason: str
    classification: str = "DEFINITE_LEAK"
    evidence: tuple[int, ...] = ()


def detect(scopes: tuple[ScopeFacts, ...], filename: str) -> tuple[Finding, ...]:
    """Find resources that remain open at the end of their source scope."""
    findings: list[Finding] = []
    resources = ResourceDetector().detect(scopes, filename)
    for resource in resources:
        if not resource.is_closed:
            findings.append(
                Finding(
                    filename=filename,
                    scope=resource.scope,
                    resource_type=resource.resource_type,
                    variable=resource.variable,
                    opened_line=resource.opened_line,
                    closed_line=resource.closed_line,
                    reason="No cleanup found before scope exit.",
                )
            )
    return tuple(findings)


def detect_function(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    scope: ScopeFacts,
    filename: str,
) -> tuple[Finding, ...]:
    """Analyze one function with CFG-aware path-sensitive dataflow."""
    cfg = CFGBuilder().build(function)
    result = DataflowAnalyzer().analyze(cfg, scope.operations)
    lifecycle_resources = ResourceDetector().detect((scope,), filename)
    escaped_variables = {
        operation.variable
        for operation in scope.operations
        if operation.kind == "return"
    }
    opened_lines = {
        operation.variable: operation.line
        for operation in scope.operations
        if operation.kind == "acquire"
    }
    resource_types = {
        operation.variable: operation.resource_type
        for operation in scope.operations
        if operation.kind == "acquire"
    }
    findings = [
        Finding(
            filename=filename,
            scope=scope.name,
            resource_type=resource_types[variable],
            variable=variable,
            opened_line=opened_lines[variable],
            closed_line=None,
            reason="Resource remains open on at least one reachable path.",
            classification="DEFINITE_LEAK",
            evidence=(opened_lines[variable],),
        )
        for variable in result.leaked_variables
        if variable in opened_lines
    ]
    known = {(finding.variable, finding.opened_line) for finding in findings}
    for resource in lifecycle_resources:
        key = (resource.variable, resource.opened_line)
        if (
            not resource.is_closed
            and resource.variable not in escaped_variables
            and key not in known
        ):
            findings.append(
                Finding(
                    filename=filename,
                    scope=resource.scope,
                    resource_type=resource.resource_type,
                    variable=resource.variable,
                    opened_line=resource.opened_line,
                    closed_line=resource.closed_line,
                    reason="Resource was replaced before cleanup.",
                )
            )
    return tuple(findings)
