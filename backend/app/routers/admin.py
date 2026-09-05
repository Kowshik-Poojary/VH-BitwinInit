"""Admin dashboard aggregation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.db import get_db
from app.services.issues import (
    get_pr_issues,
    get_pr_logs,
    get_repo_issues,
    get_repo_logs,
    get_repo_prs,
)

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/overview")
def overview() -> dict:
    db = get_db()
    action_runs = db["action_runs"]
    scans = db["scans"]

    total_action_runs = action_runs.count_documents({})
    total_pr_runs = action_runs.count_documents({"pr_number": {"$ne": None}})
    total_scans = scans.count_documents({})

    repos_from_actions = set(action_runs.distinct("repo"))
    repos_from_scans = set(scans.distinct("repo_url"))

    findings_agg = list(
        action_runs.aggregate(
            [{"$group": {"_id": None, "total": {"$sum": "$summary.total"}}}]
        )
    )
    total_findings = findings_agg[0]["total"] if findings_agg else 0

    return {
        "total_repos": len(repos_from_actions | repos_from_scans),
        "total_action_runs": total_action_runs,
        "total_pr_runs": total_pr_runs,
        "total_scans": total_scans,
        "total_findings": total_findings,
    }


@router.get("/repos")
def repos() -> list[dict]:
    pipeline = [
        {"$sort": {"received_at": -1}},
        {
            "$group": {
                "_id": "$repo",
                "run_count": {"$sum": 1},
                "pr_numbers": {"$addToSet": "$pr_number"},
                "last_run_at": {"$first": "$received_at"},
                "last_conclusion": {"$first": "$conclusion"},
                "total_errors": {"$sum": "$summary.errors"},
            }
        },
        {"$sort": {"last_run_at": -1}},
    ]
    rows = []
    for row in get_db()["action_runs"].aggregate(pipeline):
        pr_count = sum(1 for pr in row["pr_numbers"] if pr is not None)
        rows.append(
            {
                "repo": row["_id"],
                "run_count": row["run_count"],
                "pr_count": pr_count,
                "last_run_at": row["last_run_at"],
                "last_conclusion": row["last_conclusion"],
                "total_errors": row["total_errors"],
            }
        )
    return rows


@router.get("/recent")
def recent(limit: int = 20) -> list[dict]:
    docs = list(
        get_db()["action_runs"].find().sort("received_at", -1).limit(limit)
    )
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        doc["finding_count"] = len(doc.get("findings", []))
        doc.pop("findings", None)
    return docs


@router.get("/users")
def users() -> list[dict]:
    return list(get_db()["users"].find())


@router.get("/repos/{repo:path}/prs/{pr_number:int}/logs")
def pr_logs(repo: str, pr_number: int) -> list[dict]:
    return get_pr_logs(repo, pr_number)


@router.get("/repos/{repo:path}/prs/{pr_number:int}/issues")
def pr_issues(repo: str, pr_number: int) -> dict:
    return get_pr_issues(repo, pr_number)


@router.get("/repos/{repo:path}/prs")
def repo_prs(repo: str) -> list[dict]:
    return get_repo_prs(repo)


@router.get("/repos/{repo:path}/logs")
def repo_logs(repo: str) -> list[dict]:
    return get_repo_logs(repo)


@router.get("/repos/{repo:path}/issues")
def repo_issues(repo: str) -> dict:
    return get_repo_issues(repo)
