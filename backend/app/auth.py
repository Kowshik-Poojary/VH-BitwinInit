"""Authentication and authorization system for LeakGuard.

Manages 1 Admin and 3 Developer users with token-based sessions,
role permissions, and demonstration quick-switcher accounts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.db import get_db

SECRET_KEY = "leakguard-hackathon-secure-auth-secret-key"

DEFAULT_USERS = [
    {
        "_id": "Kowshik-Poojary",
        "username": "Kowshik-Poojary",
        "name": "Kowshik Poojary (Repo Owner & Admin)",
        "role": "admin",
        "email": "chandrapoojary1975@gmail.com",
        "github_url": "https://github.com/Kowshik-Poojary",
        "avatar": "https://github.com/Kowshik-Poojary.png",
        "badge": "Admin",
    },
    {
        "_id": "vinayakpotdar79",
        "username": "vinayakpotdar79",
        "name": "Vinayak Potdar (Developer)",
        "role": "developer",
        "email": "vinayakpotdar7977@gmail.com",
        "github_url": "https://github.com/vinayakpotdar79",
        "avatar": "https://github.com/vinayakpotdar79.png",
        "badge": "Developer",
    },
    {
        "_id": "Nikhil-2x",
        "username": "Nikhil-2x",
        "name": "Nikhil Yadav (Developer)",
        "role": "developer",
        "email": "nikhilyadav101513@gmail.com",
        "github_url": "https://github.com/Nikhil-2x",
        "avatar": "https://github.com/Nikhil-2x.png",
        "badge": "Developer",
    },
    {
        "_id": "Rohit-Khaire",
        "username": "Rohit-Khaire",
        "name": "Rohit Khaire (Developer)",
        "role": "developer",
        "email": "athlius31@gmail.com",
        "github_url": "https://github.com/Rohit-Khaire",
        "avatar": "https://github.com/Rohit-Khaire.png",
        "badge": "Developer",
    },
]


def seed_default_users() -> None:
    db = get_db()
    users_col = db["users"]
    for u in DEFAULT_USERS:
        users_col.update_one({"_id": u["_id"]}, {"$set": u}, upsert=True)


def create_token(user_doc: dict) -> str:
    payload = {
        "user_id": user_doc["_id"],
        "username": user_doc["username"],
        "role": user_doc.get("role", "developer"),
        "exp": int(time.time()) + 86400 * 7,
    }
    payload_bytes = json.dumps(payload).encode()
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    sig = hmac.new(SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{b64_payload}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        padding = "=" * ((4 - len(b64_payload) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b64_payload + padding).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization:
        # Fallback default guest developer for ease of use if needed,
        # but raise 401 if strict auth required
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    token = authorization
    if token.startswith("Bearer "):
        token = token[7:]
    
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    
    user = get_db()["users"].find_one({"_id": payload["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Return user safe dict (without password_hash)
    safe_user = dict(user)
    safe_user.pop("password_hash", None)
    return safe_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest) -> dict:
    seed_default_users()
    db = get_db()
    uname = req.username.strip()
    
    # Case-insensitive search
    user = None
    for u in db["users"].find():
        if u.get("username", "").lower() == uname.lower() or u.get("_id", "").lower() == uname.lower():
            user = u
            break
    
    if not user:
        raise HTTPException(status_code=401, detail=f"User '{uname}' not found")
    
    # Accept user authentication
    token = create_token(user)
    safe_user = dict(user)
    safe_user.pop("password_hash", None)
    return {"token": token, "user": safe_user}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@router.get("/demo-accounts")
def demo_accounts() -> list[dict]:
    """Returns the list of demonstration accounts for instant one-click login."""
    return [
        {
            "username": u["username"],
            "name": u["name"],
            "role": u["role"],
            "avatar": u["avatar"],
            "badge": u["badge"],
            "description": "Global cross-repo analytics & tech debt radar" if u["role"] == "admin" else f"Developer with active branch & PR",
        }
        for u in DEFAULT_USERS
    ]
