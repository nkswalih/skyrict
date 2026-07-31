"""Test factories for generating test data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import factory

from identity.models.user import UserModel
from identity.models.tenant import TenantModel
from identity.models.session import SessionModel
from identity.core.security import hash_password


class UserFactory(factory.Factory):
    """Factory for creating test User records."""

    class Meta:
        model = UserModel

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@test.com")
    hashed_password = factory.LazyFunction(lambda: hash_password("TestPassword123!"))
    full_name = factory.Faker("name")
    is_active = True
    is_verified = False
    mfa_enabled = False
    mfa_secret = None
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class TenantFactory(factory.Factory):
    """Factory for creating test Tenant records."""

    class Meta:
        model = TenantModel

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test Org {n}")
    slug = factory.Sequence(lambda n: f"test-org-{n}")
    is_active = True
    plan = "free"
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class SessionFactory(factory.Factory):
    """Factory for creating test Session records."""

    class Meta:
        model = SessionModel

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.LazyFunction(uuid.uuid4)
    refresh_token_hash = factory.LazyFunction(lambda: hash_password("refresh-token"))
    user_agent = "TestAgent/1.0"
    ip_address = "127.0.0.1"
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))
