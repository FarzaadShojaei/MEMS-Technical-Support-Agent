.PHONY: install run ingest test lint

install:
	pip install -r requirements.txt

ingest:
	python scripts/ingest.py

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check app scripts tests
