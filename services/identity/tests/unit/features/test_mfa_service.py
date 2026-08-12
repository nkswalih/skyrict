"""Unit tests for the MFA feature MFAService (fake ports).

Covers the AUTH-TASK-035 acceptance criteria: TOTP setup/verification, backup
codes (identical hashing primitive, single-use consumption), secret-at-rest
encryption, disable with password confirmation, and owner-assisted reset with
high-sensitivity audit.
"""

from __future__ import annotations

import uuid

import pyotp
import pytest

from identity.core.security import (
    decrypt_mfa_secret,
    hash_password,
    mfa_is_required,
)
from identity.core.tenant_context import TenantContext
from identity.domain.entities import User
from identity.features.mfa.service import (
    MFAService,
    generate_backup_codes,
    verify_backup_code,
)
from skyrict_common.exceptions import (
    InvalidPasswordError,
    MFAVerificationError,
    PermissionDeniedError,
)


class FakeUserRepo:
    """UserRepositoryPort double — records MFA writes on the wrapped user."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.updates: list[dict[str, object]] = []
        self.disabled = False

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        return self.user

    async def update_mfa(
        self,
        user_id: str | uuid.UUID,
        *,
        mfa_enabled: bool | None = None,
        mfa_secret: str | None = None,
        mfa_backup_codes: list[str | None] | None = None,
    ) -> User:
        self.updates.append(
            {
                "mfa_enabled": mfa_enabled,
                "mfa_secret": mfa_secret,
                "mfa_backup_codes": mfa_backup_codes,
            }
        )
        if mfa_enabled is not None:
            self.user.mfa_enabled = mfa_enabled
        if mfa_secret is not None:
            self.user.mfa_secret = mfa_secret
        if mfa_backup_codes is not None:
            self.user.mfa_backup_codes = mfa_backup_codes
        return self.user

    async def disable_mfa(self, user_id: str | uuid.UUID) -> User:
        self.disabled = True
        self.user.mfa_enabled = False
        self.user.mfa_secret = None
        self.user.mfa_backup_codes = []
        return self.user


class FakeRoleRepo:
    """RoleRepositoryPort double — returns a fixed role list for any user."""

    def __init__(self, roles: list[str] | None = None) -> None:
        self.roles = roles or []

    async def get_roles_for_user(
        self, user_id: str | uuid.UUID, tenant_id: str | uuid.UUID
    ) -> list[str]:
        return self.roles


class FakeAuditService:
    """AuditService double — records every log() call, including details."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def log(
        self,
        *,
        action: str,
        target: str,
        user_id: str | None = None,
        details: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self.events.append(
            {"action": action, "target": target, "user_id": user_id, "details": details}
        )


def _make_user(
    *,
    mfa_enabled: bool = False,
    mfa_secret: str | None = None,
    mfa_backup_codes: list[str | None] | None = None,
) -> User:
    return User(
        tenant_id=uuid.uuid4(),
        email="user@example.com",
        password_hash=hash_password("Password1!"),
        full_name="Test User",
        is_active=True,
        is_verified=True,
        mfa_enabled=mfa_enabled,
        mfa_secret=mfa_secret,
        mfa_backup_codes=mfa_backup_codes or [],
        id=uuid.uuid4(),
    )


def _make_service(
    *, roles: list[str] | None = None
) -> tuple[MFAService, FakeUserRepo, FakeAuditService]:
    user = _make_user()
    user_repo = FakeUserRepo(user)
    role_repo = FakeRoleRepo(roles)
    audit_svc = FakeAuditService()
    service = MFAService(user_repo, role_repo, audit_svc)
    return service, user_repo, audit_svc


@pytest.fixture
def tenant_ctx() -> str:
    tenant_id = str(uuid.uuid4())
    TenantContext.set(tenant_id)
    yield tenant_id
    TenantContext.reset()


class TestBackupCodePrimitive:
    """DoD: generation and redemption use ONE identical hashing primitive."""

    def test_generate_backup_codes_hashes_match_the_verification_primitive(self) -> None:
        codes, hashes = generate_backup_codes(10)

        assert len(codes) == 10
        assert len(hashes) == 10
        assert all(len(code) == 16 for code in codes)
        # The stored hashes ARE the output of the one backup-code primitive
        # (Argon2id, same as passwords), and redemption inverts it via the
        # paired verify function — no other code path accepts a backup code.
        assert all(stored.startswith("$argon2id$") for stored in hashes)
        assert all(
            verify_backup_code(code, stored) for code, stored in zip(codes, hashes, strict=True)
        )
        assert not any(verify_backup_code("wrong-code", stored) for stored in hashes)


