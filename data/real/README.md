# Real data

Outputs of `scripts/data/build_real_jobs.py` and `scripts/data/build_priors.py`, built from
the Kaggle datasets in `data/raw/` (git ignored). Every record has `provenance: real`.

Committed: `taxonomy.yaml` (rules), `skill_vocab.json`, `price_stats.json`,
`outcome_priors.json`, `scam_lexicon.json` (aggregates) and `job_stream_sample.json`
(200 masked rows for CI). Git ignored: `*.parquet` (`jobs_clean.parquet`,
`job_stream_1500.parquet`). See docs/DATA_CARD.md.
