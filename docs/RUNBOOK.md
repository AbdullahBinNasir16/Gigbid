# Runbook

## Start everything (Docker)

```bash
cp .env.example .env        # fill in every empty value; never commit .env
docker compose -f infra/docker-compose.yml --env-file .env up --build
```
Web: http://localhost:3000 · API: http://localhost:8000/docs · GigSim: http://localhost:8081 ·
Langfuse: http://localhost:3001 (traces) · MCP servers: :8101 marketplace, :8102 portfolio,
:8103 workspace (Streamable HTTP at `/mcp`, bearer auth).

## Start locally without Docker (Windows, as developed)

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev,data]"
uvicorn gigsim.app:app --port 8081                       # terminal 1
GIGSIM_API_TOKEN=${GIGSIM_API_TOKEN} uvicorn apps.api.main:app --port 8000   # terminal 2
cd apps/web && npm ci && npm run dev                      # terminal 3 -> http://localhost:5173
arq worker.main.WorkerSettings                            # optional, needs Redis
```
Without `DATABASE_URL` the API uses SQLite under `data/processed/` (checkpoints, app DB,
memory); with it, Postgres. `MODEL_PROFILE=open` uses Ollama; `open_hosted` uses the hosted
open models with `OPEN_MODEL_API_KEY`.

## Scheduling and why these intervals

| Mode | Interval | Why |
|---|---|---|
| GigSim | `marketplace.polling_interval_seconds` = 300 s | simulator time runs 60x faster; 5 minutes gives a steady stream without approaching the 120 req/min limit |
| Upwork live | `marketplace.live_polling_interval_seconds` = 1800 s | a freelancer checking saved searches twice an hour is normal human behaviour; more often would look like scraping, and new posts rarely matter within minutes |

All marketplace calls also pass a per-user token bucket at `marketplace.max_requests_per_minute`
(20), well under GigSim's limit. Live mode never scrapes, never uses cookies or a browser, and
creates drafts only.

## Idempotency

* Worker: a job is enqueued with `_job_id = <user>:<job>`; `run_job` skips jobs already
  `done`, `awaiting_approval` or `submitted`, so a restart never double-analyses.
* Graph: the thread id is `<user>:<job>`; re-running resumes the same checkpointed thread.
* Marketplace writes: idempotency keys derived from the thread id; GigSim stores responses
  per key (persisted with `GIGSIM_STATE_FILE`), so a retry never submits or spends twice.

## Incidents

| Symptom | What happens | What to do |
|---|---|---|
| Marketplace down (kill GigSim or the marketplace MCP server) | adapter retries with backoff, circuit opens after 5 failures, `/health` reports `unavailable`, UI shows the red banner, runs are marked `queued` | restart the service; the worker's `retry_queued` (every 5 min) or `POST /api/retry-queued` resumes them |
| GigSim 429 | adapter sleeps for `Retry-After` (bounded) and retries | none |
| Node keeps failing | after `budgets.node_max_retries` the thread goes to `dead_letter` with the reason | open the run viewer, fix, re-run the job |
| Step or token budget hit | thread goes to `needs_attention` | review in the run viewer |
| Crash while a proposal waits for approval | the interrupt payload is in the checkpoint | restart; the Studio still shows it; approve once |

## Crash-and-resume demo (viva question 2)

1. Open a job awaiting approval in the Studio.
2. Stop the API process. Start it again.
3. Refresh the Studio: the same draft is there (read from the checkpoint).
4. Approve. The run viewer shows `submit`; GigSim shows one proposal and one Connects spend.
   Re-sending the approval replays with `Idempotent-Replayed: true` and spends nothing.

## Policy change request (2 Nov update)

Change only config or data: `platform_rules.connects` (cost, tiers, weekly budget),
`data/policy_pack/banned_phrases.txt`, `risk_rules`, thresholds or prompts. Pricing also reads
the current cost from each GigSim job. Then run `pytest` and `python -m evals.runners.smoke_gate`.

## Evaluation commands

```bash
python -m evals.runners.rag_eval            # retrieval variants -> evals/results/rag_variants.json
python -m evals.runners.decision_eval       # bid/skip, scam, injection, price -> decisions.json
python -m evals.runners.smoke_gate          # 30-job PR gate (evals/thresholds.json)
MODEL_PROFILE=open_hosted python -m evals.runners.gigsim_outcomes   # reply rate + X2 A/B
MODEL_PROFILE=open_hosted python -m evals.runners.tool_granularity  # R&D question A
python -m evals.runners.llm_speed           # local tokens/s
```
`make` is not required; the Makefile targets call the same commands.
