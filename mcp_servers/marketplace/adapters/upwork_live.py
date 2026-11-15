"""Live adapter: the official Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1)
behind the same marketplace port as GigSim, so the graph cannot tell which one it uses.

* Transport: langchain-mcp-adapters MultiServerMCPClient over Streamable HTTP with the
  user's OAuth access token (stored Fernet-encrypted per user: apps/api/auth).
* Tool mapping: Upwork's tool names are discovered at connect time and matched to port
  methods by name hints (UPWORK_TOOL_HINTS); unknown capabilities raise InvalidRequest
  instead of guessing.
* Writes are drafts only. `submit_proposal` never submits on Upwork: it creates/updates the
  draft and returns `requires_platform_confirmation`, because the user must confirm on
  Upwork as the platform requires. Nothing is sent without approval in GigBid first.
* Reads are rate-limited by the shared token bucket and scheduled no more often than
  marketplace.live_polling_interval_seconds (docs/RUNBOOK.md). No scraping, no cookies,
  no browser automation.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from agent.config import get_config
from agent.marketplace_port import (
    AuthFailed,
    ClientHistory,
    ConnectsBalance,
    InvalidRequest,
    Job,
    MarketplacePort,
    Message,
    ProposalPayload,
    Unavailable,
    WriteResult,
)

UPWORK_MCP_URL = os.environ.get("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
UPWORK_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "search_jobs": ("search_jobs", "job_search", "find_jobs", "search"),
    "get_job": ("get_job", "job_details", "job"),
    "get_client_history": ("client", "company", "buyer"),
    "get_connects_balance": ("connects", "balance"),
    "list_messages": ("messages", "rooms", "conversation"),
    "create_proposal_draft": ("proposal_draft", "create_proposal", "draft_proposal", "proposal"),
    "send_message": ("send_message", "message_draft", "reply"),
}


class UpworkLiveMarketplace(MarketplacePort):
    def __init__(self, user_id: str = "default", oauth: str | None = None) -> None:
        self.user_id = user_id
        self.token = oauth or self._load_token()
        self._client: Any = None
        self._tools: dict[str, str] = {}
        self._drafts: dict[str, str] = {}

    def _load_token(self) -> str:
        if os.environ.get("UPWORK_ACCESS_TOKEN"):
            return os.environ["UPWORK_ACCESS_TOKEN"]
        try:
            from apps.api.auth import load_oauth_token

            tok = load_oauth_token(self.user_id, "upwork")
        except Exception:  # noqa: BLE001
            tok = None
        if not tok:
            raise AuthFailed("connect your Upwork account first (Settings -> Connected accounts)")
        return tok["access_token"]

    async def _session_tools(self) -> dict[str, str]:
        if self._tools:
            return self._tools
        from langchain_mcp_adapters.client import MultiServerMCPClient

        self._client = MultiServerMCPClient({"upwork": {
            "transport": "streamable_http", "url": UPWORK_MCP_URL,
            "headers": {"Authorization": f"Bearer {self.token}"},
            "timeout": get_config().marketplace.request_timeout_seconds}})
        try:
            async with self._client.session("upwork") as s:
                names = [t.name for t in (await s.list_tools()).tools]
        except Exception as exc:
            raise Unavailable(f"Upwork MCP unreachable: {type(exc).__name__}") from exc
        for method, hints in UPWORK_TOOL_HINTS.items():
            match = next((n for h in hints for n in names if h in n.lower()), None)
            if match:
                self._tools[method] = match
        return self._tools

    async def _call(self, method: str, args: dict[str, Any]) -> Any:
        tools = await self._session_tools()
        if method not in tools:
            raise InvalidRequest(f"Upwork MCP exposes no tool for '{method}'")
        async with self._client.session("upwork") as s:
            res = await s.call_tool(tools[method], args)
        if res.isError:
            raise InvalidRequest(" ".join(getattr(c, "text", "") for c in res.content)[:500])
        return res.structuredContent or {}

    # ------------------------------------------------------------------ reads
    async def search_jobs(self, query: str = "", *, limit: int = 20,
                          since: datetime | None = None) -> list[Job]:
        data = await self._call("search_jobs", {"query": query, "limit": limit})
        items = data.get("items") or data.get("jobs") or []
        return [Job.model_validate(_job(j)) for j in items]

    async def get_job(self, job_id: str) -> Job:
        return Job.model_validate(_job(await self._call("get_job", {"job_id": job_id})))

    async def get_client_history(self, client_id: str) -> ClientHistory:
        d = await self._call("get_client_history", {"client_id": client_id})
        return ClientHistory(client_id=client_id, completed_projects=int(d.get("jobs_posted", 0)),
                             rating=d.get("rating"), total_spend=float(d.get("total_spent", 0) or 0),
                             payment_verified=bool(d.get("payment_verified", False)),
                             country=d.get("country"))

    async def get_connects_balance(self) -> ConnectsBalance:
        d = await self._call("get_connects_balance", {})
        return ConnectsBalance(balance=int(d.get("balance", d.get("connects", 0))))

    async def list_messages(self, thread_id: str | None = None) -> list[Message]:
        d = await self._call("list_messages", {"room_id": thread_id} if thread_id else {})
        return [Message.model_validate(m) for m in d.get("items", [])]

    # ----------------------------------------------------------------- writes
    async def create_proposal_draft(self, payload: ProposalPayload, *, idempotency_key: str,
                                    dry_run: bool = False) -> WriteResult:
        if dry_run:
            return WriteResult(ok=True, dry_run=True, idempotency_key=idempotency_key,
                               preview={"action": "create_proposal_draft (Upwork draft)",
                                        **payload.model_dump()})
        if idempotency_key in self._drafts:
            return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                               replayed=True, resource_id=self._drafts[idempotency_key])
        d = await self._call("create_proposal_draft", payload.model_dump())
        draft_id = str(d.get("id") or d.get("draft_id") or idempotency_key)
        self._drafts[idempotency_key] = draft_id
        return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                           resource_id=draft_id)

    async def submit_proposal(self, draft_id: str, *, idempotency_key: str,
                              dry_run: bool = False) -> WriteResult:
        # Upwork requires the freelancer to confirm submission on the platform itself.
        return WriteResult(ok=True, dry_run=dry_run, idempotency_key=idempotency_key,
                           resource_id=draft_id,
                           preview={"status": "requires_platform_confirmation",
                                    "note": "Draft created on Upwork; confirm it there."})

    async def send_message(self, thread_id: str, text: str, *, idempotency_key: str,
                           dry_run: bool = False) -> WriteResult:
        if dry_run:
            return WriteResult(ok=True, dry_run=True, idempotency_key=idempotency_key,
                               preview={"action": "message draft", "thread_id": thread_id,
                                        "text": text})
        d = await self._call("send_message", {"room_id": thread_id, "text": text})
        return WriteResult(ok=True, dry_run=False, idempotency_key=idempotency_key,
                           resource_id=str(d.get("id", "")),
                           preview={"status": "draft; confirm on Upwork"})


def _job(j: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": str(j.get("id") or j.get("job_id")), "title": j.get("title", ""),
            "description": j.get("description", ""), "skills": j.get("skills", []),
            "budget_type": j.get("budget_type", "unknown"), "budget_min": j.get("budget_min"),
            "budget_max": j.get("budget_max"), "client_id": j.get("client_id"),
            "provenance": "real"}
