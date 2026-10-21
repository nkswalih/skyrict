"""Invitation service - create, accept, and expire invite tokens."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from identity.core.audit_events import INVITATION_ACCEPTED, INVITATION_CREATED, INVITATION_EXPIRED
from identity.core.config import settings
from identity.core.constants import INVITATION_TOKEN_EXPIRE_DAYS
from identity.core.email import EmailService
from identity.core.security import hash_invitation_token, hash_password, validate_password_policy
from identity.db.session import async_session_factory
from identity.domain.entities import Invitation, MembershipStatus, User
from identity.features.invitations.ports import InvitationRepositoryPort
from skyrict_common.exceptions import (
    InvitationAlreadyUsedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    NotFoundError,
    UserAlreadyExistsError,
    ValidationError,
)

if TYPE_CHECKING:
    from identity.features.audit.service import AuditService
    from identity.features.avatars.service import AvatarService
    from identity.features.memberships.service import MembershipService
    from identity.features.organizations.ports import TenantRepositoryPort
    from identity.features.roles.ports import RoleRepositoryPort
    from identity.features.users.ports import UserRepositoryPort

logger = structlog.get_logger("identity.invitations")


class InvitationService:
    def __init__(
        self,
        invitation_repo: InvitationRepositoryPort,
        user_repo: UserRepositoryPort,
        tenant_repo: TenantRepositoryPort,
        role_repo: RoleRepositoryPort,
        email_service: EmailService,
        membership_service: MembershipService,
        audit_service: AuditService,
        *,
        avatar_service: AvatarService | None = None,
    ) -> None:
        self.invitation_repo = invitation_repo
        self.user_repo = user_repo
        self.tenant_repo = tenant_repo
        self.role_repo = role_repo
        self.email_service = email_service
        self.membership_service = membership_service
        self.audit_service = audit_service
        self.avatar_service = avatar_service

    async def create_invitation(
        self,
        *,
        tenant_id: str | uuid.UUID,
        email: str,
        role_name: str,
        created_by_user_id: str | uuid.UUID,
        inviter_name: str = "",
        organization_name: str = "",
        base_url: str | None = None,
        expires_in_hours: int | None = None,
    ) -> tuple[Invitation, str]:

        role = await self.role_repo.get_by_name(tenant_id, role_name)
        if role is None or role.id is None:
            raise ValidationError(f"Role '{role_name}' does not exist in this organization")

        existing_user = await self.user_repo.get_by_email(tenant_id, email)
        if existing_user is not None:
            raise ValidationError("A user with this email already exists in this organization")

        # A Skyrict account is global per email (``uq_users_email``): an email
        # that already belongs to an account in ANY tenant cannot be invited
        # into a second one - accepting would violate that index. Reject it
        # here, as a conflict the admin can act on, instead of letting the
        # invitee discover it as an IntegrityError 500 at accept time.
        if await self.user_repo.email_exists_global(email):
            raise UserAlreadyExistsError("This email is unavailable.")

        # The INVITED membership reserves the email within the tenant; it is
        # the canonical pending relationship (no placeholder user). When that
        # reservation belongs to a DEAD invite (time-expired or admin-expired)
        # the email must be re-invitable: the same row is renewed in place so
        # the tenant keeps one INVITED membership per email. A LIVE invitation
        # still blocks a re-send.
        membership = await self.membership_service.get_by_email(tenant_id, email)
        if membership is not None and membership.status is not MembershipStatus.INVITED:
            raise ValidationError("This email is already a member or invited in this organization")

        prior_invitation = await self.invitation_repo.get_by_email(tenant_id, email)
        if prior_invitation is not None and self._is_live(prior_invitation):
            raise ValidationError(
                "This email already has a pending invitation in this organization"
            )

        if membership is not None:
            assert membership.id is not None
            membership = await self.membership_service.renew_invited(
                membership_id=membership.id,
                role_id=role.id,
                invited_by_user_id=created_by_user_id,
            )
        else:
            membership = await self.membership_service.create_invited(
                tenant_id=tenant_id,
                email=email,
                role_id=role.id,
                invited_by_user_id=created_by_user_id,
            )

        token = secrets.token_urlsafe(32)
        if expires_in_hours is not None:
            expires_at = datetime.now(UTC) + timedelta(hours=expires_in_hours)
        else:
            expires_at = datetime.now(UTC) + timedelta(days=INVITATION_TOKEN_EXPIRE_DAYS)

        invitation = await self.invitation_repo.create(
            Invitation(
                tenant_id=uuid.UUID(str(tenant_id)),
                email=email,
                token_hash=hash_invitation_token(token),
                role_name=role_name,
                created_by_user_id=uuid.UUID(str(created_by_user_id)),
                expires_at=expires_at,
                membership_id=membership.id,
            )
        )

        await self.email_service.send_invitation(
            to=email,
            inviter_name=inviter_name,
            organization_name=organization_name,
            token=token,
            base_url=base_url or settings.EMAIL_VERIFICATION_BASE_URL or None,
        )

        assert invitation.id is not None
        await self.audit_service.log(
            action=INVITATION_CREATED,
            target=f"invitation:{invitation.id}",
            user_id=str(created_by_user_id),
            tenant_id=str(tenant_id),
        )

        return invitation, token

    async def list_invitations(
        self, tenant_id: str | uuid.UUID, *, offset: int = 0, limit: int = 20
    ) -> list[Invitation]:
        """List invitations for a tenant, newest first."""
        return await self.invitation_repo.list_by_tenant(tenant_id, offset=offset, limit=limit)

    async def verify_invitation(self, *, token: str) -> tuple[Invitation, str | None]:
        """Validate a token before the accept form is shown.

        Returns the invitation and the organization name (or None when the
        tenant is gone) so the invitee can see who invited them. Raises the
        standard Invitation* errors for invalid, expired, or used tokens.
        """
        invitation = await self._load_valid_invitation(token)
        tenant = await self.tenant_repo.get_by_id(invitation.tenant_id)
        return invitation, tenant.name if tenant is not None else None

    @staticmethod
    def _is_live(invitation: Invitation) -> bool:
        """An invitation still reserves the email while unexpired AND unused.

        ``used_at`` alone is not enough: an admin "expire" also stamps
        ``used_at`` (with no user), so a dead invite must not block a re-send.
        """
        return invitation.used_at is None and invitation.expires_at >= datetime.now(UTC)

    async def _load_valid_invitation(self, token: str) -> Invitation:
        invitation = await self.invitation_repo.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError("Invalid invitation token")

        if invitation.expires_at < datetime.now(UTC):
            raise InvitationExpiredError("Invitation has expired")

        if invitation.used_at is not None:
            raise InvitationAlreadyUsedError("Invitation has already been used")

        return invitation

    async def accept_invitation(
        self,
        *,
        token: str,
        email: str,
        password: str,
        full_name: str,
        avatar: bytes | None = None,
    ) -> User:
        invitation = await self._load_valid_invitation(token)

        if invitation.email.lower() != email.lower():
            raise InvitationEmailMismatchError("Email does not match the invitation")

        validate_password_policy(password)

        tenant_id = invitation.tenant_id

        existing = await self.user_repo.get_by_email(tenant_id, email)
        if existing is not None:
            raise UserAlreadyExistsError(
                "A user with this email already exists in this organization"
            )

        # Invitations created before the create-time global guard (or sent by a
        # stale client) can point at an email that registered elsewhere since.
        # Fail with a conflict the invitee can act on - never an IntegrityError.
        if await self.user_repo.email_exists_global(email):
            raise UserAlreadyExistsError(
                "This email already has a Skyrict account; "
                "sign in instead of accepting the invitation"
            )

        user = await self.user_repo.create(
            User(
                tenant_id=uuid.UUID(str(tenant_id)),
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                is_active=True,
                is_verified=True,
            )
        )

        assert invitation.id is not None
        assert user.id is not None

        if avatar and self.avatar_service is not None:
            await self.avatar_service.attach_to_user(
                user_id=str(user.id), tenant_id=str(tenant_id), data=avatar
            )

        role = await self.role_repo.get_by_name(tenant_id, invitation.role_name)
        if role is None or role.id is None:
            raise ValidationError(
                f"Role '{invitation.role_name}' no longer exists in this organization"
            )
        await self.role_repo.grant_to_user(
            user_id=user.id,
            role_id=role.id,
            tenant_id=tenant_id,
            scope_id=uuid.UUID(str(tenant_id)),
        )

        if invitation.membership_id is not None:
            await self.membership_service.activate(
                membership_id=invitation.membership_id, user_id=user.id
            )
        else:
            # Legacy invitation (pre-0009): no linked membership exists, so
            # materialize an ACTIVE membership for the new user.
            await self.membership_service.create_active(
                tenant_id=tenant_id,
                user_id=user.id,
                role_id=role.id,
                invited_email=email,
            )

        await self.invitation_repo.mark_used(invitation.id, user.id)

        await self.audit_service.log(
            action=INVITATION_ACCEPTED,
            target=f"invitation:{invitation.id}",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
        )

        await self._mirror_grant_to_core(
            tenant_id=uuid.UUID(str(tenant_id)),
            role=role,
            user_id=user.id,
            invitation_email=invitation.email,
        )

        return user

    async def _mirror_grant_to_core(
        self,
        *,
        tenant_id: uuid.UUID,
        role: object,
        user_id: uuid.UUID,
        invitation_email: str = "",
    ) -> None:
        """ACCEPTED Phase-1 bridge: mirror the grant into core's RBAC tables.

        The Kafka bus does not exist yet (``publish_event`` is a logging stub),
        so core's ``require_permission`` - which resolves grants from
        ``core_roles`` / ``core_user_roles`` - would never see invitees. Both
        services share one database, so this writes the same upserts core's
        own ``apply_role_grants`` consumer handler performs (same composite-PK
        shapes, same scope semantics: scope_id = tenant id). Permissions are
        REPLACED on conflict (never merged), so a role edit that removed
        permissions propagates to core on the next invite accept.

        Additionally binds the invited employee record: when exactly ONE
        non-terminated ``erp_employees`` row in the tenant carries the
        invitation email and no ``user_id`` yet, that row is linked to the new
        user. The self-service portal resolves its caller through this link.

        Failures are logged, never raised: accept must succeed even if the
        mirror needs a later replay (the future consumer / ``core
        provision-rbac`` heals it).
        """
        role_id = getattr(role, "id", None)
        role_name = getattr(role, "name", None)
        permissions = list(getattr(role, "permissions", None) or [])
        if role_id is None or role_name is None:
            logger.warning("rbac_mirror.skipped_missing_role", role=role_name)
            return
        try:
            async with async_session_factory() as session:
                await session.execute(
                    text(
                        "INSERT INTO core_roles (tenant_id, id, name, permissions, is_system_role) "
                        "VALUES (:tid, :rid, :rname, :perms, :sys) "
                        "ON CONFLICT (tenant_id, name) DO UPDATE SET "
                        "permissions = EXCLUDED.permissions, "
                        "is_system_role = EXCLUDED.is_system_role, updated_at = now()"
                    ),
                    {
                        "tid": tenant_id,
                        "rid": role_id,
                        "rname": role_name,
                        "perms": permissions,
                        "sys": bool(getattr(role, "is_system_role", True)),
                    },
                )
                row = (
                    await session.execute(
                        text("SELECT id FROM core_roles WHERE tenant_id = :tid AND name = :rname"),
                        {"tid": tenant_id, "rname": role_name},
                    )
                ).scalar_one()
                await session.execute(
                    text(
                        "INSERT INTO core_user_roles (tenant_id, id, user_id, role_id, scope_id) "
                        "VALUES (:tid, gen_random_uuid(), :uid, :crid, :tid) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"tid": tenant_id, "uid": user_id, "crid": row},
                )
                if invitation_email:
                    # Bind the invited employee ONLY when the email match is
                    # unambiguous (exactly one unlinked candidate); ambiguous
                    # or missing matches stay unbound - portal access then
                    # fails closed with a clear error.
                    await session.execute(
                        text(
                            "UPDATE erp_employees e SET user_id = :uid, updated_at = now() "
                            "WHERE e.tenant_id = :tid AND e.user_id IS NULL "
                            "AND e.employment_status <> 'terminated' "
                            "AND lower(e.email) = lower(:email) "
                            "AND (SELECT count(*) FROM erp_employees c "
                            "     WHERE c.tenant_id = e.tenant_id AND c.user_id IS NULL "
                            "     AND c.employment_status <> 'terminated' "
                            "     AND lower(c.email) = lower(:email)) = 1"
                        ),
                        {"tid": tenant_id, "uid": user_id, "email": invitation_email},
                    )
                await session.commit()
            logger.info(
                "rbac_mirror.granted",
                tenant_id=str(tenant_id),
                user_id=str(user_id),
                role=role_name,
            )
        except Exception:
            logger.exception(
                "rbac_mirror.failed",
                tenant_id=str(tenant_id),
                user_id=str(user_id),
                role=role_name,
            )

    async def expire_invitation(
        self, invitation_id: str | uuid.UUID, tenant_id: str | uuid.UUID
    ) -> None:
        try:
            await self.invitation_repo.mark_used(invitation_id, None)
        except NotFoundError as exc:
            raise InvitationNotFoundError("Invitation not found") from exc
        await self.audit_service.log(
            action=INVITATION_EXPIRED,
            target=f"invitation:{invitation_id}",
            user_id=None,
            tenant_id=str(tenant_id),
        )
