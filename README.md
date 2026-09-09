<p align="center">
  <img src="https://img.shields.io/badge/Stage-Alpha-red?style=flat-square" alt="Alpha"/>
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square" alt="License"/>
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome"/>
  <a href="https://github.com/nkswalih/skyrict/actions/workflows/ci-identity.yml"><img src="https://github.com/nkswalih/skyrict/actions/workflows/ci-identity.yml/badge.svg" alt="CI - Identity Service"/></a>
</p>

<br/>

<p align="center">
  <h1 align="center">Skyrict</h1>
  <p align="center">Event-driven business operations platform with integrated market intelligence and autonomous agent execution.</p>
</p>

---

## Overview

Skyrict is an open-source, AI-native platform that merges business operations (ERP) with real-time market intelligence into a single system. Traditional ERP treats your company as an isolated entity processing internal transactions. Skyrict treats your company as a node in a live global market - ingesting external signals, correlating them with internal operations, and letting AI agents act on the synthesis.

---

## Repository Structure

```
skyrict/
├── apps/                    # Deployable frontend clients
│   ├── web/                 # Next.js 15 / React 19 / TypeScript
│   ├── mobile/              # Mobile app scaffold
│   └── desktop/             # Desktop app scaffold
│
├── packages/                # Shared TypeScript packages
│   ├── api-client/          # Generated from OpenAPI schemas
│   ├── types/               # Shared TS types/interfaces
│   ├── ui/                  # Shared React components
│   └── auth/                # Token storage, refresh logic
│
├── services/                # Deployable Python microservices
│   ├── identity/            # AuthN, AuthZ, MFA, Sessions, Audit
│   ├── core/                # ERP monolith: inventory, CRM, sales, finance, HR, payroll + /api/v1/ai proxy
│   ├── ai-agent/            # Provider-agnostic AI service (NL query, restock suggestions, anomaly detection)
│   └── _template/           # Scaffold copied for every new service, keeps structure consistent
│
├── libs/                    # Shared Python packages
│   ├── skyrict-common/      # Exceptions, logging, pagination, schemas
│   ├── skyrict-events/      # Kafka event schemas, producer/consumer base classes
│   └── skyrict-testing/     # Test fixtures, factories, JWT key generation
│
├── infra/                   # Infrastructure as Code
│   ├── docker/              # Docker Compose for local dev
│   ├── k8s/                 # Kubernetes manifests (base + overlays)
│   └── terraform/           # Cloud infrastructure
│
├── docs/
│   ├── architecture/adr/    # Architecture Decision Records
│   └── handbooks/           # Product & engineering handbooks
│
├── .github/                 # GitHub governance & CI
│   ├── workflows/           # CI/CD workflows
│   ├── CODEOWNERS           # Team-based review routing
│   └── dependabot.yml       # Automated dependency updates
│
├── pyproject.toml           # uv workspace root
├── package.json             # pnpm workspace root
├── turbo.json               # Frontend task pipeline
├── Makefile                 # Single entrypoint for all dev commands
└── ...
```

### Identity Service Layering

```
services/identity/src/identity/
├── api/              # FastAPI routes, dependency injection
├── core/             # Config, security, middleware, tenant context
├── domain/           # Pure Python entities and value objects
├── services/         # Application/use-case layer (business logic)
├── repositories/     # DB access only (no business logic)
├── models/           # SQLAlchemy ORM models
├── schemas/          # Pydantic request/response DTOs
├── events/           # Kafka event producers/consumers
└── db/               # Async engine, session factory, RLS
```

Why this layering: `api → services → repositories → models`. Business logic never touches the DB directly. JWT verification happens in exactly one place (`core/security.py`). Tenant context flows through a ContextVar, not function parameters.

---

## Tech Stack

| Layer                  | Choice                                                                |
| ---------------------- | --------------------------------------------------------------------- |
| Python package manager | **uv** (workspaces, single lockfile)                                  |
| Language               | Python 3.12+ / TypeScript 5.7+                                        |
| Web framework          | FastAPI (async, type-safe, OpenAPI)                                   |
| ORM                    | SQLAlchemy 2.0 (async) + Alembic                                      |
| Frontend               | Next.js 15 / React 19 / shadcn/ui                                     |
| Frontend tooling       | pnpm + Turborepo                                                      |
| OLTP                   | PostgreSQL 16 + Row-Level Security                                    |
| Cache                  | Redis 7                                                               |
| Event bus              | Kafka 3.x (KRaft mode) - deferred until 3+ services need async events |
| CI/CD                  | GitHub Actions (path-filtered)                                        |
| Containers             | Docker                                                                |

---

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose v2
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- pnpm (`npm install -g pnpm`)

## Quick Start

