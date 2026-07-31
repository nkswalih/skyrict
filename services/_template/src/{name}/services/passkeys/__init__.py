"""Passkey (WebAuthn) service package."""

from __future__ import annotations

import uuid


class PasskeyService:
    """Handles WebAuthn/FIDO2 passkey operations."""

    def __init__(self, user_repo) -> None:
        self.user_repo = user_repo

    async def start_registration(self, user_id: uuid.UUID) -> dict:
        """Initiate passkey registration — return challenge options."""
        raise NotImplementedError

    async def complete_registration(self, user_id: uuid.UUID, credential: dict) -> dict:
        """Complete passkey registration after browser ceremony."""
        raise NotImplementedError

    async def start_authentication(self, email: str) -> dict:
        """Initiate passkey authentication — return challenge options."""
        raise NotImplementedError

    async def complete_authentication(self, credential: dict) -> dict:
        """Complete passkey authentication after browser ceremony."""
        raise NotImplementedError
