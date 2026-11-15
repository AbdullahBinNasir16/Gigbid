"""Graph runtime: one compiled bid graph with a durable checkpointer, an event bus for live
streaming, and job runs that execute as background tasks (never inside a web request).

Degraded mode: if the marketplace is unreachable, runs are marked `queued` with the reason,
the UI shows a banner, and `retry_queued` re-runs them once the marketplace is back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from typing import Any

from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph, get_checkpointer
from agent.memory.store import get_store
from apps.api import db
from mcp_servers.common import mask_obj

log = logging.getLogger("gigbid.runtime")
_graph: Any = None
_lock = asyncio.Lock()
_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
_history: dict[str, list[dict]] = defaultdict(list)
_tasks: set[asyncio.Task] = set()
_slots: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_RUNS", "2")))
    return _slots


async def graph() -> Any:
    global _graph
    async with _lock:
        if _graph is None:
            _graph = build_bid_graph(await get_checkpointer(), get_store())
    return _graph


def callbacks(trace_id: str, user_id: str) -> list[Any]:
    """Langfuse callback when keys are set; one trace id flows through every node."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception:  # noqa: BLE001
        return []


def publish(thread_id: str, event: dict) -> None:
    event = mask_obj(event) | {"at": time.time()}
    _history[thread_id] = (_history[thread_id] + [event])[-300:]
    for q in list(_subs[thread_id]):
        q.put_nowait(event)


async def subscribe(thread_id: str):  # type: ignore[no-untyped-def]
    q: asyncio.Queue = asyncio.Queue()
    for e in _history.get(thread_id, []):
        q.put_nowait(e)
    _subs[thread_id].append(q)
    try:
        while True:
            yield await q.get()
    finally:
        _subs[thread_id].remove(q)


def thread_for(user_id: str, job_id: str) -> str:
    return f"{user_id[:8]}:{job_id}"


def _summ(update: Any) -> str:
    if isinstance(update, dict):
        tr = update.get("trace") or []
        if tr:
            last = tr[-1]
            return getattr(last, "result_summary", None) or str(last)[:200]
        return ", ".join(update)[:200]
    return str(update)[:200]


async def _drive(user: dict, thread_id: str, job_id: str, payload: Any) -> None:
    async with _sem():
        await _drive_inner(user, thread_id, job_id, payload)


