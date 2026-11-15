"""Single-agent-graph demo: draft one grounded proposal for a dev job, stop at approval.

Run: MODEL_PROFILE=open_hosted python -m scripts.demo_proposal [persona]
Prints the decision, the draft, per-claim support and the dry_run preview, and writes
evals/results/demo_proposal.json (cited in the README).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.config import get_config
from agent.graphs.bid_graph import build_bid_graph
from agent.marketplace_port import Job
from agent.memory import store as mem
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.fake import FakeMarketplace

ROOT = Path(__file__).resolve().parents[1]


async def main(persona: str) -> None:
    logging.disable(logging.INFO)
    mem.set_store(InMemoryStore())
    rows = [json.loads(x) for x in (ROOT / f"evals/datasets/dev_{persona}.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    for job in (r for r in rows if r["gold"]["gold_decision"] == "bid"
                and r["job_id"].startswith("job_")):
        server.set_port(FakeMarketplace(jobs=[Job(
            job_id=job["job_id"], title=job["title"], description=job["description"],
            skills=job["skills"], budget_type=job["budget_type"])]))
        g = build_bid_graph(InMemorySaver())
        t = time.perf_counter()
        cfg = {"configurable": {"thread_id": job["job_id"]}}
        out = await g.ainvoke({"thread_id": job["job_id"], "persona": persona, "job": job,
                               "client": job.get("client")}, cfg)
        if "__interrupt__" not in out:
            continue
        p = out["__interrupt__"][0].value
        result = {"profile": get_config().models.profile, "job_id": job["job_id"],
                  "title": job["title"], "seconds": round(time.perf_counter() - t, 1),
                  "tokens": out["counters"].tokens, "critic_loops": out["counters"].critic_loops,
                  "verification": out.get("verification"),
                  "cover_letter": p["draft"]["cover_letter"],
                  "claims": [{"text": c["text"], "support": c["support"],
                              "evidence": c["evidence_ids"]} for c in p["draft"]["claims"]],
                  "preview": p["preview"], "price": p["price"]}
        (ROOT / "evals/results/demo_proposal.json").write_text(json.dumps(result, indent=2),
                                                              encoding="utf-8")
        print(json.dumps(result, indent=2))
        return
    print("no bid job found")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ai_ml"))
