"""FastAPI entrypoint for the LeakGuard web backend."""

from __future__ import annotations

import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure src/ package is discoverable even if not installed in editable mode
_SRC_PATH = str(Path(__file__).resolve().parents[2] / "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router, seed_default_users
from app.routers import admin, reports, scan
from app.routers.user_router import router as user_router
from app.services.branch_service import sync_real_branches


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize real GitHub team users and git branches on startup
    try:
        seed_default_users()
        sync_real_branches(force_reset=True)
    except Exception as e:
        print(f"Startup initialization note: {e}")
    yield


app = FastAPI(title="LeakGuard Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(scan.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
