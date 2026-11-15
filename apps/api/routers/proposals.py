"""Pipeline board: proposals by state, from the marketplace (via MCP-backed port)."""

from __future__ import annotations

from fastapi import APIRouter

from agent.marketplace_port import get_marketplace
from apps.api.auth import CurrentUser

router = APIRouter(prefix="/proposals", tags=["proposals"])
COLUMNS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


@router.get("/pipeline")
async def pipeline(user: CurrentUser) -> dict:
    board: dict[str, list] = {c: [] for c in COLUMNS}
    try:
        port = get_marketplace()
        props = await port.list_proposals() if hasattr(port, "list_proposals") else []
    except Exception as exc:  # noqa: BLE001
        return {"columns": board, "marketplace": "unavailable", "detail": str(exc)[:200]}
    for p in props:
        col = "drafted" if p["state"] == "draft" else p["state"]
        board.setdefault(col, []).append({"proposal_id": p["proposal_id"], "job_id": p["job_id"],
                                          "amount": p["amount"], "state": p["state"],
                                          "thread_id": p.get("thread_id"),
                                          "events": p.get("events", [])})
    return {"columns": board, "marketplace": "ok"}
