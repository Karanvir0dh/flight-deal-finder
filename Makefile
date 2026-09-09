.PHONY: install test lint format typecheck init-db run-once web

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

init-db:
	flight-deals init-db

run-once:
	flight-deals run-once --mock

web:
	uvicorn flight_deals.api.app:create_app --factory --host 0.0.0.0 --port 8000
