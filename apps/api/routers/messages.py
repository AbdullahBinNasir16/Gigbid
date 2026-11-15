"""Client threads with suggested replies; replies go through the conversation graph and
its approval interrupt before anything is sent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langgraph.types import Command

from agent.graphs.bid_graph import get_checkpointer
from agent.graphs.conversation_graph import build_conversation_graph
from agent.marketplace_port import get_marketplace
from apps.api.auth import CurrentUser
from apps.api.schemas import ApprovalIn

router = APIRouter(prefix="/messages", tags=["messages"])
_graph = None


async def graph():  # type: ignore[no-untyped-def]
    global _graph
    if _graph is None:
        _graph = build_conversation_graph(await get_checkpointer())
    return _graph


@router.get("/threads")
async def threads(user: CurrentUser) -> dict:
    try:
        port = get_marketplace()
        ts = await port.list_threads() if hasattr(port, "list_threads") else []
    except Exception as exc:  # noqa: BLE001
        return {"threads": [], "marketplace": "unavailable", "detail": str(exc)[:200]}
    return {"threads": ts, "marketplace": "ok"}


@router.get("/threads/{thread_id}")
async def thread(thread_id: str, user: CurrentUser) -> dict:
    msgs = await get_marketplace().list_messages(thread_id)
    g = await graph()
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    pending = None
    for t in snap.tasks or ():
        for i in t.interrupts or ():
            pending = i.value
    return {"messages": [m.model_dump(mode="json") for m in msgs], "pending": pending,
            "intent": snap.values.get("intent"), "status": str(snap.values.get("status") or "")}


@router.post("/threads/{thread_id}/suggest")
async def suggest(thread_id: str, user: CurrentUser) -> dict:
    g = await graph()
    out = await g.ainvoke({"thread_id": thread_id, "user_id": user["user_id"]},
                          {"configurable": {"thread_id": thread_id}})
    intr = out.get("__interrupt__")
    return {"pending": intr[0].value if intr else None, "intent": out.get("intent"),
            "status": str(out.get("status") or ""), "reason": out.get("status_reason")}


@router.post("/threads/{thread_id}/approve")
async def approve(thread_id: str, body: ApprovalIn, user: CurrentUser) -> dict:
    g = await graph()
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    if not any(t.interrupts for t in snap.tasks or ()):
        raise HTTPException(404, "no pending reply for this thread")
    out = await g.ainvoke(Command(resume=body.model_dump(exclude_none=True)
                                  | {"user_id": user["user_id"]}),
                          {"configurable": {"thread_id": thread_id}})
    intr = out.get("__interrupt__")
    return {"status": str(out.get("status") or ""), "pending": intr[0].value if intr else None,
            "sent": out.get("sent_message_ids", [])}
