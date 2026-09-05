"""User-facing 'scan a repo by URL' endpoints."""

from __future__ import annotations

import json
import queue
import threading

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import get_current_user
from app.db import get_db
from app.scan_service import ScanError, run_scan

router = APIRouter(prefix="/api", tags=["scan"], dependencies=[Depends(get_current_user)])


class ScanRequest(BaseModel):
    repo_url: str


@router.post("/scan")
def scan(request: ScanRequest) -> dict:
    try:
        return run_scan(request.repo_url)
    except ScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scan/stream")
def scan_stream(repo_url: str) -> StreamingResponse:
    """Server-sent events: live progress from the real analyzer pipeline."""
    events: "queue.Queue[dict | None]" = queue.Queue()

    def worker():
        try:
            def on_progress(step: str, data: dict):
                events.put({"step": step, **data})

            result = run_scan(repo_url, on_progress=on_progress)
            events.put({"step": "result", "result": result})
        except ScanError as exc:
            events.put({"step": "error", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            events.put({"step": "error", "message": f"Unexpected error: {exc}"})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str) -> dict:
    try:
        object_id = ObjectId(scan_id)
    except InvalidId as exc:
        raise HTTPException(status_code=404, detail="Scan not found") from exc

    doc = get_db()["scans"].find_one({"_id": object_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Scan not found")
    doc["_id"] = str(doc["_id"])
    return doc
