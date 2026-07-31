"""Shared factory_boy factories for Skyrict service testing.

Usage:
    from skyrict_testing.factories import UserFactory, TenantFactory

    # In your test:
    user = UserFactory()
    tenant = TenantFactory()
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import factory


class TenantFactory(factory.Factory):
    """Create a test tenant (organization)."""

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Sequence(lambda n: f"Test Org {n}")
    slug = factory.Sequence(lambda n: f"test-org-{n}")
    is_active = True
    plan = "free"
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class UserFactory(factory.Factory):
    """Create a test user."""

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    email = factory.Sequence(lambda n: f"user{n}@test.skyrict.io")
    full_name = factory.Sequence(lambda n: f"Test User {n}")
    is_active = True
    is_verified = True
    mfa_enabled = False
    tenant_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class SessionFactory(factory.Factory):
    """Create a test session."""

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    user_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    tenant_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ip_address = "127.0.0.1"
    user_agent = "Mozilla/5.0 (Test)"
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    last_active_at = factory.LazyFunction(lambda: datetime.now(UTC))
