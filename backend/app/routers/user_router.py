"""Developer workspace endpoints for branch management, real-time streaming, and PR gatekeeping."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.branch_service import (
    get_branch,
    get_branches_by_user,
    stream_branch_scan,
    update_branch_gate,
)

router = APIRouter(prefix="/api/user", tags=["user"])


class BranchActionRequest(BaseModel):
    action: str  # "attempt_merge" or "resolve_fix"


@router.get("/branches")
def list_user_branches(user: dict = Depends(get_current_user)) -> list[dict]:
    return get_branches_by_user(user["_id"])


@router.get("/branches/{branch_id}")
def get_branch_detail(branch_id: str, user: dict = Depends(get_current_user)) -> dict:
    branch = get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


@router.get("/branches/{branch_id}/stream")
async def stream_branch_logs(branch_id: str) -> StreamingResponse:
    """Streams real-time AST analysis events to the developer's dashboard terminal."""
    async def event_generator():
        async for evt in stream_branch_scan(branch_id):
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/branches/{branch_id}/action")
def perform_branch_action(
    branch_id: str,
    req: BranchActionRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    result = update_branch_gate(branch_id, req.action)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
