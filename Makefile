.PHONY: install run ingest test lint eval gate logs

install:
	pip install -r requirements.txt

ingest:
	python scripts/ingest.py

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check app scripts tests eval

eval:
	python eval/run_eval.py

# Tier 2 quality gate — run this BEFORE pushing. Exits 1 on regression.
gate:
	python eval/run_eval.py --gate

logs:
	python scripts/log_stats.py
