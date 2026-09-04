"""Command-line interface for LeakGuard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .baseline import filter_baseline, load_baseline, write_baseline
from .detector import Finding
from .fixer import fix_finding
from .reporting import json_report, sarif_report
from .rules import load_rules
from .scanner import ScanResult, scan_path


def _format_finding(finding: Finding) -> str:
    return (
        "X Resource leak\n"
        f"  Resource: {finding.resource_type}\n"
        f"  Opened: {finding.filename}:{finding.opened_line}\n"
        f"  Variable: {finding.variable}\n"
        f"  Scope: {finding.scope}\n"
        f"  {finding.reason}"
    )


def _format_scan_error(filename: str, message: str) -> str:
    return f"  {filename}: {message}"


def _scan_path(path: Path) -> ScanResult:
    return scan_path(path)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "baseline":
        return _baseline_command(arguments[1:])
    if arguments and arguments[0] == "scan":
        arguments = arguments[1:]

    parser = argparse.ArgumentParser(
        prog="leakguard",
        description="Detect basic Python file-resource leaks with AST analysis.",
    )
    parser.add_argument("path", type=Path, help="Python file or directory to analyze")
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        help="JSON resource-rule configuration file",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Ignore findings already present in this baseline JSON file",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply and verify conservative fixes for simple file leaks",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help="Skip a directory name; may be repeated",
    )
    args = parser.parse_args(arguments)

    if not args.path.exists():
        print(f"LeakGuard: path not found: {args.path}", file=sys.stderr)
        return 2
    if args.path.is_file() and args.path.suffix != ".py":
        print(f"LeakGuard: expected a .py file: {args.path}", file=sys.stderr)
        return 2

    try:
        result = scan_path(
            args.path,
            load_rules(args.rules),
            frozenset(args.exclude),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"LeakGuard: invalid rules: {error}", file=sys.stderr)
        return 2
    if args.baseline:
        try:
            result = ScanResult(
                result.files,
                filter_baseline(result.findings, load_baseline(args.baseline)),
                result.errors,
            )
        except (OSError, ValueError, TypeError) as error:
            print(f"LeakGuard: invalid baseline: {error}", file=sys.stderr)
            return 2

    if args.fix and result.findings:
        changed = sum(fix_finding(finding) for finding in result.findings)
        if changed:
            result = scan_path(
                args.path,
                load_rules(args.rules),
                frozenset(args.exclude),
            )

    if args.format == "json":
        print(json_report(result.findings))
        return 2 if result.errors else (1 if result.findings else 0)
    if args.format == "sarif":
        print(sarif_report(result.findings))
        return 2 if result.errors else (1 if result.findings else 0)

    print("LeakGuard")
    print("---------")
    print(f"Scanning {len(result.files)} Python file(s)...")
    print()
    if result.errors:
        print(f"{len(result.errors)} file(s) could not be analyzed:")
        for error in result.errors:
            print(_format_scan_error(error.filename, error.message))
        print()

    if result.findings:
        print(f"{len(result.findings)} resource leak(s) found")
        print()
        for finding in result.findings:
            print(_format_finding(finding))
        return 1

    if result.errors:
        print("Scan incomplete.")
        return 2

    print("No resource leaks found.")
    return 0


def _baseline_command(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="leakguard baseline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("path", type=Path)
    create.add_argument("--output", type=Path, default=Path("leakguard-baseline.json"))
    args = parser.parse_args(arguments)
    if not args.path.exists():
        print(f"LeakGuard: path not found: {args.path}", file=sys.stderr)
        return 2
    result = scan_path(args.path)
    if result.errors:
        print("LeakGuard: cannot create baseline from an incomplete scan", file=sys.stderr)
        return 2
    write_baseline(args.output, result.findings)
    print(f"Wrote {len(result.findings)} finding(s) to {args.output}")
    return 0
