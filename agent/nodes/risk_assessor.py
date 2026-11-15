"""Risk Assessor: client quality from history plus scam, free-work, off-platform and
injection signals. Rules and weights are in config.risk_rules (a policy update is a YAML
edit). Reads client history through the marketplace MCP tool when the job has a client id.
"""

from __future__ import annotations

import re
from typing import Any

from agent.config import get_config
from agent.handoffs import RiskFlag, RiskReport, SuspiciousSpan
from agent.mcp_client import ToolBox
from agent.nodes._common import event, timed, tool_events
from agent.state import step

FLAG_FOR = {"off_platform_payment": RiskFlag.off_platform_payment,
            "off_platform_contact": RiskFlag.off_platform_payment,
            "free_work": RiskFlag.free_work, "personal_data_request": RiskFlag.personal_data_request,
            "upfront_deposit": RiskFlag.scam, "too_good": RiskFlag.scam}
SCAM_SIGNALS = {"off_platform_payment", "free_work", "personal_data_request", "scam"}


def injection_spans(text: str) -> list[SuspiciousSpan]:
    out = []
    for pat in get_config().risk_rules.get("injection_patterns", []):
        for m in re.finditer(pat, text, re.IGNORECASE):
            s = max(0, m.start() - 40)
            out.append(SuspiciousSpan(text=text[s:m.end() + 80][:1000],
                                      flag=RiskFlag.prompt_injection, start=m.start(),
                                      end=m.end()))
    return out[:20]


def assess(job: dict[str, Any], client: dict[str, Any] | None) -> RiskReport:
    rules = get_config().risk_rules
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    probs: list[float] = []
    flags: set[str] = set()
    spans: list[SuspiciousSpan] = []
    reasons: list[str] = []
    for name, sig in rules.get("signals", {}).items():
        hits = [m for p in sig["patterns"] for m in re.finditer(p, text, re.IGNORECASE)]
        if hits:
            probs.append(float(sig["weight"]))
            flag = FLAG_FOR.get(name, RiskFlag.scam)
            flags.add(flag.value)
            reasons.append(f"{name.replace('_', ' ')}: \"{hits[0].group(0)}\"")
            spans.extend(SuspiciousSpan(text=text[max(0, h.start() - 30):h.end() + 30],
                                        flag=flag, start=h.start(), end=h.end())
                         for h in hits[:2])
    inj = injection_spans(text)
    if inj:
        flags.add(RiskFlag.prompt_injection.value)
        reasons.append("job post contains instructions aimed at AI assistants (ignored)")
    c = rules.get("client", {})
    client = client or {}
    if client and not client.get("payment_verified", True):
        probs.append(c.get("unverified_payment", 0.15))
        flags.add(RiskFlag.unverified_payment.value)
        reasons.append("client payment method not verified")
    if client and not (client.get("total_spend") or 0):
        probs.append(c.get("no_spend_history", 0.1))
        reasons.append("client has no spend history")
    rating = client.get("rating")
    if rating is not None and rating < c.get("low_rating_below", 3.5):
        probs.append(c.get("low_rating_weight", 0.2))
        flags.add(RiskFlag.low_client_rating.value)
        reasons.append(f"client rating {rating}")
    if job.get("duplicate_of"):
        flags.add(RiskFlag.duplicate.value)
        reasons.append(f"duplicate of {job['duplicate_of']}")
    keep = 1.0
    for p in probs:
        keep *= 1 - p
    score = round(1 - keep, 3)
    is_scam = score >= get_config().thresholds.scam_risk and bool(flags & SCAM_SIGNALS)
    return RiskReport(score=score, flags=sorted(flags), is_scam=is_scam,
                      injection_detected=bool(inj), suspicious_spans=(spans + inj)[:20],
                      explanation="; ".join(reasons) or "no risk signals found")


async def risk_assessor(state: dict) -> dict:
    job = state["job"]
    client = state.get("client") or job.get("client")
    calls: list[dict] = []
    with timed() as t:
        if not client and job.get("client_id"):
            tb = ToolBox("risk", trace_id=state.get("trace_id"))
            try:
                client = await tb.call("get_client_history", client_id=job["client_id"])
            except Exception:  # noqa: BLE001 - assess the post alone if history is unavailable
                client = None
            calls = tb.calls
        dup = state.get("duplicate_of") or job.get("duplicate_of")
        report = assess(job | {"duplicate_of": dup}, client)
    return {"analyses": {"risk": report}, "counters": step(),
            "trace": [*tool_events(state, "risk", calls),
                      event(state, "risk", duration_ms=t["ms"],
                            result_summary=f"risk={report.score} flags={report.flags}")]}
