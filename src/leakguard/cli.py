"""LeakGuard command-line interface."""

from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

from leakguard.analyzer import analyze_project_structure
from leakguard.serialization import format_human_report, project_analysis_to_json
from leakguard.analyzer import analyze_project
from leakguard.models import Finding, FindingCategory
from leakguard.reporter import (
    post_github_pr_review,
    render_json,
    render_sarif,
    render_text,
    report_run_to_backend,
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
    scan_parser.add_argument("path", type=str, nargs="+")
    scan_parser.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    scan_parser.add_argument("--output", type=str, default=None)
    scan_parser.add_argument("--fail-on", choices=["error", "warning", "any"], default="error")
    scan_parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")
    scan_parser.add_argument(
        "--comment-pr",
        action="store_true",
        help="Post inline review comments to GitHub PR when GITHUB_TOKEN is available",
    )
    scan_parser.add_argument(
        "--report-url",
        type=str,
        default=os.environ.get("LEAKGUARD_REPORT_URL", ""),
        help="Base URL of the LeakGuard web backend to report this run's summary to (admin dashboard)",
    )
    scan_parser.add_argument(
        "--report-token",
        type=str,
        default=os.environ.get("LEAKGUARD_INGEST_TOKEN", ""),
        help="Shared-secret token sent as X-LeakGuard-Token when posting to --report-url",
    )
    scan_parser.add_argument(
        "--max-loops",
        default="x",
        help="Upper limit of loop iterations to traverse during leak analysis (default: 'x')",
    )
    scan_parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "After reporting findings, interactively offer to auto-apply quick fixes "
            "(wraps a leaked acquire in a 'with' block) for findings where it's safe to do so"
        ),
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
    paths = [Path(p) for p in args.path]
    for path in paths:
        if not path.exists():
            print(f"Error: path does not exist: {path}", file=sys.stderr)
            return 2

    findings = []
    for path in paths:
        findings.extend(analyze_project(path, max_loops=args.max_loops))
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

    if args.fix:
        _run_interactive_fix(findings)

    blocking = {
        "error": {"ERROR"},
        "warning": {"ERROR", "WARNING"},
        "any": {"ERROR", "WARNING", "INFO"},
    }[args.fail_on]
    is_blocked = any(finding.severity.value in blocking for finding in findings)

    if args.report_url:
        report_run_to_backend(
            findings, args.report_url, is_blocked, report_token=args.report_token or None
        )

    return 1 if is_blocked else 0


def _run_interactive_fix(findings: list[Finding]) -> None:
    from leakguard.fixer import build_with_fix

    leak_findings = [f for f in findings if f.category == FindingCategory.RESOURCE_LEAK]
    if not leak_findings:
        return

    by_file: dict[str, list[Finding]] = {}
    for finding in leak_findings:
        by_file.setdefault(finding.location.file, []).append(finding)

    interactive = sys.stdin.isatty()

    print("\n" + "=" * 60)
    print("  Quick Fix")
    print("=" * 60)
    if not interactive:
        print(
            "(no interactive terminal attached - showing suggestions only, none applied)"
        )

    apply_all = False
    fixed = 0
    considered = 0

    for file_path, file_findings in by_file.items():
        path = Path(file_path)
        for finding in sorted(file_findings, key=lambda f: f.location.line):
            try:
                source = path.read_text(encoding="utf-8", newline="")
            except OSError as exc:
                print(f"  Skipping {file_path}: {exc}", file=sys.stderr)
                continue

            suggestion = build_with_fix(source, finding)
            if suggestion is None:
                continue

            considered += 1
            print(
                f"\n{file_path}:{finding.location.line}  {finding.rule_id}  {finding.message}"
            )
            print(suggestion.preview)

            if not interactive:
                continue

            if not apply_all:
                answer = input("Apply this fix? [y/N/a=all/q=quit]: ").strip().lower()
                if answer == "q":
                    print("Stopped applying quick fixes.")
                    return
                if answer == "a":
                    apply_all = True
                elif answer != "y":
                    continue

            path.write_text("".join(suggestion.new_lines), encoding="utf-8", newline="")
            fixed += 1
            print(f"  Fixed: wrapped '{finding.details.get('variable')}' in a with-block.")

    if considered == 0:
        print("\nNo automatic quick fixes available for the detected findings.")
    elif not interactive:
        print(f"\n{considered} quick fix(es) available - run `leakguard scan ... --fix` from an interactive terminal to apply.")
    else:
        print(f"\nApplied {fixed} of {considered} available quick fix(es).")
        print("Re-run `leakguard scan` to verify the remaining findings.")


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
