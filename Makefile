.PHONY: install dev api web worker test lint eval eval-smoke eval-full seed demo graphs api-client update-snapshots data data-inspect gigsim up

install:
	python -m pip install -e ".[dev,data]"
	cd apps/web && npm ci

# Local dev: GigSim, API and web (three terminals, or `make up` with Docker)
dev: gigsim
api:
	uvicorn apps.api.main:app --reload --port 8000
web:
	cd apps/web && npm run dev
worker:
	arq worker.main.WorkerSettings
gigsim:
	uvicorn gigsim.app:app --reload --port 8081
up:
	docker compose -f infra/docker-compose.yml --env-file .env up --build

test:
	pytest -q
	cd apps/web && npx playwright test

lint:
	ruff check agent rag mcp_servers apps/api evals worker
	python scripts/check_repo_rules.py

# Retrieval + decisions + GigSim reply-rate run; writes evals/results/*.json
eval:
	python -m evals.runners.rag_eval
	python -m evals.runners.decision_eval
	python -m evals.runners.gigsim_outcomes --per-persona 15

eval-smoke:
	python -m evals.runners.smoke_gate

eval-full: eval
	python -m evals.runners.tool_granularity
	python -m evals.runners.llm_speed

# Rebuild personas, dev set and held-out set (deterministic)
seed:
	python -m scripts.data.build_personas

demo:
	python -m scripts.demo_proposal ai_ml

graphs:
	python -c "from agent.graphs.bid_graph import graph as b; from agent.graphs.conversation_graph import graph as c; open('docs/images/bid_graph.mmd','w').write(b.get_graph().draw_mermaid()); open('docs/images/conversation_graph.mmd','w').write(c.get_graph().draw_mermaid())"

api-client:
	curl -s http://localhost:8000/openapi.json -o apps/web/openapi.json
	cd apps/web && npm run gen:api

update-snapshots:
	UPDATE_SNAPSHOTS=1 pytest -q tests/contract

data-inspect:
	python scripts/data/inspect_raw.py

# Rebuild real data from data/raw (about 10 minutes). Needs the Kaggle files, see docs/DATA_CARD.md.
data:
	python -m scripts.data.build_real_jobs
	python -m scripts.data.build_priors
