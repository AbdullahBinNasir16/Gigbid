"""Compliance Guard: enforce the policy pack. No tools.

Removes contact details and guarantee language; blocks a draft that offers free work,
moves to off-platform payment, or echoes instructions injected in the job post. Banned
phrases come from platform_rules.banned_phrases_file, so a policy update adds a line there.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from agent.config import get_config
from agent.handoffs import ComplianceVerdict
from agent.nodes._common import event
from agent.state import step
from mcp_servers.common import mask_pii

ROOT = Path(__file__).resolve().parents[2]
BLOCKING = re.compile(r"(work for free|free (sample|trial)|unpaid|pay (me )?outside|off[- ]platform"
                      r"|whats ?app|telegram|skype|wire transfer|western union|paypal)", re.I)
INJECTION_ECHO = re.compile(r"(guarantee 5-star|will work for free|system prompt|admin mode|"
                            r"submit immediately|skip the review)", re.I)
GUARANTEE = re.compile(r"[^.!?]*\b(guarantee[ds]?|100% (satisfaction|success)|risk-free)\b[^.!?]*[.!?]",
                       re.I)


@lru_cache(maxsize=1)
def banned_phrases() -> tuple[str, ...]:
    path = ROOT / get_config().platform_rules.banned_phrases_file
    if not path.exists():
        return ()
    return tuple(line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#"))


def check(text: str) -> ComplianceVerdict:
    reasons, removed = [], []
    for m in INJECTION_ECHO.finditer(text):
        reasons.append(f"draft follows an instruction injected in the job post: '{m.group(0)}'")
    for m in BLOCKING.finditer(text):
        reasons.append(f"off-platform or free-work language: '{m.group(0)}'")
    cleaned = text
    for m in GUARANTEE.finditer(text):
        removed.append(m.group(0).strip()[:500])
        cleaned = cleaned.replace(m.group(0), "")
    masked = mask_pii(cleaned)
    if masked != cleaned:
        removed.append("contact details")
        cleaned = masked
    for phrase in banned_phrases():
        if phrase in cleaned.lower() and not any(phrase in r.lower() for r in reasons):
            # remove the sentence that carries a banned phrase
            for s in re.split(r"(?<=[.!?])\s+", cleaned):
                if phrase in s.lower():
                    removed.append(s.strip()[:500])
                    cleaned = cleaned.replace(s, "")
    cleaned = re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", cleaned)).strip()
    if reasons:
        return ComplianceVerdict(verdict="block", reasons=reasons[:20], removed_items=removed[:40],
                                 cleaned_text=cleaned)
    return ComplianceVerdict(verdict="pass", removed_items=removed[:40], cleaned_text=cleaned)


def compliance(state: dict) -> dict:
    draft = state["drafts"][-1]
    v = check(draft.cover_letter)
    return {"compliance": v, "final_text": v.cleaned_text or draft.cover_letter,
            "counters": step(),
            "trace": [event(state, "compliance", result_summary=f"{v.verdict}; removed "
                                                                f"{len(v.removed_items)}")]}
