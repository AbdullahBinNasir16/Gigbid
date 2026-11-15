"""Users, sessions and the encrypted OAuth token store.

Passwords: PBKDF2-SHA256 with a per-user salt. Sessions: HMAC-signed bearer tokens
(JWT_SECRET_KEY). OAuth tokens (e.g. Upwork): Fernet-encrypted at rest (FERNET_KEY), never
logged, and always read by (user_id, provider).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api import db

SECRET = os.environ.get("JWT_SECRET_KEY") or "dev-only-secret-change-me"
TTL = 60 * 60 * 24 * 7
DEFAULT_SETTINGS = {"persona": "ai_ml", "autonomy": "suggest", "hourly_floor": None,
                    "weekly_connects_budget": 80, "saved_searches": ["python", "dashboard",
                                                                     "react", "machine learning"],
                    "marketplace": "gigsim"}


def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_token(user_id: str) -> str:
    body = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + TTL}).encode())
    sig = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> str | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data["sub"] if data["exp"] > time.time() else None
    except Exception:  # noqa: BLE001
        return None


def create_user(username: str, password: str, settings: dict[str, Any] | None = None) -> str:
    uid = str(uuid.uuid4())
    db.q(db.insert(db.users).values(user_id=uid, username=username.lower(),
                                    pw_hash=hash_pw(password), created_at=db.now(),
                                    settings=json.dumps(DEFAULT_SETTINGS | (settings or {}))))
    return uid


def get_user(user_id: str) -> dict[str, Any] | None:
    rows = db.q(db.select(db.users).where(db.users.c.user_id == user_id))
    if not rows:
        return None
    u = rows[0]
    return {"user_id": u["user_id"], "username": u["username"],
            "settings": DEFAULT_SETTINGS | json.loads(u["settings"] or "{}")}


def login(username: str, password: str) -> str | None:
    rows = db.q(db.select(db.users).where(db.users.c.username == username.lower()))
    if rows and check_pw(password, rows[0]["pw_hash"]):
        return make_token(rows[0]["user_id"])
    return None


def seed_reviewer() -> None:
    """Preloaded reviewer login with a persona (credentials from env, never in the repo)."""
    name = os.environ.get("REVIEWER_USERNAME", "reviewer")
    pw = os.environ.get("REVIEWER_PASSWORD", "reviewer-dev-password")
    if not db.q(db.select(db.users.c.user_id).where(db.users.c.username == name)):
        create_user(name, pw, {"persona": "ai_ml"})


bearer = HTTPBearer(auto_error=False)


def current_user(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
                 ) -> dict[str, Any]:
    uid = read_token(cred.credentials) if cred else None
    user = get_user(uid) if uid else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


# ----------------------------------------------------------- OAuth token store
def _fernet():  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    key = os.environ.get("FERNET_KEY")
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(SECRET.encode()).digest()).decode()
    return Fernet(key.encode())


def store_oauth_token(user_id: str, provider: str, token: dict[str, Any]) -> None:
    ct = _fernet().encrypt(json.dumps(token).encode()).decode()
    db.q(db.delete(db.tokens).where(db.tokens.c.user_id == user_id,
                                    db.tokens.c.provider == provider))
    db.q(db.insert(db.tokens).values(user_id=user_id, provider=provider, ciphertext=ct,
                                     updated_at=db.now()))


def load_oauth_token(user_id: str, provider: str) -> dict[str, Any] | None:
    rows = db.q(db.select(db.tokens).where(db.tokens.c.user_id == user_id,
                                           db.tokens.c.provider == provider))
    return json.loads(_fernet().decrypt(rows[0]["ciphertext"].encode())) if rows else None
