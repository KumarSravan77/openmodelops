PYTHON ?= python3
.PHONY: test lint go-test go-build run-mlops run-agents run-factory run-metal run-judgeops run-ecommerce validate local-up local-up-ai local-up-full local-down local-smoke banking-up banking-smoke banking-load banking-down kind-create kind-deploy kind-delete kind-smoke

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	cd go && test -z "$$(gofmt -l .)"

go-test:
	cd go && go test ./...

go-build:
	cd go && go build ./cmd/omo ./cmd/operator ./cmd/admission

run-mlops:
	uvicorn platforms.mlops.api:app --host 0.0.0.0 --port 8001

run-agents:
	uvicorn platforms.agents.api:app --host 0.0.0.0 --port 8002

run-factory:
	uvicorn platforms.factory.api:app --host 0.0.0.0 --port 8004

run-metal:
	$(PYTHON) -m uvicorn platforms.metal_runtime.api:app --host 127.0.0.1 --port 8008

run-judgeops:
	$(PYTHON) -m uvicorn platforms.judgeops.api:app --host 127.0.0.1 --port 8009

run-ecommerce:
	$(PYTHON) -m uvicorn platforms.ecommerce.api:app --host 127.0.0.1 --port 8010

validate: lint test go-test

local-up:
	./scripts/local-stack.sh up core

local-up-ai:
	./scripts/local-stack.sh up ai

local-up-full:
	./scripts/local-stack.sh up full

local-down:
	./scripts/local-stack.sh down

local-smoke:
	./scripts/local-smoke-test.sh

banking-up:
	docker compose --profile banking-benchmark up -d --build banking-api

banking-smoke:
	LOAD_PROFILE=smoke docker compose --profile load-test run --rm banking-load

banking-load:
	docker compose --profile load-test run --rm banking-load

banking-down:
	docker compose --profile banking-benchmark --profile load-test down

kind-create:
	kind create cluster --name openmodelops --config deploy/kind/cluster.yaml

kind-deploy:
	./scripts/kind-deploy.sh

kind-delete:
	kind delete cluster --name openmodelops

kind-smoke:
	./scripts/kind-smoke-test.sh
