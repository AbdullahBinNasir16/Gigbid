"""30-job smoke eval for pull requests, with failure thresholds (evals/thresholds.json).

Runs 10 dev jobs per persona through the real analysis nodes (bid-or-skip F1, scam recall)
and drafts proposals for the jobs it would bid on (template writer, no LLM in CI), then
verifies their claims. Fails (exit 1) if F1 drops or unsupported claims rise past the gate.
Writes evals/results/smoke.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from agent.config import get_config
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from evals.runners.decision_eval import analyse, load, prf

ROOT = Path(__file__).resolve().parents[2]


async def main() -> int:
    import logging

    logging.disable(logging.INFO)
    get_config().generation["writer_mode"] = "template"
    gate = json.loads((ROOT / "evals/thresholds.json").read_text(encoding="utf-8"))
    tp = fp = fn = 0
    unsupported_before, unsupported_after, drafts = [], [], 0
    for persona in ("ai_ml", "fullstack", "data_analyst"):
        rows = load(persona)
        real = [j for j in rows if j["job_id"].startswith("job_")]
        bids = [j for j in real if j["gold"]["gold_decision"] == "bid"][:3]
        skips = [j for j in real if j["gold"]["gold_decision"] == "skip"][:4]
        planted = [j for j in rows if j["gold"]["is_scam"]][:2] +             [j for j in rows if j["gold"]["injected"]][:1]
        jobs = bids + skips + planted  # fixed, stratified 10 per persona
        for job in jobs:
            s = await analyse(job, persona)
            pred, gold = s["decision"].decision == "bid", job["gold"]["gold_decision"] == "bid"
            tp, fp, fn = tp + (pred and gold), fp + (pred and not gold), fn + (gold and not pred)
            if pred:
                s |= {"price": None, "drafts": [], "critiques": [], "user_id": "ci"}
                s["drafts"] = writer(s)["drafts"]
                v = verifier(s)["verification"]
                unsupported_before.append(v["unsupported_before"])
                unsupported_after.append(v["unsupported_after"])
                drafts += 1
    f1 = prf(tp, fp, fn)["f1"]
    after = sum(unsupported_after) / len(unsupported_after) if unsupported_after else 0.0
    result = {"jobs": 30, "bid_f1": f1, "drafts": drafts,
              "unsupported_rate_before": round(sum(unsupported_before) / max(1, drafts), 4),
              "unsupported_rate_after": round(after, 4), "gate": gate}
    (ROOT / "evals/results/smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    ok = f1 >= gate["min_bid_f1"] and after <= gate["max_unsupported_rate_after"]
    if not ok:
        print("SMOKE GATE FAILED", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
