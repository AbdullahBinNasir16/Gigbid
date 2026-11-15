"""Build the real job data: cleaned jobs, the 1,500 job stream and price statistics.

Inputs (git ignored, see docs/DATA_CARD.md): data/raw/<dataset>/...
Outputs:
  data/real/jobs_clean.parquet        all cleaned jobs (git ignored)
  data/real/job_stream_1500.parquet   stratified stream for GigSim and the dev set (git ignored)
  data/real/job_stream_sample.json    200 row sample (committed, for CI and review)
  data/real/skill_vocab.json          skill vocabulary from the 60k set (committed)
  data/real/price_stats.json          budget percentiles (committed)
  docs/data_preprocessing_log.md      what was dropped and why, with counts (committed)

Usage: python scripts/data/build_real_jobs.py
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from scripts.data.common import (
    RAW,
    REAL,
    ROOT,
    Classifier,
    SkillMatcher,
    clean_text,
    has_pii,
    load_taxonomy,
    mask_pii,
    near_dup_key,
    normalise_text,
    parse_money,
    parse_rate_range,
    stable_id,
)

SRC_50K = "asaniczka/upwork-job-postings-dataset-2024-50k-records"
SRC_200K = "asaniczka/all-jobs-on-upwork-200k-plus"
SRC_60K = "ahmedmyalo/upwork-freelance-jobs-60k"
SRC_CONTRACTS = "asaniczka/freelance-contracts-dataset-1-3-million-entries"
FILES_200K = [
    "all_upwork_jobs_2024-02-07-2024-03-24.csv",
    "all_upwork_jobs_2024-03-24-2024-05-21.csv",
    "all_upwork_jobs_2024-05-21-2024-07-25.csv",
]
PCTS = {"p10": 10, "p25": 25, "p50": 50, "p75": 75, "p90": 90}
MIN_N = 20

COLUMNS = [
    "job_id", "title", "description", "skills", "category", "budget_type", "budget_min",
    "budget_max", "posted_date", "period", "client_country", "client_spend",
    "client_payment_verified", "client_rating", "client_feedback_count", "connects_cost",
    "applicants", "experience_level", "source_dataset", "provenance",
]

log: dict[str, Any] = {}


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in {"true", "false"}:
        return v.lower() == "true"
    return None


def _budget_from_flags(is_hourly: Any, low: Any, high: Any, budget: Any) -> tuple[str, Any, Any]:
    """asaniczka sets: is_hourly may be missing; infer from which fields are filled."""
    h = _bool(is_hourly)
    lo, hi, b = parse_money(low), parse_money(high), parse_money(budget)
    if h is True or (h is None and (lo or hi) and not b):
        return "hourly", lo or hi, hi or lo
    if h is False or (h is None and b):
        return "fixed", b, b
    return "unknown", None, None


def load_60k(vocab_cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(RAW / "upwork_freelance_jobs_60k" / "Final_Upwork_Dataset.csv",
                     encoding="utf-8-sig", low_memory=False)
    log["60k_raw_rows"] = len(df)
    df = df.dropna(subset=["Job_URL"])
    cat_cols = [f"Category_{i}" for i in range(1, 10)]
    skills = df[cat_cols].apply(
        lambda r: list(dict.fromkeys(s.strip() for s in r.dropna().astype(str) if s.strip())), axis=1
    )
    freq = Counter(s for lst in skills for s in lst)
    short_ok = set(vocab_cfg["short_whitelist"])
    vocab = [
        s for s, n in freq.most_common()
        if n >= vocab_cfg["min_frequency"] and (len(s) >= vocab_cfg["min_length"] or s in short_ok)
    ][: vocab_cfg["max_vocab"]]
    log["skill_vocab_size"] = len(vocab)

    rows = []
    for r, sk in zip(df.itertuples(index=False), skills, strict=True):
        rec = r._asdict()
        if rec["Payment_type"] == "Hourly":
            lo, hi = parse_rate_range(rec["Hourly_Rate"])
            if lo is None:
                lo, hi = parse_money(rec["Start_rate"]), parse_money(rec["End_rate"])
            btype, bmin, bmax = "hourly", lo, hi or lo
        elif rec["Payment_type"] == "Fixed-price":
            cost = parse_money(rec["Job_Cost"])
            btype, bmin, bmax = "fixed", cost, cost
        else:
            btype, bmin, bmax = "unknown", None, None
        rows.append({
            "job_id": stable_id("job_", SRC_60K, str(rec["Job_URL"]).split("?")[0]),
            "title": "",  # filled below from "Job Title"
            "description": "" if pd.isna(rec["Description"]) else str(rec["Description"]),
            "skills": sk,
            "budget_type": btype, "budget_min": bmin, "budget_max": bmax,
            "posted_date": None, "period": "2023-02..2023-03",
            "client_country": rec["Client_Country"],
            "client_spend": None,  # filled below from "Spent($)"
            "client_payment_verified": rec["Payment_Situation"] == "Payment verified",
            "client_rating": rec["Rating"],
            "client_feedback_count": rec["Feedback_Num"],
            "connects_cost": rec["Connects_Num"],
            "applicants": rec["Applicants_Num"],
            "experience_level": rec["EX_level_demand"],
            "search_keyword": rec["Search_Keyword"],
            "url_key": str(rec["Job_URL"]).split("?")[0],
            "source_dataset": SRC_60K,
        })
    out = pd.DataFrame(rows)
    # itertuples renames columns that are not identifiers; restore by position.
    out["title"] = df["Job Title"].fillna("").astype(str).values
    out["client_spend"] = pd.to_numeric(df["Spent($)"], errors="coerce").values
    return out, vocab


def load_50k(matcher: SkillMatcher) -> pd.DataFrame:
    df = pd.read_csv(RAW / "upwork_jobs_50k" / "upwork-jobs.csv", low_memory=False)
    log["50k_raw_rows"] = len(df)
    budgets = [
        _budget_from_flags(h, lo, hi, b)
        for h, lo, hi, b in zip(df.is_hourly, df.hourly_low, df.hourly_high, df.budget, strict=True)
    ]
    out = pd.DataFrame({
        "job_id": [stable_id("job_", SRC_50K, str(u).split("?")[0]) for u in df.link],
        "title": df.title.fillna("").astype(str),
        "description": df.description.fillna("").astype(str),
        "skills": [matcher.find(f"{t} {d}") for t, d in zip(df.title, df.description, strict=True)],
        "budget_type": [b[0] for b in budgets],
        "budget_min": [b[1] for b in budgets],
        "budget_max": [b[2] for b in budgets],
        "posted_date": pd.to_datetime(df.published_date, utc=True, errors="coerce"),
        "period": "2023-12..2024-02",
        "client_country": df.country,
        "url_key": df.link.astype(str).str.split("?").str[0],
        "source_dataset": SRC_50K,
    })
    return out


def clean(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    c = cfg["cleaning"]
    df = df.assign(title=df.title.map(clean_text), description=df.description.map(clean_text))
    n0 = len(df)
    df = df[df.description.fillna("").str.strip().str.len() >= c["min_description_chars"]]
    log["dropped_short_or_missing_description"] = n0 - len(df)

    n1 = len(df)
    df = df.drop_duplicates(subset=["url_key"])
    log["dropped_duplicate_url"] = n1 - len(df)

    n2 = len(df)
    full_key = df.title.map(normalise_text) + "|" + df.description.map(normalise_text)
    df = df[~full_key.duplicated()]
    log["dropped_exact_duplicate_text"] = n2 - len(df)

    n3 = len(df)
    nkey = [near_dup_key(t, d, c["near_duplicate_prefix_chars"])
            for t, d in zip(df.title, df.description, strict=True)]
    df = df[~pd.Series(nkey, index=df.index).duplicated()]
    log["dropped_near_duplicate"] = n3 - len(df)

    # Out of range budgets are nulled, not dropped: the text is still useful.
    fb, hr = c["fixed_budget_usd"], c["hourly_rate_usd"]
    fixed_bad = (df.budget_type == "fixed") & ~df.budget_min.between(fb["min"], fb["max"])
    hourly_bad = (df.budget_type == "hourly") & ~(
        df.budget_min.between(hr["min"], hr["max"]) & df.budget_max.between(hr["min"], hr["max"])
    )
    bad = (fixed_bad | hourly_bad) & df.budget_min.notna()
    log["budgets_nulled_out_of_range"] = int(bad.sum())
    df.loc[bad, ["budget_min", "budget_max"]] = np.nan

    pii_rows = int(sum(has_pii(t) or has_pii(d) for t, d in zip(df.title, df.description, strict=True)))
    log["rows_with_pii_masked"] = pii_rows
    df["title"] = df.title.map(mask_pii)
    df["description"] = df.description.map(mask_pii)
    return df


def stratified_stream(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    s = cfg["stream"]
    rng = np.random.default_rng(s["seed"])
    persona_cats = {c for cats in cfg["persona_categories"].values() for c in cats}
    counts = df.category.value_counts()
    alloc: dict[str, int] = {c: min(s["persona_floor"], int(counts.get(c, 0))) for c in persona_cats}
    remaining = s["size"] - sum(alloc.values())
    others = counts.drop(labels=list(persona_cats), errors="ignore")
    share = others / others.sum()
    for c, frac in share.items():
        alloc[str(c)] = min(int(counts[c]), max(s["other_min"], round(frac * remaining)))
    # Fix rounding so the total is exact: adjust the largest non persona category.
    largest = str(others.idxmax())
    alloc[largest] += s["size"] - sum(alloc.values())
    parts = []
    for c, n in sorted(alloc.items()):
        pool = df[df.category == c]
        idx = rng.choice(len(pool), size=n, replace=False)
        parts.append(pool.iloc[np.sort(idx)])
    stream = pd.concat(parts).sample(frac=1, random_state=s["seed"]).reset_index(drop=True)
    log["stream_allocation"] = dict(sorted(alloc.items()))
    return stream


def _pcts(values: pd.Series) -> dict[str, float] | None:
    v = values.dropna()
    if len(v) < MIN_N:
        return None
    out: dict[str, float] = {k: round(float(np.percentile(v, p)), 2) for k, p in PCTS.items()}
    out["n"] = len(v)
    return out


def _by_type(frame: pd.DataFrame) -> dict[str, Any]:
    """Hourly uses the midpoint of the posted range; fixed uses the posted budget."""
    res: dict[str, Any] = {}
    fixed = frame[frame.budget_type == "fixed"].budget_min
    hourly = frame[frame.budget_type == "hourly"][["budget_min", "budget_max"]].mean(axis=1)
    if (f := _pcts(fixed)) is not None:
        res["fixed"] = f
    if (h := _pcts(hourly)) is not None:
        res["hourly"] = h
    return res


def load_200k_prices(clf: Classifier, cfg: dict[str, Any]) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(RAW / "all_upwork_jobs_200k" / f, low_memory=False) for f in FILES_200K])
    log["200k_raw_rows"] = len(df)
    df = df.drop_duplicates(subset=["link"])
    log["200k_unique_links"] = len(df)
    budgets = [
        _budget_from_flags(h, lo, hi, b)
        for h, lo, hi, b in zip(df.is_hourly, df.hourly_low, df.hourly_high, df.budget, strict=True)
    ]
    out = pd.DataFrame({
        "budget_type": [b[0] for b in budgets],
        "budget_min": [b[1] for b in budgets],
        "budget_max": [b[2] for b in budgets],
        "category": [clf.classify(t) for t in df.title.fillna("").astype(str)],
    })
    c = cfg["cleaning"]
    fb, hr = c["fixed_budget_usd"], c["hourly_rate_usd"]
    ok = ((out.budget_type == "fixed") & out.budget_min.between(fb["min"], fb["max"])) | (
        (out.budget_type == "hourly")
        & out.budget_min.between(hr["min"], hr["max"])
        & out.budget_max.between(hr["min"], hr["max"])
    )
    log["200k_rows_with_valid_budget"] = int(ok.sum())
    return out[ok]


def load_contract_prices(clf: Classifier) -> pd.DataFrame:
    df = pd.read_csv(RAW / "freelance_contracts_1_3m" / "contracts.csv",
                     usecols=["job_title", "total_paid", "hourly_rate"], dtype={"job_title": str})
    log["contracts_raw_rows"] = len(df)
    df["category"] = [clf.classify(t) for t in df.job_title.fillna("")]
    return df


def price_stats(jobs: pd.DataFrame, asking_200k: pd.DataFrame, contracts: pd.DataFrame,
                vocab: list[str]) -> dict[str, Any]:
    asking = pd.concat([jobs[["budget_type", "budget_min", "budget_max", "category"]], asking_200k])
    stats: dict[str, Any] = {
        "generated_by": "scripts/data/build_real_jobs.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provenance": "real",
        "note": ("Asking prices from job posts (budgets clients posted, not prices paid). "
                 "Hourly values are the midpoint of the posted range. Paid prices come from "
                 "the contracts dataset. Percentiles are only given when n >= 20."),
        "sources": {"asking": [SRC_50K, SRC_200K, SRC_60K], "paid": [SRC_CONTRACTS]},
        "overall": _by_type(asking),
        "by_category": {c: _by_type(g) for c, g in asking.groupby("category")},
    }
    by_skill: dict[str, Any] = {}
    exploded = jobs[["skills", "budget_type", "budget_min", "budget_max"]].explode("skills")
    top = exploded.skills.value_counts()
    for skill in [s for s in top.index if s in set(vocab)][:400]:
        r = _by_type(exploded[exploded.skills == skill])
        if r:
            by_skill[skill] = r
    stats["by_skill"] = by_skill

    paid: dict[str, Any] = {}
    hourly = contracts[contracts.hourly_rate.between(3, 300)]
    fixed = contracts[contracts.hourly_rate.isna() & contracts.total_paid.between(5, 100000)]
    for c in sorted(contracts.category.unique()):
        entry: dict[str, Any] = {}
        if (h := _pcts(hourly[hourly.category == c].hourly_rate)) is not None:
            entry["hourly_rate"] = h
        if (f := _pcts(fixed[fixed.category == c].total_paid)) is not None:
            entry["fixed_total_paid"] = f
        if entry:
            paid[c] = entry
    stats["paid_by_category"] = paid

    # Connects cost versus posted fixed budget (60k set only: it has both).
    j60 = jobs[(jobs.source_dataset == SRC_60K) & jobs.connects_cost.notna()]
    tiers = [0, 100, 500, 1000, 5000, 1e9]
    conn: dict[str, Any] = {}
    fixed60 = j60[j60.budget_type == "fixed"]
    for lo, hi in itertools.pairwise(tiers):
        g = fixed60[(fixed60.budget_min >= lo) & (fixed60.budget_min < hi)]
        if len(g) >= MIN_N:
            conn[f"{int(lo)}-{int(hi) if hi < 1e9 else 'inf'}"] = {
                "median": float(g.connects_cost.median()),
                "distribution": {str(int(k)): int(v) for k, v in g.connects_cost.value_counts().sort_index().items()},
                "n": len(g),
            }
    stats["connects_by_fixed_budget"] = conn
    stats["connects_overall"] = {
        str(int(k)): int(v) for k, v in j60.connects_cost.value_counts().sort_index().items()
    }
    return stats


def write_log(cfg: dict[str, Any], jobs: pd.DataFrame, stream: pd.DataFrame) -> None:
    lines = [
        "# Data preprocessing log",
        "",
        "Generated by `scripts/data/build_real_jobs.py`. Counts are from the last run.",
        "",
        "| step | count |",
        "|---|---|",
    ]
    for k, v in log.items():
        if not isinstance(v, dict):
            lines.append(f"| {k} | {v:,} |")
    lines += [
        "",
        f"Cleaned jobs: {len(jobs):,}. By source: "
        + ", ".join(f"{k} = {v:,}" for k, v in jobs.source_dataset.value_counts().items()),
        "",
        "## Category counts in cleaned jobs",
        "",
        "| category | jobs |",
        "|---|---|",
        *[f"| {k} | {v:,} |" for k, v in jobs.category.value_counts().items()],
        "",
        f"## Stream allocation (seed {cfg['stream']['seed']}, size {len(stream)})",
        "",
        ("Persona categories get a floor of "
        f"{cfg['stream']['persona_floor']} jobs; other categories are proportional with a "
        f"minimum of {cfg['stream']['other_min']}."),
        "",
        "| category | jobs |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in log["stream_allocation"].items()],
        "",
        "## Rules applied",
        "",
        (f"* Dropped rows whose description is missing or shorter than "
        f"{cfg['cleaning']['min_description_chars']} characters."),
        ("* Dropped duplicate job URLs (query string removed), then exact duplicates of normalised "
        "title plus description, then near duplicates (same normalised title and the same first "
        f"{cfg['cleaning']['near_duplicate_prefix_chars']} normalised description characters). "
        "The 60k set is loaded first, so its richer rows win ties."),
        "* Budgets outside the configured ranges were set to null (row kept).",
        ("* Emails, URLs, phone numbers (9 to 15 digits) and messenger handles were replaced "
        "with [EMAIL], [URL], [PHONE] and [HANDLE]."),
        "* Category comes from the weighted keyword rules in data/real/taxonomy.yaml.",
        ("* Skills: the 60k set's own skill tags; for the 50k set, vocabulary skills found in the "
        "title and description."),
    ]
    (ROOT / "docs" / "data_preprocessing_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    cfg = load_taxonomy()
    clf = Classifier(cfg)

    print("loading 60k ...")
    j60, vocab = load_60k(cfg["skills"])
    matcher = SkillMatcher(vocab, cfg["skills"]["short_whitelist"])
    print("loading 50k ...")
    j50 = load_50k(matcher)

    jobs = clean(pd.concat([j60, j50], ignore_index=True), cfg)
    jobs["category"] = [
        clf.classify(t, d, s) for t, d, s in zip(jobs.title, jobs.description, jobs.skills, strict=True)
    ]
    jobs["provenance"] = "real"
    jobs = jobs.reindex(columns=COLUMNS).reset_index(drop=True)
    log["cleaned_jobs"] = len(jobs)

    REAL.mkdir(parents=True, exist_ok=True)
    jobs.to_parquet(REAL / "jobs_clean.parquet", index=False)
    stream = stratified_stream(jobs, cfg)
    stream.to_parquet(REAL / "job_stream_1500.parquet", index=False)
    sample = stream.head(200).copy()
    sample["posted_date"] = sample.posted_date.astype(str).replace({"NaT": None})
    (REAL / "job_stream_sample.json").write_text(
        sample.to_json(orient="records", indent=1, force_ascii=False), encoding="utf-8"
    )
    (REAL / "skill_vocab.json").write_text(
        json.dumps({"provenance": "real", "source_dataset": SRC_60K, "skills": vocab}, indent=1),
        encoding="utf-8",
    )

    print("price statistics ...")
    stats = price_stats(jobs, load_200k_prices(clf, cfg), load_contract_prices(clf), vocab)
    (REAL / "price_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")

    write_log(cfg, jobs, stream)
    for k, v in log.items():
        print(f"{k}: {v}")
    print(f"stream rows: {len(stream)}  categories: {stream.category.nunique()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
