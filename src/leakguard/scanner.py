"""Project scanner for discovering Python files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".tox",
        ".eggs",
        "*.egg-info",
        "dist",
        "build",
    }
)


@dataclass
class ScanConfig:
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))
    exclude_patterns: list[str] = field(default_factory=list)
    max_file_size: int | None = None


def _should_exclude_dir(name: str, config: ScanConfig) -> bool:
    if name in config.exclude_dirs:
        return True
    for pattern in config.exclude_patterns:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
    return False


def discover_python_files(path: Path, config: ScanConfig | None = None) -> list[Path]:
    """Recursively discover .py files under path.

    Supports both directory and single-file paths.
    """
    config = config or ScanConfig()
    path = path.resolve()

    if path.is_file():
        if path.suffix == ".py":
            return [path]
        return []

    if not path.is_dir():
        return []

    discovered: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return

        for entry in entries:
            if entry.is_dir():
                if not _should_exclude_dir(entry.name, config):
                    _walk(entry)
            elif entry.is_file() and entry.suffix == ".py":
                discovered.append(entry)

    _walk(path)
    return discovered
