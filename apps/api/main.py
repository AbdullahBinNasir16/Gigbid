"""GigBid API (FastAPI). The web app talks only to this; agents talk only to MCP tools."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.api import auth, db
from apps.api.routers import analytics, approvals, jobs, messages, proposals, runs
from apps.api.routers import auth as auth_router
from apps.api.schemas import Health

log = logging.getLogger("gigbid.api")
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    auth.seed_reviewer()
    if os.environ.get("WARM_INDEXES", "1") == "1":
        from rag.index.store import warm

        await asyncio.to_thread(warm)
    if os.environ.get("SEED_ON_START") == "1":
        asyncio.get_running_loop().create_task(_seed_reviewer_inbox())
    yield


async def _seed_reviewer_inbox() -> None:
    """Fill the reviewer's inbox once at boot (same path as pressing "Scout now")."""
    from apps.api.routers.jobs import scout_now

    name = os.environ.get("REVIEWER_USERNAME", "reviewer")
    rows = db.q(db.select(db.users.c.user_id).where(db.users.c.username == name))
    if not rows:
        return
    user = auth.get_user(rows[0]["user_id"])
    has_jobs = db.q(db.select(db.jobs.c.job_id).where(db.jobs.c.user_id == user["user_id"]))
    if user and not has_jobs:
        try:
            await scout_now(user, limit=4)
        except Exception as exc:  # noqa: BLE001 - seeding is best effort
            log.warning("seed scout failed: %s", exc)


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth_router.router, jobs.router, approvals.router, runs.router, proposals.router,
          messages.router, analytics.router):
    app.include_router(r, prefix="/api")


@app.get("/health", response_model=Health)
@app.get("/api/health", response_model=Health)
async def health() -> Health:
    """Marketplace reachability drives the UI's degraded-mode banner."""
    from agent.marketplace_port import get_marketplace

    queued = len(db.q(db.select(db.jobs.c.job_id).where(db.jobs.c.status == "queued")))
    try:
        await asyncio.wait_for(get_marketplace().get_connects_balance(), timeout=4)
        return Health(status="ok", marketplace="ok", queued=queued)
    except Exception as exc:  # noqa: BLE001
        return Health(status="degraded", marketplace="unavailable",
                      marketplace_detail=f"{type(exc).__name__}: {exc}"[:200], queued=queued)


@app.post("/api/retry-queued")
async def retry_queued(user: auth.CurrentUser) -> dict:
    from apps.api import runtime

    return {"restarted": await runtime.retry_queued(user)}


# Serve the built React app from the same origin when present (single-container deploy).
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        f = WEB_DIST / path
        return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")