```bash
git clone https://github.com/nkswalih/skyrict.git
cd skyrict

# 1. Install all dependencies
make setup

# 2. Configure the local environment
cp services/identity/.env.example services/identity/.env
uv run python -m skyrict_testing.generate_keys  # JWT RS256 keys -> .dev/keys/ (gitignored)

# 3. Start dev servers (infra + identity service)
make dev

# 4. In another terminal, start the frontend
make dev-web
```

- API docs: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`

### Local Multi-Tenant Routing

The identity service is multi-tenant: in production each tenant reaches it via
its own subdomain (`https://acme.skyrict.com/...`), and the ingress injects an
`X-Tenant-Slug` header before forwarding. The dev stack mirrors that contract
so tenant resolution behaves identically locally and in production - no
staging DNS required.

`docker compose` (dev) starts an `nginx` proxy (see `infra/nginx/dev.conf`)
that routes `*.localhost` subdomains to the identity service and derives
`X-Tenant-Slug` from the subdomain. No `/etc/hosts` edits are needed on
most machines: modern OSes resolve `*.localhost` to `127.0.0.1` automatically.
If yours doesn't, add the sample tenants to your hosts file instead
(`127.0.0.1 acme.localhost globex.localhost`).

```bash
# Boot the full stack (Postgres, Redis, identity service, nginx)
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml up -d

# Hit two different fake tenant subdomains
curl -s http://acme.localhost/api/v1/health
curl -s http://globex.localhost/api/v1/health
# Both reach the identity service; the first carries X-Tenant-Slug: acme,
# the second X-Tenant-Slug: globex. Watch per-subdomain traffic with:
docker logs -f skyrict-nginx
```

**Path-based fallback** - for environments without wildcard DNS, prefix the
path with the tenant slug. Nginx strips the prefix and injects the header:

```bash
# http://localhost/acme/login          -> /api/v1/auth/login  + X-Tenant-Slug: acme
# http://localhost/acme/api/v1/health  -> /api/v1/health      + X-Tenant-Slug: acme
curl -s http://localhost/acme/api/v1/health
```

**Port 80 already in use?** Set a different host port - e.g. add
`NGINX_PORT=8080` to `infra/docker/.env` (or export it in your shell), then
use `http://acme.localhost:8080/docs`.

> The service resolves the tenant **once per request in middleware**: in
> staging/production from the `Host` subdomain (first label of
> `IDENTITY_BASE_DOMAIN`, e.g. `acme.skyrict.com` → `acme`), and in dev/test
> from the `X-Tenant-Slug` header that nginx injects - there is no bypass path
> in any environment. The resolved tenant is stored in `TenantContext` and
> cross-checked against the JWT `tenant_id` claim on every authenticated
> request; a mismatch is rejected with 401 (RFC 7807
> `application/problem+json`). See the
> [identity service README](services/identity/README.md) for details.

### Manual Setup

```bash
# Python deps
uv sync

# Frontend deps
cd apps/web && pnpm install

# Boot infrastructure (Postgres, Redis)
docker compose -f infra/docker/docker-compose.yml up -d
# Kafka is intentionally deferred - see "Roadmap & Scope" below.

# Run migrations
make migrate

# Start identity service
make dev
```

---

## Development

```bash
# Install git hooks (run once after clone)
./scripts/setup-hooks.sh        # Unix/macOS
.\scripts\setup-hooks.ps1       # Windows

# Common tasks
make setup          # Install deps, create DB, run migrations
make dev            # Start identity service in dev mode
make dev-web        # Start Next.js dev server
make dev-all        # Start everything
make test           # Run all tests
make test-unit      # Unit tests only
make test-cov       # Tests with coverage
make lint           # Ruff + mypy
make format         # Auto-format code
make migrate        # Run pending Alembic migrations
make migrate-create MSG="add users table"  # Create new migration
make seed           # Load reference data
make build          # Build Docker image
make check          # Full CI check (lint + test)
make clean          # Remove build artifacts
make help           # Show all available targets
```

### Git Hooks

```bash
./scripts/setup-hooks.sh        # Unix/macOS
.\scripts\setup-hooks.ps1       # Windows
```

Pre-commit hooks: Ruff lint, Ruff format, mypy, YAML/JSON/TOML validation, large file check, direct push block, conventional commit lint.

### AI Agent Service (local dev)

The `ai-agent` service (port 8002) hosts the AI assistant features - natural-language inventory queries, restock suggestions, stock anomaly detection. It is provider-agnostic: any OpenAI-compatible endpoint works (OpenRouter, Groq, OpenAI, or a local Ollama via its OpenAI-compatible API). With no provider configured the service boots and serves health; AI calls then return a typed `503 ai_unavailable`.

