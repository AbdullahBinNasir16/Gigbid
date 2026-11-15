"""Bid graph: one thread per job.

intake -> [Send] analyst | risk | matcher (parallel) -> decide -> skip/watch: END
       -> bid: pricing -> writer -> verifier -> critic -> (revise, at most critic_max_loops)
       -> writer ... -> compliance -> (block: needs_attention) -> approval [interrupt]
       -> approve/edit: submit -> END ; reject: END ; edit that fails compliance: approval

Every node is wrapped by `guarded`: per-node retries with backoff, a dead-letter status
when retries run out, and a needs-attention status when the step or token budget is spent.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.config import get_config
from agent.nodes._common import event, over_budget
from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState, Status, step

STOP = {Status.needs_attention, Status.dead_letter}
PARALLEL = {"analyst", "risk", "matcher"}  # must not write `status` (no reducer)


def guarded(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    async def run(state: dict) -> dict:
        reason = over_budget(state)
        if reason:
            if name in PARALLEL:
                return {"errors": [f"{name}: {reason}"], "counters": step()}
            return {"status": Status.needs_attention, "status_reason": reason,
                    "trace": [event(state, name, "error", result_summary=reason)]}
        b = get_config().budgets
        last: Exception | None = None
        for attempt in range(b.node_max_retries + 1):
            try:
                res = fn(state)
                return await res if inspect.isawaitable(res) else res
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ in ("GraphInterrupt", "Interrupt") or \
                        "Interrupt" in type(exc).__name__:
                    raise
                last = exc
                await asyncio.sleep(min(4.0, 0.5 * 2 ** attempt))
        msg = f"{name} failed after {b.node_max_retries + 1} attempts: " \
              f"{type(last).__name__}: {str(last)[:300]}"
        out: dict = {"errors": [msg], "trace": [event(state, name, "error", result_summary=msg)]}
        if name not in PARALLEL:
            out |= {"status": Status.dead_letter, "status_reason": msg}
        return out

    run.__name__ = name
    return run


def intake(state: dict) -> dict:
    job = state["job"]
    return {"trace_id": state.get("trace_id") or str(uuid.uuid4()),
            "duplicate_of": state.get("duplicate_of") or job.get("duplicate_of"),
            "status": Status.running, "counters": step(),
            "trace": [event(state, "intake", "node_start",
                            result_summary=f"job {job.get('job_id')}")]}


def fan_out(state: dict) -> list[Send]:
    return [Send("analyst", state), Send("risk", state), Send("matcher", state)]


def _stopped(state: dict) -> bool:
    return state.get("status") in STOP


def after_decide(state: dict) -> str:
    if _stopped(state):
        return END
    d = state.get("decision")
    if state.get("errors") and (d is None or not state.get("analyses", {}).get("fit")):
        return "dead_letter"
    return "pricing" if d and d.decision == "bid" else END


def after_critic(state: dict) -> str:
    if _stopped(state):
        return END
    return "writer" if state["critiques"][-1].verdict == "revise" else "compliance"


def after_compliance(state: dict) -> str:
    if _stopped(state):
        return END
    return "blocked" if state["compliance"].verdict == "block" else "approval"


def after_approval(state: dict) -> str:
    if _stopped(state):
        return END
    last = state["approvals"][-1]
    if last.action == "reject":
        return END
    if last.action == "edit" and state["compliance"].verdict == "block":
        return "approval"
    return "submit"


def next_or_stop(target: str) -> Callable[[dict], str]:
    return lambda s: END if _stopped(s) else target


def blocked(state: dict) -> dict:
    reasons = "; ".join(state["compliance"].reasons)
    return {"status": Status.needs_attention, "status_reason": f"compliance block: {reasons}",
            "trace": [event(state, "compliance", "error", result_summary=reasons[:500])]}


def dead_letter(state: dict) -> dict:
    return {"status": Status.dead_letter,
            "status_reason": "; ".join(state.get("errors", []))[:1000] or "analysis failed"}


def build_bid_graph(checkpointer: Any = None, store: Any = None):
    g = StateGraph(BidState)
    nodes = {"analyst": analyst, "risk": risk_assessor, "matcher": fit_matcher,
             "decide": decide, "pricing": pricing, "writer": writer, "verifier": verifier,
             "critic": critic, "compliance": compliance, "approval": approval,
             "submit": submit}
    g.add_node("intake", intake)
    for name, fn in nodes.items():
        g.add_node(name, guarded(name, fn))
    g.add_node("blocked", blocked)
    g.add_node("dead_letter", dead_letter)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "matcher"])
    for n in ("analyst", "risk", "matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing", "dead_letter", END])
    g.add_conditional_edges("pricing", next_or_stop("writer"), ["writer", END])
    g.add_conditional_edges("writer", next_or_stop("verifier"), ["verifier", END])
    g.add_conditional_edges("verifier", next_or_stop("critic"), ["critic", END])
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", END])
    g.add_conditional_edges("compliance", after_compliance, ["blocked", "approval", END])
    g.add_conditional_edges("approval", after_approval, ["approval", "submit", END])
    g.add_edge("submit", END)
    g.add_edge("blocked", END)
    g.add_edge("dead_letter", END)
    return g.compile(checkpointer=checkpointer, store=store)


async def get_checkpointer() -> Any:
    """Postgres when DATABASE_URL is postgres, else SQLite under data/processed."""
    import os
    from pathlib import Path

    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        conn = await AsyncConnection.connect(url.replace("postgresql+psycopg", "postgresql"),
                                             autocommit=True, prepare_threshold=0,
                                             row_factory=dict_row)
        saver = AsyncPostgresSaver(conn)
    else:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = Path(os.environ.get("CHECKPOINT_DB",
                                   Path(__file__).resolve().parents[2] / "data" / "processed"
                                   / "checkpoints.sqlite"))
        path.parent.mkdir(parents=True, exist_ok=True)
        saver = AsyncSqliteSaver(await aiosqlite.connect(str(path)))
    await saver.setup()
    return saver


graph = build_bid_graph()  # for rendering and langgraph dev (no checkpointer)
