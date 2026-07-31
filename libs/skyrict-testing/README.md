# skyrict-testing

Shared test utilities — fixtures, factories, and helpers for all Skyrict services.

## Usage

```toml
# In any service's pyproject.toml
[project]
dependencies = ["skyrict-testing"]
```

```python
from skyrict_testing.fixtures import rsa_private_key, rsa_public_key
from skyrict_testing.factories import UserFactory, TenantFactory, SessionFactory

# In your tests:
user = UserFactory()
tenant = TenantFactory()
```

## RSA keys for tests

Tests never use committed key material. The `rsa_keypair`, `rsa_private_key`,
and `rsa_public_key` fixtures generate a fresh RSA-2048 pair in memory for
every test session.

For local development, generate gitignored keys:

```bash
python -m skyrict_testing.generate_keys
# Creates .dev/keys/{private,public}.pem (gitignored)
```

## Modules

| Module | Purpose |
|--------|---------|
| `fixtures` | `rsa_private_key`, `rsa_public_key`, `anyio_backend` pytest fixtures |
| `factories` | `UserFactory`, `TenantFactory`, `SessionFactory` (factory_boy) |
| `generate_keys` | CLI to generate RSA 2048-bit key pairs for local RS256 JWT development |
