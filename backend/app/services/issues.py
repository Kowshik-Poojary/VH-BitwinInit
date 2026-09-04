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


def get_pr_logs(repo: str, pr_number: int) -> list[dict]:
    db = get_db()
    runs = list(
        db["action_runs"]
        .find({"repo": repo, "pr_number": pr_number})
        .sort("received_at", -1)
    )
    for run in runs:
        run["_id"] = str(run["_id"])
        run["user"] = get_user(run.get("user_id"))
        run["finding_count"] = len(run.get("findings", []))
        run.pop("findings", None)
    return runs


def _issues_for_run(repo: str, run: dict) -> dict:
    """New-vs-pre-existing breakdown of one run's findings.

    A finding is "new" only if this exact run is the one that first
    introduced its fingerprint anywhere in the repo (tracked in
    `repo_issues`, keyed by repo+fingerprint independent of PR/push). A
    finding that pre-dates this run — even if this is the first time *this*
    PR's branch happens to contain it — is reported "pre-existing" along
    with whoever's run first surfaced it.
    """
    db = get_db()
    run_id = str(run["_id"])
    issues = []
    for finding in run.get("findings", []):
        fp = fingerprint(finding)
        record = db["repo_issues"].find_one({"_id": f"{repo}::{fp}"})
        is_new = bool(record) and record.get("first_seen_run_id") == run_id
        first_seen_user = get_user(
            record.get("first_seen_user_id") if record else run.get("user_id")
        )
        issues.append(
            {
                "fingerprint": fp,
                "rule_id": finding.get("rule_id"),
                "severity": finding.get("severity"),
                "message": finding.get("message"),
                "location": finding.get("location"),
                "is_new": is_new,
                "first_seen_at": record.get("first_seen_at") if record else run.get("received_at"),
                "first_seen_user": first_seen_user,
            }
        )

    return {
        "run_id": run_id,
        "pr_number": run.get("pr_number"),
        "conclusion": run.get("conclusion"),
        "received_at": run.get("received_at"),
        "user": get_user(run.get("user_id")),
        "issues": issues,
    }


def get_repo_issues(repo: str) -> dict:
    db = get_db()
    latest_run = db["action_runs"].find_one(
        {"repo": repo}, sort=[("received_at", -1)]
    )
    if not latest_run:
        return {"latest_run_id": None, "issues": []}

    result = _issues_for_run(repo, latest_run)
    result["latest_run_id"] = result["run_id"]
    return result


def get_repo_prs(repo: str) -> list[dict]:
    """One row per PR number that has ever reported a run for this repo."""
    db = get_db()
    pipeline = [
        {"$match": {"repo": repo, "pr_number": {"$ne": None}}},
        {"$sort": {"received_at": -1}},
        {
            "$group": {
                "_id": "$pr_number",
                "run_count": {"$sum": 1},
                "last_run_at": {"$first": "$received_at"},
                "last_conclusion": {"$first": "$conclusion"},
                "last_user_id": {"$first": "$user_id"},
                "total_errors": {"$sum": "$summary.errors"},
            }
        },
        {"$sort": {"last_run_at": -1}},
    ]
    rows = []
    for row in db["action_runs"].aggregate(pipeline):
        rows.append(
            {
                "pr_number": row["_id"],
                "run_count": row["run_count"],
                "last_run_at": row["last_run_at"],
                "last_conclusion": row["last_conclusion"],
                "last_user": get_user(row["last_user_id"]),
                "total_errors": row["total_errors"],
            }
        )
    return rows


def get_pr_issues(repo: str, pr_number: int) -> dict:
    db = get_db()
    latest_run = db["action_runs"].find_one(
        {"repo": repo, "pr_number": pr_number}, sort=[("received_at", -1)]
    )
    if not latest_run:
        return {"latest_run_id": None, "pr_number": pr_number, "issues": []}
    return _issues_for_run(repo, latest_run)
