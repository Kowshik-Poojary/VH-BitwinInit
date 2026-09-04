"""Safe file reading and AST parsing."""

from __future__ import annotations

import ast
import tokenize
from io import BytesIO
from pathlib import Path

from leakguard.models import AnalysisError, AnalysisErrorType


def read_python_source(path: Path) -> tuple[str | None, AnalysisError | None]:
    """Read a Python file respecting encoding declarations.

    Returns (source, error). On success error is None.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return None, AnalysisError(
            error_type=AnalysisErrorType.READ_ERROR,
            file=str(path),
            message=str(exc),
        )

    try:
        encoding = _detect_encoding(raw_bytes)
        source = raw_bytes.decode(encoding)
        return source, None
    except (UnicodeDecodeError, LookupError, tokenize.TokenError) as exc:
        return None, AnalysisError(
            error_type=AnalysisErrorType.READ_ERROR,
            file=str(path),
            message=f"Encoding error: {exc}",
        )


def _detect_encoding(raw_bytes: bytes) -> str:
    """Detect encoding using Python's tokenize module."""
    try:
        encoding, _ = tokenize.detect_encoding(BytesIO(raw_bytes).readline)
        return encoding
    except (SyntaxError, UnicodeDecodeError, tokenize.TokenError):
        return "utf-8"


def parse_python_source(
    source: str, filename: str = "<unknown>"
) -> tuple[ast.Module | None, AnalysisError | None]:
    """Parse Python source into an AST module.

    Returns (tree, error). On success error is None.
    """
    try:
        tree = ast.parse(source, filename=filename)
        return tree, None
    except SyntaxError as exc:
        return None, AnalysisError(
            error_type=AnalysisErrorType.PARSE_ERROR,
            file=filename,
            message=exc.msg or str(exc),
            line=exc.lineno,
            column=exc.offset,
        )