async def _drive_inner(user: dict, thread_id: str, job_id: str, payload: Any) -> None:
    g = await graph()
    trace_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}, "run_name": f"bid:{job_id}",
           "callbacks": callbacks(trace_id, user["user_id"]),
           "metadata": {"user_id": user["user_id"], "job_id": job_id, "trace_id": trace_id}}
    t0 = time.perf_counter()
    publish(thread_id, {"type": "run_start", "job_id": job_id, "trace_id": trace_id})
    db.upsert_run(thread_id, user["user_id"], job_id=job_id, status="running")
    try:
        async for chunk in g.astream(payload, cfg, stream_mode="updates"):
            for node, upd in chunk.items():
                if node == "__interrupt__":
                    publish(thread_id, {"type": "interrupt", "node": "approval",
                                        "summary": "waiting for your approval"})
                else:
                    publish(thread_id, {"type": "node", "node": node, "summary": _summ(upd)})
        await persist(user, thread_id, job_id, time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"[:500]
        unavailable = "Unavailable" in reason or "unreachable" in reason or "circuit" in reason
        status = "queued" if unavailable else "dead_letter"
        db.upsert_run(thread_id, user["user_id"], status=status, summary=reason)
        db.upsert_job(user["user_id"], job_id, status=status)
        publish(thread_id, {"type": "error", "summary": reason, "status": status})
        log.warning("run %s failed: %s", thread_id, reason)
    publish(thread_id, {"type": "run_end"})


async def persist(user: dict, thread_id: str, job_id: str, seconds: float) -> dict:
    g = await graph()
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    v = snap.values
    pending = bool(snap.interrupts) if hasattr(snap, "interrupts") else bool(snap.next)
    status = "awaiting_approval" if pending else str(v.get("status") or "done").split(".")[-1]
    a = v.get("analyses", {})
    d = v.get("decision")
    analysis = {k: (x.model_dump(mode="json") if hasattr(x, "model_dump") else x)
                for k, x in a.items()}
    analysis["evidence"] = [e.model_dump(mode="json") for e in v.get("evidence", [])]
    if v.get("price"):
        analysis["price"] = v["price"].model_dump(mode="json")
    if d:
        analysis["decision"] = d.model_dump(mode="json")
    analysis["status_reason"] = v.get("status_reason")
    c = v.get("counters")
    metrics = {"seconds": round(seconds, 2), "steps": c.steps if c else 0,
               "tokens": c.tokens if c else 0, "critic_loops": c.critic_loops if c else 0,
               "verification": v.get("verification"), "submitted": bool(v.get("submitted")),
               "connects": v["price"].connects_cost if v.get("price") and v.get("submitted") else 0}
    db.upsert_job(user["user_id"], job_id, analysis=analysis, decision=d.decision if d else None,
                  fit=d.fit_score if d else None, risk=d.risk_score if d else None,
                  status="submitted" if v.get("submitted") else status, thread_id=thread_id)
    db.upsert_run(thread_id, user["user_id"], status=status, summary=v.get("status_reason"),
                  metrics=metrics)
    return {"status": status}


def start_run(user: dict, job: dict) -> str:
    thread_id = thread_for(user["user_id"], job["job_id"])
    persona = user["settings"].get("persona", "ai_ml")
    db.upsert_job(user["user_id"], job["job_id"], data=job, status="analysing",
                  thread_id=thread_id)
    payload = {"thread_id": thread_id, "user_id": user["user_id"], "persona": persona,
               "job": job, "client": job.get("client"), "duplicate_of": job.get("duplicate_of")}
    _spawn(_drive(user, thread_id, job["job_id"], payload))
    return thread_id


def resume(user: dict, thread_id: str, job_id: str, decision: dict) -> None:
    _history.pop(thread_id, None)
    _spawn(_drive(user, thread_id, job_id, Command(resume=decision | {"user_id": user["user_id"]})))


def _spawn(coro: Any) -> None:
    t = asyncio.get_running_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def pending_approval(thread_id: str) -> dict | None:
    g = await graph()
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    for intr in getattr(snap, "interrupts", ()) or ():
        return intr.value
    for task in snap.tasks or ():
        for intr in task.interrupts or ():
            return intr.value
    return None


async def history(thread_id: str) -> list[dict]:
    """Checkpoint history, newest first: lets the UI replay a job from any node."""
    g = await graph()
    out = []
    async for s in g.aget_state_history({"configurable": {"thread_id": thread_id}}, limit=60):
        out.append({"checkpoint_id": s.config["configurable"].get("checkpoint_id"),
                    "next": list(s.next), "step": s.metadata.get("step") if s.metadata else None,
                    "status": str(s.values.get("status") or "")})
    return out


async def trace(thread_id: str) -> list[dict]:
    g = await graph()
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    return [json.loads(e.model_dump_json()) for e in snap.values.get("trace", [])]


async def retry_queued(user: dict) -> int:
    rows = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"],
                                         db.jobs.c.status == "queued"))
    for r in rows:
        start_run(user, json.loads(r["data"]))
    return len(rows)


async def recover_interrupted() -> int:
    """After a crash or restart, continue runs that were in flight from their last checkpoint.

    A job left as analysing/resuming/running has no live task any more. If its thread has a
    checkpoint with pending nodes, resume it (input None continues from that checkpoint);
    otherwise start it again. Writes stay exactly-once through the idempotency keys.
    """
    from apps.api import auth

    rows = db.q(db.select(db.jobs).where(db.jobs.c.status.in_(["analysing", "resuming",
                                                               "running"])))
    g = await graph()
    n = 0
    for r in rows:
        user = auth.get_user(r["user_id"])
        if not user or not r["thread_id"]:
            continue
        snap = await g.aget_state({"configurable": {"thread_id": r["thread_id"]}})
        if snap.next and not getattr(snap, "interrupts", ()):
            _spawn(_drive(user, r["thread_id"], r["job_id"], None))
        elif not snap.values:
            start_run(user, json.loads(r["data"]))
        else:
            await persist(user, r["thread_id"], r["job_id"], 0.0)
        n += 1
    return n
