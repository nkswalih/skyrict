"""Passkey (WebAuthn) service — registration and authentication."""

from __future__ import annotations

import uuid

from identity.application.auth.repository.user import UserRepository
from skyrict_common.exceptions import PasskeyError


class PasskeyService:
    """Handles WebAuthn/FIDO2 passkey operations."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def start_registration(self, user_id: uuid.UUID) -> dict:
        """Initiate passkey registration — return challenge options."""
        # TODO: Implement WebAuthn registration ceremony
        # Return PublicKeyCredentialCreationOptions
        return {
            "challenge": "placeholder-challenge",
            "rp": {"name": "Skyrict", "id": "skyrict.dev"},
            "user": {"id": str(user_id)},
        }

    async def complete_registration(self, user_id: uuid.UUID, credential: dict) -> dict:
        """Complete passkey registration after browser ceremony."""
        # TODO: Verify attestation, store credential
        raise PasskeyError("Passkey registration not yet implemented")

    async def start_authentication(self, email: str) -> dict:
        """Initiate passkey authentication — return challenge options."""
        # TODO: Implement WebAuthn authentication ceremony
        return {
            "challenge": "placeholder-challenge",
            "timeout": 60000,
        }

    async def complete_authentication(self, credential: dict) -> dict:
        """Complete passkey authentication after browser ceremony."""
        # TODO: Verify assertion, return user info
        raise PasskeyError("Passkey authentication not yet implemented")
