PYTHON ?= python3
.PHONY: test lint go-test go-build run-mlops run-agents run-factory validate local-up local-up-ai local-up-full local-down local-smoke kind-create kind-deploy kind-delete kind-smoke

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

kind-create:
	kind create cluster --name openmodelops --config deploy/kind/cluster.yaml

kind-deploy:
	./scripts/kind-deploy.sh

kind-delete:
	kind delete cluster --name openmodelops

kind-smoke:
	./scripts/kind-smoke-test.sh
