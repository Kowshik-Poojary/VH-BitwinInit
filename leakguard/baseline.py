"""Baseline creation and filtering for known findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .detector import Finding


def finding_key(finding: Finding) -> str:
    return "|".join(
        (
            finding.filename,
            str(finding.opened_line),
            finding.resource_type,
            finding.variable,
        )
    )


def load_baseline(path: str | Path) -> set[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(payload.get("findings", []))


def write_baseline(path: str | Path, findings: Iterable[Finding]) -> None:
    keys = sorted(finding_key(finding) for finding in findings)
    Path(path).write_text(
        json.dumps({"version": 1, "findings": keys}, indent=2) + "\n",
        encoding="utf-8",
    )


def filter_baseline(
    findings: Iterable[Finding],
    baseline: set[str],
) -> tuple[Finding, ...]:
    return tuple(finding for finding in findings if finding_key(finding) not in baseline)
