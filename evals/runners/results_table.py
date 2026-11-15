"""Regenerate the results tables in README.md from evals/results/*.json.

Run: python -m evals.runners.results_table
Replaces everything between <!-- results:start --> and <!-- results:end --> in README.md, so
every number in those tables is copied from a committed results file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "evals/results"


def load(name: str) -> dict | None:
    p = R / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def rag_table() -> str:
    d, f = load("rag_variants.json"), load("rag_followup.json")
    rows = dict(d["results"]) if d else {}
    if f:
        rows.update({k: v for k, v in f["results"].items() if k not in rows})
    out = ["| Variant | Evidence Recall@5 | MRR | nDCG@10 | p95 retrieval latency (s) |",
           "|---|---|---|---|---|"]
    for name, per in rows.items():
        a = per["all"]
        star = " **(shipped)**" if name == "V4 outcome" else ""
        out.append(f"| {name}{star} | {a['recall@5']} | {a['mrr']} | {a['ndcg@10']} | "
                   f"{a['p95_latency_s']} |")
    return "\n".join(out)


def persona_table() -> str:
    d = load("rag_variants.json")
    if not d:
        return ""
    out = ["| Persona | V0 Recall@5 | V4 Recall@5 | V0 nDCG@10 | V4 nDCG@10 |", "|---|---|---|---|---|"]
    for p in ("ai_ml", "fullstack", "data_analyst"):
        v0, v4 = d["results"]["V0 naive"][p], d["results"]["V4 outcome"][p]
        out.append(f"| {p} | {v0['recall@5']} | {v4['recall@5']} | {v0['ndcg@10']} | "
                   f"{v4['ndcg@10']} |")
    return "\n".join(out)


def decision_table() -> str:
    d = load("decisions.json")
    if not d:
        return ""
    out = [("| Persona | Bid/skip F1 | Scam precision | Scam recall | Injection detection recall | "
           "Price in fair band | p95 s per job analysed |"), "|---|---|---|---|---|---|---|"]
    for p, r in d["results"].items():
        out.append(f"| {p} | {r['bid']['f1']} | {r['scam']['precision']} | {r['scam']['recall']} "
                   f"| {r['injection_detection']['recall']} | {r['price_in_fair_band']} | "
                   f"{r['p95_latency_s_per_job_analysed']} |")
    return "\n".join(out)


def headline_table() -> str:
    rag, xp, demo = load("rag_variants.json"), load("gigsim_outcomes.json"), load("demo_proposal.json")
    v0 = rag["results"]["V0 naive"]["all"] if rag else {}
    v4 = rag["results"]["V4 outcome"]["all"] if rag else {}
    a = (xp or {}).get("summary", {}).get("A_llm", {})
    lat = demo["seconds"] if demo else "n/a"
    out = [("| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims per proposal (after verification) "
           "| GigSim reply rate | p95 latency (s) | Cost per proposal (USD) |"),
           "|---|---|---|---|---|---|---|",
           (f"| V0 (naive dense retrieval) | {v0.get('recall@5')} | {v0.get('ndcg@10')} | "
           f"not run | not run | {v0.get('p95_latency_s')} (retrieval only) | 0.0 |"),
           (f"| Shipped: V4 + LLM writer + verification | {v4.get('recall@5')} | {v4.get('ndcg@10')} "
           f"| {a.get('unsupported_claim_rate_after_verification', 'n/a')} | {a.get('reply_rate', 'n/a')} "
           f"| {lat} (one proposal, demo_proposal.json) | 0.0 (Groq free tier) |")]
    return "\n".join(out)


def tools_table() -> str:
    d = load("tool_granularity.json")
    if not d:
        return ""
    out = ["| Tool set | Tools | Tool-selection accuracy | Argument accuracy | Tokens per task |",
           "|---|---|---|---|---|"]
    for k, v in d["results"].items():
        out.append(f"| {k} | {v['tools']} | {v['tool_selection_accuracy']} | "
                   f"{v['argument_accuracy']} | {v['tokens_per_task']} |")
    return "\n".join(out) + f"\n\nModel: {d['model']}, 40 tasks."


def multiagent_table() -> str:
    d = load("multiagent_compare.json")
    if not d:
        return "_Pending: run `python -m evals.runners.multiagent_compare`._"
    out = [("| System | Bid/skip accuracy | Unsupported claims per proposal | Compliance violations "
           "left | Planted scams/injections handled | Tokens per job | p50 s |"),
           "|---|---|---|---|---|---|---|"]
    for k, v in d["results"].items():
        out.append(f"| {k} | {v['bid_skip_accuracy']} | {v['unsupported_claims_per_proposal']} | "
                   f"{v['compliance_violations_left']} | {v['planted_handled']} | "
                   f"{v['tokens_per_job']} | {v['p50_seconds']} |")
    return "\n".join(out) + f"\n\nAll LLM calls: {d['model_for_all_llm_calls']}; persona {d['persona']}."


def xp_table() -> str:
    d = load("gigsim_outcomes.json")
    if not d:
        return "_Pending: run `python -m evals.runners.gigsim_outcomes`._"
    out = ["| Arm | Proposals | Replied or better | Reply rate | Interview or hired | Mean words |",
           "|---|---|---|---|---|---|"]
    for k, v in d["summary"].items():
        out.append(f"| {k} | {v['n']} | {v['replied_or_better']} | {v['reply_rate']} | "
                   f"{v['interview_or_hired']} | {v['mean_words']} |")
    fe = d["fisher_exact"]
    return "\n".join(out) + f"\n\nFisher's exact test p = {fe['p_value']} (two-sided)."


def main() -> None:
    block = f"### Headline (B5)\n\n{headline_table()}\n\n### Retrieval variants (dev set, all personas)\n\n{rag_table()}\n\n### By persona\n\n{persona_table()}\n\n### Decisions (dev set, shipped config)\n\n{decision_table()}\n\n### R&D A: tool granularity\n\n{tools_table()}\n\n### R&D C: single agent vs supervisor vs hand-built graph\n\n{multiagent_table()}\n\n### Signature extension X2: proposal A/B test in GigSim\n\n{xp_table()}"
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    readme.write_text(f"{head}{start}\n{block}\n{end}{tail}", encoding="utf-8")
    print("README results updated")


if __name__ == "__main__":
    main()
