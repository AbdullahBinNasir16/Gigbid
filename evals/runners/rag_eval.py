"""Retrieval evaluation: Recall@5, MRR and nDCG@10 per variant and persona on the dev set.

Run: python -m evals.runners.rag_eval [--variants v0_naive,v2_hybrid ...] [--limit N]
Writes evals/results/rag_variants.json and rag_variants.csv.

Relevance is judged at project level: an item is relevant when its project is one of the
job's gold projects. Ranked lists are reduced to distinct projects (first occurrence), so a
variant cannot score twice by returning three chunks of the same project.
Only jobs with at least one gold project are scored (others have nothing to retrieve).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

from rag.index.store import get_index
from rag.retriever import flags_for
from rag.variants.base import Pipeline

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]

CONFIGS: dict[str, list[str]] = {
    "V0 naive": ["v0_naive"],
    "V1 decomposition": ["v1_decomposition"],
    "V2 hybrid": ["v2_hybrid"],
    "V3 rerank": ["v3_rerank"],
    "V4 outcome": ["v4_outcome_aware"],
    "V5 multi-vector": ["v5_multivector"],
    "V8 corrective": ["v8_corrective"],
    "V1+V2": ["v1_decomposition", "v2_hybrid"],
    "V1+V2+V3": ["v1_decomposition", "v2_hybrid", "v3_rerank"],
    "V1+V2+V3+V4": ["v1_decomposition", "v2_hybrid", "v3_rerank", "v4_outcome_aware"],
    "V2+V3": ["v2_hybrid", "v3_rerank"],
    "V2+V4": ["v2_hybrid", "v4_outcome_aware"],
    "V1+V2+V4": ["v1_decomposition", "v2_hybrid", "v4_outcome_aware"],
}


def load_dev(persona: str) -> list[dict]:
    path = ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def project_ranking(index, ranked: list[tuple[str, float]]) -> list[str]:
    seen, out = set(), []
    for cid, _ in ranked:
        proj = index.by_id[cid].project or f"_none:{cid}"
        if proj not in seen:
            seen.add(proj)
            out.append(proj)
    return out


def metrics(ranking: list[str], gold: set[str]) -> dict[str, float]:
    recall5 = len(set(ranking[:5]) & gold) / len(gold)
    mrr = next((1 / (i + 1) for i, p in enumerate(ranking) if p in gold), 0.0)
    dcg = sum(1 / math.log2(i + 2) for i, p in enumerate(ranking[:10]) if p in gold)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
    return {"recall@5": recall5, "mrr": mrr, "ndcg@10": dcg / idcg if idcg else 0.0}


def evaluate(names: list[str], persona: str, jobs: list[dict]) -> dict:
    index = get_index(persona)
    pipe = Pipeline(index, flags_for(names))
    rows, lat = [], []
    for job in jobs:
        gold = set(job["gold"]["gold_projects"])
        t = time.perf_counter()
        if pipe.flags.corrective:
            from rag.variants.v8_corrective import corrective_rank

            ranked = corrective_rank(pipe, job, 10)
        else:
            ranked = pipe.rank(job, 30)
        lat.append(time.perf_counter() - t)
        rows.append(metrics(project_ranking(index, ranked), gold))
    n = len(rows)
    lat.sort()
    return {
        "n": n,
        **{m: round(sum(r[m] for r in rows) / n, 4) for m in ("recall@5", "mrr", "ndcg@10")},
        "p50_latency_s": round(lat[n // 2], 4),
        "p95_latency_s": round(lat[min(n - 1, int(n * 0.95))], 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="rag_variants")
    args = ap.parse_args()
    chosen = [c.strip() for c in args.configs.split(",") if c.strip()]
    results: dict[str, dict] = {}
    for persona in PERSONAS:
        jobs = [j for j in load_dev(persona) if j["gold"]["gold_projects"]]
        if args.limit:
            jobs = jobs[: args.limit]
        for name in chosen:
            r = evaluate(CONFIGS[name], persona, jobs)
            results.setdefault(name, {})[persona] = r
            print(f"{persona:13s} {name:18s} R@5={r['recall@5']:.3f} MRR={r['mrr']:.3f} "
                  f"nDCG@10={r['ndcg@10']:.3f} p95={r['p95_latency_s']:.2f}s", flush=True)
    for name, per in results.items():
        n = sum(v["n"] for v in per.values())
        per["all"] = {m: round(sum(v[m] * v["n"] for v in per.values()) / n, 4)
                      for m in ("recall@5", "mrr", "ndcg@10")}
        per["all"]["p95_latency_s"] = max(v["p95_latency_s"] for k, v in per.items() if k != "all")
        per["all"]["n"] = n
    RESULTS.mkdir(parents=True, exist_ok=True)
    meta = {"embed_model": get_index(PERSONAS[0]).embed_model,
            "reranker": get_index(PERSONAS[0]).rerank_model,
            "relevance": "project-level, gold_projects from evals/datasets",
            "hardware": "CPU only, 8 cores, 16 GB RAM"}
    (RESULTS / f"{args.out}.json").write_text(json.dumps({"meta": meta, "results": results},
                                                         indent=2), encoding="utf-8")
    with (RESULTS / f"{args.out}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config", "persona", "n", "recall@5", "mrr", "ndcg@10", "p95_latency_s"])
        for name, per in results.items():
            for persona, r in per.items():
                w.writerow([name, persona, r["n"], r["recall@5"], r["mrr"], r["ndcg@10"],
                            r["p95_latency_s"]])


if __name__ == "__main__":
    main()
