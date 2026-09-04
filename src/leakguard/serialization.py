"""JSON serialization for LeakGuard analysis results."""

from __future__ import annotations

import json
from typing import Any

from leakguard.models import Finding, ProjectAnalysis


def project_analysis_to_json(project: ProjectAnalysis, indent: int = 2) -> str:
    return json.dumps(project.to_dict(), indent=indent)


def findings_to_json(findings: list[Finding], indent: int = 2) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=indent)


def format_human_report(project: ProjectAnalysis) -> str:
    stats = project.statistics
    lines = [
        "LeakGuard",
        "================================",
        "",
        f"Project: {project.project_path}",
        "",
        f"Files discovered: {stats.files_discovered}",
        f"Files analyzed:   {stats.files_analyzed}",
        f"Parse errors:     {stats.parse_errors}",
    ]

    if stats.read_errors:
        lines.append(f"Read errors:      {stats.read_errors}")
    if stats.size_limit_errors:
        lines.append(f"Size limit errors:{stats.size_limit_errors}")

    lines.extend(
        [
            "",
            f"Functions:         {stats.total_functions}",
            f"Classes:            {stats.total_classes}",
            f"Calls:            {stats.total_calls}",
            "",
            "Resource acquisitions:",
        ]
    )

    if stats.resource_acquisitions:
        for resource_type, count in sorted(stats.resource_acquisitions.items()):
            lines.append(f"    {resource_type + ':':<12}{count}")
    else:
        lines.append("    (none)")

    lines.extend(
        [
            "",
            f"Close operations: {stats.resource_closes}",
            f"Context managers: {stats.context_managers}",
            "",
            "Timing:",
            f"    Scan:     {stats.scan_time_ms:.1f} ms",
            f"    Parse:    {stats.parse_time_ms:.1f} ms",
            f"    Extract:  {stats.extract_time_ms:.1f} ms",
            f"    Total:    {stats.total_time_ms:.1f} ms",
        ]
    )

    if project.errors:
        lines.extend(["", "Analysis errors:"])
        for err in project.errors:
            loc = ""
            if err.line is not None:
                loc = f":{err.line}"
                if err.column is not None:
                    loc += f":{err.column}"
            lines.append(f"  [{err.error_type.value}] {err.file}{loc}")
            lines.append(f"    {err.message}")

    lines.extend(["", "Analysis completed."])
    return "\n".join(lines)
