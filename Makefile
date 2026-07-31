.PHONY: help setup dev test lint migrate seed clean benchmark format check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------- Setup ----------

setup: ## Install all dependencies and boot infrastructure
	uv sync
	cd apps/web && pnpm install
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml up -d
	uv run --directory services/identity alembic upgrade head

# ---------- Development ----------

dev: ## Start all services in dev mode (identity service + frontend)
	docker compose -f infra/docker/docker-compose.yml up -d postgres redis kafka
	uv run --directory services/identity identity serve --reload

dev-web: ## Start frontend dev server
	cd apps/web && pnpm dev

dev-all: ## Start everything (infra + backend + frontend)
	docker compose -f infra/docker/docker-compose.yml up -d
	uv run --directory services/identity identity serve --reload &
	cd apps/web && pnpm dev

# ---------- Testing ----------

test: ## Run all tests
	uv run pytest services/identity/tests/ -v --tb=short

test-unit: ## Run unit tests only
	uv run pytest services/identity/tests/unit/ -v --tb=short -m unit

test-integration: ## Run integration tests (requires Docker)
	uv run pytest services/identity/tests/integration/ -v --tb=short -m integration

test-cov: ## Run tests with coverage report
	uv run pytest services/identity/tests/ -v --cov=services/identity/src --cov-report=html --cov-report=term

# ---------- Linting ----------

lint: ## Run ruff check + ruff format check + mypy
	uv run ruff check services/ libs/
	uv run ruff format --check services/ libs/
	uv run mypy services/identity/src/

lint-full: ## Full lint: ruff + flake8 + mypy + bandit
	uv run ruff check services/ libs/
	uv run flake8 services/ libs/
	uv run mypy services/identity/src/
	uv run bandit -r services/ libs/

format: ## Auto-format code (ruff)
	uv run ruff check --fix services/ libs/
	uv run ruff format services/ libs/

format-legacy: ## Auto-format using isort + black
	uv run isort services/ libs/
	uv run black services/ libs/

# ---------- Database ----------

migrate: ## Run pending Alembic migrations
	uv run --directory services/identity identity migrate

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add users table")
	uv run --directory services/identity alembic revision --autogenerate -m "$(MSG)"

seed: ## Load reference data
	uv run --directory services/identity identity seed

# ---------- Build ----------

build: ## Build identity service Docker image
	docker build -t skyrict/identity:latest -f services/identity/Dockerfile services/identity/

build-web: ## Build frontend
	cd apps/web && pnpm build

# ---------- Cleanup ----------

clean: ## Remove build artifacts, caches, venvs
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/

# ---------- Benchmark ----------

benchmark: ## Run performance benchmarks
	uv run pytest services/identity/tests/ -v -m slow --benchmark-only

# ---------- Hooks ----------

hooks: ## Install git hooks
	./scripts/setup-hooks.sh

# ---------- CI ----------

check: lint test ## Run full CI check locally (lint + test)
