# =============================================================================
# Skyrict Identity Service — Multi-stage Dockerfile
#
# Stages:
#   base        Shared deps install (uv sync --no-dev)
#   dev         Dev deps + live-reload CMD (default build target)
#   production  Minimal final image, non-root, no dev deps, no tests
#
# Build:
#   Dev:        docker build --target dev -f services/identity/Dockerfile .
#   Production: docker build --target production -f services/identity/Dockerfile .
# =============================================================================

# ---------------------------------------------------------------------------
# Stage: base — shared dependency install
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# System deps needed for asyncpg, cryptography (RSA), argon2-cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root files
COPY pyproject.toml uv.lock ./

# Copy service + lib pyproject.toml files (for dependency resolution)
COPY services/identity/pyproject.toml services/identity/
COPY libs/skyrict-common/pyproject.toml libs/skyrict-common/

# Install production deps only
RUN uv sync --frozen --no-dev --directory services/identity

# ---------------------------------------------------------------------------
# Stage: dev — adds dev dependencies, live reload
# ---------------------------------------------------------------------------
FROM base AS dev

# Re-sync with dev dependencies (pytest, mypy, etc.)
RUN uv sync --frozen --directory services/identity

# Copy source code
COPY services/identity/src services/identity/src
COPY libs/skyrict-common/src libs/skyrict-common/src

# Copy tests (dev only — never reaches production)
COPY services/identity/tests services/identity/tests

# Copy alembic config and migrations
COPY services/identity/alembic services/identity/alembic
COPY services/identity/alembic.ini services/identity/alembic.ini

EXPOSE 8000

CMD ["uv", "run", "--directory", "services/identity", \
     "uvicorn", "identity.main:app", \
     "--reload", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Stage: production — minimal final image, non-root
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Security: non-root user
RUN groupadd --gid 1000 skyrict && \
    useradd --uid 1000 --gid skyrict --create-home skyrict

WORKDIR /app

# System deps for runtime (asyncpg, argon2-cffi, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY the virtual environment from base (no source tree, no tests)
COPY --from=base /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source (no tests, no tests/fixtures/)
COPY services/identity/src services/identity/src
COPY libs/skyrict-common/src libs/skyrict-common/src

# Copy alembic migrations (needed at runtime for DB migrations)
COPY services/identity/alembic services/identity/alembic
COPY services/identity/alembic.ini services/identity/alembic.ini

# Set ownership
RUN chown -R skyrict:skyrict /app

USER skyrict

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

CMD ["uvicorn", "identity.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--no-access-log"]
