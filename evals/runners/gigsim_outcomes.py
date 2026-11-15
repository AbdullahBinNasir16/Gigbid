"""GigSim outcome run and the X2 proposal experiment (A/B test on reply rate).

Run: MODEL_PROFILE=open_hosted python -m evals.runners.gigsim_outcomes --per-persona 15
For a fixed set of GigSim jobs that GigBid decides to bid on, two strategies draft a
proposal for the SAME job, each submitted from its own GigSim user so outcomes never
interfere:
  A  grounded LLM writer (writer -> claim verification -> compliance), the shipped design
  B  evidence-only template writer (deterministic, no LLM)
Then simulated time is advanced a week and reply / interview / hire states are read back.
Significance: Fisher's exact test (two-sided) on replied-or-better.

For the run only, the Connects cost per proposal is set to 1 through GigSim's admin policy
endpoint so both arms can afford the sample; the previous policy is restored afterwards and
both are recorded in the results. gigsim/ is never modified.
Writes evals/results/gigsim_outcomes.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

import httpx
from scipy.stats import fisher_exact

from agent.config import get_config
from agent.marketplace_port import ProposalPayload
from agent.nodes.compliance import check
from agent.nodes.pricing import quote
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from evals.runners.decision_eval import analyse
from mcp_servers.marketplace.adapters.gigsim import GigSimMarketplace

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("GIGSIM_BASE_URL", "http://localhost:8081")
ADMIN = {"Authorization": f"Bearer {os.environ.get('GIGSIM_ADMIN_TOKEN', 'dev-gigsim-admin')}"}
CATEGORIES = {"ai_ml": "ai_ml", "fullstack": "web_dev", "data_analyst": "data_analytics"}
GOOD = {"replied", "interview", "hired"}


async def draft(state: dict, mode: str) -> tuple[str, dict]:
    get_config().generation["writer_mode"] = mode
    s = dict(state) | {"drafts": [], "critiques": [], "user_id": f"xp-{mode}"}
    s["drafts"] = (await asyncio.to_thread(writer, s))["drafts"]
    v = await asyncio.to_thread(verifier, s)
    s["drafts"] = v["drafts"]
    text = check(s["drafts"][-1].cover_letter).cleaned_text or s["drafts"][-1].cover_letter
    return text, v["verification"] | {"writer": s["drafts"][0].strategy}


async def main() -> None:
    logging.disable(logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=15)
    ap.add_argument("--advance-minutes", type=int, default=7 * 24 * 60)
    a = ap.parse_args()
    from rag.index.store import warm

    warm()
    run = uuid.uuid4().hex[:6]
    arms = {"A_llm": GigSimMarketplace(user_id=f"xp_{run}_a", token="dev-gigsim-token"),
            "B_template": GigSimMarketplace(user_id=f"xp_{run}_b", token="dev-gigsim-token")}
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as http:
        old_policy = (await http.get("/admin/policy", headers=ADMIN)).json()
        await http.post("/admin/policy", headers=ADMIN,
                        json={"cost_per_proposal": 1, "note": f"X2 experiment {run}"})
        rows, t0 = [], time.time()
        try:
            for persona, cat in CATEGORIES.items():
                jobs = (await http.get("/jobs", params={"category": cat, "limit": 100},
                                       headers={"Authorization": "Bearer dev-gigsim-token"})).json()
                n = 0
                for job in jobs["items"]:
                    if n >= a.per_persona:
                        break
                    client = (await http.get(f"/clients/{job['client_id']}",
                                             headers={"Authorization": "Bearer dev-gigsim-token"})
                              ).json() if job.get("client_id") else None
                    state = await analyse(job | {"client": client}, persona)
                    if state["decision"].decision != "bid":
                        continue
                    n += 1
                    price = quote(job, state["decision"].fit_score, persona)
                    state |= {"price": price, "user_id": "xp"}
                    for arm, port in arms.items():
                        text, ver = await draft(state, "llm" if arm == "A_llm" else "template")
                        key = f"{run}:{arm}:{job['job_id']}"
                        try:
                            d = await port.create_proposal_draft(ProposalPayload(
                                job_id=job["job_id"], cover_letter=text, amount=price.amount,
                                budget_type=price.budget_type), idempotency_key=key + ":d")
                            await port.submit_proposal(d.resource_id, idempotency_key=key + ":s")
                            rows.append({"arm": arm, "persona": persona, "job_id": job["job_id"],
                                         "proposal_id": d.resource_id, "words": len(text.split()),
                                         "unsupported_before": ver["unsupported_before"],
                                         "unsupported_after": ver["unsupported_after"],
                                         "claims": ver["claims"], "writer": ver["writer"]})
                            if arm == "A_llm":
                                await asyncio.sleep(8)  # stay under the hosted tokens/minute limit
                        except Exception as exc:  # noqa: BLE001
                            rows.append({"arm": arm, "persona": persona, "job_id": job["job_id"],
                                         "error": f"{type(exc).__name__}: {exc}"[:200]})
                    print(persona, n, job["title"][:50], flush=True)
            await http.post("/admin/advance", params={"minutes": a.advance_minutes}, headers=ADMIN)
        finally:
            restore = {"cost_per_proposal": old_policy.get("connects", {}).get("cost_per_proposal", 6),
                       "cost_by_budget_usd": old_policy.get("connects", {}).get("cost_by_budget_usd"),
                       "note": f"restore after X2 experiment {run}"}
            await http.post("/admin/policy", headers=ADMIN,
                            json={k: v for k, v in restore.items() if v is not None})
    states: dict[str, str] = {}
    for port in arms.values():
        for p in await port.list_proposals():
            states[p["proposal_id"]] = p["state"]
    summary = {}
    for arm in arms:
        # arm A only counts proposals the LLM really wrote (no silent template fallback)
        ok = [r for r in rows if r["arm"] == arm and "proposal_id" in r
              and (arm != "A_llm" or str(r.get("writer", "")).startswith("llm"))]
        for r in ok:
            r["state"] = states.get(r["proposal_id"], "?")
        replied = sum(r["state"] in GOOD for r in ok)
        summary[arm] = {"n": len(ok), "replied_or_better": replied,
                        "reply_rate": round(replied / len(ok), 4) if ok else None,
                        "hired": sum(r["state"] == "hired" for r in ok),
                        "interview_or_hired": sum(r["state"] in ("interview", "hired") for r in ok),
                        "mean_words": round(sum(r["words"] for r in ok) / max(1, len(ok)), 1),
                        "unsupported_claim_rate_before_verification": round(
                            sum(r["unsupported_before"] for r in ok) / max(1, len(ok)), 4),
                        "unsupported_claim_rate_after_verification": round(
                            sum(r["unsupported_after"] for r in ok) / max(1, len(ok)), 4)}
    a_, b_ = summary["A_llm"], summary["B_template"]
    table = [[a_["replied_or_better"], a_["n"] - a_["replied_or_better"]],
             [b_["replied_or_better"], b_["n"] - b_["replied_or_better"]]]
    odds, p = fisher_exact(table)
    out = {"run": run, "profile": get_config().models.profile, "minutes_advanced": a.advance_minutes,
           "policy_during_run": {"cost_per_proposal": 1}, "policy_restored": restore,
           "summary": summary, "fisher_exact": {"table": table, "odds_ratio": odds,
                                                 "p_value": round(float(p), 4)},
           "seconds": round(time.time() - t0, 1), "rows": rows}
    (ROOT / "evals/results/gigsim_outcomes.json").write_text(json.dumps(out, indent=2, default=str),
                                                            encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("summary", "fisher_exact")}, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
