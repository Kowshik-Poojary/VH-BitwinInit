"""Seed 10 demo users and realistic multi-run repo history into MongoDB.

No auth is involved: this writes directly into the same collections the real
GitHub Action report endpoint would, via `ingest_action_run`, so the admin
dashboard has enough history to show run logs and current-vs-past issue
attribution without needing real CI traffic.

Usage:
    python backend/scripts/seed_demo_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db  # noqa: E402
from app.services.issues import ingest_action_run  # noqa: E402

USERS = [
    {"_id": "user_1", "name": "Ava Thompson"},
    {"_id": "user_2", "name": "Liam Chen"},
    {"_id": "user_3", "name": "Sofia Martinez"},
    {"_id": "user_4", "name": "Noah Patel"},
    {"_id": "user_5", "name": "Maya Ivanova"},
    {"_id": "user_6", "name": "Ethan Wright"},
    {"_id": "user_7", "name": "Priya Raman"},
    {"_id": "user_8", "name": "Lucas Silva"},
    {"_id": "user_9", "name": "Hana Suzuki"},
    {"_id": "user_10", "name": "Oscar Kowalski"},
]

NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def finding(rule_id, resource_type, file, line, message, confidence="HIGH"):
    return {
        "rule_id": rule_id,
        "severity": "ERROR",
        "category": "RESOURCE_LEAK",
        "message": message,
        "status": "DEFINITE_LEAK",
        "resource_type": resource_type,
        "location": {"file": file, "line": line, "column": 4, "end_line": None, "end_column": None},
        "details": {"confidence": confidence},
    }


def summary_for(findings: list[dict]) -> dict:
    return {
        "total": len(findings),
        "errors": sum(1 for f in findings if f["severity"] == "ERROR"),
        "warnings": sum(1 for f in findings if f["severity"] == "WARNING"),
        "info": 0,
    }


def run(repo, user_id, day, findings, *, pr_number=None, sha="deadbeef"):
    payload = {
        "repo": repo,
        "pr_number": pr_number,
        "sha": sha,
        "user_id": user_id,
        "conclusion": "fail" if findings else "pass",
        "summary": summary_for(findings),
        "findings": findings,
    }
    ingest_action_run(payload, received_at=days_ago(day))


def seed_inventory_service():
    repo = "demo-org/inventory-service"

    issue_a = finding("LKG-R003", "db", "app/db/connection.py", 42,
                       "opened at line 42, no close() found before exit at line 47")
    issue_b = finding("LKG-R001", "file", "app/services/export.py", 18,
                       "opened at line 18, no close() found on exception path at line 24")
    issue_c = finding("LKG-R004", "tempfile", "app/utils/tempcache.py", 9,
                       "opened at line 9, no close() found before exit at line 15", confidence="MEDIUM")
    issue_d = finding("LKG-R001", "file", "app/services/export.py", 55,
                       "opened at line 55, no close() found on return path at line 60")
    issue_e = finding("LKG-R003", "db", "app/db/connection.py", 80,
                       "opened at line 80, no close() found before exit at line 88")

    run(repo, "user_1", 14, [issue_a, issue_b], pr_number=101)
    run(repo, "user_2", 11, [issue_a, issue_b, issue_c], pr_number=104)
    run(repo, "user_3", 9, [issue_a, issue_b, issue_c])
    run(repo, "user_4", 6, [issue_a, issue_c, issue_d], pr_number=110)
    run(repo, "user_5", 3, [issue_c, issue_d], pr_number=115)
    run(repo, "user_6", 1, [issue_d, issue_e], pr_number=118)


def seed_payment_gateway():
    repo = "demo-org/payment-gateway"

    issue_f = finding("LKG-R002", "socket", "gateway/socket_client.py", 30,
                       "opened at line 30, no close() found before exit at line 36")
    issue_g = finding("LKG-R001", "file", "gateway/ledger.py", 12,
                       "opened at line 12, no close() found on exception path at line 19")
    issue_h = finding("LKG-R004", "tempfile", "gateway/report_writer.py", 5,
                       "opened at line 5, no close() found before exit at line 11", confidence="LOW")

    run(repo, "user_7", 10, [issue_f, issue_g], pr_number=55)
    run(repo, "user_8", 7, [issue_f, issue_h], pr_number=58)
    run(repo, "user_9", 4, [issue_h], pr_number=61)
    run(repo, "user_10", 1, [])


def main():
    db = get_db()
    for user in USERS:
        db["users"].update_one({"_id": user["_id"]}, {"$set": user}, upsert=True)
    print(f"Seeded {len(USERS)} demo users")

    seed_inventory_service()
    seed_payment_gateway()
    print("Seeded run history for demo-org/inventory-service and demo-org/payment-gateway")


if __name__ == "__main__":
    main()
