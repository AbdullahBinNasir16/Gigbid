"""Background worker (Arq on Redis): scheduled scouting and long agent runs, outside web
requests.

Run: arq worker.main.WorkerSettings
* scout_all: every marketplace.polling_interval_seconds (gigsim) or the conservative
  live_polling_interval_seconds (upwork_live), runs each user's saved searches, dedups and
  enqueues new jobs. Job ids are the dedup key, so a restart never analyses a job twice.
* run_job: drives the bid graph for one job (thread id = user + job, so re-enqueueing the
  same job resumes the same checkpointed thread instead of starting a second one).
* retry_queued: re-runs jobs parked while the marketplace was down.
"""

from __future__ import annotations

import json
import os
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from agent.config import get_config


async def run_job(ctx: dict, user_id: str, job: dict[str, Any]) -> str:
    from apps.api import auth, db, runtime

    user = auth.get_user(user_id)
    if user is None:
        return "unknown user"
    thread_id = runtime.thread_for(user_id, job["job_id"])
    rows = db.q(db.select(db.jobs.c.status).where(db.jobs.c.user_id == user_id,
                                                  db.jobs.c.job_id == job["job_id"]))
    if rows and rows[0]["status"] in ("done", "awaiting_approval", "submitted", "duplicate"):
        return "already processed"  # idempotent: a worker restart never double-analyses
    db.upsert_job(user_id, job["job_id"], data=job, status="analysing", thread_id=thread_id)
    payload = {"thread_id": thread_id, "user_id": user_id,
               "persona": user["settings"].get("persona", "ai_ml"), "job": job,
               "client": job.get("client"), "duplicate_of": job.get("duplicate_of")}
    await runtime._drive(user, thread_id, job["job_id"], payload)
    return thread_id


async def scout_all(ctx: dict) -> int:
    from agent.mcp_client import ToolBox
    from agent.nodes.scout import dedupe
    from apps.api import db

    seen: dict[str, str] = ctx.setdefault("seen", {})
    n = 0
    for u in db.q(db.select(db.users)):
        settings = json.loads(u["settings"] or "{}")
        tb = ToolBox("scout")
        found: dict[str, dict] = {}
        for q in settings.get("saved_searches") or [""]:
            for j in (await tb.call("search_jobs", query=q, limit=10))["items"]:
                found.setdefault(j["job_id"], j)
        known = {r["job_id"] for r in db.q(db.select(db.jobs.c.job_id)
                                            .where(db.jobs.c.user_id == u["user_id"]))}
        for j in dedupe(list(found.values()), seen):
            if j["job_id"] in known or j["duplicate_of"]:
                continue
            await ctx["redis"].enqueue_job("run_job", u["user_id"], j,
                                           _job_id=f"{u['user_id']}:{j['job_id']}")
            n += 1
    return n


async def retry_queued(ctx: dict) -> int:
    from apps.api import db

    rows = db.q(db.select(db.jobs).where(db.jobs.c.status == "queued"))
    for r in rows:
        await ctx["redis"].enqueue_job("run_job", r["user_id"], json.loads(r["data"]),
                                       _job_id=f"retry:{r['user_id']}:{r['job_id']}")
    return len(rows)


def _interval_minutes() -> set[int]:
    m = get_config().marketplace
    secs = m.live_polling_interval_seconds if m.mode == "upwork_live" else m.polling_interval_seconds
    step = max(1, secs // 60)
    return set(range(0, 60, step)) if step < 60 else {0}


class WorkerSettings:
    functions = [run_job, scout_all, retry_queued]
    cron_jobs = [cron(scout_all, minute=_interval_minutes(), run_at_startup=False),
                 cron(retry_queued, minute=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    max_jobs = int(os.environ.get("MAX_CONCURRENT_RUNS", "2"))
    job_timeout = 900
