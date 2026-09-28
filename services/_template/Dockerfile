FROM python:3.12-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root
COPY pyproject.toml uv.lock ./

# Copy every workspace member manifest (the workspace glob is services/* and
# libs/*, and `uv sync --frozen` refuses to resolve if a member is missing).
# READMEs too: hatchling requires the `readme` declared in each pyproject.toml.
COPY services/{name}/pyproject.toml services/{name}/
COPY services/{name}/README.md services/{name}/
COPY libs/skyrict-common/pyproject.toml libs/skyrict-common/
COPY libs/skyrict-common/README.md libs/skyrict-common/
COPY libs/skyrict-events/pyproject.toml libs/skyrict-events/
COPY libs/skyrict-events/README.md libs/skyrict-events/

# Copy source BEFORE the sync. `skyrict-common` and `skyrict-events` are
# workspace dependencies that uv builds during `uv sync`; with only manifests
# present the sync yields a venv with no importable path entry and the container
# dies on ModuleNotFoundError. This is the exact defect that shipped in all
# three production Dockerfiles - keep the order.
COPY services/{name}/src services/{name}/src
COPY libs/skyrict-common/src libs/skyrict-common/src
COPY libs/skyrict-events/src libs/skyrict-events/src

# Install deps
RUN uv sync --frozen --no-dev --directory services/{name}

# Fail the build rather than a production replica if the venv is unusable.
# find_spec resolves the module without executing it - importing {name}.main
# would build its Settings and demand runtime env vars that do not exist at
# build time, which would fail the build for the wrong reason.
RUN /app/.venv/bin/python -c "import importlib.util as u; mods=('{name}','{name}.main','skyrict_common','skyrict_events'); missing=[m for m in mods if u.find_spec(m) is None]; assert not missing, 'unimportable in final image: %s' % missing; print('imports ok')"

# Runtime
EXPOSE 8000

# 1 worker per container: replicas scale horizontally, workers do not. Four
# workers will OOM a 0.5 GiB container.
CMD ["uv", "run", "--directory", "services/{name}", "{name}", "serve", \
     "--host", "0.0.0.0", "--port", "8000"]
