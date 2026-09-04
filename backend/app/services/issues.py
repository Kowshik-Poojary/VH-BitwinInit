"""Cross-run issue identity: who/when a finding was first seen in a repo.

Each finding is fingerprinted by (rule_id, file, line) within a repo. The
first run that reports a fingerprint "owns" it (first_seen_user_id); every
later run that reports the same fingerprint is a pre-existing issue, not a
new one introduced by that run's user.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.db import get_db

UNKNOWN_USER = {"_id": "unknown", "name": "Unknown / unattributed"}


def fingerprint(finding: dict) -> str:
    location = finding.get("location", {})
    key = f"{finding.get('rule_id')}|{location.get('file')}|{location.get('line')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def get_user(user_id: str | None) -> dict:
    if not user_id:
        return UNKNOWN_USER
    doc = get_db()["users"].find_one({"_id": user_id})
    if not doc:
        return {"_id": user_id, "name": user_id}
    return doc


def ingest_action_run(payload: dict, *, received_at: datetime | None = None) -> dict:
    """Store an action-run report and update each finding's first-seen record.

    `payload` is the report body: repo, pr_number, sha, user_id, conclusion,
    summary, findings (list of Finding.to_dict()).
    """
    db = get_db()
    received_at = received_at or datetime.now(timezone.utc)

    run_doc = dict(payload)
    run_doc["received_at"] = received_at
    run_doc.setdefault("findings", [])
    inserted = db["action_runs"].insert_one(run_doc)
    run_id = str(inserted.inserted_id)
    run_doc["_id"] = run_id

    repo = payload["repo"]
    user_id = payload.get("user_id")
    for finding in run_doc["findings"]:
        fp = fingerprint(finding)
        location = finding.get("location", {})
        db["repo_issues"].update_one(
            {"_id": f"{repo}::{fp}"},
            {
                "$setOnInsert": {
                    "repo": repo,
                    "fingerprint": fp,
                    "rule_id": finding.get("rule_id"),
                    "file": location.get("file"),
                    "line": location.get("line"),
                    "message": finding.get("message"),
                    "first_seen_run_id": run_id,
                    "first_seen_user_id": user_id,
                    "first_seen_at": received_at,
                }
            },
            upsert=True,
        )

    return run_doc


def get_repo_logs(repo: str) -> list[dict]:
    db = get_db()
    runs = list(
        db["action_runs"].find({"repo": repo}).sort("received_at", -1)
    )
    for run in runs:
        run["_id"] = str(run["_id"])
        run["user"] = get_user(run.get("user_id"))
        run["finding_count"] = len(run.get("findings", []))
        run.pop("findings", None)
    return runs


def get_repo_issues(repo: str) -> dict:
    db = get_db()
    latest_run = db["action_runs"].find_one(
        {"repo": repo}, sort=[("received_at", -1)]
    )
    if not latest_run:
        return {"latest_run_id": None, "issues": []}

    latest_run_id = str(latest_run["_id"])
    issues = []
    for finding in latest_run.get("findings", []):
        fp = fingerprint(finding)
        record = db["repo_issues"].find_one({"_id": f"{repo}::{fp}"})
        is_new = bool(record) and record.get("first_seen_run_id") == latest_run_id
        first_seen_user = get_user(
            record.get("first_seen_user_id") if record else latest_run.get("user_id")
        )
        issues.append(
            {
                "fingerprint": fp,
                "rule_id": finding.get("rule_id"),
                "severity": finding.get("severity"),
                "message": finding.get("message"),
                "location": finding.get("location"),
                "is_new": is_new,
                "first_seen_at": record.get("first_seen_at") if record else latest_run.get("received_at"),
                "first_seen_user": first_seen_user,
            }
        )

    return {"latest_run_id": latest_run_id, "issues": issues}
