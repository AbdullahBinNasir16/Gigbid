"""Pending approvals and approve / edit / reject, which resume the interrupted graph thread.

Pending approvals are read from the checkpoint, so a page refresh or an API restart never
loses one.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from apps.api import db, runtime
from apps.api.auth import CurrentUser
from apps.api.schemas import ApprovalIn, ApprovalItem

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalItem])
async def pending(user: CurrentUser) -> list[ApprovalItem]:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.status == "awaiting_approval"))
    out = []
    for r in rows:
        payload = await runtime.pending_approval(r["thread_id"])
        if payload:
            out.append(ApprovalItem(thread_id=r["thread_id"], job_id=r["job_id"],
                                    title=json.loads(r["data"]).get("title", ""),
                                    payload=payload))
    return out


@router.get("/{thread_id}", response_model=ApprovalItem)
async def one(thread_id: str, user: CurrentUser) -> ApprovalItem:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.thread_id == thread_id))
    payload = await runtime.pending_approval(thread_id) if rows else None
    if not payload:
        raise HTTPException(404, "no pending approval for this thread")
    return ApprovalItem(thread_id=thread_id, job_id=rows[0]["job_id"],
                        title=json.loads(rows[0]["data"]).get("title", ""), payload=payload)


@router.post("/{thread_id}")
async def decide(thread_id: str, body: ApprovalIn, user: CurrentUser) -> dict:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.thread_id == thread_id))
    if not rows or not await runtime.pending_approval(thread_id):
        raise HTTPException(404, "no pending approval for this thread")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a rejection needs a reason")
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "an edit needs the edited text")
    db.upsert_job(user["user_id"], rows[0]["job_id"], status="resuming")
    runtime.resume(user, thread_id, rows[0]["job_id"], body.model_dump(exclude_none=True))
    return {"ok": True, "thread_id": thread_id}
