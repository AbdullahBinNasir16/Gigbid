# Project status (handoff note)

Last updated: 15 November 2026. Branch: `feat/phase00b-data-sim` (stacked on `feat/phase01-foundation`).

## Done
- Phase 0: starter kit fixed, compose skeleton, CI, repo rule checker.
- Phase 1: config (open, open_hosted, paid profiles), get_llm, handoffs, state with reducers, marketplace port, fake adapter. Notes: docs/notes/phase01.md.
- Phase 0B-1: real data pipeline (scripts/data/), 109,391 cleaned jobs, 1,500 job stream (committed), price stats, outcome priors, scam lexicon, DATA_CARD with licences, NOTICE.md.
- Phase 0B-3: GigSim simulator (gigsim/) with tests, API.md, Dockerfile, compose service, sanity check (evals/results/gigsim_sanity.json). Notes: docs/notes/phase00b.md.

## Next
1. After the move to D:, point heavy caches at D: (OLLAMA_MODELS, HF_HOME, PIP_CACHE_DIR), make a .venv in the repo, `pip install -e ".[dev,data]"`.
2. Decide model sizes now that disk space is available (config.yaml open profile; embeddings and reranker).
3. Add a CI job that runs `docker compose up` and checks health endpoints (Docker is not used locally).
4. Phase 0B-2: personas (AI/ML engineer, full stack developer, data analyst), structured project catalogs with checkable facts, generated case studies, READMEs, reviews, about 150 labelled proposals each, dev eval set (about 200 jobs per persona, gold labels, planted scams, injections, duplicates), held out set in data/heldout/ (git ignored), provenance test.

## Machine facts
- Windows 11 Home, 16 GB RAM, 8 cores, GPU MX130 2 GB. Ollama installed with qwen2.5:3b.
- No Docker and no `make` on PATH; run Makefile commands directly.
- Raw Kaggle data in data/raw/ (git ignored). Rebuild with `python -m scripts.data.build_real_jobs` then `python -m scripts.data.build_priors` (about 10 minutes).

## Open questions for the student
- Upwork account or not (decides Phase 3B live run).
- Groq (or other hosted open model) key for the open_hosted profile.
