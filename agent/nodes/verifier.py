"""Claim verification node (B3): check every claim against evidence, drop unsupported ones
before the Critic sees the draft. Records the unsupported rate before and after."""

from __future__ import annotations

from agent.handoffs import ClaimSupport
from agent.nodes._common import event, timed
from agent.state import step
from rag.verify import check_claims, verify_claims


def verifier(state: dict) -> dict:
    draft = state["drafts"][-1]
    evidence = state.get("evidence", [])
    with timed() as t:
        v = verify_claims(draft.cover_letter, evidence)
        after = check_claims(v.cleaned_text, evidence) if v.cleaned_text else []
        rate_after = (sum(c.support == ClaimSupport.unsupported for c in after) / len(after)
                      if after else 0.0)
        paragraphs = [p for p in v.cleaned_text.split("\n\n") if p.strip()] or draft.paragraphs
        cleaned = draft.model_copy(update={
            "paragraphs": paragraphs, "cover_letter": "\n\n".join(paragraphs),
            "claims": v.claims, "status": "verified"})
    info = {"claims": len(v.claims), "unsupported_before": v.unsupported_rate,
            "unsupported_after": rate_after, "removed": v.removed,
            "partly": [c.text for c in v.claims if c.support == ClaimSupport.partly_supported]}
    return {"drafts": [cleaned], "verification": info, "counters": step(),
            "trace": [event(state, "verifier", duration_ms=t["ms"],
                            result_summary=f"{len(v.claims)} claims, removed {len(v.removed)}, "
                                           f"unsupported {v.unsupported_rate:.0%} -> "
                                           f"{rate_after:.0%}")]}
