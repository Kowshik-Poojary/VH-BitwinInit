"""FastAPI entrypoint for the LeakGuard web backend."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import bootstrap_admin
from app.routers import admin, auth, reports, scan


def _cors_origins() -> list[str]:
    return ["*"]


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
