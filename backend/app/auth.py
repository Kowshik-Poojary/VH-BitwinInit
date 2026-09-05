"""Minimal username/password auth for the hackathon MVP.

Not production-grade — credentials and sessions are in-memory constants, no
hashing, no expiry. Good enough to tell "admin" apart from "user" and gate
the admin dashboard behind a login. Swap for real auth before shipping.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Query

# username -> {"password": ..., "role": "admin" | "user"}
ACCOUNTS = {
    "admin": {"password": "admin123", "role": "admin"},
    "koshik": {"password": "koshik123", "role": "user"},
    "nick": {"password": "nick123", "role": "user"},
    "vinayak": {"password": "vinayak123", "role": "user"},
    "rohit": {"password": "rohit123", "role": "user"},
}

# token -> {"username": ..., "role": ...}
SESSIONS: dict[str, dict] = {}


def login(username: str, password: str) -> dict:
    account = ACCOUNTS.get(username)
    if not account or account["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = secrets.token_hex(16)
    SESSIONS[token] = {"username": username, "role": account["role"]}
    return {"token": token, "username": username, "role": account["role"]}


def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> dict:
    """Reads the session token from the Authorization header, or a `token`
    query param (needed for EventSource, which can't set headers)."""
    bearer = None
    if authorization and authorization.startswith("Bearer "):
        bearer = authorization[len("Bearer ") :]
    session = SESSIONS.get(bearer or token or "")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
