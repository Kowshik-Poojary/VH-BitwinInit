"""FastAPI entrypoint for the LeakGuard web backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, reports, scan

app = FastAPI(title="LeakGuard Backend")

# MVP: wide open CORS since there's no auth yet either. Tighten before any
# real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
