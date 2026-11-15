.PHONY: install dev api test lint eval seed demo graphs api-client update-snapshots eval-smoke
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
