"""GigSim HTTP API (student built marketplace simulator). Endpoint facts: gigsim/API.md."""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from gigsim.decisions import seeded_rng
from gigsim.models import (
    ChaosIn,
    ClientOut,
    ConnectsOut,
    DraftIn,
    JobOut,
    JobPage,
    MessageIn,
    MessageOut,
    PolicyIn,
    ProposalOut,
    SubmitOut,
    ThreadOut,
)
from gigsim.settings import admin_token, api_token, load_config
from gigsim.world import SimError, World

EXEMPT = {"/health", "/docs", "/openapi.json"}


def user_id(x_gigsim_user: Annotated[str, Header()] = "default") -> str:
    """Which simulated freelancer account the call acts for."""
    return x_gigsim_user


def require_admin(authorization: Annotated[str, Header()] = "") -> None:
    if authorization != f"Bearer {admin_token()}":
        raise HTTPException(status_code=401, detail="admin token required")


# Module level on purpose: FastAPI resolves string annotations in module globals.
UserDep = Annotated[str, Depends(user_id)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


class TokenBucket:
    """Per user token bucket. Why per user: one noisy tenant must not starve the others."""

    def __init__(self, per_minute: int, burst: int) -> None:
        self.rate = per_minute / 60.0
        self.burst = burst
        self.state: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def take(self, key: str) -> float:
        """Return 0 if allowed, else seconds to wait."""
        with self.lock:
            now = time.monotonic()
            tokens, last = self.state.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self.state[key] = (tokens - 1, now)
                return 0.0
            self.state[key] = (tokens, now)
            return (1 - tokens) / self.rate


def create_app(cfg: dict[str, Any] | None = None, world: World | None = None) -> FastAPI:
    cfg = cfg or load_config()
    state_file = os.environ.get("GIGSIM_STATE_FILE")
    world = world or World(cfg, state_file=Path(state_file) if state_file else None)
    limits = {"bucket": TokenBucket(cfg["limits"]["requests_per_minute"], cfg["limits"]["burst"])}
    chaos = {"error_rate": float(cfg["chaos"]["error_rate"]), "count": 0}

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if cfg["live"]["enabled"]:
            async def loop() -> None:
                while True:
                    await asyncio.sleep(cfg["live"]["interval_seconds"])
                    world.live_tick(1)
            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="GigSim (student built simulator)", version="0.1.0", lifespan=lifespan)
    app.state.world = world

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if path in EXEMPT or path.startswith("/admin"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {api_token()}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        user = request.headers.get("x-gigsim-user", "default")
        wait = limits["bucket"].take(user)
        if wait > 0:
            return JSONResponse({"error": "rate_limited", "retry_after": round(wait, 2)},
                                status_code=429, headers={"Retry-After": str(max(1, round(wait)))})
        if chaos["error_rate"] > 0:
            chaos["count"] += 1
            if seeded_rng(world.seed, "chaos", chaos["count"]).random() < chaos["error_rate"]:
                return JSONResponse({"error": "service_unavailable", "detail": "simulated outage"},
                                    status_code=503)
        return await call_next(request)

    @app.exception_handler(SimError)
    async def sim_error(_: Request, exc: SimError) -> JSONResponse:
        return JSONResponse({"error": str(exc), "detail": jsonable_encoder(exc.detail)},
                            status_code=exc.status)

    def idempotent(route: str, user: str, key: str | None, fn: Any, status: int = 200) -> JSONResponse:
        """Run a write once per (user, route, key). A retry returns the stored response."""
        if not key or not (8 <= len(key) <= 200):
            raise HTTPException(status_code=400, detail="Idempotency-Key header (8 to 200 chars) required")
        with world.lock:
            prior = world.idem_get(user, route, key)
            if prior is not None:
                return JSONResponse(prior["body"], status_code=prior["status"],
                                    headers={"Idempotent-Replayed": "true"})
            try:
                body, code = jsonable_encoder(fn()), status
            except SimError as exc:
                body, code = {"error": str(exc), "detail": jsonable_encoder(exc.detail)}, exc.status
            # Only final outcomes are stored; a 402 or 422 is final for that request too.
            world.idem_put(user, route, key, code, body)
            return JSONResponse(body, status_code=code)

    # ----------------------------------------------------------------- public
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "gigsim", "jobs": len(world.jobs),
                "sim_time": world.now().isoformat()}

    @app.get("/jobs", response_model=JobPage)
    def search_jobs(
        q: str = "", category: str | None = None, since: datetime | None = None,
        until: datetime | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        total, items = world.search_jobs(q, since, until, category, limit, offset)
        return {"total": total, "items": items}

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str) -> dict[str, Any]:
        return world.get_job(job_id)

    @app.get("/clients/{client_id}", response_model=ClientOut)
    def get_client(client_id: str) -> dict[str, Any]:
        return world.get_client(client_id)

    @app.get("/connects", response_model=ConnectsOut)
    def connects(user: UserDep) -> dict[str, Any]:
        return world.connects(user)

    @app.post("/proposals", response_model=ProposalOut, status_code=201)
    def create_draft(body: DraftIn, user: UserDep, key: IdemKey = None) -> JSONResponse:
        return idempotent("create_draft", user, key,
                          lambda: world.public_proposal(world.create_draft(user, body.model_dump())), 201)

    @app.post("/proposals/{proposal_id}/submit", response_model=SubmitOut)
    def submit(proposal_id: str, user: UserDep, key: IdemKey = None) -> JSONResponse:
        def run() -> dict[str, Any]:
            p, cost, balance = world.submit(user, proposal_id)
            return {"proposal": world.public_proposal(p), "connects_spent": cost, "balance_after": balance}
        return idempotent(f"submit:{proposal_id}", user, key, run)

    @app.get("/proposals", response_model=list[ProposalOut])
    def list_proposals(user: UserDep, state: str | None = None) -> list[dict[str, Any]]:
        return world.list_proposals(user, state)

    @app.get("/proposals/{proposal_id}", response_model=ProposalOut)
    def get_proposal(proposal_id: str, user: UserDep) -> dict[str, Any]:
        return world.get_proposal(user, proposal_id)

    @app.get("/threads", response_model=list[ThreadOut])
    def list_threads(user: UserDep) -> list[dict[str, Any]]:
        return world.list_threads(user)

    @app.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
    def list_messages(thread_id: str, user: UserDep) -> list[dict[str, Any]]:
        return world.list_messages(user, thread_id)

    @app.post("/threads/{thread_id}/messages", response_model=MessageOut, status_code=201)
    def send_message(thread_id: str, body: MessageIn, user: UserDep, key: IdemKey = None) -> JSONResponse:
        return idempotent(f"message:{thread_id}", user, key,
                          lambda: world.send_message(user, thread_id, body.text), 201)

    # ------------------------------------------------------------------ admin
    admin = [Depends(require_admin)]

    @app.post("/admin/reset", dependencies=admin)
    def reset(seed: int | None = None) -> dict[str, Any]:
        world.reset(seed)
        if world.state_file:
            world._save()
        return {"ok": True, "seed": world.seed, "jobs": len(world.jobs)}

    @app.post("/admin/jobs", dependencies=admin)
    def load_jobs(rows: list[dict[str, Any]], replace: bool = False) -> dict[str, Any]:
        return {"loaded": world.load_jobs(rows, replace=replace)}

    @app.post("/admin/clients", dependencies=admin)
    def load_clients(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"loaded": world.load_clients(rows)}

    @app.get("/admin/policy", dependencies=admin)
    def get_policy() -> dict[str, Any]:
        return world.policy()

    @app.post("/admin/policy", dependencies=admin)
    def set_policy(body: PolicyIn) -> dict[str, Any]:
        return world.set_policy(body.model_dump(exclude_none=True))

    @app.post("/admin/chaos", dependencies=admin)
    def set_chaos(body: ChaosIn) -> dict[str, Any]:
        if body.error_rate is not None:
            chaos["error_rate"] = body.error_rate
        if body.requests_per_minute is not None or body.burst is not None:
            limits["bucket"] = TokenBucket(
                body.requests_per_minute or cfg["limits"]["requests_per_minute"],
                body.burst or cfg["limits"]["burst"],
            )
        return {"error_rate": chaos["error_rate"], "requests_per_minute": limits["bucket"].rate * 60,
                "burst": limits["bucket"].burst}

    @app.post("/admin/advance", dependencies=admin)
    def advance(minutes: Annotated[float, Query(gt=0, le=60 * 24 * 30)]) -> dict[str, Any]:
        return {"sim_time": world.advance(minutes).isoformat()}

    @app.post("/admin/live/tick", dependencies=admin)
    def live_tick(n: Annotated[int, Query(ge=1, le=100)] = 1) -> dict[str, Any]:
        return {"added": world.live_tick(n)}

    return app


app = create_app()
