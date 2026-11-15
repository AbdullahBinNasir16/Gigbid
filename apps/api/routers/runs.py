"""Agent run viewer: live node-by-node events (SSE), the full trace, checkpoint history."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from apps.api import auth, db, runtime
from apps.api.auth import CurrentUser

router = APIRouter(prefix="/runs", tags=["runs"])


def _own(user_id: str, thread_id: str) -> None:
    if not db.q(db.select(db.jobs.c.job_id).where(db.jobs.c.user_id == user_id,
                                                  db.jobs.c.thread_id == thread_id)):
        raise HTTPException(404, "run not found")


@router.get("/{thread_id}/stream")
async def stream(thread_id: str, request: Request, token: str) -> StreamingResponse:
    """Server-Sent Events. EventSource cannot set headers, so the session token is a query
    parameter on this one endpoint."""
    uid = auth.read_token(token)
    if not uid:
        raise HTTPException(401, "not signed in")
    _own(uid, thread_id)

    async def gen():  # type: ignore[no-untyped-def]
        yield "retry: 3000\n\n"
        async for ev in runtime.subscribe(thread_id):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{thread_id}/trace")
async def trace(thread_id: str, user: CurrentUser) -> list[dict]:
    _own(user["user_id"], thread_id)
    return await runtime.trace(thread_id)


@router.get("/{thread_id}/history")
async def history(thread_id: str, user: CurrentUser) -> list[dict]:
    _own(user["user_id"], thread_id)
    return await runtime.history(thread_id)


@router.get("")
def list_runs(user: CurrentUser) -> list[dict]:
    rows = db.q(db.select(db.runs).where(db.runs.c.user_id == user["user_id"]))
    for r in rows:
        r["metrics"] = json.loads(r["metrics"] or "{}")
    return sorted(rows, key=lambda r: str(r["updated_at"]), reverse=True)[:200]
