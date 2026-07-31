"""MFA service package — TOTP, backup codes."""

from __future__ import annotations

import secrets
import uuid


class MFAService:
    """Handles multi-factor authentication setup and verification."""

    def __init__(self, user_repo) -> None:
        self.user_repo = user_repo

    async def setup_totp(self, user_id: uuid.UUID) -> dict:
        """Generate a TOTP secret and provisioning URI for a user."""
        raise NotImplementedError

    async def verify_totp(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify a TOTP code."""
        raise NotImplementedError

    async def enable_mfa(self, user_id: uuid.UUID, secret: str, code: str) -> None:
        """Enable MFA after verifying the first TOTP code."""
        raise NotImplementedError

    async def disable_mfa(self, user_id: uuid.UUID, password: str) -> None:
        """Disable MFA after password confirmation."""
        raise NotImplementedError
