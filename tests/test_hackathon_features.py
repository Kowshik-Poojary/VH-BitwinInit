"""Integration tests for real GitHub team accounts and live git branches:

- 1 Admin (Kowshik-Poojary) and 3 Developers (vinayakpotdar79, Nikhil-2x, Rohit-Khaire)
- Real git branches discovery and live AST analysis
- Real-time Warn-then-Block gatekeeper on PR merge attempts
- Admin Energy Channeling Radar & Hotspots
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import seed_default_users
from app.main import app
from app.services.branch_service import sync_real_branches


@pytest.fixture(autouse=True)
def init_data():
    seed_default_users()
    sync_real_branches(force_reset=True)


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_login_admin_and_users(client):
    # Test Admin login (Kowshik-Poojary)
    res = client.post(
        "/api/auth/login",
        json={"username": "Kowshik-Poojary", "password": "password123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "admin"
    assert "token" in data
    admin_token = data["token"]

    # Test Developer login (vinayakpotdar79)
    res_dev = client.post(
        "/api/auth/login",
        json={"username": "vinayakpotdar79", "password": "password123"},
    )
    assert res_dev.status_code == 200
    assert res_dev.json()["user"]["role"] == "developer"

    # Test unknown user
    res_bad = client.post(
        "/api/auth/login",
        json={"username": "non-existent-user-xyz", "password": "any"},
    )
    assert res_bad.status_code == 401

    # Verify /api/auth/me
    res_me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_me.status_code == 200
    assert res_me.json()["username"] == "Kowshik-Poojary"


def test_demo_accounts_list(client):
    res = client.get("/api/auth/demo-accounts")
    assert res.status_code == 200
    accounts = res.json()
    assert len(accounts) == 4
    usernames = [a["username"] for a in accounts]
    assert "Kowshik-Poojary" in usernames
    assert "vinayakpotdar79" in usernames
    assert "Nikhil-2x" in usernames
    assert "Rohit-Khaire" in usernames


def test_developer_branches_and_warn_block_gatekeeper(client):
    # Login as vinayakpotdar79
    res_login = client.post(
        "/api/auth/login",
        json={"username": "vinayakpotdar79", "password": "password123"},
    )
    token = res_login.json()["token"]

    # Get user branches
    res = client.get(
        "/api/user/branches", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    branches = res.json()
    assert len(branches) >= 1

    vinayak_branch = next(b for b in branches if b["branch"] == "dev-vinayak")
    assert vinayak_branch["gate_status"] in ["WARNED", "BLOCKED", "PASSED"]

    branch_id = vinayak_branch["_id"]

    # Attempt merge while having errors -> must trigger HARD BLOCK
    res_merge = client.post(
        f"/api/user/branches/{branch_id}/action",
        json={"action": "attempt_merge"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_merge.status_code == 200
    assert res_merge.json()["gate_status"] == "BLOCKED"

    # Simulate applying fix -> transitions to PASSED
    res_fix = client.post(
        f"/api/user/branches/{branch_id}/action",
        json={"action": "resolve_fix"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_fix.status_code == 200
    assert res_fix.json()["gate_status"] == "PASSED"
    assert res_fix.json()["summary"]["errors"] == 0


def test_admin_energy_channeling_radar(client):
    res = client.get("/api/admin/hotspots")
    assert res.status_code == 200
    data = res.json()
    assert "resource_breakdown" in data
    assert "recommendations" in data
    assert "critical_branches" in data
    assert len(data["recommendations"]) > 0

    # Test all branches endpoint
    res_branches = client.get("/api/admin/branches")
    assert res_branches.status_code == 200
    branches = res_branches.json()
    assert len(branches) >= 3
    branch_names = [b["branch"] for b in branches]
    assert "dev-vinayak" in branch_names
    assert "main" in branch_names
