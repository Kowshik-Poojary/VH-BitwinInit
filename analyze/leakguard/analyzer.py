"""Project analysis orchestration."""

from __future__ import annotations

import time
from pathlib import Path

from leakguard.models import (
    AnalysisError,
    AnalysisErrorType,
    AnalysisStatistics,
    Finding,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    FileAnalysis,
    OperationKind,
    ProjectAnalysis,
    SourceLocation,
)
from leakguard.parser import parse_python_source, read_python_source
from leakguard.scanner import ScanConfig, discover_python_files
from leakguard.visitor import ProjectASTVisitor


def _path_to_module(file_path: Path, project_root: Path) -> str:
    try:
        relative = file_path.relative_to(project_root)
    except ValueError:
        relative = file_path
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else file_path.stem


def analyze_file(
    file_path: Path,
    project_root: Path,
    max_file_size: int | None = None,
) -> tuple[FileAnalysis | None, list[AnalysisError]]:
    """Analyze a single Python file."""
    errors: list[AnalysisError] = []
    path_str = str(file_path)

    if max_file_size is not None:
        try:
            size = file_path.stat().st_size
            if size > max_file_size:
                err = AnalysisError(
                    error_type=AnalysisErrorType.SIZE_LIMIT,
                    file=path_str,
                    message=f"File size {size} exceeds limit {max_file_size}",
                )
                return None, [err]
        except OSError as exc:
            return None, [
                AnalysisError(
                    error_type=AnalysisErrorType.READ_ERROR,
                    file=path_str,
                    message=str(exc),
                )
            ]

    read_start = time.perf_counter()
    source, read_error = read_python_source(file_path)
    read_ms = (time.perf_counter() - read_start) * 1000

    if read_error is not None:
        return None, [read_error]

    assert source is not None

    parse_start = time.perf_counter()
    tree, parse_error = parse_python_source(source, filename=path_str)
    parse_ms = (time.perf_counter() - parse_start) * 1000

    if parse_error is not None:
        return None, [parse_error]

    assert tree is not None

    module_name = _path_to_module(file_path, project_root)
    extract_start = time.perf_counter()
    visitor = ProjectASTVisitor(filename=path_str, module_name=module_name)
    visitor.visit(tree)
    extract_ms = (time.perf_counter() - extract_start) * 1000

    del tree
    del source

    analysis = visitor.analysis
    analysis.parse_time_ms = parse_ms
    analysis.extract_time_ms = extract_ms
    return analysis, errors


def _aggregate_statistics(
    file_analyses: list[FileAnalysis],
    errors: list[AnalysisError],
    files_discovered: int,
    scan_time_ms: float,
    total_time_ms: float,
) -> AnalysisStatistics:
    stats = AnalysisStatistics(
        files_discovered=files_discovered,
        files_analyzed=len(file_analyses),
        files_skipped=files_discovered - len(file_analyses) - len(errors),
        parse_errors=sum(
            1 for e in errors if e.error_type == AnalysisErrorType.PARSE_ERROR
        ),
        read_errors=sum(
            1 for e in errors if e.error_type == AnalysisErrorType.READ_ERROR
        ),
        size_limit_errors=sum(
            1 for e in errors if e.error_type == AnalysisErrorType.SIZE_LIMIT
        ),
        scan_time_ms=scan_time_ms,
        total_time_ms=total_time_ms,
    )

    parse_total = 0.0
    extract_total = 0.0

    for fa in file_analyses:
        stats.total_functions += len(fa.functions)
        stats.total_classes += len(fa.classes)
        stats.total_calls += len(fa.calls)
        stats.context_managers += len(fa.context_managers)
        parse_total += fa.parse_time_ms
        extract_total += fa.extract_time_ms

        for op in fa.resource_operations:
            if op.kind == OperationKind.ACQUIRE and op.resource_type:
                stats.resource_acquisitions[op.resource_type] = (
                    stats.resource_acquisitions.get(op.resource_type, 0) + 1
                )
            elif op.kind == OperationKind.CLOSE:
                stats.resource_closes += 1

    stats.parse_time_ms = parse_total
    stats.extract_time_ms = extract_total
    return stats


def _errors_to_findings(errors: list[AnalysisError]) -> list[Finding]:
    findings: list[Finding] = []
    for err in errors:
        rule_id = {
            AnalysisErrorType.PARSE_ERROR: "LKG-E001",
            AnalysisErrorType.READ_ERROR: "LKG-E002",
            AnalysisErrorType.SIZE_LIMIT: "LKG-E003",
            AnalysisErrorType.ANALYSIS_ERROR: "LKG-E004",
        }.get(err.error_type, "LKG-E000")

        findings.append(
            Finding(
                rule_id=rule_id,
                severity=FindingSeverity.ERROR,
                category=FindingCategory.ANALYSIS,
                message=err.message,
                location=SourceLocation(
                    file=err.file,
                    line=err.line or 0,
                    column=err.column or 0,
                ),
                status=FindingStatus.ERROR,
                details={"error_type": err.error_type.value},
            )
        )
    return findings


def analyze_project_structure(
    path: str | Path,
    *,
    exclude_dirs: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
    max_file_size: int | None = None,
) -> ProjectAnalysis:
    """Analyze project structure and return structured ProjectAnalysis."""
    total_start = time.perf_counter()
    project_path = Path(path).resolve()

    config = ScanConfig(
        exclude_dirs=exclude_dirs or ScanConfig().exclude_dirs,
        exclude_patterns=exclude_patterns or [],
        max_file_size=max_file_size,
    )

    scan_start = time.perf_counter()
    if project_path.is_file():
        py_files = discover_python_files(project_path, config)
        project_root = project_path.parent
    else:
        py_files = discover_python_files(project_path, config)
        project_root = project_path
    scan_time_ms = (time.perf_counter() - scan_start) * 1000

    file_analyses: list[FileAnalysis] = []
    errors: list[AnalysisError] = []

    for py_file in py_files:
        try:
            analysis, file_errors = analyze_file(
                py_file, project_root, max_file_size=config.max_file_size
            )
        except Exception as exc:
            errors.append(
                AnalysisError(
                    error_type=AnalysisErrorType.ANALYSIS_ERROR,
                    file=str(py_file),
                    message=f"Unexpected analysis error: {exc}",
                )
            )
            continue

        errors.extend(file_errors)
        if analysis is not None:
            file_analyses.append(analysis)

    total_time_ms = (time.perf_counter() - total_start) * 1000
    statistics = _aggregate_statistics(
        file_analyses,
        errors,
        files_discovered=len(py_files),
        scan_time_ms=scan_time_ms,
        total_time_ms=total_time_ms,
    )

    return ProjectAnalysis(
        project_path=str(project_path),
        file_analyses=file_analyses,
        errors=errors,
        statistics=statistics,
    )


def analyze_project(
    path: str | Path,
    *,
    exclude_dirs: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
    max_file_size: int | None = None,
) -> list[Finding]:
    """Public API: analyze a project and return findings.

    Currently returns diagnostic findings for analysis errors.
    Resource leak classification will be added by the lifecycle engine.
    """
    project = analyze_project_structure(
        path,
        exclude_dirs=exclude_dirs,
        exclude_patterns=exclude_patterns,
        max_file_size=max_file_size,
    )
    return _errors_to_findings(project.errors)
