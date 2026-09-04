"""Output renderers for LeakGuard findings."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

from leakguard.models import Finding, FindingSeverity

SARIF_RULES = [
    {
        "id": "LKG-R001",
        "name": "FileResourceLeak",
        "shortDescription": {"text": "Unclosed file handle detected across code path"},
        "fullDescription": {
            "text": "A file resource was acquired via open() or similar but not closed on all paths to exit."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Ensure file is closed via try/finally or a 'with' context manager."},
    },
    {
        "id": "LKG-R002",
        "name": "SocketResourceLeak",
        "shortDescription": {"text": "Unclosed network socket detected across code path"},
        "fullDescription": {
            "text": "A socket was created but not closed or shutdown on all paths to exit."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Ensure socket is closed explicitly or wrapped in cleanup logic."},
    },
    {
        "id": "LKG-R003",
        "name": "DatabaseConnectionLeak",
        "shortDescription": {"text": "Unclosed database connection detected across code path"},
        "fullDescription": {
            "text": "A database connection was established but not closed on all paths to exit."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Ensure database connection is closed or managed via context manager."},
    },
    {
        "id": "LKG-R004",
        "name": "TempFileResourceLeak",
        "shortDescription": {"text": "Unclosed temporary file resource detected"},
        "fullDescription": {
            "text": "A NamedTemporaryFile or TemporaryFile was acquired without guaranteed closure."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Ensure temporary file is closed or managed with 'with' block."},
    },
    {
        "id": "LKG-E001",
        "name": "ParseError",
        "shortDescription": {"text": "Python syntax error prevented analysis"},
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "LKG-E002",
        "name": "ReadError",
        "shortDescription": {"text": "Failed to read source file"},
        "defaultConfiguration": {"level": "error"},
    },
]


def render_json(findings: list[Finding]) -> str:
    return json.dumps(
        {
            "summary": {
                "total_findings": len(findings),
                "errors": sum(1 for f in findings if f.severity == FindingSeverity.ERROR),
                "warnings": sum(1 for f in findings if f.severity == FindingSeverity.WARNING),
            },
            "findings": [f.to_dict() for f in findings],
        },
        indent=2,
    )


def render_text(findings: list[Finding], use_color: bool = True) -> str:
    lines = [
        "============================================================",
        "  LeakGuard — Static Resource Leak Analysis Report",
        "============================================================",
        "",
    ]
    if not findings:
        lines.append("  All resources safely managed. No leaks detected!")
        lines.append("")
        return "\n".join(lines)

    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.location.file, []).append(finding)

    error_count = 0
    warning_count = 0

    for file_path, file_findings in by_file.items():
        lines.append(f"File: {file_path}")
        lines.append("-" * min(len(file_path) + 6, 60))

        for f in file_findings:
            if f.severity == FindingSeverity.ERROR:
                error_count += 1
            elif f.severity == FindingSeverity.WARNING:
                warning_count += 1

            confidence = f.details.get("confidence", "HIGH")
            loc = f"{f.location.file}:{f.location.line}:{f.location.column}"
            lines.append(
                f"  {loc}  {f.rule_id}  {f.severity.value}  [{confidence}]  {f.message}"
            )

            path_trace = f.details.get("path_trace", [])
            if path_trace:
                lines.append("    Path trace:")
                for step in path_trace:
                    lines.append(
                        f"      line {step.get('line')}: {step.get('event', '')}"
                    )
        lines.append("")

    lines.append("-" * 60)
    lines.append(
        f"Summary: {len(findings)} finding(s) ({error_count} errors, {warning_count} warnings)"
    )
    lines.append("=" * 60)
    return "\n".join(lines)


def _to_sarif_uri(file_path: str) -> str:
    try:
        rel = os.path.relpath(file_path, os.getcwd())
        return rel.replace("\\", "/")
    except Exception:
        return file_path.replace("\\", "/")


def render_sarif(findings: list[Finding]) -> str:
    results: list[dict[str, Any]] = []

    for finding in findings:
        sarif_level = "error" if finding.severity == FindingSeverity.ERROR else "warning"
        uri = _to_sarif_uri(finding.location.file)

        result_dict: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "level": sarif_level,
            "message": {"text": finding.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": uri},
                        "region": {
                            "startLine": max(finding.location.line, 1),
                            "startColumn": max(finding.location.column + 1, 1),
                        },
                    }
                }
            ],
            "properties": {
                "confidence": finding.details.get("confidence", "HIGH"),
                "resourceType": finding.resource_type or "resource",
            },
        }

        path_trace = finding.details.get("path_trace")
        if path_trace:
            thread_flow_locations = []
            for step in path_trace:
                step_uri = _to_sarif_uri(step.get("file") or finding.location.file)
                thread_flow_locations.append(
                    {
                        "location": {
                            "physicalLocation": {
                                "artifactLocation": {"uri": step_uri},
                                "region": {
                                    "startLine": max(step.get("line", 1), 1),
                                    "startColumn": max(step.get("column", 0) + 1, 1),
                                },
                            },
                            "message": {"text": step.get("event", "trace point")},
                        }
                    }
                )
            result_dict["codeFlows"] = [
                {"threadFlows": [{"locations": thread_flow_locations}]}
            ]

        results.append(result_dict)

    sarif_log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "LeakGuard",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/leakguard/leakguard",
                        "rules": SARIF_RULES,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif_log, indent=2)


def _extract_pr_context(event_path: str | None = None) -> tuple[str | None, int | None]:
    """Best-effort (repo_full_name, pr_number) from the GitHub Actions event payload."""
    gh_event = event_path or os.environ.get("GITHUB_EVENT_PATH")
    gh_repo = os.environ.get("GITHUB_REPOSITORY")

    pr_number = None
    repo_name = gh_repo
    if gh_event:
        try:
            event_file = Path(gh_event)
            if event_file.exists():
                event_data = json.loads(event_file.read_text(encoding="utf-8"))
                pr_number = event_data.get("pull_request", {}).get("number")
                if not pr_number:
                    pr_number = event_data.get("number")
                repo_name = repo_name or event_data.get("repository", {}).get("full_name")
        except Exception:
            pass
    return repo_name, pr_number


def post_github_pr_review(
    findings: list[Finding],
    token: str | None = None,
    event_path: str | None = None,
) -> bool:
    """Post inline PR review comments when running in GitHub Actions environment."""
    gh_token = token or os.environ.get("GITHUB_TOKEN")
    gh_event = event_path or os.environ.get("GITHUB_EVENT_PATH")

    if not gh_token or not gh_event:
        return False

    try:
        repo_name, pr_number = _extract_pr_context(gh_event)
        if not pr_number or not repo_name:
            return False

        comments: list[dict[str, Any]] = []
        for finding in findings:
            if finding.location.line <= 0:
                continue
            rel_file = _to_sarif_uri(finding.location.file)
            confidence = finding.details.get("confidence", "HIGH")
            comments.append(
                {
                    "path": rel_file,
                    "line": finding.location.line,
                    "body": (
                        f"🛡️ **LeakGuard ({finding.rule_id})** — `{finding.severity.value}` [{confidence}]\n\n"
                        f"{finding.message}\n"
                        f"> Resource `{finding.details.get('variable', '')}` ({finding.resource_type}) must be safely closed across all execution paths."
                    ),
                }
            )

        review_body = (
            f"### 🛡️ LeakGuard Static Analysis Results\n\n"
            f"Detected **{len(findings)}** resource issue(s) across the codebase."
        )
        event_type = "REQUEST_CHANGES" if any(f.severity == FindingSeverity.ERROR for f in findings) else "COMMENT"

        payload = {
            "body": review_body,
            "event": event_type,
            "comments": comments,
        }

        url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/reviews"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201)
    except Exception as exc:
        print(f"Note: GitHub PR review comment posting skipped: {exc}", file=sys.stderr)
        return False


def report_run_to_backend(
    findings: list[Finding],
    report_url: str,
    blocked: bool,
) -> bool:
    """POST a summary of this run to the LeakGuard web backend's admin dashboard.

    Best-effort only: a backend outage or misconfigured URL must never fail CI.
    """
    if not report_url:
        return False

    try:
        repo_name, pr_number = _extract_pr_context()
        if not repo_name:
            return False

        summary = {
            "total": len(findings),
            "errors": sum(1 for f in findings if f.severity == FindingSeverity.ERROR),
            "warnings": sum(1 for f in findings if f.severity == FindingSeverity.WARNING),
            "info": sum(1 for f in findings if f.severity not in (FindingSeverity.ERROR, FindingSeverity.WARNING)),
        }
        findings_payload = []
        for f in findings:
            d = f.to_dict()
            d["location"]["file"] = _to_sarif_uri(f.location.file)
            findings_payload.append(d)

        payload = {
            "repo": repo_name,
            "pr_number": pr_number,
            "sha": os.environ.get("GITHUB_SHA"),
            "user_id": os.environ.get("LEAKGUARD_USER_ID"),
            "conclusion": "fail" if blocked else "pass",
            "summary": summary,
            "findings": findings_payload,
        }

        req = urllib.request.Request(
            report_url.rstrip("/") + "/api/reports/action-run",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception as exc:
        print(f"Note: reporting run to backend skipped: {exc}", file=sys.stderr)
        return False
