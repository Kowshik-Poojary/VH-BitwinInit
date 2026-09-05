"""FastAPI entrypoint for the LeakGuard web backend."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import bootstrap_admin
from app.routers import admin, auth, reports, scan


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if os.environ.get("LEAKGUARD_DEV") == "1":
        return ["*"]
    raise RuntimeError(
        "CORS_ORIGINS environment variable is not set. "
        "Set it to a comma-separated list of allowed frontend origins "
        "(e.g. `http://localhost:8080,https://leakguard.mycorp.internal`), "
        "or set LEAKGUARD_DEV=1 for local development."
    )


app = FastAPI(title="LeakGuard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(scan.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.on_event("startup")
def _bootstrap_admin() -> None:
    bootstrap_admin()


@app.get("/health")
def health() -> dict:
    return {"ok": True}
