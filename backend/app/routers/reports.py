"""Callback endpoint the GitHub Action reports each run's results to."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.services.issues import ingest_action_run


def _require_ingest_token(
    x_leakguard_token: str | None = Header(default=None),
) -> None:
    """Shared-secret auth for CI ingest. Not a user JWT: the caller is the
    GitHub Action, not a person, so a rotating server-side token stored as a
    GitHub Actions secret is the right shape."""
    expected = os.environ.get("LEAKGUARD_INGEST_TOKEN")
    if not expected:
        if os.environ.get("LEAKGUARD_DEV") == "1":
            return
        raise HTTPException(
            status_code=503,
            detail="Ingest endpoint is not configured (LEAKGUARD_INGEST_TOKEN unset)",
        )
    if not x_leakguard_token or x_leakguard_token != expected:
        raise HTTPException(status_code=401, detail="Invalid ingest token")


router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(_require_ingest_token)],
)


class RunSummary(BaseModel):
    total: int = 0
    errors: int = 0
    warnings: int = 0
    info: int = 0


class ActionRunReport(BaseModel):
    repo: str
    pr_number: int | None = None
    sha: str | None = None
    user_id: str | None = None
    conclusion: str
    summary: RunSummary
    findings: list[dict[str, Any]] = []


@router.post("/action-run")
def report_action_run(report: ActionRunReport) -> dict:
    ingest_action_run(report.model_dump())
    return {"ok": True}
