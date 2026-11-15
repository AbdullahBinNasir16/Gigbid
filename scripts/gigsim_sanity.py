"""Sanity check of GigSim client behaviour: specific versus generic letters on real jobs.

Why: the simulator must reward specific, evidence based proposals over generic ones
without being trivially gameable. Writes evals/results/gigsim_sanity.json so the numbers
quoted in docs trace to a file. Runs the World in process (no HTTP), rule mode, fixed seed.

Usage: python -m scripts.gigsim_sanity [--jobs 400]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from gigsim.settings import load_config
from gigsim.world import World

ROOT = Path(__file__).resolve().parents[1]

GENERIC = (
    "Dear hiring manager, I am writing to apply for your job. I am a hard working and "
    "passionate freelancer with many years of experience. I can do this job very well and on "
    "time. Please contact me."
)


def specific(job: dict) -> str:
    skills = ", ".join(job["skills"][:3])
    return (
        f"For your {job['title'][:60]} project: I built a similar solution with {skills} for a "
        "client last year, delivering it in 3 weeks and cutting their manual work by 40%. I can "
        "share the repo and start with a small first milestone."
    )


def padded(job: dict) -> str:
    return GENERIC + " " + " ".join(["I am very reliable and committed to quality."] * 60)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=400)
    args = parser.parse_args()
    cfg = load_config()
    world = World(cfg)
    jobs = [j for j in world.jobs.values() if j["skills"] and j.get("budget_max")][: args.jobs]
    styles = {"specific": specific, "generic": lambda _j: GENERIC, "generic_padded": padded}
    results = {}
    for name, make_letter in styles.items():
        viewed = replied = hired = 0
        for i, job in enumerate(jobs):
            user = f"{name}-{i}"
            btype = job["budget_type"] if job["budget_type"] != "unknown" else "fixed"
            p = world.create_draft(user, {"job_id": job["job_id"], "cover_letter": make_letter(job),
                                          "amount": float(job["budget_max"]), "budget_type": btype})
            world.submit(user, p.proposal_id)
            d = world.proposals[p.proposal_id].decision
            viewed, replied, hired = viewed + d["viewed"], replied + d["replied"], hired + d["hired"]
        n = len(jobs)
        results[name] = {"n": n, "viewed_rate": round(viewed / n, 4),
                         "reply_rate": round(replied / n, 4), "hire_rate": round(hired / n, 4)}
    out = {
        "generated_by": "scripts/gigsim_sanity.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": cfg["seed"], "decision_mode": cfg["decision"]["mode"],
        "note": "Same jobs, same simulated clients, one proposal per job per style. "
                "Price = posted budget. Relative comparison inside GigSim only.",
        "results": results,
    }
    path = ROOT / "evals" / "results" / "gigsim_sanity.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
