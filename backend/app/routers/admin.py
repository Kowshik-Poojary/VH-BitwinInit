"""Admin dashboard aggregation and Energy Channeling Radar endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.db import get_db
from app.services.branch_service import get_all_branches
from app.services.issues import (
    get_pr_issues,
    get_pr_logs,
    get_repo_issues,
    get_repo_logs,
    get_repo_prs,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
        pr_count = sum(1 for pr in row.get("pr_numbers", []) if pr is not None)
        rows.append(
            {
                "repo": row["_id"],
                "run_count": row.get("run_count", 0),
                "pr_count": pr_count,
                "last_run_at": row.get("last_run_at"),
                "last_conclusion": row.get("last_conclusion", "pass"),
                "total_errors": row.get("total_errors", 0),
            }
        )
    return rows


@router.get("/hotspots")
def hotspots() -> dict:
    """Energy Channeling Radar: Identifies where the admin should channel engineering focus."""
    db = get_db()
    branches = get_all_branches()

    resource_breakdown: dict[str, int] = {"db": 0, "socket": 0, "file": 0, "tempfile": 0}
    repo_leak_scores: dict[str, int] = {}
    developer_leak_scores: dict[str, int] = {}
    critical_branches = []

    # Aggregate from active working branches
    for b in branches:
        repo = b.get("repo", "unknown")
        user = b.get("user_name", "unknown")
        err_count = b.get("summary", {}).get("errors", 0)

        repo_leak_scores[repo] = repo_leak_scores.get(repo, 0) + err_count
        developer_leak_scores[user] = developer_leak_scores.get(user, 0) + err_count

        if err_count > 0:
            critical_branches.append({
                "repo": repo,
                "branch": b.get("branch"),
                "pr_number": b.get("pr_number"),
                "user_name": user,
                "errors": err_count,
                "gate_status": b.get("gate_status", "WARNED"),
                "findings": b.get("findings", []),
            })

        for f in b.get("findings", []):
            rt = f.get("resource_type", "file")
            resource_breakdown[rt] = resource_breakdown.get(rt, 0) + 1

    # Also aggregate from historic repo_issues
    for issue in db["repo_issues"].find():
        rid = issue.get("rule_id", "")
        if "R001" in rid:
            resource_breakdown["file"] += 1
        elif "R002" in rid:
            resource_breakdown["socket"] += 1
        elif "R003" in rid:
            resource_breakdown["db"] += 1
        elif "R004" in rid:
            resource_breakdown["tempfile"] += 1

    # Recommendations for where admin should channel energy
    recommendations = []
    if resource_breakdown.get("socket", 0) > 0:
        recommendations.append({
            "priority": "HIGH",
            "area": "Network Socket Lifecycles",
            "action": "Audit gateway/socket_client.py: sockets left open on early error returns threaten file descriptor exhaustion.",
        })
    if resource_breakdown.get("db", 0) > 0:
        recommendations.append({
            "priority": "CRITICAL",
            "area": "Database Connection Pools",
            "action": "Channel refactoring into connection factory cleanup in inventory-service to prevent connection pool exhaustion.",
        })
    if resource_breakdown.get("tempfile", 0) > 0:
        recommendations.append({
            "priority": "MEDIUM",
            "area": "Temporary File Descriptors",
            "action": "Ensure delete=False tempfiles have guaranteed close() in finally blocks or use NamedTemporaryFile as context managers.",
        })

    return {
        "resource_breakdown": resource_breakdown,
        "repo_leak_scores": [
            {"repo": r, "score": s}
            for r, s in sorted(repo_leak_scores.items(), key=lambda kv: -kv[1])
        ],
        "developer_leak_scores": [
            {"developer": d, "score": s}
            for d, s in sorted(developer_leak_scores.items(), key=lambda kv: -kv[1])
        ],
        "critical_branches": sorted(critical_branches, key=lambda x: -x["errors"]),
        "recommendations": recommendations,
    }


@router.get("/branches")
def branches() -> list[dict]:
    """All working branches across all repositories with live gate status."""
    return get_all_branches()


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


@router.get("/repos/{repo:path}/logs")
def repo_logs(repo: str) -> list[dict]:
    return get_repo_logs(repo)


@router.get("/repos/{repo:path}/issues")
def repo_issues(repo: str) -> dict:
    return get_repo_issues(repo)


@router.get("/repos/{repo:path}/prs")
def repo_prs(repo: str) -> list[dict]:
    return get_repo_prs(repo)


@router.get("/repos/{repo:path}/prs/{pr_number:int}/logs")
def pr_logs(repo: str, pr_number: int) -> list[dict]:
    return get_pr_logs(repo, pr_number)


@router.get("/repos/{repo:path}/prs/{pr_number:int}/issues")
def pr_issues(repo: str, pr_number: int) -> dict:
    return get_pr_issues(repo, pr_number)
