.PHONY: help setup dev test lint migrate seed clean benchmark format check test-e2e

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

test-e2e: ## Run the Playwright auth e2e suite (infra + identity TEST on :8000; web on :3000 required — see make dev-web)
	@echo ">> Ensuring infra (postgres :5433, redis :6379)..."
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml up -d postgres redis
	@mkdir -p .dev/keys
	@if [ ! -f .dev/keys/private.pem ] || [ ! -f .dev/keys/public.pem ]; then \
		echo ">> Generating JWT keys..."; \
		openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .dev/keys/private.pem; \
		openssl rsa -pubout -in .dev/keys/private.pem -out .dev/keys/public.pem; \
	fi
	@if [ ! -f .dev/e2e-mfa.key ]; then \
		echo ">> Generating MFA encryption key..."; \
		uv run --directory services/identity python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .dev/e2e-mfa.key; \
	fi
	@echo ">> Migrating identity DB..."
	@set -e; \
	export IDENTITY_MFA_ENCRYPTION_KEY="$$(cat .dev/e2e-mfa.key | tr -d '\n')"; \
	IDENTITY_DATABASE_URL='postgresql+asyncpg://skyrict:skyrict@127.0.0.1:5433/skyrict_identity' \
	IDENTITY_REDIS_URL='redis://127.0.0.1:6379/0' \
	IDENTITY_JWT_PRIVATE_KEY_PATH='$(CURDIR)/.dev/keys/private.pem' \
	IDENTITY_JWT_PUBLIC_KEY_PATH='$(CURDIR)/.dev/keys/public.pem' \
	IDENTITY_JWKS_ISSUER='https://auth.skyrict.io' \
	IDENTITY_JWKS_AUDIENCE='api.skyrict.io' \
	uv run --directory services/identity alembic upgrade head
	@set -e; \
	if curl -sf http://127.0.0.1:8000/api/v1/ready > /dev/null 2>&1; then \
		echo ">> identity already healthy on :8000 - using it (MUST run with IDENTITY_ENVIRONMENT=test)"; \
	else \
		echo ">> starting identity in TEST mode on :8000..."; \
		( \
			export IDENTITY_MFA_ENCRYPTION_KEY="$$(cat .dev/e2e-mfa.key | tr -d '\n')"; \
			IDENTITY_ENVIRONMENT=test \
			IDENTITY_DATABASE_URL='postgresql+asyncpg://skyrict:skyrict@127.0.0.1:5433/skyrict_identity' \
			IDENTITY_REDIS_URL='redis://127.0.0.1:6379/0' \
			IDENTITY_JWT_PRIVATE_KEY_PATH='$(CURDIR)/.dev/keys/private.pem' \
			IDENTITY_JWT_PUBLIC_KEY_PATH='$(CURDIR)/.dev/keys/public.pem' \
			IDENTITY_JWKS_ISSUER='https://auth.skyrict.io' \
			IDENTITY_JWKS_AUDIENCE='api.skyrict.io' \
			IDENTITY_RATE_LIMIT_LOGIN='8' \
			IDENTITY_RATE_LIMIT_LOGIN_IP='200' \
			IDENTITY_RATE_LIMIT_MFA_VERIFY='200' \
			IDENTITY_RATE_LIMIT_MFA_ENROLL='200' \
			IDENTITY_SIGNUP_START_RATE_LIMIT='200' \
			IDENTITY_SIGNUP_CODE_RATE_LIMIT='200' \
			IDENTITY_SIGNUP_VERIFY_RATE_LIMIT='200' \
			IDENTITY_SIGNUP_CHECK_RATE_LIMIT='200' \
			IDENTITY_SIGNUP_CAPTCHA_RATE_LIMIT='200' \
			uv run --directory services/identity identity serve > /tmp/skyrict-identity.log 2>&1 & \
			echo $$! > /tmp/skyrict-identity.pid \
		); \
		trap 'kill "$$(cat /tmp/skyrict-identity.pid 2>/dev/null)" 2>/dev/null || true' EXIT; \
	fi; \
	echo ">> waiting for identity..."; \
	for i in $$(seq 1 90); do curl -sf http://127.0.0.1:8000/api/v1/ready > /dev/null 2>&1 && break; sleep 1; done; \
	curl -sf http://127.0.0.1:8000/api/v1/ready > /dev/null || { echo ">> identity failed to start - see /tmp/skyrict-identity.log"; tail -n 40 /tmp/skyrict-identity.log 2>/dev/null || true; exit 1; }; \
	echo ">> running Playwright suite..."; \
	cd apps/web && E2E_LOGIN_RATE_LIMIT='8' pnpm test:e2e

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
	docker build -t skyrict/identity:latest -f services/identity/Dockerfile .

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
