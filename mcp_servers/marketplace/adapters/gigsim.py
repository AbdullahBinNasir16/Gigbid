"""GigSim adapter for the marketplace port.

Why the guards: GigSim rate-limits (429 + Retry-After) and injects 503s. The adapter
stays under marketplace.max_requests_per_minute with its own token bucket, retries with
bounded exponential backoff, and opens a circuit breaker after repeated failures so the
UI can show "marketplace unavailable" instead of hanging. Every write forwards the
idempotency key, so a retry can never submit twice or spend Connects twice.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any

import httpx

from agent.config import get_config
from agent.marketplace_port import (
    AuthFailed,
    ClientHistory,
    ConnectsBalance,
    InsufficientConnects,
    InvalidRequest,
    Job,
    MarketplacePort,
    Message,
    ProposalPayload,
    RateLimited,
    Unavailable,
    WriteResult,
)


class _Bucket:
    def __init__(self, per_minute: int) -> None:
        self.rate = per_minute / 60.0
        self.capacity = max(1.0, per_minute / 6)
        self.tokens = self.capacity
        self.t = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
                self.t = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


class _Breaker:
    def __init__(self, threshold: int, cooldown: float) -> None:
        self.threshold, self.cooldown = threshold, cooldown
        self.failures = 0
        self.opened_at: float | None = None

    def check(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.cooldown:
            self.opened_at = None  # half open: let one call through
            self.failures = self.threshold - 1
            return
        raise Unavailable("marketplace circuit open")

    def ok(self) -> None:
        self.failures, self.opened_at = 0, None

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


# Shared per process so every adapter instance respects one budget and one breaker.
_BUCKETS: dict[str, _Bucket] = {}
_BREAKERS: dict[str, _Breaker] = {}


class GigSimMarketplace(MarketplacePort):
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 user_id: str = "default", transport: httpx.AsyncBaseTransport | None = None
                 ) -> None:
        cfg = get_config().marketplace
        self.cfg = cfg
        self.base_url = base_url or os.environ.get("GIGSIM_BASE_URL", "http://localhost:8081")
        self.token = token if token is not None else os.environ.get("GIGSIM_API_TOKEN", "")
        self.user_id = user_id
        self._transport = transport
        self.bucket = _BUCKETS.setdefault(user_id, _Bucket(cfg.max_requests_per_minute))
        self.breaker = _BREAKERS.setdefault(
            self.base_url, _Breaker(cfg.circuit_breaker.failure_threshold,
                                    cfg.circuit_breaker.cooldown_seconds))

    # ------------------------------------------------------------- transport
    async def _request(self, method: str, path: str, *, params: dict | None = None,
                       json: Any = None, idempotency_key: str | None = None
                       ) -> tuple[Any, httpx.Headers]:
        self.breaker.check()
        headers = {"X-GigSim-User": self.user_id}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        retry = self.cfg.retry
        last: Exception | None = None
        for attempt in range(retry.max_attempts):
            await self.bucket.take()
            try:
                async with httpx.AsyncClient(base_url=self.base_url, transport=self._transport,
                                             timeout=self.cfg.request_timeout_seconds) as c:
                    r = await c.request(method, path, params=params, json=json, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = Unavailable(f"marketplace unreachable: {exc.__class__.__name__}")
            else:
                if r.status_code < 400:
                    self.breaker.ok()
                    return r.json(), r.headers
                body = _body(r)
                if r.status_code == 429:
                    wait = float(r.headers.get("Retry-After") or body.get("retry_after") or 1)
                    last = RateLimited(retry_after=wait)
                    await asyncio.sleep(min(wait, retry.max_delay_seconds))
                    continue
                if r.status_code >= 500:
                    last = Unavailable(f"marketplace error {r.status_code}")
                else:
                    self.breaker.ok()  # the server answered; a client error is not an outage
                    raise _client_error(r.status_code, body)
            delay = min(retry.max_delay_seconds, retry.base_delay_seconds * 2 ** attempt)
            await asyncio.sleep(delay)
        self.breaker.fail()
        assert last is not None
        raise last

    # ------------------------------------------------------------------ reads
    async def search_jobs(self, query: str = "", *, limit: int = 20,
                          since: datetime | None = None) -> list[Job]:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if query:
            params["q"] = query
        if since:
            params["since"] = since.isoformat()
        data, _ = await self._request("GET", "/jobs", params=params)
        return [Job.model_validate(j) for j in data["items"]]

    async def get_job(self, job_id: str) -> Job:
        data, _ = await self._request("GET", f"/jobs/{job_id}")
        return Job.model_validate(data)

    async def get_client_history(self, client_id: str) -> ClientHistory:
        data, _ = await self._request("GET", f"/clients/{client_id}")
        return ClientHistory.model_validate(data)

    async def get_connects_balance(self) -> ConnectsBalance:
        data, _ = await self._request("GET", "/connects")
        return ConnectsBalance.model_validate(data)

    async def list_messages(self, thread_id: str | None = None) -> list[Message]:
        if thread_id:
            data, _ = await self._request("GET", f"/threads/{thread_id}/messages")
            return [Message.model_validate(m) for m in data]
        threads, _ = await self._request("GET", "/threads")
        out: list[Message] = []
        for t in threads:
            data, _ = await self._request("GET", f"/threads/{t['thread_id']}/messages")
            out.extend(Message.model_validate(m) for m in data)
        return out

    async def list_threads(self) -> list[dict[str, Any]]:
        data, _ = await self._request("GET", "/threads")
        return data

    async def list_proposals(self, state: str | None = None) -> list[dict[str, Any]]:
        data, _ = await self._request("GET", "/proposals", params={"state": state} if state else None)
        return data

    # ----------------------------------------------------------------- writes
    async def create_proposal_draft(self, payload: ProposalPayload, *, idempotency_key: str,
                                    dry_run: bool = False) -> WriteResult:
        if dry_run:
            job = await self.get_job(payload.job_id)
            return WriteResult(ok=True, dry_run=True, idempotency_key=idempotency_key,
                               connects_cost=job.connects_cost or 0,
                               preview={"action": "create_proposal_draft", **payload.model_dump()})
        data, headers = await self._request("POST", "/proposals", json=payload.model_dump(),
                                            idempotency_key=idempotency_key)
        return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                           replayed=headers.get("Idempotent-Replayed") == "true",
                           resource_id=data["proposal_id"],
                           connects_cost=data.get("connects_cost") or 0)

    async def submit_proposal(self, draft_id: str, *, idempotency_key: str,
                              dry_run: bool = False) -> WriteResult:
        if dry_run:
            prop, _ = await self._request("GET", f"/proposals/{draft_id}")
            bal = await self.get_connects_balance()
            job = await self.get_job(prop["job_id"])
            cost = job.connects_cost or 0
            return WriteResult(ok=True, dry_run=True, idempotency_key=idempotency_key,
                               resource_id=draft_id, connects_cost=cost,
                               connects_balance_after=bal.balance - cost,
                               preview={"action": "submit_proposal", "proposal_id": draft_id,
                                        "job_id": prop["job_id"],
                                        "cover_letter": prop["cover_letter"],
                                        "amount": prop["amount"]})
        data, headers = await self._request("POST", f"/proposals/{draft_id}/submit",
                                            idempotency_key=idempotency_key)
        return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                           replayed=headers.get("Idempotent-Replayed") == "true",
                           resource_id=draft_id, connects_cost=data["connects_spent"],
                           connects_balance_after=data["balance_after"])

    async def send_message(self, thread_id: str, text: str, *, idempotency_key: str,
                           dry_run: bool = False) -> WriteResult:
        if dry_run:
            return WriteResult(ok=True, dry_run=True, idempotency_key=idempotency_key,
                               preview={"action": "send_message", "thread_id": thread_id,
                                        "text": text})
        data, headers = await self._request("POST", f"/threads/{thread_id}/messages",
                                            json={"text": text}, idempotency_key=idempotency_key)
        return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                           replayed=headers.get("Idempotent-Replayed") == "true",
                           resource_id=data["message_id"])


def _body(r: httpx.Response) -> dict[str, Any]:
    try:
        b = r.json()
        return b if isinstance(b, dict) else {}
    except ValueError:
        return {}


def _client_error(status: int, body: dict[str, Any]) -> Exception:
    msg = f"{body.get('error', 'error')}: {body.get('detail')}"
    if status == 401:
        return AuthFailed(msg)
    if status == 402:
        return InsufficientConnects(msg)
    return InvalidRequest(f"{status} {msg}")
