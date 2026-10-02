from __future__ import annotations

import httpx
import structlog

from identity.core.config import Environment, settings

logger = structlog.get_logger("identity.turnstile")

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileVerifier:
    def __init__(
        self,
        *,
        secret_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secret_key = secret_key if secret_key is not None else settings.TURNSTILE_SECRET_KEY
        self._client = client

    async def verify(self, token: str | None) -> bool:
        if not self._secret_key:
            return settings.ENVIRONMENT in (Environment.DEV, Environment.TEST)
        if not token:
            # Logged separately from a siteverify rejection: no token at all
            # means the client never solved a challenge - a blocked or
            # never-rendered widget - which is a different fault than a
            # challenge Cloudflare actively refused.
            logger.warning("turnstile_token_missing")
            return False
        try:
            if self._client is not None:
                response = await self._client.post(
                    _TURNSTILE_VERIFY_URL,
                    data={"secret": self._secret_key, "response": token},
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        _TURNSTILE_VERIFY_URL,
                        data={"secret": self._secret_key, "response": token},
                    )
            payload = response.json()
            if payload.get("success"):
                return True
            # The reason exists nowhere but here. Callers only ever raise a
            # generic ValidationError, so without this line a wrong secret, an
            # expired token, a replayed single-use token and an unregistered
            # hostname are four indistinguishable outcomes from outside - and
            # an incident responder has nothing to search for.
            #
            # The token itself is never logged: it is single-use credential
            # material, and a rejection log is exactly where it would leak.
            logger.warning(
                "turnstile_verify_rejected",
                error_codes=list(payload.get("error-codes") or []),
                hostname=payload.get("hostname"),
            )
            return False
        except Exception as exc:
            logger.warning("turnstile_verify_failed", error=str(exc))
            return False
