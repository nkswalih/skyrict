# ADR-0014: One account per email; invitations for registered emails conflict

## Status

Accepted

## Date

2026-10-21

## Context

Migration `0005_onboarding_wizard_fields` (SKY-30) made a Skyrict account
global per email: it deleted cross-tenant duplicate `users.email` rows and
added the unique index `uq_users_email`. The onboarding signup flow enforces
the same rule in the application (`email_exists_global`). Login stays
tenant-scoped because the sign-in surface is per tenant
(`<tenant>.signin.skyrict.in`).

The invitation flow was written against the older per-tenant model. Its only
duplicate check was `user_repo.get_by_email(tenant_id, email)`, so an email
that already had an account in another tenant passed the check and then hit
the global index on `INSERT`. The resulting `IntegrityError` was unhandled and
became a 500. Production hit this on 2026-10-21
(`POST /api/v1/invitations/accept` on `fourstoats`): `duplicate key value
violates unique constraint "uq_users_email"`.

## Decision

An email identifies one account platform-wide, and that account belongs to one
tenant.

- Inviting an email that already has an account - in any tenant - is rejected
  at invite creation with `409 USER_ALREADY_EXISTS` and the message
  "This email is unavailable." (the same copy the signup form uses).
- `accept_invitation` re-checks globally, so invitations created before this
  guard (or while a registrant raced the invite) return the same conflict.
- `UserRepository.create` maps the `uq_users_email` / `uq_users_tenant_email`
  integrity violations to the domain conflict, so no caller can turn a
  duplicate email into a 500.

## Consequences

- An admin cannot add an existing Skyrict user to a second workspace. Doing so
  requires a deliberate cross-tenant membership design (see Alternatives), not
  an invite.
- The same email keeps one password and one home tenant; there are no
  per-tenant accounts sharing an email.
- The database index and the application checks agree, and both agree with the
  signup availability rule.
- The invite-time conflict is actionable: the admin sees "This email is
  unavailable." in the invite form instead of an opaque 500 after the invitee
  fills the form.

## Alternatives considered

- **Per-tenant accounts** (drop `uq_users_email`, keep
  `uq_users_tenant_email`): would let the same email exist in several tenants
  with separate passwords, but reverses SKY-30, removes the one-account
  invariant the signup flow relies on, and leaves the person with two
  credentials.
- **Reuse the existing account and attach a membership**: preserves a single
  account, but silently joins an account to another tenant and needs the
  invitee to prove ownership of the existing credentials - a sign-in-based
  accept flow the current password-creating accept form does not implement.
