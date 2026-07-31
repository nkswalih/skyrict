# {name} Service

<!-- Replace {name} with your service name and describe what it does. -->

## Endpoints

<!-- Document your API endpoints here. -->

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness probe |
| GET | `/api/v1/ready` | Readiness probe |

## Local Development

```bash
# From repo root
uv run --directory services/{name} {name} serve --reload
```

## Running Tests

```bash
uv run pytest services/{name}/tests/unit/ -v
```

## Environment Variables

See `.env.example` for all required variables. Prefix: `{NAME}_` (uppercase).
