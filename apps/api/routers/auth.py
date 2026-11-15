"""Sign-in, sign-up, profile settings and marketplace connection."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from apps.api import auth, db
from apps.api.auth import CurrentUser
from apps.api.schemas import LoginIn, MeOut, Settings, SignupIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn) -> TokenOut:
    token = auth.login(body.username, body.password)
    if not token:
        raise HTTPException(401, "wrong username or password")
    return TokenOut(token=token)


@router.post("/signup", response_model=TokenOut)
def signup(body: SignupIn) -> TokenOut:
    if db.q(db.select(db.users.c.user_id).where(db.users.c.username == body.username.lower())):
        raise HTTPException(409, "username taken")
    uid = auth.create_user(body.username, body.password, {"persona": body.persona})
    return TokenOut(token=auth.make_token(uid))


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser) -> MeOut:
    return MeOut(user_id=user["user_id"], username=user["username"],
                 settings=Settings.model_validate(user["settings"]))


@router.put("/settings", response_model=MeOut)
def save_settings(body: Settings, user: CurrentUser) -> MeOut:
    db.q(db.update(db.users).where(db.users.c.user_id == user["user_id"])
         .values(settings=json.dumps(body.model_dump())))
    return MeOut(user_id=user["user_id"], username=user["username"], settings=body)


@router.post("/connect/upwork")
def connect_upwork(user: CurrentUser) -> dict:
    """Starts the OAuth 2.1 flow against the official Upwork MCP server. Tokens returned by
    the callback are stored encrypted per user (auth.store_oauth_token)."""
    return {"status": "requires_oauth", "authorize_url": "https://mcp.upwork.com/mcp",
            "note": "Live mode needs an Upwork account; GigSim stays the default."}
