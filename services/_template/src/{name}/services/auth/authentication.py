"""Authentication service — login, register, password verification."""

from __future__ import annotations


class AuthenticationService:
    """Handles user authentication — login, register, password verification."""

    def __init__(self, user_repo, tenant_repo, token_service, audit_service) -> None:
        self.user_repo = user_repo
        self.tenant_repo = tenant_repo
        self.token_service = token_service
        self.audit_service = audit_service

    async def login(self, request, *, ip_address=None, user_agent=None) -> dict:
        """Authenticate a user and return token pair."""
        raise NotImplementedError

    async def register(self, request, *, ip_address=None, user_agent=None) -> dict:
        """Register a new user."""
        raise NotImplementedError
