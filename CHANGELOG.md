# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Workspace-based monorepo structure with `uv` (Python) and `pnpm` (Node.js)
- Identity service scaffold with full layering (api, core, domain, services, repositories, models, schemas, events, db)
- Identity service: JWT auth (access + refresh tokens), user registration, login, logout, token refresh
- Identity service: multi-tenancy via ContextVar-based TenantContext with RLS support
- Identity service: middleware stack (request-id, tenant context, timing)
- Identity service: MFA (TOTP setup/verify), passkey stubs, SSO stubs
- Identity service: session management (list, revoke, revoke all)
- Identity service: audit logging
- Identity service: async SQLAlchemy 2.0 with Alembic migrations
- Identity service: Dockerfile for container builds
- `libs/skyrict-common` — shared exceptions, logging, pagination, response envelopes
- `libs/skyrict-events` — shared Kafka event schemas and producer/consumer base classes
- `services/_template` — copy-to-bootstrap scaffold for new services
- Next.js 15 web app skeleton (auth routes, dashboard routes)
- Docker Compose for local dev (PostgreSQL 16, Redis 7, Kafka 3.x KRaft)
- CI/CD workflows: ci-identity, ci-web, codeql, cd-staging, cd-production
- Dependabot for pip, npm, Docker, and GitHub Actions auto-updates
- CODEOWNERS with team-based review routing
- Issue templates (bug report, feature request)
- Pull request template
- ADR-001: Use uv workspaces for Python monorepo
- ADR-002: Single identity service with internal modules
- Makefile with 20+ dev targets
- Pre-commit hooks (Ruff, mypy, commitlint, file checks)
- `.tool-versions` for pinned Python/Node versions
