.PHONY: help install dev test test-live lint format check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install backend deps and pre-commit hooks (frontend deps land with the frontend ticket)
	uv sync
	uv run pre-commit install

dev: ## Run FastAPI dev server at http://127.0.0.1:8000 (auto-reload)
	uv run uvicorn zlens.api.app:app --reload --port 8000

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

check: ## Everything that must pass before push (lint + test)
	$(MAKE) lint
	$(MAKE) test
