# GigSim: a student built marketplace simulator

**GigSim was built by the student for the AI-4016 GigBid assignment. It is not an official
simulator and it is not Upwork.** It stands in for a freelance marketplace during development,
evaluation and the demo. Reply and hire rates measured on GigSim only mean something
relative to other runs on GigSim.

GigSim is independent of the agent code: it imports nothing from `agent/`, `rag/` or
`mcp_servers/`. Agents reach it only through the marketplace MCP server and its adapter.

## Run

```bash
# local
uvicorn gigsim.app:app --port 8081
# docker (from the repo root)
docker compose -f infra/docker-compose.yml up -d gigsim
curl http://localhost:8081/health
```

Env: `GIGSIM_API_TOKEN`, `GIGSIM_ADMIN_TOKEN` (dev defaults exist for local runs only),
`GIGSIM_DATA_DIR` (default `<repo>/data`), `GIGSIM_STATE_FILE` (optional JSON file that keeps
proposals, Connects and idempotency keys across restarts), and `GIGSIM_LLM_*` for the
optional LLM client mode. Endpoints: [API.md](API.md). Settings: [config.yaml](config.yaml).

## Where the data comes from

* **Jobs:** `data/real/job_stream_1500.parquet` (real Upwork postings from two Kaggle
  datasets, cleaned and PII masked by `scripts/data/build_real_jobs.py`). If it is missing,
  the committed 200 row sample `data/real/job_stream_sample.json` is used (CI does this).
  Historical jobs are spread over the last 30 simulated days. Dev or hidden test jobs can be
  loaded with `POST /admin/jobs`.
* **Live stream:** a timer (or `POST /admin/live/tick`) adds jobs: real jobs re-posted
  now (60%), near duplicates (15%), scam patterns (15%) and posts with injected instructions
  (10%). Templates: [templates.yaml](templates.yaml).
* **Clients:** 600 synthetic clients. Their public history (payment verified, spend, rating,
  feedback count, country) is sampled from the real distributions in
  `data/real/outcome_priors.json` (60k dataset). 3% are scam clients.
* **Hidden preferences** (synthetic, never returned by the API): per job, 1 to 3 must have
  skills taken from the job's own skill list, a budget ceiling of 0.9 to 1.3 times the
  posted budget, and whether the client dislikes generic openings (70% do).

## How a client decides (rule mode, the default)

```
base     = min(0.8, 0.8 / applicants_mid)            # competition, from real applicant counts
logit    = 1.2 * skill_coverage      # share of hidden must have skills named in the letter
         + 0.6 * evidence            # 1 if a past work verb and a number appear, 0.5 verb only
         - 1.4 * generic_opening     # only if this client dislikes generic openings
         + 0.4 * mirrors_problem     # opening reuses job title words
         - 1.5 * over_budget         # (price - ceiling) / ceiling, capped at 2
         - 1.0 * too_long            # over 320 words; grows to 2x at 640 words
         - 0.6 * too_short           # under 40 words
p_reply  = min(0.8, base * exp(logit))
p_view   = min(1, 0.35 + 2.5 * p_reply)
interview | reply   ~ 0.35 + 0.3 * skill_coverage   (never for scam clients)
hire | interview    ~ 0.5, only if the price is within the ceiling
```

Every draw uses an RNG seeded from (global seed, user, job, client), so the same proposal
always gets the same outcome. Outcomes appear over simulated time: viewed after 10 minutes to
4 hours, replied 1 to 24 hours later, and so on. Scam clients reply eagerly with scam signals.

**LLM mode** (`decision.mode: llm`): an open model gets the job, the hidden preferences, the
base rate and the delimited proposal, and returns a JSON decision at temperature 0 with a
fixed seed. If the model is not configured or the call fails, the rule result is used.

## Sanity check

`python -m scripts.gigsim_sanity` sends a specific letter, a generic letter and a padded
generic letter to the same 400 real jobs and writes `evals/results/gigsim_sanity.json`.
Specific letters must get clearly more replies than generic ones, padding must not help, and
no style should be close to certain. A first calibration gave specific letters a reply rate
near the cap, which would leave nothing for the writer to improve; `reply_scale` and the
weights were lowered after that.

## Known weaknesses (say these in the report)

* The rule rewards things the writer can learn to imitate: naming skills, adding numbers,
  avoiding stock openings. A writer could add numbers that are not true. GigSim cannot see
  truth, which is why GigBid's claim verification matters.
* A first version could be gamed by padding: a short generic letter got a larger
  "too short" penalty than a padded one got for being "too long". A unit test caught it; the
  long penalty is now larger and grows with length (`test_long_padding_does_not_game_the_client`).
* No dataset has real proposal outcomes, so `reply_scale` and the weights are design choices,
  not fitted values. Absolute reply rates are not comparable to the real site.
* Hidden must have skills come from the job's own skill tags, so retrieval that copies the
  job's skill words is rewarded. Keep that in mind when reading outcome-aware results.

## Tests

`pytest gigsim -q`: endpoints, auth, hidden fields never exposed, idempotent submit (one
spend), duplicate submit blocked, 429 with Retry-After, 503 injection and recovery, admin
policy update applied to the next submit, banned phrases, Connects shortfall, outcomes over
time, threads and tenant isolation, live planted jobs, JSON loading, restart persistence,
determinism, specific beats generic, padding does not pay, over budget lowers replies.
