.PHONY: help install dev dev-web dev-all build-web test test-live lint format check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install backend deps, pre-commit hooks and frontend deps
	uv sync
	uv run pre-commit install
	pnpm --dir frontend install

dev: ## Run FastAPI dev server at http://127.0.0.1:8000 (auto-reload)
	uv run uvicorn zlens.api.app:app --reload --port 8000

dev-web: ## Run Vite dev server (proxies /api to :8000) at http://127.0.0.1:5173
	pnpm --dir frontend run dev

dev-all: ## Run backend and Vite dev server together
	uv run uvicorn zlens.api.app:app --reload --port 8000 &
	pnpm --dir frontend run dev

build-web: ## Typecheck and build frontend into the FastAPI-hosted bundle
	pnpm --dir frontend run build

test: ## Run offline tests (live-marked tests excluded)
	uv run pytest

test-live: ## Run tests against the real local ~/.zcode database
	uv run pytest -m live

lint: ## Ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix lint violations and reformat
	uv run ruff check --fix .
	uv run ruff format .

check: ## Everything that must pass before push (lint + test + frontend build)
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) build-web
