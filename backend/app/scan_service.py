"""Clone a public git repo and run the LeakGuard analyzer against it."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Callable

from leakguard.analyzer import analyze_project
from leakguard.models import FindingSeverity

from app.db import get_db

ProgressCallback = Callable[[str, dict], None]

_URL_RE = re.compile(r"^https://[\w.-]+/[\w.\-~/]+?(?:\.git)?/?$")

CLONE_TIMEOUT_SECONDS = 60


class ScanError(Exception):
    """Raised when a repo URL can't be validated or cloned."""


def _validate_url(repo_url: str) -> str:
    repo_url = repo_url.strip()
    if not _URL_RE.match(repo_url):
        raise ScanError("Only public https:// git repository URLs are supported")
    return repo_url


def _clone_repo(repo_url: str, dest: str) -> None:
    # This tool is documented as "public repos only" -- explicitly strip any
    # locally-configured git credential helper and disable interactive auth
    # prompts, so a private repo fails cleanly instead of silently succeeding
    # via whatever credentials happen to be cached on the machine running
    # this backend.
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        subprocess.run(
            [
                "git",
                "-c", "credential.helper=",
                "-c", "core.askPass=",
                "clone", "--depth", "1", repo_url, dest,
            ],
            check=True,
            capture_output=True,
            timeout=CLONE_TIMEOUT_SECONDS,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise ScanError(f"Could not clone repository: {exc.stderr.strip()[:500]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ScanError("Cloning the repository timed out") from exc


def _summarize(findings: list) -> dict:
    summary = {"total": len(findings), "errors": 0, "warnings": 0, "info": 0}
    for finding in findings:
        if finding.severity == FindingSeverity.ERROR:
            summary["errors"] += 1
        elif finding.severity == FindingSeverity.WARNING:
            summary["warnings"] += 1
        else:
            summary["info"] += 1
    return summary


def _by_rule(findings: list) -> list[dict]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
    return [
        {"rule_id": rule_id, "count": count}
        for rule_id, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def _relativize(file_path: str, root: str) -> str:
    """Strip the temp clone dir prefix off a finding's file path.

    Windows can report the same directory via different short/long path
    spellings (8.3 vs long names) for the mkdtemp root vs. the paths returned
    by directory walking, so a plain os.path.relpath can wander "up and back
    down" instead of stripping cleanly. Anchoring on the temp dir's unique
    basename (the random mkdtemp suffix) sidesteps that entirely.
    """
    normalized = file_path.replace("\\", "/")
    marker = "/" + os.path.basename(root) + "/"
    idx = normalized.find(marker)
    if idx == -1:
        try:
            return os.path.relpath(file_path, root).replace("\\", "/")
        except ValueError:
            return normalized
    return normalized[idx + len(marker) :]


def run_scan(repo_url: str, on_progress: ProgressCallback | None = None) -> dict:
    def emit(step: str, **data):
        if on_progress:
            on_progress(step, data)

    repo_url = _validate_url(repo_url)
    emit("validated", repo_url=repo_url)

    tmpdir = tempfile.mkdtemp(prefix="leakguard-scan-")
    try:
        emit("cloning", repo_url=repo_url)
        _clone_repo(repo_url, tmpdir)
        emit("cloned")

        def analyzer_progress(step: str, data: dict):
            emit(step, **data)

        findings = analyze_project(tmpdir, on_progress=analyzer_progress)

        emit("summarizing")
        summary = _summarize(findings)
        by_rule = _by_rule(findings)

        finding_dicts = []
        for f in findings:
            d = f.to_dict()
            d["location"]["file"] = _relativize(d["location"]["file"], tmpdir)
            finding_dicts.append(d)

        doc = {
            "repo_url": repo_url,
            "created_at": datetime.now(timezone.utc),
            "summary": summary,
            "by_rule": by_rule,
            "findings": finding_dicts,
        }
        emit("saving")
        inserted = get_db()["scans"].insert_one(doc)
        doc["_id"] = str(inserted.inserted_id)
        emit("done", scan_id=doc["_id"])
        return doc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
