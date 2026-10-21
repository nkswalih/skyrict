"""UserRepository.create must translate duplicate-email inserts into a 409.

The global ``uq_users_email`` index is the last line of defence for the
one-account-per-email rule (SKY-30): a caller that races the application-level
check must still get a domain conflict, never an unhandled ``IntegrityError``
that FastAPI renders as a 500.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy.exc import IntegrityError

from identity.domain.entities import User
from identity.features.users.repository import UserRepository
from skyrict_common.exceptions import UserAlreadyExistsError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _user() -> User:
    return User(
        tenant_id=uuid.uuid4(),
        email="dup@test.com",
        password_hash="hash",
        full_name="Duplicate User",
        is_active=True,
        is_verified=True,
    )


class _RaisingSession:
    """AsyncSession stand-in whose flush raises one fixed IntegrityError."""

    def __init__(self, error: IntegrityError) -> None:
        self._error = error
        self.added: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        raise self._error

    async def refresh(self, instance: object) -> None:
        raise AssertionError("refresh must not run after a failed flush")


def _repo_raising(message: str) -> UserRepository:
    error = IntegrityError("INSERT INTO users", {}, Exception(message))
    return UserRepository(cast("AsyncSession", _RaisingSession(error)))


class TestUserRepositoryConflictMapping:
    async def test_global_unique_violation_is_a_conflict(self) -> None:
        repo = _repo_raising('duplicate key value violates unique constraint "uq_users_email"')

        with pytest.raises(UserAlreadyExistsError):
            await repo.create(_user())

    async def test_tenant_unique_violation_is_a_conflict(self) -> None:
        repo = _repo_raising(
            'duplicate key value violates unique constraint "uq_users_tenant_email"'
        )

        with pytest.raises(UserAlreadyExistsError):
            await repo.create(_user())

    async def test_unrelated_integrity_error_is_reraised(self) -> None:
        repo = _repo_raising('insert or update on table "users" violates foreign key constraint')

        with pytest.raises(IntegrityError):
            await repo.create(_user())
