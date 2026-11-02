SHELL := /bin/bash
UV ?= uv
NPM ?= npm
COMPOSE ?= docker compose -p data-optimizer-local
LOCAL_TOOLS := .tools

ifeq ($(shell docker compose version >/dev/null 2>&1 && echo available),)
ifneq ($(shell command -v docker-compose 2>/dev/null),)
COMPOSE := docker-compose -p data-optimizer-local
endif
endif

ifneq (,$(wildcard $(LOCAL_TOOLS)/uv-bin/uv))
UV := $(LOCAL_TOOLS)/uv-bin/uv
endif
NODE_PATH := $(CURDIR)/$(LOCAL_TOOLS)/node24/bin

.PHONY: setup setup-deps infra-up infra-down dev check test test-integration build demo migrate seed-local storage-init cleanup-expired

setup:
	bash scripts/bootstrap-tools.sh
	$(MAKE) --no-print-directory setup-deps

setup-deps:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) sync --locked --all-groups --project backend
	cd frontend && PATH="$(NODE_PATH):$$PATH" npm_config_cache="$(CURDIR)/$(LOCAL_TOOLS)/npm-cache" npm ci --no-audit --no-fund

infra-up:
	$(COMPOSE) -f infra/compose.yaml up -d

infra-down:
	$(COMPOSE) -f infra/compose.yaml down

dev:
	UV="$(UV)" bash scripts/dev.sh

contracts:
	$(UV) run --locked --project backend python scripts/generate-frontend-contracts.py

check:
	$(UV) run --locked --project backend python scripts/generate-frontend-contracts.py --check
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend ruff check backend/src backend/tests evaluation scripts/demo.py scripts/verify-clean-checkout.py scripts/verify-s14-browser.py
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend mypy --config-file backend/pyproject.toml backend/src
	cd frontend && PATH="$(NODE_PATH):$$PATH" npm run lint && PATH="$(NODE_PATH):$$PATH" npm run typecheck

test:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend pytest backend/tests
	cd frontend && PATH="$(NODE_PATH):$$PATH" npm test -- --run

test-integration:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend pytest -m integration backend/tests/integration

migrate:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer migrate

seed-local:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer seed-local

storage-init:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer storage-init

cleanup-expired:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer cleanup-expired

build:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python -m build --no-isolation backend
	cd frontend && PATH="$(NODE_PATH):$$PATH" npm run build

demo: build
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/demo.py --output-dir "$$(mktemp -d /tmp/data-optimizer-demo.XXXXXX)"

.PHONY: evaluate test-release-browser verify-clean calibrate release-check
evaluate:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python evaluation/run.py --output-dir docs/evidence/s14-evaluation

test-release-browser:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-s14-browser.py

verify-clean:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-clean-checkout.py --output-dir docs/evidence/s14-clean --demo

calibrate:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python evaluation/capacity.py --output-dir docs/evidence/s14-capacity

# Keep service/browser workers sequential: they share fixed demo-tenant advisory locks.
# Start local infrastructure and build the benchmark image first; see release runbook.
release-check:
	$(MAKE) check test build
	$(MAKE) test-integration
	$(MAKE) test-benchmark
	$(MAKE) test-release-browser
	$(MAKE) evaluate
	$(MAKE) calibrate
	$(MAKE) demo

.PHONY: benchmark-image test-benchmark
benchmark-image:
	$(UV) export --locked --no-dev --no-emit-project --project backend --output-file infra/worker/requirements.lock >/dev/null
	docker build -t data-optimizer-benchmark:s06 -f infra/worker/Dockerfile .

test-benchmark:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend pytest -m benchmark_sandbox backend/tests/test_benchmark_sandbox.py

.PHONY: worker dispatch-jobs cleanup-assessments job-metrics
worker:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer worker

dispatch-jobs:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer dispatch-jobs

cleanup-assessments:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer cleanup-assessments

job-metrics:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend data-optimizer job-metrics

.PHONY: contracts test-browser
test-browser:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-s10-browser.py

.PHONY: test-assistance-browser
test-assistance-browser:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-s11-browser.py

.PHONY: test-reports-browser
test-reports-browser:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-s12-browser.py

.PHONY: test-observations-browser
test-observations-browser:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend python scripts/verify-s13-browser.py
