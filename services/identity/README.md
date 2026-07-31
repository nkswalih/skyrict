# Identity Service

Authentication, authorization, multi-tenancy, sessions, and audit for Skyrict.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Authenticate with email/password |
| POST | `/api/v1/auth/register` | Register a new account |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Revoke session |
| POST | `/api/v1/auth/introspect` | Inspect a token |
| GET | `/api/v1/users/me` | Get current user profile |
| PUT | `/api/v1/users/me` | Update profile |
| POST | `/api/v1/users/me/password` | Change password |
| GET | `/api/v1/organizations/me` | Get current org |
| POST | `/api/v1/organizations` | Create org |
| GET | `/api/v1/sessions` | List active sessions |
| DELETE | `/api/v1/sessions/{id}` | Revoke session |
| DELETE | `/api/v1/sessions` | Revoke all sessions |
| POST | `/api/v1/mfa/setup` | Initiate MFA setup |
| POST | `/api/v1/mfa/verify` | Verify MFA code |
| POST | `/api/v1/passkeys/register/start` | Start passkey registration |
| POST | `/api/v1/sso/oidc/start` | Start OIDC SSO |
| GET | `/api/v1/health` | Liveness probe |
| GET | `/api/v1/ready` | Readiness probe |

## Local Development

```bash
# From repo root
make dev

# Or directly
uv run --directory services/identity identity serve --reload
```

## Running Tests

```bash
# Unit tests (no DB needed)
uv run pytest services/identity/tests/unit/ -v

# Integration tests (requires Docker)
uv run pytest services/identity/tests/integration/ -v
```

## Environment Variables

See `.env.example` for all required variables. Prefix: `IDENTITY_`
