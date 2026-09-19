.PHONY: test lint run-mlops run-agents run-factory validate

test:
	python -m pytest -q

lint:
	python -m ruff check .

run-mlops:
	uvicorn platforms.mlops.api:app --host 0.0.0.0 --port 8001

run-agents:
	uvicorn platforms.agents.api:app --host 0.0.0.0 --port 8002

run-factory:
	uvicorn platforms.factory.api:app --host 0.0.0.0 --port 8004

validate: lint test
