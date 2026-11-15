.PHONY: install dev api test lint eval seed demo graphs api-client update-snapshots eval-smoke data data-inspect gigsim
install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn apps.api.main:app --reload --port 8000

api:
	uvicorn apps.api.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check .

eval:
	python -m evals.runners.run_demo_eval

seed:
	python -c "print('TODO: implement sample data seeding')"

demo:
	python -c "print('TODO: implement the end-to-end demo')"

graphs:
	python -c "print('TODO: implement graph visualization')"

api-client:
	python -c "print('TODO: generate the API client')"

update-snapshots:
	python -c "print('TODO: implement snapshot updates')"

eval-smoke:
	python -c "print('TODO: implement smoke evaluations')"

data-inspect:
	python scripts/data/inspect_raw.py

# Rebuild real data from data/raw (about 10 minutes). Needs the Kaggle files, see docs/DATA_CARD.md.
data:
	python -m scripts.data.build_real_jobs
	python -m scripts.data.build_priors

gigsim:
	uvicorn gigsim.app:app --reload --port 8081
