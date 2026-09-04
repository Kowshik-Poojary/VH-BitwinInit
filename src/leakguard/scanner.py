from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
}


def discover_python_files(root: Path) -> list[Path]:
    """Return Python files under a file or directory."""

    if root.is_file():
        if root.suffix == ".py":
            return [root]
        return []

    files: list[Path] = []

    for path in root.rglob("*.py"):
        if any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue

        files.append(path)

    return sorted(files)