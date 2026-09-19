.PHONY: test lint run-mlops run-agents validate

test:
	python -m pytest -q

lint:
	python -m ruff check .

run-mlops:
	uvicorn platforms.mlops.api:app --host 0.0.0.0 --port 8001

run-agents:
	uvicorn platforms.agents.api:app --host 0.0.0.0 --port 8002

validate: lint test
