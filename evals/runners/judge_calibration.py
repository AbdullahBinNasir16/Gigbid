"""LLM-judge calibration (B4): the student labels 30 proposals, the judge labels the same 30,
and we report Cohen's kappa. Human labels must come from the student, never from a model.

Step 1  python -m evals.runners.judge_calibration prepare
        -> evals/datasets/judge_items.jsonl (30 proposals: GigSim run drafts + past proposals)
           evals/datasets/judge_labels.csv  (fill the `human` column: good | weak)
Step 2  MODEL_PROFILE=open_hosted python -m evals.runners.judge_calibration judge
        -> adds the judge's label per item (evals/datasets/judge_items.jsonl)
Step 3  python -m evals.runners.judge_calibration kappa
        -> evals/results/judge_calibration.json (kappa, agreement, disagreements to discuss)
Rubric (same for both): "good" = specific opening that mirrors the client's problem, at least
one concrete claim backed by the portfolio, no invented facts, clear next step; else "weak".
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "evals/datasets/judge_items.jsonl"
LABELS = ROOT / "evals/datasets/judge_labels.csv"
RUBRIC = ("Label this freelance proposal 'good' or 'weak'. good = specific opening that mirrors "
          "the client's problem, at least one concrete claim backed by real past work, no "
          "invented facts, a clear next step. Otherwise weak. Reply with one word.")


def prepare() -> None:
    rng = random.Random(4016)
    items = []
    for persona in ("ai_ml", "fullstack", "data_analyst"):
        rows = [json.loads(x) for x in (ROOT / f"data/personas/{persona}/proposals.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        for r in rng.sample(rows, 10):
            items.append({"id": r["id"], "job": r["job_title"], "text": r["text"]})
    with ITEMS.open("w", encoding="utf-8") as f:
        for it in items[:30]:
            f.write(json.dumps(it) + "\n")
    with LABELS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "job", "text", "human"])
        for it in items[:30]:
            w.writerow([it["id"], it["job"], it["text"], ""])
    print(f"wrote {ITEMS} and {LABELS}; fill the human column with good or weak")


def judge() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.llm import get_llm

    llm = get_llm("critic")
    items = [json.loads(x) for x in ITEMS.read_text(encoding="utf-8").splitlines()]
    for it in items:
        msg = llm.invoke([SystemMessage(content=RUBRIC),
                          HumanMessage(content=f"Job: {it['job']}\nProposal: {it['text']}")])
        it["judge"] = "good" if "good" in str(msg.content).lower() else "weak"
    ITEMS.write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    print("judge labels added")


def kappa() -> None:
    items = {json.loads(x)["id"]: json.loads(x) for x in ITEMS.read_text(encoding="utf-8")
             .splitlines()}
    with LABELS.open(encoding="utf-8") as f:
        human = {r["id"]: r["human"].strip().lower() for r in csv.DictReader(f)
                 if r["human"].strip()}
    pairs = [(human[i], items[i]["judge"]) for i in human if "judge" in items.get(i, {})]
    if len(pairs) < 30:
        sys.exit(f"only {len(pairs)} labelled pairs; label all 30 first")
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n)
             for c in ("good", "weak"))
    k = (po - pe) / (1 - pe) if pe < 1 else 1.0
    out = {"n": n, "agreement": round(po, 4), "cohens_kappa": round(k, 4),
           "disagreements": [{"id": i, "human": human[i], "judge": items[i]["judge"],
                              "text": items[i]["text"]} for i in human
                             if items[i].get("judge") != human[i]]}
    (ROOT / "evals/results/judge_calibration.json").write_text(json.dumps(out, indent=2),
                                                              encoding="utf-8")
    print(json.dumps({k_: out[k_] for k_ in ("n", "agreement", "cohens_kappa")}))


if __name__ == "__main__":
    {"prepare": prepare, "judge": judge, "kappa": kappa}[sys.argv[1] if len(sys.argv) > 1
                                                       else "prepare"]()
