"""Pricing Strategist: bid from market statistics, client spend and the user's floor; decide
whether the Connects cost is worth it. Connects cost comes from config tiers (or the
marketplace's current policy when the job carries it), so a policy update needs no code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agent.config import get_config
from agent.handoffs import PriceQuote
from agent.mcp_client import ToolBox
from agent.nodes._common import event, tool_events
from agent.nodes.fit_matcher import persona_profile
from agent.state import step

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def price_stats() -> dict:
    return json.loads((ROOT / "data/real/price_stats.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def outcome_priors() -> dict:
    p = ROOT / "data/real/outcome_priors.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def quote(job: dict, fit: float, persona: str, balance: int | None = None) -> PriceQuote:
    cfg = get_config()
    t = cfg.thresholds.price
    prof = persona_profile(persona)
    bt = job.get("budget_type") if job.get("budget_type") in ("fixed", "hourly") else "fixed"
    cat = price_stats()["by_category"].get(job.get("category") or "other") or \
        price_stats()["by_category"]["other"]
    stats = cat.get(bt) or {}
    low = float(stats.get(t.band_low_percentile, 0) or 0)
    high = float(stats.get(t.band_high_percentile, 0) or 0)
    floor = float(prof.get("hourly_floor" if bt == "hourly" else "fixed_floor")
                  or (t.floor_hourly_usd if bt == "hourly" else t.floor_fixed_usd))
    bmin, bmax = job.get("budget_min"), job.get("budget_max")
    reasons = []
    if bmax:
        # stay inside the client's stated range; aim higher in it when fit is strong
        lo = bmin or bmax
        target = lo + (bmax - lo) * (0.4 + 0.5 * fit)
        reasons.append(f"client range {lo:g}-{bmax:g} {bt}; fit {fit:.2f} places the bid at "
                       f"{0.4 + 0.5 * fit:.0%} of the range")
    else:
        target = (low + high) / 2 if high else floor
        reasons.append(f"no client budget; market {t.band_low_percentile}-"
                       f"{t.band_high_percentile} for {job.get('category')} is {low:g}-{high:g}")
    if target < floor:
        reasons.append(f"raised to your floor {floor:g} (never quote below it)")
        target = floor
    amount = round(target, 0 if target >= 20 else 2)
    size = (bmax or amount) * (40 if bt == "hourly" else 1)
    connects = int(job.get("connects_cost") or cfg.connects_cost_for(size))
    # expected value per Connect: reply-rate prior x fit x the job value, net of the fee
    prior = outcome_priors().get("reply_rate", {}).get(job.get("category") or "", 0.08) \
        if isinstance(outcome_priors().get("reply_rate"), dict) else 0.08
    value = amount * (40 if bt == "hourly" else 1) * (1 - cfg.platform_rules.fees
                                                     .service_fee_percent / 100)
    ev_per_connect = prior * fit * value / max(connects, 1)
    worth = ev_per_connect >= t.min_expected_value_per_connect_usd
    if balance is not None and balance < connects:
        worth = False
        reasons.append(f"only {balance} Connects left, this job costs {connects}")
    reasons.append(f"{connects} Connects; expected value per Connect ${ev_per_connect:.2f} "
                   f"({'worth it' if worth else 'below'} the ${t.min_expected_value_per_connect_usd:g}"
                   " threshold)")
    return PriceQuote(amount=max(amount, 1.0), budget_type=bt, rationale=". ".join(reasons)[:1500],
                      band_low=low or None, band_high=high or None, connects_cost=min(connects, 100),
                      worth_it=worth)


async def pricing(state: dict) -> dict:
    fit = state["analyses"]["fit"].score if state.get("analyses", {}).get("fit") else 0.5
    tb = ToolBox("pricing", trace_id=state.get("trace_id"))
    balance = None
    try:
        balance = (await tb.call("get_connects_balance"))["balance"]
    except Exception:  # noqa: BLE001 - quote without balance; approval shows dry_run anyway
        pass
    q = quote(state["job"], fit, state.get("persona", "ai_ml"), balance)
    return {"price": q, "counters": step(),
            "trace": [*tool_events(state, "pricing", tb.calls),
                      event(state, "pricing", result_summary=f"{q.amount} {q.budget_type}, "
                                                             f"{q.connects_cost} Connects")]}
