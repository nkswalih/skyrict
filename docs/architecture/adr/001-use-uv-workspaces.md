# ADR-001: Use uv workspaces for Python monorepo

## Status

Accepted

## Date

2026-07-27

## Context

We need a Python package manager that supports a monorepo with multiple independently-deployable services (`services/identity`, `services/core`, etc.) and shared libraries (`libs/skyrict-common`). The team is 4 people. We need:

- Fast installs (CI and local dev)
- Single lockfile across all Python packages
- Workspace member discovery
- Native async/Pydantic/SQLAlchemy support
- Good CI caching

Options evaluated:

| Tool | Workspace Support | Lockfile | Speed | Maturity |
|------|-------------------|----------|-------|----------|
| **uv** | Native (`[tool.uv.workspace]`) | Single `uv.lock` | Fastest (Rust) | Growing rapidly |
| Poetry (monorepo plugin) | Via `poetry-monorepo` plugin | Per-package | Moderate | Plugin-dependent |
| pip + requirements files | Manual | None | Slow | Mature |
| PDM | Partial | Single | Moderate | Moderate |

## Decision

Use **uv** as the Python package manager with native workspace support.

Root `pyproject.toml` declares workspace members:

```toml
[tool.uv.workspace]
members = ["services/*", "libs/*"]
```

Each service/lib has its own `pyproject.toml` with dependencies. One `uv.lock` at the root locks everything.

## Consequences

### Positive

- One lockfile for reproducible installs across all services and libraries
- Fast installs (Rust-based, 10-100x faster than pip)
- Native workspace dependency resolution
- First-class Pydantic/SQLAlchemy support
- Excellent CI caching via `astral-sh/setup-uv`

### Negative

- uv is newer than Poetry — smaller community, fewer blog posts/tutorials
- Some edge cases may still have bugs (mitigated by active development)
- Team members need to learn uv (mitigated by similar CLI to pip)

### Risks

- uv breaking changes between versions (mitigated by `uv.lock` and pinned version in CI)
