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

check:
	UV_CACHE_DIR="$(LOCAL_TOOLS)/uv-cache" $(UV) run --locked --project backend ruff check backend/src backend/tests
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

demo:
	@echo 'The assessment pipeline is not implemented until later sprints. No demo results are available.' >&2
	@exit 2
