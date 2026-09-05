"""Callback endpoint the GitHub Action reports each run's results to."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.issues import ingest_action_run

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
