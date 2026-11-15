"""Tiny API client for local smoke checks: python -m scripts.api_smoke <cmd> [args].

cmds: inbox | approvals | approve <thread> | reject <thread> <reason> | runs | health
"""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE = os.environ.get("GIGBID_API", "http://localhost:8000")


def token() -> str:
    r = httpx.post(f"{BASE}/api/auth/login", json={
        "username": os.environ.get("REVIEWER_USERNAME", "reviewer"),
        "password": os.environ.get("REVIEWER_PASSWORD", "reviewer-dev-password")})
    r.raise_for_status()
    return r.json()["token"]


def main() -> None:
    cmd, *args = sys.argv[1:] or ["inbox"]
    h = {"authorization": f"Bearer {token()}"}
    if cmd == "inbox":
        for c in httpx.get(f"{BASE}/api/jobs", headers=h).json():
            print(f"{c['decision']!s:6} {c['status']!s:18} fit={c['fit']} risk={c['risk']} "
                  f"price={c['price']} {c['title'][:55]}")
    elif cmd == "approvals":
        for a in httpx.get(f"{BASE}/api/approvals", headers=h, timeout=60).json():
            p = a["payload"]
            print(a["thread_id"], a["title"][:50])
            print(p["draft"]["cover_letter"][:900], "\n", p["preview"], "\n")
    elif cmd in ("approve", "reject"):
        body = {"action": cmd} | ({"reason": " ".join(args[1:])} if cmd == "reject" else {})
        print(httpx.post(f"{BASE}/api/approvals/{args[0]}", headers=h, json=body).json())
    elif cmd == "runs":
        print(json.dumps(httpx.get(f"{BASE}/api/runs", headers=h).json()[:10], indent=1,
                         default=str))
    else:
        print(httpx.get(f"{BASE}/health").json())


if __name__ == "__main__":
    main()
