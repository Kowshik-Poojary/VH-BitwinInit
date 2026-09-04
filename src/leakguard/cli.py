import argparse
from pathlib import Path

from .scanner import discover_python_files


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="leakguard",
        description="Static resource-leak analyzer for Python projects.",
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Python file or project directory to scan.",
    )

    args = parser.parse_args()

    root = Path(args.path).resolve()

    if not root.exists():
        parser.error(f"path does not exist: {args.path}")

    files = discover_python_files(root)

    print("LeakGuard")
    print("────────────")
    print(f"Target: {root}")
    print(f"Python files found: {len(files)}")

    for file in files:
        print(f"  • {file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())