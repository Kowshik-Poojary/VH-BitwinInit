"""JWT auth backed by Mongo.

Model: there is one admin account, and any number of "user" (developer)
accounts created under that admin (`admin_id` points back to the admin's
username). Still basic on purpose — one HS256 secret, no refresh tokens,
no per-admin multi-tenancy beyond this single admin — but no more
in-memory/hardcoded credentials.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, Query

from app.db import get_db
from app.security import hash_password, verify_password

def _require_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    if os.environ.get("LEAKGUARD_DEV") == "1":
        return "dev-secret-change-me"
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Set it to a long random string (e.g. `openssl rand -hex 32`), "
        "or set LEAKGUARD_DEV=1 for local development."
    )


JWT_SECRET = _require_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 12


def _accounts():
    return get_db()["accounts"]


def bootstrap_admin() -> None:
    """Create the single admin account from env vars on first boot.

    Idempotent: if an admin already exists in Mongo, does nothing. Otherwise
    reads ADMIN_USERNAME / ADMIN_PASSWORD from the environment and inserts
    the admin. Fails loudly if neither an admin exists nor the env vars are
    set, so a fresh deployment never boots without any way to log in.
    """
    accounts = _accounts()
    if accounts.find_one({"role": "admin"}):
        return

    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "No admin account exists yet. Set ADMIN_USERNAME and "
            "ADMIN_PASSWORD environment variables so the first-run admin "
            "can be created."
        )

    accounts.update_one(
        {"_id": username},
        {
            "$set": {
                "username": username,
                "password_hash": hash_password(password),
                "role": "admin",
                "admin_id": None,
            }
        },
        upsert=True,
    )


def create_user(admin_id: str, username: str, password: str) -> dict:
    accounts = _accounts()
    if accounts.find_one({"_id": username}):
        raise HTTPException(status_code=409, detail="Username already exists")
    accounts.insert_one(
        {
            "_id": username,
            "username": username,
            "password_hash": hash_password(password),
            "role": "user",
            "admin_id": admin_id,
        }
    )
    return {"username": username, "role": "user"}


def list_team(admin_id: str) -> list[dict]:
    return [
        {"username": a["username"], "role": a["role"]}
        for a in _accounts().find({"admin_id": admin_id})
    ]


def _issue_token(account: dict) -> str:
    payload = {
        "sub": account["username"],
        "role": account["role"],
        "admin_id": account.get("admin_id"),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def login(username: str, password: str) -> dict:
    account = _accounts().find_one({"_id": username})
    if not account or not verify_password(password, account["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _issue_token(account)
    return {"token": token, "username": account["username"], "role": account["role"]}


def _decode_token(raw: str) -> dict:
    try:
        return jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> dict:
    """Reads the JWT from the Authorization header, or a `token` query param
    (needed for EventSource, which can't set headers)."""
    bearer = None
    if authorization and authorization.startswith("Bearer "):
        bearer = authorization[len("Bearer ") :]
    raw = bearer or token
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(raw)
    return {
        "username": payload["sub"],
        "role": payload["role"],
        "admin_id": payload.get("admin_id"),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
