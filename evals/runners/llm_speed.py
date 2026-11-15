"""Local LLM throughput on this machine (tokens/second, latency) for the open profile.

Run: python -m evals.runners.llm_speed --base http://localhost:11434/v1 --models qwen2.5:3b,qwen2.5:7b
Writes evals/results/llm_speed.json. The prompt is a real writer prompt (prompt + evidence).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PROMPT = (ROOT / "agent/prompts/writer.md").read_text(encoding="utf-8").replace("{style_rules}", "")
USER = ("JOB POST: Need a LangChain RAG chatbot over our help-centre articles with citations.\n"
        "EVIDENCE:\n[E1] I built a retrieval-augmented chatbot over 3,200 help-centre articles "
        "with source citations; it cut first-response time from 9 hours to 40 seconds.\n"
        "[E2] Hybrid BM25 and embedding search over 80,000 products with a reranker.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:11434/v1")
    ap.add_argument("--models", default="qwen2.5:3b,qwen2.5:7b")
    ap.add_argument("--runs", type=int, default=2)
    a = ap.parse_args()
    out = {"hardware": "Intel laptop CPU, 8 cores, 16 GB RAM, MX130 2 GB (CPU inference)",
           "server": a.base, "models": {}}
    for m in a.models.split(","):
        rows = []
        for _ in range(a.runs):
            t = time.perf_counter()
            r = httpx.post(f"{a.base}/chat/completions", timeout=600, json={
                "model": m, "temperature": 0.4, "max_tokens": 350,
                "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": USER}]})
            dt = time.perf_counter() - t
            r.raise_for_status()
            u = r.json()["usage"]
            rows.append({"seconds": round(dt, 1), "completion_tokens": u["completion_tokens"],
                         "prompt_tokens": u["prompt_tokens"],
                         "tokens_per_s": round(u["completion_tokens"] / dt, 2)})
            print(m, rows[-1], flush=True)
        out["models"][m] = {"runs": rows, "mean_tokens_per_s":
                            round(sum(x["tokens_per_s"] for x in rows) / len(rows), 2),
                            "mean_seconds": round(sum(x["seconds"] for x in rows) / len(rows), 1)}
    (ROOT / "evals/results/llm_speed.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
