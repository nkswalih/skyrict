# =============================================================================
# Skyrict Core Service - Production Dockerfile
#
# Stages:
#   base        Shared deps install (uv sync --no-dev)
#   production  Minimal final image, non-root, no dev deps, no tests
#
# Build:
#   docker build --target production -f services/core/Dockerfile .
# =============================================================================

# ---------------------------------------------------------------------------
# Stage: base - shared dependency install
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# System deps needed for asyncpg, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root files
COPY pyproject.toml uv.lock ./

# Copy every workspace member pyproject.toml file (for dependency resolution).
# The workspace glob is services/* and libs/* - uv --frozen refuses to resolve
# if a member manifest is missing. READMEs too: hatchling requires the `readme`
# file declared in each pyproject.toml to be present when building the members.
COPY services/identity/pyproject.toml services/identity/
COPY services/identity/README.md services/identity/
COPY services/core/pyproject.toml services/core/
COPY services/core/README.md services/core/
COPY libs/skyrict-common/pyproject.toml libs/skyrict-common/
COPY libs/skyrict-common/README.md libs/skyrict-common/
COPY libs/skyrict-events/pyproject.toml libs/skyrict-events/
COPY libs/skyrict-events/README.md libs/skyrict-events/
COPY libs/skyrict-testing/pyproject.toml libs/skyrict-testing/
COPY libs/skyrict-testing/README.md libs/skyrict-testing/

# The source trees MUST be present before `uv sync` runs. `skyrict-common` and
# `skyrict-events` are declared as workspace dependencies, so uv builds them
# during the sync; with only their manifests copied, hatchling has no package
# directory to build, the sync silently produces a venv with no path entry for
# any of them, and the container then dies on
# `ModuleNotFoundError: No module named 'core'`.
COPY services/core/src services/core/src
COPY libs/skyrict-common/src libs/skyrict-common/src
COPY libs/skyrict-events/src libs/skyrict-events/src

# Install production deps only
RUN uv sync --frozen --no-dev --directory services/core

# Fail the build here rather than at runtime if the venv is not importable.
RUN /app/.venv/bin/python -c "import core, skyrict_common, skyrict_events; print('core image imports ok')"

# ---------------------------------------------------------------------------
# Stage: production - minimal final image, non-root
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Security: non-root user
RUN groupadd --gid 1000 skyrict && \
    useradd --uid 1000 --gid skyrict --create-home skyrict

WORKDIR /app

# System deps for runtime (asyncpg, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY the virtual environment from base (no source tree, no tests)
COPY --from=base /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source (no tests, no tests/fixtures/). The venv already
# resolves these from the paths installed by the base stage, so this is for
# alembic's `prepend_sys_path = src` and for source-level debugging.
COPY services/core/src services/core/src
COPY libs/skyrict-common/src libs/skyrict-common/src
COPY libs/skyrict-events/src libs/skyrict-events/src

# Copy alembic migrations (needed at runtime for DB migrations)
COPY services/core/alembic services/core/alembic
COPY services/core/alembic.ini services/core/alembic.ini

# Re-verify in the final image: this is the layer that actually ships, so a
# regression here must break the build rather than a replica in production.
# find_spec resolves the module without executing it - importing core.main
# would build its Settings and demand runtime env vars that do not exist at
# build time, which would fail the build for the wrong reason.
RUN /app/.venv/bin/python -c "import importlib.util as u; mods=('core','core.main','skyrict_common','skyrict_events'); missing=[m for m in mods if u.find_spec(m) is None]; assert not missing, 'unimportable in final image: %s' % missing; print('final image ok')"

# Set ownership
RUN chown -R skyrict:skyrict /app

USER skyrict

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/v1/health')"]

# 1 worker, not 4. Measured resident memory at a single worker is 173 MiB
# against a 0.5 GiB container limit; four workers of this app are an OOM kill
# on every replica. Scale out with more replicas (see maxReplicas in
# infra/azure/modules/apps.bicep) rather than forking workers inside a
# 0.5 GiB container.
CMD ["uvicorn", "core.main:app", \
     "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "1", "--no-access-log"]
