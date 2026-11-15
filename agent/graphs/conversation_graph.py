"""Conversation graph: one thread per client conversation.

read -> classify (question | negotiation | interview_request | scam_signal | other)
     -> slots (interview only, Workspace MCP) -> draft -> compliance -> approval [interrupt]
     -> send (Marketplace write + tentative hold, only after approval) -> END
A scam signal never gets a drafted reply; it goes to the user flagged.
"""

from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.config import get_config
from agent.handoffs import ApprovalDecision, ApprovalPayload, DryRunPreview
from agent.mcp_client import ToolBox
from agent.nodes._common import call_llm, event, tool_events, untrusted
from agent.nodes.compliance import check
from agent.nodes.risk_assessor import assess
from agent.prompts import load_prompt
from agent.state import ConversationState, Status, step

INTENT_RULES = [
    ("scam_signal", r"whats ?app|telegram|outside (the )?platform|pay(ment)? (via|by) (crypto|"
                    r"gift|wire)|bank (login|details)|copy of your id|free (sample|trial)"),
    ("interview_request", r"\b(call|interview|meet|zoom|chat (live|now)|talk|available)\b"),
    ("negotiation", r"\b(rate|price|budget|discount|lower|cheaper|\$\d+|cost)\b"),
    ("question", r"\?"),
]


def classify_text(text: str) -> str:
    for label, pat in INTENT_RULES:
        if re.search(pat, text, re.I):
            return label
    return "other"


async def read(state: dict) -> dict:
    tb = ToolBox("liaison", trace_id=state.get("trace_id"))
    msgs = (await tb.call("list_messages", thread_id=state["thread_id"]))["items"]
    return {"new_messages": msgs, "counters": step(),
            "trace": tool_events(state, "liaison", tb.calls)}


def classify(state: dict) -> dict:
    client_msgs = [m for m in state.get("new_messages", []) if m["sender"] == "client"]
    last = client_msgs[-1]["text"] if client_msgs else ""
    intent = classify_text(last)
    if assess({"title": "", "description": last}, None).is_scam:
        intent = "scam_signal"
    return {"intent": intent, "counters": step(),
            "trace": [event(state, "classify", result_summary=intent)]}


async def slots(state: dict) -> dict:
    tb = ToolBox("liaison", trace_id=state.get("trace_id"))
    s = (await tb.call("get_free_slots", days_ahead=5, duration_minutes=30, max_slots=3))["slots"]
    return {"proposed_slots": s, "counters": step(), "trace": tool_events(state, "liaison", tb.calls)}


def draft(state: dict) -> dict:
    msgs = state.get("new_messages", [])
    history = "\n".join(f"{m['sender']}: {m['text']}" for m in msgs[-6:])
    slot_text = "; ".join(s["start"][:16].replace("T", " ") + " UTC"
                          for s in state.get("proposed_slots", []))
    intent = state.get("intent", "other")
    tokens = 0
    text = ""
    if get_config().generation.get("writer_mode") == "llm":
        try:
            text, tokens = call_llm("liaison", load_prompt("liaison").replace("{intent}", intent),
                                    f"{untrusted('conversation', history)}\nSLOTS: {slot_text}")
        except Exception:  # noqa: BLE001
            text = ""
    if not text.strip():
        if intent == "interview_request" and slot_text:
            text = (f"Thanks for getting back to me. I would be glad to talk. I am free at "
                    f"{slot_text}. Let me know which works and I will send an invite here.")
        elif intent == "negotiation":
            text = ("Thanks for the details. My quote reflects the scope we discussed; if the "
                    "budget is tight, I can suggest a smaller first milestone so you can judge "
                    "the work before committing to the rest.")
        else:
            text = ("Thanks for your message. Happy to answer that: could you share a bit more "
                    "about the expected timeline so I can give you a precise reply?")
    return {"reply_draft": text.strip()[:5000], "counters": step(tokens),
            "trace": [event(state, "liaison", tokens=tokens, result_summary=f"draft for {intent}")]}


def flag_scam(state: dict) -> dict:
    return {"status": Status.needs_attention,
            "status_reason": "client message shows scam signals; no reply drafted",
            "trace": [event(state, "classify", "error", result_summary="scam signal")]}


def compliance(state: dict) -> dict:
    v = check(state["reply_draft"])
    return {"compliance": v, "reply_draft": v.cleaned_text or state["reply_draft"],
            "counters": step()}


def approval(state: dict) -> dict:
    payload = ApprovalPayload(
        thread_id=state["thread_id"], kind="message", message_text=state["reply_draft"],
        compliance=state.get("compliance"),
        preview=DryRunPreview(action="send_message", connects_cost=0,
                              payload={"thread_id": state["thread_id"],
                                       "text": state["reply_draft"],
                                       "slots": state.get("proposed_slots", [])}))
    d = ApprovalDecision.model_validate(interrupt(payload.model_dump(mode="json")))
    out: dict[str, Any] = {"approvals": [d], "approval_request": payload, "counters": step()}
    if d.action == "edit":
        v = check(d.edited_text or "")
        out |= {"reply_draft": v.cleaned_text or d.edited_text, "compliance": v}
    if d.action == "reject":
        out |= {"status": Status.done, "status_reason": f"rejected: {d.reason}"}
    return out


async def send(state: dict) -> dict:
    tb = ToolBox("liaison", trace_id=state.get("trace_id"), approved=True)
    n = len(state.get("approvals", []))
    res = await tb.call("send_message", thread_id=state["thread_id"], text=state["reply_draft"],
                        idempotency_key=f"{state['thread_id']}:reply:{n}"[:200], dry_run=False)
    if state.get("intent") == "interview_request" and state.get("proposed_slots"):
        await tb.call("create_tentative_hold", start=state["proposed_slots"][0]["start"],
                      duration_minutes=30, title=f"Client interview ({state['thread_id']})",
                      idempotency_key=f"{state['thread_id']}:hold:{n}"[:200])
    return {"sent_message_ids": [res.get("resource_id") or ""], "status": Status.done,
            "counters": step(), "trace": tool_events(state, "liaison", tb.calls)}


def route_intent(state: dict) -> str:
    i = state.get("intent")
    return "flag_scam" if i == "scam_signal" else "slots" if i == "interview_request" else "draft"


def route_approval(state: dict) -> str:
    last = state["approvals"][-1]
    if last.action == "reject":
        return END
    if state["compliance"].verdict == "block":
        return "approval"
    return "send"


def build_conversation_graph(checkpointer: Any = None, store: Any = None):
    g = StateGraph(ConversationState)
    for name, fn in (("read", read), ("classify", classify), ("slots", slots), ("draft", draft),
                     ("flag_scam", flag_scam), ("compliance", compliance),
                     ("approval", approval), ("send", send)):
        g.add_node(name, fn)
    g.add_edge(START, "read")
    g.add_edge("read", "classify")
    g.add_conditional_edges("classify", route_intent, ["flag_scam", "slots", "draft"])
    g.add_edge("slots", "draft")
    g.add_edge("draft", "compliance")
    g.add_edge("compliance", "approval")
    g.add_conditional_edges("approval", route_approval, ["approval", "send", END])
    g.add_edge("send", END)
    g.add_edge("flag_scam", END)
    return g.compile(checkpointer=checkpointer, store=store)


graph = build_conversation_graph()