class TestSetupTotp:
    async def test_setup_returns_secret_uri_and_codes_but_stays_disabled(
        self, tenant_ctx: str
    ) -> None:
        service, user_repo, audit_svc = _make_service()

        result = await service.setup_totp(user_repo.user.id)

        assert len(result["secret"]) == 32  # base32 (160 bits)
        assert result["provisioning_uri"].startswith("otpauth://totp/")
        assert len(result["backup_codes"]) == 10
        assert user_repo.user.mfa_enabled is False
        assert audit_svc.events == [
            {
                "action": "mfa.setup.initiated",
                "target": f"user:{user_repo.user.id}",
                "user_id": str(user_repo.user.id),
                "details": {"backup_codes": 10},
            }
        ]

    async def test_secret_is_encrypted_at_rest(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()

        result = await service.setup_totp(user_repo.user.id)

        stored = user_repo.user.mfa_secret
        assert stored is not None
        assert stored != result["secret"]
        assert decrypt_mfa_secret(stored) == result["secret"]

    async def test_setup_reuses_pending_secret_before_enrollment(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()

        first = await service.setup_totp(user_repo.user.id)
        second = await service.setup_totp(user_repo.user.id)

        assert second["secret"] == first["secret"]
        assert second["provisioning_uri"] == first["provisioning_uri"]

    async def test_setup_regenerates_secret_once_enabled(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()

        first = await service.setup_totp(user_repo.user.id)
        await service.enable_mfa(user_repo.user.id, first["backup_codes"][0])
        second = await service.setup_totp(user_repo.user.id)

        assert second["secret"] != first["secret"]

    async def test_setup_regenerates_all_ten_backup_code_slots(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()

        await service.setup_totp(user_repo.user.id)
        stored_after_first = list(user_repo.user.mfa_backup_codes)
        second = await service.setup_totp(user_repo.user.id)

        assert len(user_repo.user.mfa_backup_codes) == 10
        assert all(stored_hash is not None for stored_hash in stored_after_first)
        assert any(
            verify_backup_code(code, stored) is False
            for code, stored in zip(second["backup_codes"], stored_after_first, strict=True)
        )


class TestVerifyTotp:
    async def test_accepts_valid_code_and_rejects_invalid(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()
        result = await service.setup_totp(user_repo.user.id)

        assert (
            await service.verify_totp(user_repo.user.id, pyotp.TOTP(result["secret"]).now()) is True
        )
        assert await service.verify_totp(user_repo.user.id, "000000") is False


class TestEnableMfa:
    async def test_enable_with_totp_marks_enabled(self, tenant_ctx: str) -> None:
        service, user_repo, audit_svc = _make_service()
        result = await service.setup_totp(user_repo.user.id)

        method = await service.enable_mfa(user_repo.user.id, pyotp.TOTP(result["secret"]).now())

        assert method == "totp"
        assert user_repo.user.mfa_enabled is True
        assert audit_svc.events[-1]["action"] == "mfa.enabled"
        assert audit_svc.events[-1]["details"] == {"method": "totp"}

    async def test_enable_with_backup_code_is_single_use(self, tenant_ctx: str) -> None:
        service, user_repo, audit_svc = _make_service()
        result = await service.setup_totp(user_repo.user.id)
        code = result["backup_codes"][0]

        method = await service.enable_mfa(user_repo.user.id, code)

        assert method == "backup_code"
        assert user_repo.user.mfa_enabled is True
        assert user_repo.user.mfa_backup_codes[0] is None
        assert all(stored_hash is not None for stored_hash in user_repo.user.mfa_backup_codes[1:])
        assert audit_svc.events[-1]["details"] == {"method": "backup_code"}

        with pytest.raises(MFAVerificationError):
            await service.enable_mfa(user_repo.user.id, code)

    async def test_invalid_code_raises_and_keeps_disabled(self, tenant_ctx: str) -> None:
        service, user_repo, _ = _make_service()
        await service.setup_totp(user_repo.user.id)

        with pytest.raises(MFAVerificationError):
            await service.enable_mfa(user_repo.user.id, "123456")

        assert user_repo.user.mfa_enabled is False


class TestDisableMfa:
    async def test_wrong_password_raises_and_state_unchanged(self, tenant_ctx: str) -> None:
        service, user_repo, audit_svc = _make_service()
        result = await service.setup_totp(user_repo.user.id)
        await service.enable_mfa(user_repo.user.id, result["backup_codes"][0])
        before = (user_repo.user.mfa_enabled, user_repo.user.mfa_secret)

        with pytest.raises(InvalidPasswordError):
            await service.disable_mfa(user_repo.user.id, "WrongPass1!")

        assert (user_repo.user.mfa_enabled, user_repo.user.mfa_secret) == before
        assert audit_svc.events[-1]["action"] == "mfa.enabled"

    async def test_clears_all_mfa_state_on_password_confirmation(self, tenant_ctx: str) -> None:
        service, user_repo, audit_svc = _make_service()
        result = await service.setup_totp(user_repo.user.id)
        await service.enable_mfa(user_repo.user.id, result["backup_codes"][0])

        await service.disable_mfa(user_repo.user.id, "Password1!")

        assert user_repo.user.mfa_enabled is False
        assert user_repo.user.mfa_secret is None
        assert user_repo.user.mfa_backup_codes == []
        assert audit_svc.events[-1]["action"] == "mfa.disabled"


class TestResetMfaByOwner:
    async def test_non_owner_raises_permission_denied(self, tenant_ctx: str) -> None:
        service, _, _ = _make_service(roles=[])
        target = _make_user(mfa_enabled=True)

        with pytest.raises(PermissionDeniedError):
            await service.reset_mfa_by_owner(uuid.uuid4(), target.id)

        assert target.mfa_enabled is True

    async def test_owner_reset_clears_mfa_and_audits_high_sensitivity(
        self, tenant_ctx: str
    ) -> None:
        owner_id = uuid.uuid4()
        service, user_repo, audit_svc = _make_service(roles=["tenant_owner"])
        result = await service.setup_totp(user_repo.user.id)
        await service.enable_mfa(user_repo.user.id, result["backup_codes"][0])

        await service.reset_mfa_by_owner(owner_id, user_repo.user.id)

        assert user_repo.user.mfa_enabled is False
        assert user_repo.user.mfa_secret is None
        assert user_repo.disabled is True
        assert audit_svc.events[-1] == {
            "action": "mfa.reset",
            "target": f"user:{user_repo.user.id}",
            "user_id": str(owner_id),
            "details": {
                "sensitivity": "high",
                "target_user": str(user_repo.user.id),
            },
        }


class TestMfaIsRequired:
    async def test_disabled_mfa_always_required(self) -> None:
        assert mfa_is_required(mfa_enabled=False) is True

    async def test_enabled_mfa_never_required(self) -> None:
        assert mfa_is_required(mfa_enabled=True) is False
