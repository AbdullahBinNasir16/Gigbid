"""Bid decision: skip, watch or bid from fit and risk, using config thresholds only."""

from __future__ import annotations

from agent.config import get_config
from agent.handoffs import BidDecision
from agent.nodes._common import event
from agent.state import Status, step


def decide(state: dict) -> dict:
    t = get_config().thresholds
    a = state.get("analyses", {})
    fit, risk, spec = a.get("fit"), a.get("risk"), a.get("job_spec")
    fit_score = fit.score if fit else 0.0
    risk_score = risk.score if risk else 0.0
    reasons: list[str] = []
    if risk and risk.is_scam:
        decision = "skip"
        reasons.append(f"scam signals: {risk.explanation}"[:500])
    elif risk_score >= t.scam_risk:
        decision = "skip"
        reasons.append(f"risk {risk_score:.2f} >= {t.scam_risk}: {risk.explanation}"[:500])
    elif "duplicate" in (risk.flags if risk else []):
        decision = "skip"
        reasons.append("duplicate of a job already in the queue")
    elif fit_score >= t.fit.bid:
        decision = "bid"
        reasons.append(f"fit {fit_score:.2f} >= {t.fit.bid}")
    elif fit_score >= t.fit.watch:
        decision = "watch"
        reasons.append(f"fit {fit_score:.2f} between watch {t.fit.watch} and bid {t.fit.bid}")
    else:
        decision = "skip"
        reasons.append(f"fit {fit_score:.2f} < {t.fit.watch}")
    if fit and fit.missing_skills and decision != "bid":
        reasons.append(f"missing: {', '.join(fit.missing_skills[:5])}"[:500])
    if fit and fit.matched_skills:
        reasons.append(f"matched: {', '.join(fit.matched_skills[:5])}"[:500])
    if risk and risk.injection_detected:
        reasons.append("injected instructions in the post were ignored")
    auto = decision == "skip" and fit_score < t.autonomy.auto_skip_below_fit
    d = BidDecision(decision=decision, reasons=reasons[:10], fit_score=fit_score,
                    risk_score=risk_score, auto=auto)
    out: dict = {"decision": d, "counters": step(),
                 "trace": [event(state, "decide", result_summary=f"{decision}: {reasons[0]}")]}
    if decision != "bid":
        out |= {"status": Status.done, "status_reason": f"{decision}: {reasons[0]}"}
    _ = spec
    return out
