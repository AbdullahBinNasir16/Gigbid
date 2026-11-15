"""Analytics, health (degraded mode) and the memory viewer."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from fastapi import APIRouter

from agent.memory.store import delete_memory, list_memory
from apps.api import db
from apps.api.auth import CurrentUser
from apps.api.schemas import MemoryItem

router = APIRouter(tags=["analytics"])


@router.get("/analytics")
def analytics(user: CurrentUser) -> dict:
    jobs = db.q(db.select(db.jobs).where(db.jobs.c.user_id == user["user_id"]))
    runs = db.q(db.select(db.runs).where(db.runs.c.user_id == user["user_id"]))
    by_cat: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    for j in jobs:
        cat = json.loads(j["data"]).get("category") or "other"
        by_cat[cat][j["decision"] or "pending"] += 1
        by_cat[cat]["submitted"] += j["status"] == "submitted"
        a = json.loads(j["analysis"]) if j["analysis"] else {}
        if j["decision"] == "skip" and (a.get("decision") or {}).get("reasons"):
            reasons[a["decision"]["reasons"][0].split(":")[0][:60]] += 1
    m = [json.loads(r["metrics"] or "{}") for r in runs]
    secs = sorted(x.get("seconds", 0) for x in m if x.get("seconds"))
    p95 = secs[min(len(secs) - 1, int(len(secs) * 0.95))] if secs else None
    return {"by_category": {k: dict(v) for k, v in by_cat.items()},
            "connects_spent": sum(x.get("connects", 0) for x in m),
            "proposals_submitted": sum(bool(x.get("submitted")) for x in m),
            "runs": len(runs), "p95_run_seconds": p95,
            "tokens_total": sum(x.get("tokens", 0) for x in m),
            "cost_usd_total": 0.0,  # open profile: local or free-tier open models
            "top_skip_reasons": reasons.most_common(6)}


@router.get("/memory/{kind}", response_model=list[MemoryItem])
def memory(kind: str, user: CurrentUser) -> list[MemoryItem]:
    return [MemoryItem(key=i["key"], rule=i.get("rule", ""), promoted_by=i.get("promoted_by"))
            for i in list_memory(user["user_id"], kind)]


@router.delete("/memory/{kind}/{key}")
def forget(kind: str, key: str, user: CurrentUser) -> dict:
    delete_memory(user["user_id"], kind, key)
    return {"ok": True}
