"""Build outcome priors and a scam lexicon from the real datasets.

Outputs (committed, aggregates only):
  data/real/outcome_priors.json   priors GigSim uses to make client behaviour realistic
  data/real/scam_lexicon.json     phrases that separate fraudulent from legitimate posts

Honest limits (also in docs/DATA_CARD.md):
* No dataset contains proposals, replies or hires. Reply priors are PROXIES built from
  competition (applicants per job) and freelancer-side success rates.
* freelancer_success_churn looks synthetic itself (smooth distributions, round ids).
* trial_1 fraudulent rows follow one template, so the lexicon is narrow.

Usage: python -m scripts.data.build_priors   (run build_real_jobs first)
"""

from __future__ import annotations

import itertools
import json
import math
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from scripts.data.common import RAW, REAL, tokenize

HEXISH = re.compile(r"[0-9a-f]{16,}")

SRC_CHURN = "sarveshchhetri/freelancer-success-earnings-and-churn-prediction"
SRC_CONTRACTS = "asaniczka/freelance-contracts-dataset-1-3-million-entries"
SRC_60K = "ahmedmyalo/upwork-freelance-jobs-60k"
SRC_TRIAL = "adityammantri/trial-1"

# Midpoint of each applicants bucket in the 60k set.
APPLICANT_MIDPOINTS = {
    "Less than 5": 3, "5 to 10": 7.5, "10 to 15": 12.5, "15 to 20": 17.5, "20 to 50": 35, "50+": 60,
}
# churn primary_skill -> our taxonomy category
CHURN_TO_CATEGORY = {
    "AI & Machine Learning": "ai_ml",
    "Data Science & Analytics": "data_analytics",
    "Web Development": "web_dev",
    "Mobile App Development": "mobile_dev",
    "Graphic Design": "design",
    "Digital Marketing": "marketing",
    "SEO / SEM": "marketing",
    "Content Writing / Copywriting": "writing",
    "Video Editing": "video",
    "Virtual Assistant": "admin",
    "Accounting & Finance": "admin",
}


def q(values: pd.Series, ps: tuple[int, ...] = (10, 25, 50, 75, 90)) -> dict[str, float]:
    v = values.dropna()
    out = {f"p{p}": round(float(np.percentile(v, p)), 3) for p in ps}
    out["n"] = len(v)
    return out


def competition(jobs: pd.DataFrame) -> dict[str, Any]:
    j = jobs[jobs.source_dataset == SRC_60K].copy()
    j["applicants_mid"] = j.applicants.map(APPLICANT_MIDPOINTS)
    out: dict[str, Any] = {}
    for cat, g in j.groupby("category"):
        dist = g.applicants.value_counts(normalize=True).round(4).to_dict()
        out[str(cat)] = {
            "applicants_bucket_share": dist,
            "applicants_mid_mean": round(float(g.applicants_mid.mean()), 2),
            "n": len(g),
        }
    return out


def client_population(jobs: pd.DataFrame) -> dict[str, Any]:
    j = jobs[jobs.source_dataset == SRC_60K]
    rated = j[j.client_feedback_count > 0]
    return {
        "payment_verified_rate": round(float(j.client_payment_verified.mean()), 4),
        "spend_usd": q(j.client_spend),
        "share_zero_spend": round(float((j.client_spend.fillna(0) == 0).mean()), 4),
        "rating_if_rated": q(rated.client_rating),
        "feedback_count": q(j.client_feedback_count),
        "share_unrated": round(float((j.client_feedback_count.fillna(0) == 0).mean()), 4),
        "top_countries": j.client_country.value_counts(normalize=True).head(10).round(4).to_dict(),
        "source_dataset": SRC_60K,
    }


def freelancer_side() -> dict[str, Any]:
    f = pd.read_csv(RAW / "freelancer_success_churn" / "freelancer_gig_success_dataset.csv")
    f["category"] = f.primary_skill.map(CHURN_TO_CATEGORY)
    by_cat = {}
    for cat, g in f.groupby("category"):
        by_cat[str(cat)] = {
            "job_success_rate_pct": q(g.job_success_rate),
            "repeat_client_rate": q(g.repeat_client_rate),
            "avg_response_time_hrs": q(g.avg_response_time_hrs),
            "hourly_rate_usd": q(g.hourly_rate_usd),
            "n": len(g),
        }
    # Does having a portfolio relate to success? A weak signal the simulator may use.
    portfolio_effect = {
        "success_score_with_portfolio": round(float(f[f.has_portfolio == 1].success_score.mean()), 2),
        "success_score_without_portfolio": round(float(f[f.has_portfolio == 0].success_score.mean()), 2),
    }
    return {
        "source_dataset": SRC_CHURN,
        "warning": "This dataset appears synthetic (smooth distributions, sequential ids). "
        "Use only as a weak prior.",
        "rows": len(f),
        "by_category": by_cat,
        "portfolio_effect": portfolio_effect,
    }


