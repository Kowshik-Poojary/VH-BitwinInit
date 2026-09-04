"""LeakGuard command-line interface."""

from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

from leakguard.analyzer import analyze_project_structure
from leakguard.serialization import format_human_report, project_analysis_to_json
from leakguard.analyzer import analyze_project
from leakguard.reporter import (
    post_github_pr_review,
    render_json,
    render_sarif,
    render_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leakguard",
        description="LeakGuard - Python resource leak static analyzer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze a Python project or file"
    )
    analyze_parser.add_argument(
        "path",
        type=str,
        help="Path to a Python project directory or single .py file",
    )

    scan_parser = subparsers.add_parser("scan", help="Scan a Python project for resource leaks")
    scan_parser.add_argument("path", type=str)
    scan_parser.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    scan_parser.add_argument("--output", type=str, default=None)
    scan_parser.add_argument("--fail-on", choices=["error", "warning", "any"], default="error")
    scan_parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")
    scan_parser.add_argument(
        "--comment-pr",
        action="store_true",
        help="Post inline review comments to GitHub PR when GITHUB_TOKEN is available",
    )
    analyze_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    analyze_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        dest="exclude_dirs",
        help="Directory name to exclude (can be repeated)",
    )
    analyze_parser.add_argument(
        "--max-file-size",
        type=int,
        default=None,
        help="Maximum file size in bytes; larger files produce SIZE_LIMIT errors",
    )
    analyze_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (reserved for future use, default: 1)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _run_analyze(args)
    if args.command == "scan":
        return _run_scan(args)

    return 1


def _run_scan(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 2

    findings = analyze_project(path)
    confidence_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    minimum = confidence_rank[args.min_confidence.upper()]
    findings = [
        finding
        for finding in findings
        if confidence_rank.get(finding.details.get("confidence", "LOW"), 0) >= minimum
    ]
    renderer = {"text": render_text, "json": render_json, "sarif": render_sarif}[args.format]
    output = renderer(findings)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)

    if args.comment_pr or (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_EVENT_PATH")):
        post_github_pr_review(findings)

    blocking = {
        "error": {"ERROR"},
        "warning": {"ERROR", "WARNING"},
        "any": {"ERROR", "WARNING", "INFO"},
    }[args.fail_on]
    return 1 if any(finding.severity.value in blocking for finding in findings) else 0


def _run_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 2

    if args.workers != 1:
        print(
            "Note: --workers is reserved for future use; using single-process mode.",
            file=sys.stderr,
        )

    from leakguard.scanner import DEFAULT_EXCLUDE_DIRS

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    if args.exclude_dirs:
        exclude_dirs.update(args.exclude_dirs)

    project = analyze_project_structure(
        path,
        exclude_dirs=exclude_dirs,
        max_file_size=args.max_file_size,
    )

    if args.format == "json":
        print(project_analysis_to_json(project))
    else:
        print(format_human_report(project))

    has_errors = bool(project.errors)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
