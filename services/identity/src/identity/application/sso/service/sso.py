"""SSO service — SAML/OIDC identity provider integration."""

from __future__ import annotations

from identity.application.auth.repository.user import UserRepository
from skyrict_common.exceptions import SkyrictError


class SSOService:
    """Handles SAML and OIDC SSO flows."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def start_oidc_flow(self, provider: str, redirect_uri: str) -> dict:
        """Generate OIDC authorization URL."""
        # TODO: Build OIDC auth URL with state, nonce, PKCE
        return {
            "authorization_url": f"https://idp.example.com/authorize?provider={provider}",
            "state": "placeholder-state",
        }

    async def handle_oidc_callback(self, code: str, state: str) -> dict:
        """Exchange OIDC code for tokens, create/find user, return session."""
        # TODO: Implement OIDC code exchange, user provisioning
        raise SkyrictError("SSO not yet configured")

    async def start_saml_flow(self, provider: str) -> dict:
        """Generate SAML AuthnRequest."""
        # TODO: Build SAML AuthnRequest
        raise SkyrictError("SAML SSO not yet implemented")

    async def handle_saml_callback(self, saml_response: str) -> dict:
        """Process SAML Response assertion."""
        # TODO: Parse and validate SAML response
        raise SkyrictError("SAML SSO not yet implemented")
