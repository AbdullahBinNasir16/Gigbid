"""Job inbox, job detail, scouting and running the bid graph for a job."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from agent.mcp_client import ToolBox
from agent.nodes.scout import dedupe
from apps.api import db, runtime
from apps.api.auth import CurrentUser
from apps.api.schemas import JobCard, JobDetail, RunStarted

router = APIRouter(prefix="/jobs", tags=["jobs"])
_seen: dict[str, dict[str, str]] = {}


def _card(r: dict) -> JobCard:
    j = json.loads(r["data"])
    a = json.loads(r["analysis"]) if r.get("analysis") else {}
    return JobCard(job_id=r["job_id"], title=j.get("title", ""), category=j.get("category"),
                   budget_type=j.get("budget_type"), budget_min=j.get("budget_min"),
                   budget_max=j.get("budget_max"), connects_cost=j.get("connects_cost"),
                   decision=r.get("decision"), fit=r.get("fit"), risk=r.get("risk"),
                   risk_flags=(a.get("risk") or {}).get("flags", []),
                   price=(a.get("price") or {}).get("amount"), status=r.get("status"),
                   thread_id=r.get("thread_id"))


@router.get("", response_model=list[JobCard])
def inbox(user: CurrentUser, decision: str | None = None, status: str | None = None
          ) -> list[JobCard]:
    stmt = db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"])
    if decision:
        stmt = stmt.where(db.jobs.c.decision == decision)
    if status:
        stmt = stmt.where(db.jobs.c.status == status)
    cards = [_card(r) for r in db.q(stmt)]
    order = {"bid": 0, "watch": 1, None: 2, "skip": 3}
    return sorted(cards, key=lambda c: (order.get(c.decision, 2), -(c.fit or 0)))


@router.post("/scout", response_model=list[RunStarted])
async def scout_now(user: CurrentUser, limit: int = 8) -> list[RunStarted]:
    """Run saved searches now (the worker does this on a schedule) and analyse new jobs."""
    tb = ToolBox("scout")
    found: dict[str, dict] = {}
    try:
        for q in user["settings"].get("saved_searches") or [""]:
            for j in (await tb.call("search_jobs", query=q, limit=limit))["items"]:
                found.setdefault(j["job_id"], j)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"marketplace unavailable: {exc}") from exc
    known = {r["job_id"] for r in db.q(db.select(db.jobs.c.job_id)
                                        .where(db.jobs.c.user_id == user["user_id"]))}
    seen = _seen.setdefault(user["user_id"], {})
    started = []
    for j in dedupe(list(found.values()), seen):
        if j["job_id"] in known:
            continue
        if j["duplicate_of"]:
            db.upsert_job(user["user_id"], j["job_id"], data=j, decision="skip",
                          status="duplicate")
            continue
        started.append(RunStarted(thread_id=runtime.start_run(user, j)))
    return started


@router.get("/{job_id}", response_model=JobDetail)
def detail(job_id: str, user: CurrentUser) -> JobDetail:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.job_id == job_id))
    if not rows:
        raise HTTPException(404, "job not found")
    r = rows[0]
    return JobDetail(job=json.loads(r["data"]),
                     analysis=json.loads(r["analysis"]) if r["analysis"] else None,
                     status=r["status"], thread_id=r["thread_id"])


@router.post("/{job_id}/run", response_model=RunStarted)
async def run(job_id: str, user: CurrentUser) -> RunStarted:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.job_id == job_id))
    if rows:
        job = json.loads(rows[0]["data"])
    else:
        try:
            job = await ToolBox("scout").call("get_job", job_id=job_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"marketplace unavailable: {exc}") from exc
    return RunStarted(thread_id=runtime.start_run(user, job))


@router.post("/{job_id}/skip")
def skip(job_id: str, user: CurrentUser) -> dict:
    db.upsert_job(user["user_id"], job_id, status="skipped_by_user", decision="skip")
    return {"ok": True}
