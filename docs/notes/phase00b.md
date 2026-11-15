# Phase 0B notes: real data and GigSim (0B-1 and 0B-3 done, 0B-2 next)

## Which file does what
- scripts/data/inspect_raw.py: prints columns, row counts, null rates and a masked example for every raw dataset (docs/notes/raw_inspection.md).
- scripts/data/common.py: PII masking, money parsing, HTML decoding, the word n-gram PhraseIndex, the category Classifier and SkillMatcher. Shared by the scripts and unit tests.
- data/real/taxonomy.yaml: category keywords, weights, stream sampling and cleaning rules. Edit here, not in Python.
- scripts/data/build_real_jobs.py: merges the 60k and 50k job sets into one schema, cleans, dedupes, masks PII, classifies, samples the 1,500 job stream and builds price_stats.json from the job sets plus the 200k and contracts sets.
- scripts/data/build_priors.py: outcome_priors.json (competition, client population, freelancer side, contracts) and scam_lexicon.json.
- gigsim/: the simulator. world.py holds state (jobs, clients, hidden preferences, Connects, proposals, threads, idempotency, persistence); decisions.py is the client rule (and optional LLM mode); app.py is the HTTP API with auth, per user rate limiting, 5xx chaos and admin endpoints; API.md is the endpoint contract the marketplace MCP server must follow.
- scripts/gigsim_sanity.py: checks that specific letters beat generic ones on real jobs and that padding does not help; writes evals/results/gigsim_sanity.json.

## Three ways it could break
1. Category rules are keyword based. A job that mentions "dashboard" once can land in data_analytics, which changes stream allocation and price bands.
2. GigSim hidden must-have skills come from the job's own skill tags. A writer that just copies the job's skills is rewarded, so GigSim reply rates overstate how good such a writer is.
3. GigSim stores state in one JSON file. Two GigSim processes sharing a state file would overwrite each other. Run one replica only.
