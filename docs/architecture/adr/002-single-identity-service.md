# ADR-002: Single identity service with internal modules (not six microservices)

## Status

Accepted

## Date

2026-07-27

## Context

The product handbook describes AuthN, AuthZ, Token, User, Session, and Audit as six separate microservices. However, we are a 4-person team in pre-alpha with zero deployed services. Six services means:

- Six deployments to manage
- Six sets of health checks, retries, timeouts
- Six CI/CD pipelines
- Inter-service communication complexity (gRPC/Kafka between auth services)
- Distributed transaction challenges (user creation spans AuthN + Session + Audit)

## Decision

Build **one `identity` service** with six internal module layers:

```
services/identity/src/identity/
├── services/
│   ├── authn_service.py    # Authentication
│   ├── authz_service.py    # Authorization
│   ├── token_service.py    # JWT management
│   ├── mfa_service.py      # Multi-factor auth
│   ├── session_service.py  # Session tracking
│   └── audit_service.py    # Audit logging
```

Split into real microservices **only if** we hit a concrete scaling reason (e.g., audit logging throughput exceeds identity service capacity).

## Consequences

### Positive

- One deployment, one set of observability, one CI pipeline
- Shared database transactions (user creation is atomic)
- Simpler local development (`make dev` starts one service)
- Faster iteration for a 4-person team

### Negative

- Audit logging cannot scale independently (acceptable at our scale)
- All auth concerns share the same failure domain (mitigated by good error handling)

### Mitigations

- Clear internal module boundaries make future extraction straightforward
- Each service layer has its own repository — DB access is already isolated
- Event emission from each service layer means we can split on event consumers later