```bash
# Required
AI_DATABASE_URL=postgresql+asyncpg://...       # ai-agent's own DB (owns alembic branch ai_agent)
AI_REDIS_URL=redis://localhost:6379/0          # distributed rate limiting
AI_JWT_PUBLIC_KEY_PATH=./secrets/jwt_public.pem
AI_JWKS_ISSUER=https://auth.skyrict.io
AI_JWKS_AUDIENCE=api.skyrict.io

# Core data plane (compose contract: unprefixed INVENTORY_SERVICE_URL /
# REPORT_SERVICE_URL - both APIs live on the core monolith)
INVENTORY_SERVICE_URL=http://localhost:8001
REPORT_SERVICE_URL=http://localhost:8001

# Provider (optional at boot)
AI_PROVIDER=openrouter                          # or groq/openai/omniroute/agentrouter/generic
AI_MODEL=meta-llama/llama-3-8b-instruct
AI_API_KEY=sk-or-...
# AI_FALLBACK_PROVIDER / AI_FALLBACK_MODEL / AI_FALLBACK_API_KEY for failover

# Docker compose dev (infra/docker/docker-compose.dev.yml) keeps the provider
# config from services/ai-agent/.env (env_file) but applies two container-only
# corrections: the primary's AI_BASE_URL is redirected to host.docker.internal
# (a host-local gateway like omniroute@localhost:20128 is unreachable as
# localhost from inside the container) and the groq fallback is pinned to a
# current groq model (qwen/qwen3.8-27b - llama-3.1-8b-instant no longer
# exists). Values above apply to host-run `uv run ai-agent`; the container
# inherits the same .env.

# Run + migrate
uv run ai-agent serve                                 # from services/ai-agent (typer CLI)
uv run ai-agent migrate
```

Frontend/BFF never calls ai-agent directly: requests go through core (`/api/v1/ai/*`), which enforces `erp.ai.invoke` plus the module permission BEFORE forwarding and re-relays the caller's JWT (the AI service re-verifies it). Docker wiring lives in [infra/docker/docker-compose.dev.yml](infra/docker/docker-compose.dev.yml) (`skyrict-ai-agent`, port 8002→8000). Feature spec: [docs/modules/skyrict-ai/inventory-ai-features.md](docs/modules/skyrict-ai/inventory-ai-features.md).

### Branch Protection

See [docs/setup/branch-protection.md](docs/setup/branch-protection.md) for required GitHub repository settings to enforce PR-only workflow, required reviews, and CI checks.

---

## Architecture

### Target Architecture (Roadmap)

Not all of these exist yet - this is the intended end state. Today only `identity` is in active development.

```
services/
├── identity/          # Auth, JWT, OAuth2, RBAC, multi-tenancy   (in active development)
├── core/              # ERP domain (finance, inventory, procurement)   (planned)
└── intelligence/      # Signal collection, NLP, scoring, knowledge graph   (planned)
```

Future (aspirational - not yet explicitly scoped):

```
services/
├── agents/            # LLM orchestration, tool registry, guardrails
└── analytics/         # OLAP queries, materialized views
```

### Event-Driven Communication

Every domain service emits structured events to Kafka. No direct database reads between services.

```
Topic naming: {domain}.{entity}.{action}

Examples:
  identity.user.created
  identity.auth.login_success
  inventory.stock.level_changed
  finance.journal_entry.posted
```

### Multi-Tenancy

Row-Level Security (RLS) on PostgreSQL. Every query is scoped to the current tenant via `SET app.current_tenant_id`. Tenant context flows through a `ContextVar`, not function parameters.

---

## Roadmap & Scope

Skyrict is deliberately MVP-first: ship a small, secure, well-tested core before expanding scope. The following are intentionally deferred until a concrete need justifies them: SSO (SAML/OIDC), OPA policy engine, HashiCorp Vault, Kafka event bus (once 3+ services need decoupled async events), SCIM provisioning, and adaptive risk scoring.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, code standards, and PR process.

---

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md). Do **not** open a public issue for security reports.

---

## License & Trademarks

Apache License 2.0. See [LICENSE](LICENSE).

Skyrict trademarks and usage guidelines: [TRADEMARK.md](TRADEMARK.md).

---

<p align="center">
  <a href="https://github.com/nkswalih/skyrict/stargazers">
    <img alt="Stars" src="https://img.shields.io/github/stars/nkswalih/skyrict?style=social"/>
  </a>
  <a href="https://github.com/nkswalih/skyrict/network/members">
    <img alt="Forks" src="https://img.shields.io/github/forks/nkswalih/skyrict?style=social"/>
  </a>
  <a href="https://github.com/nkswalih/skyrict/issues">
    <img alt="Issues" src="https://img.shields.io/github/issues/nkswalih/skyrict"/>
  </a>
</p>

---

## Contributors

<p align="center">
  <a href="https://github.com/nkswalih/skyrict/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=nkswalih/skyrict" alt="Contributors" title="All contributors"/>
  </a>
</p>
