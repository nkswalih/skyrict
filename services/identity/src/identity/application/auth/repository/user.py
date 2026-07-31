"""User repository — DB operations for the users table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.auth.models.user import UserModel
from identity.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserModel]):
    """Repository for user CRUD operations."""

    model = UserModel

    async def get_by_email(self, email: str) -> UserModel | None:
        """Fetch a user by email address."""
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Check if a user with this email already exists."""
        user = await self.get_by_email(email)
        return user is not None

    async def list_active(self, *, offset: int = 0, limit: int = 20) -> list[UserModel]:
        """List all active users."""
        return list(
            await self.list(offset=offset, limit=limit, filters=[UserModel.is_active == True])  # noqa: E712
        )
