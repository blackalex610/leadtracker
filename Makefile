# Common development commands. Run `make help`.
API := apps/api
UV := cd $(API) && uv run

.PHONY: help install db db-stop migrate api worker web demo seed-demo test test-api test-web e2e lint typecheck build gen-api check

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (pnpm) dependencies
	cd $(API) && uv sync
	pnpm install

db: ## Start PostgreSQL in Docker (port 5432)
	docker compose up -d db

db-stop: ## Stop the PostgreSQL container
	docker compose stop db

migrate: ## Apply database migrations
	$(UV) alembic upgrade head

api: ## Run the API with an embedded worker on :8000 (auto-reload)
	$(UV) uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

worker: ## Run a standalone background worker
	$(UV) python -m app.worker

web: ## Run the frontend dev server on :5173 (proxies /api to :8000)
	pnpm dev

demo: ## Run the API in demo mode (synthetic data, no API key needed)
	cd $(API) && DEMO_MODE=true uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

seed-demo: ## Load ~120 synthetic demo businesses (DEMO_MODE only)
	cd $(API) && DEMO_MODE=true uv run python -m app.cli seed-demo --count 120

test: test-api test-web ## Run all tests

test-api: ## Backend tests (needs PostgreSQL; TEST_DATABASE_URL)
	$(UV) pytest -q

test-web: ## Frontend tests
	pnpm --filter @leadtracker/web test

e2e: ## End-to-end browser tests (starts API in demo mode + web; needs Postgres db leadtracker_e2e)
	pnpm --filter @leadtracker/web e2e

lint: ## Lint backend and frontend
	$(UV) ruff check app tests
	$(UV) ruff format --check app tests
	pnpm --filter @leadtracker/web lint

typecheck: ## Type-check backend (mypy --strict) and frontend (tsc)
	$(UV) mypy app
	pnpm --filter @leadtracker/shared typecheck
	pnpm --filter @leadtracker/web typecheck

build: ## Production build of the frontend
	pnpm build

gen-api: ## Regenerate TypeScript API types from the FastAPI schema
	pnpm gen:api

check: lint typecheck test build ## Everything CI runs
