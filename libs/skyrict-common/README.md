# skyrict-common

Shared utilities, exceptions, logging, and response schemas for all Skyrict Python services.

## Usage

```toml
# In any service's pyproject.toml
[project]
dependencies = ["skyrict-common"]
```

```python
from skyrict_common.exceptions import UserNotFoundError, AuthenticationError
from skyrict_common.schemas import ResponseEnvelope, ListResponse
from skyrict_common.pagination import PaginationParams
from skyrict_common.logging import get_logger

logger = get_logger(__name__)
```

## Modules

| Module | Purpose |
|--------|---------|
| `exceptions` | Base exceptions for every domain error (auth, user, tenant, session, validation) |
| `schemas` | `ResponseEnvelope`, `ErrorResponse`, `ListResponse`, `PaginationMeta` |
| `pagination` | `PaginationParams` with offset/limit calculation |
| `logging` | Structured JSON logging via structlog |
