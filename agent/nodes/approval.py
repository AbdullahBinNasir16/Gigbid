"""Human approval (interrupt) and exactly-once submission.

approval: builds the payload (draft, evidence behind every claim, risk report, price
rationale, compliance verdict and the dry_run preview from the marketplace) and calls
interrupt(). The graph pauses here; the checkpoint holds the payload, so a restart or a page
refresh never loses it. Resume with an ApprovalDecision (approve, edit or reject).

submit: only reachable after approve or a compliant edit. Idempotency keys are derived from
the thread id, so a crash and replay after the draft was created or submitted returns the
stored marketplace result instead of submitting or spending Connects twice.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision, ApprovalPayload, DryRunPreview
from agent.mcp_client import ToolBox
from agent.nodes._common import event, tool_events
from agent.nodes.compliance import check
from agent.state import Status, step


def _key(state: dict, what: str) -> str:
    return f"{state['thread_id']}:{what}"[:200].replace(" ", "_")


async def approval(state: dict) -> dict:
    draft, price = state["drafts"][-1], state.get("price")
    text = state.get("final_text") or draft.cover_letter
    used = {i for c in draft.claims for i in c.evidence_ids}
    evidence = [e for e in state.get("evidence", []) if e.id in used] or state.get("evidence", [])
    tb = ToolBox("submitter", trace_id=state.get("trace_id"))
    preview_payload: dict[str, Any] = {"job_id": draft.job_id, "cover_letter": text,
                                       "amount": price.amount if price else None,
                                       "budget_type": price.budget_type if price else None}
    cost, after = (price.connects_cost if price else 0), None
    try:
        dry = await tb.call("create_proposal_draft", job_id=draft.job_id, cover_letter=text,
                            amount=price.amount, budget_type=price.budget_type,
                            screening_answers=draft.screening_answers[:10],
                            idempotency_key=_key(state, "draft"), dry_run=True)
        preview_payload = dry.get("preview") or preview_payload
        cost = dry.get("connects_cost") or cost
        bal = await tb.call("get_connects_balance")
        after = bal["balance"] - cost
    except Exception:  # noqa: BLE001 - preview still shows what would be sent
        pass
    payload = ApprovalPayload(
        thread_id=state["thread_id"], kind="proposal",
        draft=draft.model_copy(update={"cover_letter": text}), evidence=evidence[:20],
        risk=state.get("analyses", {}).get("risk"), price=price, compliance=state.get("compliance"),
        preview=DryRunPreview(action="submit_proposal", payload=preview_payload,
                              connects_cost=int(cost or 0), connects_balance_after=after))
    raw = interrupt(payload.model_dump(mode="json"))
    decision = ApprovalDecision.model_validate(raw)
    out: dict[str, Any] = {"approval_request": payload, "approvals": [decision],
                           "counters": step(),
                           "trace": [*tool_events(state, "approval", tb.calls),
                                     event(state, "approval", "resume",
                                           result_summary=f"{decision.action}"
                                           + (f": {decision.reason}" if decision.reason else ""))]}
    if decision.action == "edit":
        from agent.memory.promotion_rules import record_edit

        verdict = check(decision.edited_text or "")
        try:
            out["memory_promoted"] = record_edit(decision.user_id, state["thread_id"], text,
                                                 decision.edited_text or "")
        except Exception:  # noqa: BLE001 - memory never blocks an approval
            pass
        out |= {"final_text": verdict.cleaned_text or decision.edited_text, "compliance": verdict}
        out["status"] = Status.awaiting_approval if verdict.verdict == "block" else Status.running
    elif decision.action == "reject":
        out |= {"status": Status.done, "status_reason": f"rejected: {decision.reason}"}
    else:
        out["status"] = Status.running
    out.pop("memory_promoted", None)
    return out


async def submit(state: dict) -> dict:
    if state.get("submitted"):
        return {"counters": step()}
    draft, price = state["drafts"][-1], state["price"]
    text = state.get("final_text") or draft.cover_letter
    tb = ToolBox("submitter", trace_id=state.get("trace_id"))
    created = await tb.call("create_proposal_draft", job_id=draft.job_id, cover_letter=text,
                            amount=price.amount, budget_type=price.budget_type,
                            screening_answers=draft.screening_answers[:10],
                            idempotency_key=_key(state, "draft"), dry_run=False)
    pid = created["resource_id"]
    result = await tb.call("submit_proposal", proposal_id=pid,
                           idempotency_key=_key(state, "submit"), dry_run=False)
    return {"submitted": True, "proposal_id": pid, "status": Status.done,
            "status_reason": f"submitted {pid}; {result.get('connects_cost')} Connects spent"
                             + (" (replayed, not re-sent)" if result.get("replayed") else ""),
            "counters": step(),
            "trace": [*tool_events(state, "submit", tb.calls),
                      event(state, "submit", result_summary=f"proposal {pid} submitted")]}