def contracts() -> dict[str, Any]:
    c = pd.read_csv(RAW / "freelance_contracts_1_3m" / "contracts.csv",
                    usecols=["end_date", "total_hours", "total_paid", "hourly_rate"])
    paid = c[c.total_paid > 0]
    return {
        "source_dataset": SRC_CONTRACTS,
        "rows": len(c),
        "share_open_contracts": round(float(c.end_date.isna().mean()), 4),
        "share_hourly": round(float(c.hourly_rate.notna().mean()), 4),
        "total_hours": q(c.total_hours),
        "total_paid_usd_if_paid": q(paid.total_paid),
        "share_zero_paid": round(float((c.total_paid == 0).mean()), 4),
    }


def scam_lexicon(top_k: int = 60, min_count: int = 30) -> dict[str, Any]:
    t = pd.read_excel(RAW / "trial_1" / "processed_labeled_dataset_without_encoding.xlsx",
                      usecols=["job_desc", "fraudulent"])
    t = t.dropna(subset=["fraudulent", "job_desc"])
    # Repeated company boilerplate would dominate the counts; count each text once.
    n_before = len(t)
    t = t.drop_duplicates(subset=["job_desc"])
    duplicates_dropped = n_before - len(t)
    fraud: Counter[str] = Counter()
    legit: Counter[str] = Counter()
    for text, label in zip(t.job_desc.astype(str), t.fraudulent, strict=True):
        # Drop hash-like tokens (anonymised URLs) and bare numbers.
        toks = [w for w in tokenize(text) if not HEXISH.fullmatch(w) and not w.isdigit()]
        grams = set(toks) | {" ".join(p) for p in itertools.pairwise(toks)}
        (fraud if label == 1 else legit).update(grams)
    n_f, n_l = int((t.fraudulent == 1).sum()), int((t.fraudulent == 0).sum())
    scored = []
    for g, cf in fraud.items():
        if cf < min_count:
            continue
        cl = legit.get(g, 0)
        # Smoothed log odds of document frequency.
        lo = math.log((cf + 1) / (n_f + 2)) - math.log((cl + 1) / (n_l + 2))
        scored.append((lo, g, cf, cl))
    scored.sort(reverse=True)
    return {
        "source_dataset": SRC_TRIAL,
        "provenance": "real",
        "warning": "Fraudulent rows in this dataset follow one template ('earn 5000week immediate "
        "hiring contact now at ...'). The lexicon is narrow; planted scams in the dev set use "
        "a wider, hand written set of patterns.",
        "documents": {"fraudulent": n_f, "legitimate": n_l, "duplicates_dropped": duplicates_dropped},
        "phrases": [
            {"phrase": g, "log_odds": round(lo, 3), "fraud_docs": cf, "legit_docs": cl}
            for lo, g, cf, cl in scored[:top_k]
        ],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    jobs = pd.read_parquet(REAL / "jobs_clean.parquet")
    comp = competition(jobs)
    priors = {
        "generated_by": "scripts/data/build_priors.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provenance": "real",
        "what_this_is": (
            "Priors for GigSim client behaviour. No dataset has real proposal outcomes, so "
            "reply probability is a proxy: base_reply_rate = clip(reply_scale / applicants_mid). "
            "reply_scale lives in gigsim config. Only relative comparisons inside GigSim mean "
            "anything."
        ),
        "applicant_midpoints": APPLICANT_MIDPOINTS,
        "competition_by_category": comp,
        "client_population": client_population(jobs),
        "freelancer_side": freelancer_side(),
        "contracts": contracts(),
    }
    (REAL / "outcome_priors.json").write_text(json.dumps(priors, indent=1), encoding="utf-8")
    lex = scam_lexicon()
    (REAL / "scam_lexicon.json").write_text(json.dumps(lex, indent=1), encoding="utf-8")
    print("competition categories:", list(comp))
    print("client population:", json.dumps(priors["client_population"], indent=1)[:800])
    print("top scam phrases:", [p["phrase"] for p in lex["phrases"][:15]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
