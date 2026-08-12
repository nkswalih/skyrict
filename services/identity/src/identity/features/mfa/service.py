"""MFA service — TOTP setup, verification, backup codes, owner-assisted reset.

TOTP secrets are encrypted at rest (``core.security.encrypt_mfa_secret``) and
decrypted only on read. Backup codes are single-use Argon2id hashes: the same
``hash_backup_code``/``verify_backup_code`` primitive is used at generation and
redemption, and a consumed code's slot is set to ``None`` so the array keeps
its position until a regeneration replaces all ten.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

import pyotp

from identity.core.config import settings
from identity.core.mfa_providers import PROVIDER_BACKUP_CODE, PROVIDER_TOTP
from identity.core.security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    hash_password,
    verify_password,
)
from identity.core.tenant_context import TenantContext
from skyrict_common.exceptions import (
    InvalidPasswordError,
    MFAVerificationError,
    PermissionDeniedError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    import uuid

    from identity.features.audit.service import AuditService
    from identity.features.roles.ports import RoleRepositoryPort
    from identity.features.users.ports import UserRepositoryPort

BACKUP_CODE_COUNT = 10


def hash_backup_code(code: str) -> str:
    """Hash a backup code with Argon2id — the ONE hashing primitive for codes.

    Used identically at generation (setup) and at rest. Verification goes
    through :func:`verify_backup_code`, which is the inverse of this function.
    """
    return hash_password(code)


def verify_backup_code(code: str, stored_hash: str) -> bool:
    """Verify a backup code against its stored Argon2id hash (never raises)."""
    return verify_password(code, stored_hash)


def generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> tuple[list[str], list[str | None]]:
    """Return ``(plaintext_codes, hashes)`` — each code has 64 bits of entropy.

    The hashes are produced with :func:`hash_backup_code`, the identical
    function the redemption path verifies against. The hash list is typed to
    allow a consumed slot to become ``None``.
    """
    codes = [secrets.token_hex(8) for _ in range(n)]
    return codes, [hash_backup_code(code) for code in codes]


class MFAService:
    """Handles multi-factor authentication setup and verification."""

    def __init__(
        self,
        user_repo: UserRepositoryPort,
        role_repo: RoleRepositoryPort,
        audit_service: AuditService,
    ) -> None:
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.audit_service = audit_service

    async def setup_totp(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Generate a TOTP secret, provisioning URI, and fresh backup codes.

        The secret is encrypted and persisted immediately (MFA stays disabled
        until the first code verifies). Backup codes are regenerated on every
        call, replacing all ten slots.

        A pending (not yet enabled) secret is reused so revisiting the setup
        page — reload, remount, retry after a bad code — does not invalidate a
        secret the user has already scanned into their authenticator app.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        if user.mfa_secret is not None and not user.mfa_enabled:
            secret = decrypt_mfa_secret(user.mfa_secret)
        else:
            secret = pyotp.random_base32()

        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.MFA_TOTP_ISSUER,
        )
        codes, hashes = generate_backup_codes()

        await self.user_repo.update_mfa(
            user_id,
            mfa_secret=encrypt_mfa_secret(secret),
            mfa_backup_codes=hashes,
        )
        await self.audit_service.log(
            action="mfa.setup.initiated",
            target=f"user:{user.id}",
            user_id=str(user.id),
            details={"backup_codes": len(codes)},
        )
        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "backup_codes": codes,
        }

    async def verify_totp(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify a TOTP code against the user's stored (encrypted) secret."""
        user = await self.user_repo.get_by_id(user_id)
        if user is None or not user.mfa_secret:
            return False
        plain_secret = decrypt_mfa_secret(user.mfa_secret)
        return pyotp.TOTP(plain_secret).verify(code, valid_window=1)

    async def redeem_backup_code(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify a backup code and consume it (single-use) on a match.

        The consumed slot is set to ``None`` so the remaining codes keep their
        positions until the next regeneration replaces all ten.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None or not user.mfa_backup_codes:
            return False

        stored = user.mfa_backup_codes
        for index, stored_hash in enumerate(stored):
            if stored_hash is not None and verify_backup_code(code, stored_hash):
                updated = list(stored)
                updated[index] = None
                await self.user_repo.update_mfa(user_id, mfa_backup_codes=updated)
                await self.audit_service.log(
                    action="mfa.verify.backup_code_used",
                    target=f"user:{user.id}",
                    user_id=str(user.id),
                )
                return True
        return False

    async def enable_mfa(self, user_id: uuid.UUID, code: str) -> str:
        """Verify a code (TOTP or backup code) and enable MFA.

        Returns the verified provider key (``PROVIDER_TOTP`` or
        ``PROVIDER_BACKUP_CODE``) or raises :class:`MFAVerificationError`
        when neither verifies.
        """
        if await self.verify_totp(user_id, code):
            method = PROVIDER_TOTP
        elif await self.redeem_backup_code(user_id, code):
            method = PROVIDER_BACKUP_CODE
        else:
            raise MFAVerificationError("Invalid MFA code")

        await self.user_repo.update_mfa(user_id, mfa_enabled=True)
        await self.audit_service.log(
            action="mfa.enabled",
            target=f"user:{user_id}",
            user_id=str(user_id),
            details={"method": method},
        )
        return method

    async def rotate_backup_codes(self, user_id: uuid.UUID) -> list[str]:
        """Generate a fresh set of backup codes, invalidating all previous ones.

        Unlike :meth:`setup_totp` this does NOT touch the TOTP secret, so an
        already-enrolled authenticator keeps working. The new codes are
        returned in plaintext exactly once; only Argon2id hashes are stored.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        codes, hashes = generate_backup_codes()
        await self.user_repo.update_mfa(user_id, mfa_backup_codes=hashes)
        await self.audit_service.log(
            action="mfa.backup_codes.rotated",
            target=f"user:{user.id}",
            user_id=str(user.id),
            details={"count": len(codes)},
        )
        return codes

    async def disable_mfa(self, user_id: uuid.UUID, password: str) -> None:
        """Disable MFA after password confirmation."""
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if not verify_password(password, user.password_hash):
            raise InvalidPasswordError("Current password is incorrect")

        await self.user_repo.disable_mfa(user_id)
        await self.audit_service.log(
            action="mfa.disabled",
            target=f"user:{user_id}",
            user_id=str(user_id),
        )

    async def reset_mfa_by_owner(self, owner_user_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        """Owner-assisted MFA reset for a locked-out member.

        Only a ``tenant_owner`` may reset another user's MFA. The reset is
        audit-logged as high-sensitivity so every forced unlock is traceable.
        """
        tenant_id = TenantContext.get()
        roles = await self.role_repo.get_roles_for_user(owner_user_id, tenant_id)
        if "tenant_owner" not in roles:
            raise PermissionDeniedError("Only a tenant owner can reset MFA")

        target = await self.user_repo.get_by_id(target_user_id)
        if target is None:
            raise UserNotFoundError()

        await self.user_repo.disable_mfa(target_user_id)
        await self.audit_service.log(
            action="mfa.reset",
            target=f"user:{target_user_id}",
            user_id=str(owner_user_id),
            details={"sensitivity": "high", "target_user": str(target_user_id)},
        )
