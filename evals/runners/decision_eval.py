"""Decision evaluation on the dev set: bid-or-skip F1, scam precision/recall, injection
detection, price inside the fair band, latency per job analysed.

Run: python -m evals.runners.decision_eval [--limit N] [--personas ai_ml,...]
Writes evals/results/decisions.json. Uses the real graph nodes (analyst, risk, matcher via
in-memory MCP, decide, pricing); no LLM calls in the default config.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from agent.nodes.analyst import analyst
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import quote
from agent.nodes.risk_assessor import risk_assessor
from agent.state import add_counters, merge_analyses

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]


def load(persona: str, split: str = "dev") -> list[dict]:
    path = (ROOT / "evals/datasets" / f"dev_{persona}.jsonl" if split == "dev"
            else ROOT / "data/heldout" / f"heldout_{persona}.jsonl")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


async def analyse(job: dict, persona: str) -> dict:
    state = {"thread_id": job["job_id"], "persona": persona, "job": job,
             "client": job.get("client"), "duplicate_of": job.get("duplicate_of")}
    parts = await asyncio.gather(asyncio.to_thread(analyst, state), risk_assessor(state),
                                 fit_matcher(state))
    analyses, counters = {}, None
    for p in parts:
        analyses = merge_analyses(analyses, p["analyses"])
        counters = add_counters(counters, p["counters"])
    state |= {"analyses": analyses, "counters": counters}
    return state | decide(state)


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


async def run(persona: str, jobs: list[dict]) -> tuple[dict, list[dict]]:
    c = {"bid": [0, 0, 0], "scam": [0, 0, 0], "inj": [0, 0, 0]}
    in_band = n_band = 0
    lat, rows = [], []
    for job in jobs:
        t = time.perf_counter()
        s = await analyse(job, persona)
        lat.append(time.perf_counter() - t)
        d, risk, g = s["decision"], s["analyses"]["risk"], job["gold"]
        for key, pred, gold in (("bid", d.decision == "bid", g["gold_decision"] == "bid"),
                                ("scam", risk.is_scam, g["is_scam"]),
                                ("inj", risk.injection_detected, g["injected"])):
            c[key][0] += pred and gold
            c[key][1] += pred and not gold
            c[key][2] += gold and not pred
        if d.decision == "bid" and g.get("fair_band"):
            q = quote(job, d.fit_score, persona)
            lo, hi = g["fair_band"]
            n_band += 1
            in_band += lo <= q.amount <= hi
        rows.append({"job_id": job["job_id"], "pred": d.decision, "gold": g["gold_decision"],
                     "fit": d.fit_score, "risk": d.risk_score, "reasons": d.reasons,
                     "is_scam_pred": risk.is_scam, "is_scam_gold": g["is_scam"]})
    lat.sort()
    n = len(jobs)
    return {"n": n, "bid": prf(*c["bid"]), "scam": prf(*c["scam"]),
            "injection_detection": prf(*c["inj"]),
            "price_in_fair_band": round(in_band / n_band, 4) if n_band else None,
            "priced_bids": n_band,
            "p50_latency_s_per_job_analysed": round(lat[n // 2], 3),
            "p95_latency_s_per_job_analysed": round(lat[min(n - 1, int(n * .95))], 3),
            "llm_cost_usd_per_job_analysed": 0.0}, rows


async def main() -> None:
    import logging

    logging.disable(logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--personas", default=",".join(PERSONAS))
    ap.add_argument("--split", default="dev", choices=["dev", "heldout"])
    ap.add_argument("--out", default="decisions")
    a = ap.parse_args()
    from rag.index.store import warm

    warm(a.personas.split(","))
    results, failures = {}, {}
    for p in a.personas.split(","):
        jobs = load(p, a.split)[: a.limit or None]
        results[p], rows = await run(p, jobs)
        failures[p] = [r for r in rows if r["pred"] != r["gold"]
                       and not (r["pred"] == "watch" and r["gold"] == "skip")]
        print(p, json.dumps(results[p]), flush=True)
    out = ROOT / "evals/results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.out}.json").write_text(json.dumps({"split": a.split, "results": results},
                                                  indent=2), encoding="utf-8")
    (out / f"{a.out}_failures.json").write_text(json.dumps(failures, indent=1, default=str),
                                                encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
