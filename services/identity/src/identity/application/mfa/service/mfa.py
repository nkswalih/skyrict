"""MFA service — TOTP setup, verification, backup codes."""

from __future__ import annotations

import secrets
import uuid

from identity.core.security import verify_password
from identity.application.auth.repository.user import UserRepository
from skyrict_common.exceptions import MFAVerificationError, UserNotFoundError


class MFAService:
    """Handles multi-factor authentication setup and verification."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def setup_totp(self, user_id: uuid.UUID) -> dict:
        """Generate a TOTP secret and provisioning URI for a user.

        Returns:
            dict with secret, provisioning_uri, and backup_codes
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Generate TOTP secret
        secret = secrets.token_hex(20)

        # Generate backup codes
        backup_codes = [secrets.token_hex(4) for _ in range(10)]

        # TODO: Store secret and hashed backup codes
        # TODO: Generate provisioning URI for authenticator apps

        return {
            "secret": secret,
            "backup_codes": backup_codes,
            "provisioning_uri": f"otpauth://totp/Skyrict:{user.email}?secret={secret}&issuer=Skyrict",
        }

    async def verify_totp(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify a TOTP code.

        Raises:
            MFAVerificationError: If the code is invalid.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        if not user.mfa_enabled or not user.mfa_secret:
            raise MFAVerificationError("MFA is not enabled for this user")

        # TODO: Implement actual TOTP verification using pyotp
        # For now, accept any 6-digit code
        if len(code) == 6 and code.isdigit():
            return True

        raise MFAVerificationError("Invalid MFA code")

    async def enable_mfa(self, user_id: uuid.UUID, secret: str, code: str) -> None:
        """Enable MFA after verifying the first TOTP code."""
        # Verify the code first
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # TODO: Verify TOTP code against secret
        user.mfa_enabled = True
        user.mfa_secret = secret
        await self.user_repo.commit()

    async def disable_mfa(self, user_id: uuid.UUID, password: str) -> None:
        """Disable MFA after password confirmation."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        if not verify_password(password, user.hashed_password):
            from skyrict_common.exceptions import InvalidPasswordError
            raise InvalidPasswordError()

        user.mfa_enabled = False
        user.mfa_secret = None
        await self.user_repo.commit()
