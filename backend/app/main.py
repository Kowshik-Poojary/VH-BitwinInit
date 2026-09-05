"""FastAPI entrypoint for the LeakGuard web backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import seed_default_accounts
from app.routers import admin, auth, reports, scan

app = FastAPI(title="LeakGuard Backend")

# MVP: wide open CORS. Auth is a basic JWT scheme layered on top, tighten
# this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(scan.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.on_event("startup")
def _seed_accounts() -> None:
    seed_default_accounts()


@app.get("/health")
def health() -> dict:
    return {"ok": True}
