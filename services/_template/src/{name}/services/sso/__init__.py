"""SSO service package — SAML/OIDC identity provider integration."""

from __future__ import annotations


class SSOService:
    """Handles SAML and OIDC SSO flows."""

    def __init__(self, user_repo) -> None:
        self.user_repo = user_repo

    async def start_oidc_flow(self, provider: str, redirect_uri: str) -> dict:
        """Generate OIDC authorization URL."""
        raise NotImplementedError

    async def handle_oidc_callback(self, code: str, state: str) -> dict:
        """Exchange OIDC code for tokens, create/find user, return session."""
        raise NotImplementedError

    async def start_saml_flow(self, provider: str) -> dict:
        """Generate SAML AuthnRequest."""
        raise NotImplementedError

    async def handle_saml_callback(self, saml_response: str) -> dict:
        """Process SAML Response assertion."""
        raise NotImplementedError
