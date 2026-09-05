"""Login endpoint for the basic admin/user auth."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth import login as do_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: LoginRequest) -> dict:
    return do_login(request.username, request.password)
