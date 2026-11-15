# Real data

Outputs of `scripts/data/build_real_jobs.py` and `scripts/data/build_priors.py`, built from
the Kaggle datasets in `data/raw/` (git ignored). Every record has `provenance: real`.

Committed: `taxonomy.yaml` (rules), `skill_vocab.json`, `price_stats.json`,
`outcome_priors.json`, `scam_lexicon.json` (aggregates), `job_stream_1500.parquet` and
`job_stream_sample.json` (masked job rows), and `NOTICE.md` (licences and attribution).
Git ignored: `jobs_clean.parquet` (54 MB). See docs/DATA_CARD.md.
