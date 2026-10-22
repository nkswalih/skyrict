# Contributing to Skyrict

Thanks for your interest in contributing. This document covers the workflow, standards, and expectations for contributors.

## Before You Start

- Check [open issues](https://github.com/skyrict/skyrict/issues) for existing work.
- For substantial changes (new modules, architectural changes, major refactors), open an issue first to discuss the approach. Large PRs without prior discussion are likely to be declined.
- Read the [architecture docs](docs/architecture/) to understand the domain model and event conventions.

## Development Setup

```bash
git clone https://github.com/skyrict/skyrict.git
cd skyrict
cp .env.example .env
docker compose up -d
pip install -e ".[dev]"
python -m skyrict migrate
python -m skyrict seed
python -m skyrict serve --dev
```

Install git hooks after cloning (runs lint/format/commit checks on every commit):

```bash
./scripts/setup-hooks.sh        # Unix/macOS
.\scripts\setup-hooks.ps1       # Windows
```

Run the full test suite before opening a PR:

```bash
make test
make lint
```

## Branch Strategy

- `main` - stable, deployable at all times
- `feat/{short-description}` - new features
- `fix/{short-description}` - bug fixes
- `refactor/{short-description}` - code structure changes
- `docs/{short-description}` - documentation only

Rebase on `main` before opening a PR. No merge commits.

## Commit Messages

Follow Conventional Commits:

```
feat(inventory): add batch expiration tracking

- Add batch_id foreign key to stock_level
- Add expiry_date to batch table
- Emit inventory.batch.expiring event 30 days before expiry
- Add expired stock report endpoint

Closes #142
```

Format: `type(scope): summary` followed by a blank line and bullet-point details.

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

## Code Standards

### Python

- **Formatter:** Ruff (replaces Black + isort)
- **Linter:** Ruff with default rules
- **Type checking:** mypy with strict mode on new code
- **Min version:** Python 3.12+

```toml
# pyproject.toml expectations
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
strict = true
```

- No `# type: ignore` without a linked issue number
- Prefer `async def` over `def` for I/O-bound operations
- Use Pydantic v2 models for all data validation
- Use SQLAlchemy 2.0 async patterns - no legacy `session.query()`

### TypeScript / React

- **Formatter:** Prettier
- **Linter:** ESLint with Next.js config
- Functional components only - no class components
- Use TanStack Query for server state, Zustand for client state

### Domain Logic

- Every business operation must emit a domain event
- No direct database reads across service boundaries - use events or query APIs
- All monetary values use `Decimal(19,4)` - never floats
- UUIDs for all primary keys (v7 preferred for sortability)
- Soft deletes only - no hard deletes on business data
- Audit columns on every table: `created_by`, `created_at`, `updated_by`, `updated_at`

### Database

- Migrations via Alembic - every schema change gets a migration file
- No raw SQL in application code - always through the ORM or parameterized queries
- Index naming convention: `ix_{table}_{columns}`
- Foreign key naming convention: `fk_{table}_{referenced_table}`

### Public artifacts and test data

- Docs, ADRs, PR titles and descriptions, commit messages, commands, and
  docstrings must not name real tenants, customers, user accounts, personal
  email addresses, or production request IDs.
- Describe production findings generically (`a production tenant`) and use
  reserved example domains (`@example.com`) for fixtures.

## Testing

| Type        | Tool                    | Target                 | Run                     |
| ----------- | ----------------------- | ---------------------- | ----------------------- |
| Unit        | pytest                  | 80%+ on business logic | `make test-unit`        |
| Integration | pytest + Testcontainers | Critical paths         | `make test-integration` |
| E2E         | Playwright              | User flows             | `make test-e2e`         |
| Performance | Locust / k6             | API benchmarks         | `make benchmark`        |

Every PR must include tests for the functionality being added or changed. Bug fix PRs must include a regression test.

### Test naming convention

```
tests/
├── unit/
│   ├── finance/
│   │   ├── test_journal_entry_posting.py
│   │   └── test_multi_currency_revaluation.py
│   └── inventory/
│       └── test_stock_movement.py
├── integration/
│   ├── test_procurement_three_way_match.py
│   └── test_sales_order_to_invoice.py
└── e2e/
    └── test_full_order_lifecycle.py
```

## Pull Request Process

1. **One PR, one concern.** Don't bundle unrelated changes.
2. **Fill out the PR template.** Link the issue, describe the change, list testing done.
3. **Self-review before requesting review.** Read your own diff. Fix obvious issues.
4. **Respond to review feedback within 48 hours.** Even if just acknowledging.
5. **Squash on merge.** Keep `main` history clean.

### PR Title

The `Validate PR Title` workflow enforces the title on open/edit. It must match
one of two forms; types are `feat|fix|chore|docs|test|refactor|perf|ci|build`,
scope is optional, and a `!` marks a breaking change.

1. **Jira-tracked work** — `[INTERNAL-ID]: type(scope)/TICKET-KEY summary`

   ```
   [RPT-DATA-001]: feat(core)/SKY-77 reporting data layer - parametrized runs + snapshots
   ```

   Both the internal-ID prefix (`[DOMAIN-LAYER-000]`) and the Jira key are
   mandatory for Jira-tracked PRs.

2. **Non-Jira work** — Conventional Commits, no ID/key prefix

   ```
   fix(ci): validate root CI - explicit per-package test jobs + remove dead cd-production stub
   ```

Open `scripts/new-pr.ps1` from the branch to pre-fill the title (it derives the
type, Jira key, and summary from the branch name and opens the compare page).

### PR Review Criteria

Reviewers will check:

- Does it solve the stated problem?
- Are there tests covering the change?
- Does it follow the code standards above?
- Are there any security implications? (auth, data access, input validation)
- Are domain events emitted correctly?
- Will this break backward compatibility?

### What gets merged quickly

- Small, focused PRs with tests
- Bug fixes with clear reproduction steps
- Documentation improvements with accurate content
- Performance improvements backed by benchmarks

### What gets declined

- PRs without tests for new business logic
- Formatting-only changes mixed with functional changes
- Large refactors without prior issue discussion
- Code that introduces new linting errors or type errors
- PRs that decrease test coverage on changed files

## Brand Identity

All customer-facing copy, visuals, and assets must follow
[`docs/brand/README.md`](docs/brand/README.md). It defines the positioning,
voice, messaging hierarchy, logo system, colour and type usage, applications,
and brand governance.

The short version:

- Write **Skyrict**, one word, capital S. The descriptor is **AI Business
  Operating System**.
- Lead with the decision, then the evidence. Put units and time frames on every
  number. Do not anthropomorphise agents.
- The corporate signature is always the Sky mark. ERP and AI tones are product
  wayfinding, never brand marks.
- Use exported marks from [`docs/brand/assets/`](docs/brand/assets/) and keep
  half the mark height clear on every side.
- Label unfinished capabilities "in progress". Do not imply they are live.

Brand changes need review from the design owner and one engineer. The name,
logo, and marks are governed by [`TRADEMARK.md`](TRADEMARK.md) and are separate
from the Apache 2.0 code licence.

## Design System

All web UI changes must follow [`docs/design-system/README.md`](docs/design-system/README.md).
It defines the Sky theme tokens, typography, spacing, component specs, module
worlds, motion, and accessibility rules. The live reference renders at
`/design-system` while `next dev` is running (it returns 404 in production
unless `NEXT_PUBLIC_DESIGN_SYSTEM=true`).

Use semantic tokens (`bg-primary`, `text-muted-foreground`, `border-border`)
instead of raw hex, and check light mode, dark mode, and the active module world
before opening a PR.

## Architecture Decisions

Significant design decisions should be documented as Architecture Decision Records (ADRs) in `docs/architecture/adr/`. Use the format:

```markdown
# ADR-{number}: {title}

## Status

Accepted | Proposed | Deprecated | Superseded by ADR-{number}

## Context

What is the issue that motivates this decision?

## Decision

What is the change being proposed or decided?

## Consequences

What are the tradeoffs? What becomes easier? What becomes harder?
```

## Intelligence Engine Contributions

When adding new data source collectors:

1. Implement the `BaseCollector` interface
2. Include rate limiting configuration
3. Normalize output to the `NormalizedSignal` schema
4. Write tests with mocked API responses
5. Document rate limits and data freshness in the collector's docstring

When adding new scoring algorithms:

1. Define the scoring formula in a dedicated module
2. Include unit tests with known inputs/outputs
3. Document the scoring range and interpretation
4. Add ADR if the score influences agent decisions

## Agent Contributions

When adding new agent capabilities:

1. Define the tool interface with strict input/output schemas
2. Implement guardrails - every agent action must have a policy check
3. Log all agent actions with full context for audit
4. Test with adversarial inputs - try to break the guardrails
5. Document failure modes and fallback behavior

## Questions?

Open a [GitHub Discussion](https://github.com/skyrict/skyrict/discussions) for architecture questions, design debates, or implementation guidance.
