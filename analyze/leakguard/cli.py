"""LeakGuard command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from leakguard.analyzer import analyze_project_structure
from leakguard.serialization import format_human_report, project_analysis_to_json


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

    return 1


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
