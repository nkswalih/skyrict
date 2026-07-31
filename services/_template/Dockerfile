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

# Copy this service's deps
COPY services/{name}/pyproject.toml services/{name}/
COPY libs/skyrict-common/pyproject.toml libs/skyrict-common/
COPY libs/skyrict-events/pyproject.toml libs/skyrict-events/

# Install deps
RUN uv sync --frozen --no-dev --directory services/{name}

# Copy source
COPY services/{name}/src services/{name}/src
COPY libs/skyrict-common/src libs/skyrict-common/src
COPY libs/skyrict-events/src libs/skyrict-events/src

# Runtime
EXPOSE 8000

CMD ["uv", "run", "--directory", "services/{name}", "{name}", "serve", "--host", "0.0.0.0", "--port", "8000"]
